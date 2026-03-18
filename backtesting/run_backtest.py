"""
Full backtest — all strategies, 40-ticker universe, train/test split, parallelized.

Universe : 40 tickers across 7 categories (broad market, sector ETFs, large-cap tech,
           blue chips, mid-cap growth, commodities, real estate)

Train    : per-ticker max(2005-01-01, ipo_date) → 2021-01-01  (~16 years)
Test     : 2021-01-01 → 2026-01-01  (5 years — out-of-sample)

Two-stage gate:
  TRAIN: total_trades >= 30 AND expectancy > 0
  TEST:  total_trades >= 20 AND expectancy > 0
  VALIDATED = both pass
  PENDING   = train passes, test fails (regime-sensitive)
  FAILED    = train fails

Run:
    python backtesting/run_backtest.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

from backtesting.engine import BacktestEngine
from backtesting.data import SQLiteProvider
from backtesting.results import ResultsAnalyzer

UNIVERSE = [
    # Broad market ETFs
    "SPY", "QQQ", "IWM", "DIA", "EEM", "EFA",
    # Sector ETFs (all 1998+)
    "XLF", "XLK", "XLE", "XLV", "XLY", "XLI", "XLB", "XLP",
    # Large-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "AMD", "TSLA", "META", "NFLX",
    # Large-cap blue chips
    "JPM", "BAC", "XOM", "V", "MA", "UNH", "HD",
    # Mid-cap volatile growth
    "CRM", "SQ", "SHOP", "BRK-B",
    # Commodities
    "GLD", "SLV", "USO", "TLT",
    # Real estate
    "VNQ", "XLRE",
]

TRAIN_START = "2005-01-01"
TRAIN_END   = "2021-01-01"
TEST_START  = "2021-01-01"
TEST_END    = "2026-01-01"

# Tickers with IPO after TRAIN_START — use actual first trading date
TICKER_STARTS = {
    "TSLA":  "2010-06-29",
    "META":  "2012-05-18",
    "V":     "2008-03-19",
    "SQ":    "2015-11-19",
    "SHOP":  "2015-05-21",
    "XLRE":  "2015-10-08",
}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backtest_results")


def _get_start(ticker: str, phase: str) -> str:
    if phase == "train":
        return TICKER_STARTS.get(ticker, TRAIN_START)
    return TEST_START


def _run_one(args: tuple) -> dict:
    """Worker — all strategies × one ticker × one phase.

    Fetches data once and computes SignalSnapshot once per bar across all
    strategies.  ~7× faster than per-strategy jobs on the same ticker.
    Top-level function required for pickle compatibility on macOS/Windows.
    Never raises.
    """
    from backtesting.strategies.registry import STRATEGY_REGISTRY
    ticker, start, end, phase = args
    strategies = [type(s)() for s in STRATEGY_REGISTRY]
    engine = BacktestEngine(provider=SQLiteProvider())
    try:
        logs = engine.run_batch(strategies, ticker, start, end)
        return {
            "ticker": ticker, "phase": phase,
            "logs": logs, "error": None,
        }
    except Exception as e:
        return {
            "ticker": ticker, "phase": phase,
            "logs": [], "error": str(e),
        }


def _aggregate(logs: list) -> dict:
    """Returns {strategy_name: aggregated_stats} combined across all tickers.

    ResultsAnalyzer.compute() returns per-ticker stats. This function
    sums trade counts and computes weighted expectancy across tickers
    so each strategy appears exactly once.
    """
    from collections import defaultdict
    per_strategy: dict[str, list] = defaultdict(list)
    analyzer = ResultsAnalyzer(logs)
    for s in analyzer.compute():
        per_strategy[s.strategy_name].append(s)

    result = {}
    for name, stats_list in per_strategy.items():
        total = sum(s.total_trades for s in stats_list)
        if total == 0:
            result[name] = type("S", (), {
                "strategy_name": name, "total_trades": 0,
                "win_rate": 0.0, "expectancy": 0.0,
            })()
            continue
        # Weighted expectancy by trade count
        weighted_exp = sum(s.expectancy * s.total_trades for s in stats_list) / total
        weighted_wr  = sum(s.win_rate  * s.total_trades for s in stats_list) / total
        result[name] = type("S", (), {
            "strategy_name": name,
            "total_trades": total,
            "win_rate": round(weighted_wr, 4),
            "expectancy": round(weighted_exp, 4),
        })()
    return result


if __name__ == "__main__":
    import subprocess

    # ── Pre-flight: run the cache validator ────────────────────────────────────
    print("Running cache validator...")
    validator = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "validate_cache.py")],
        capture_output=False,
    )
    if validator.returncode != 0:
        print(f"\nABORT: validate_cache.py exited {validator.returncode}. "
              "Fix data issues before running the backtest.")
        sys.exit(validator.returncode)

    from backtesting.strategies.registry import STRATEGY_REGISTRY

    MAX_WORKERS = min(multiprocessing.cpu_count(), 8)
    # Abort threshold: if more than this fraction of ticker-phase jobs fail,
    # something is systemically wrong — shut down the pool early.
    MAX_FAIL_RATE = 0.15   # 15 %

    # One job = one ticker × one phase (all strategies batched inside)
    jobs = []
    for ticker in UNIVERSE:
        jobs.append((ticker, _get_start(ticker, "train"), TRAIN_END, "train"))
        jobs.append((ticker, TEST_START, TEST_END, "test"))

    n_strategies = len(STRATEGY_REGISTRY)
    print(f"Running {len(jobs)} jobs ({len(UNIVERSE)} tickers × 2 phases, {n_strategies} strategies batched per job)")
    print(f"Workers: {MAX_WORKERS}  |  Train: {TRAIN_START}→{TRAIN_END}  Test: {TEST_START}→{TEST_END}")
    print("=" * 100)

    train_logs, test_logs = [], []
    n_failed = 0
    n_done   = 0

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_run_one, job): job for job in jobs}
        for future in as_completed(futures):
            r = future.result()
            n_done += 1
            if r["error"]:
                n_failed += 1
                print(f"  FAIL {r['ticker']:8s} [{r['phase']}]: {r['error'][:80]}")
                if n_done >= 10:
                    fail_rate = n_failed / n_done
                    if fail_rate > MAX_FAIL_RATE:
                        print(f"\nABORT: {n_failed}/{n_done} jobs failed ({fail_rate:.0%} > {MAX_FAIL_RATE:.0%} threshold).")
                        print("Likely cause: yfinance API unavailable or rate-limited.")
                        print("Run validate_cache.py to diagnose, then retry.")
                        executor.shutdown(wait=False, cancel_futures=True)
                        sys.exit(3)
            else:
                completed = r["logs"]
                print(f"  OK   {r['ticker']:8s} [{r['phase']}] → {len(completed)} strategy logs")
                for log in completed:
                    if r["phase"] == "train":
                        train_logs.append(log)
                    else:
                        test_logs.append(log)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    train_analyzer = ResultsAnalyzer(train_logs)
    test_analyzer  = ResultsAnalyzer(test_logs)
    train_analyzer.to_csv(os.path.join(OUTPUT_DIR, "train_results.csv"))
    test_analyzer.to_csv(os.path.join(OUTPUT_DIR, "test_results.csv"))

    train_stats = _aggregate(train_logs)
    test_stats  = _aggregate(test_logs)

    TRAIN_GATE = lambda s: s.total_trades >= 30 and s.expectancy > 0
    TEST_GATE  = lambda s: s.total_trades >= 20 and s.expectancy > 0

    print(f"\n{'Strategy':30s} {'TRAIN':35s} {'TEST':30s} {'VERDICT'}")
    print("-" * 105)

    verdicts = {}
    for name in sorted(train_stats.keys()):
        tr = train_stats[name]
        te = test_stats.get(name)
        train_pass = TRAIN_GATE(tr)
        test_pass  = TEST_GATE(te) if te else False

        if train_pass and test_pass:
            verdict = "VALIDATED"
        elif train_pass and not test_pass:
            verdict = "PENDING"
        else:
            verdict = "FAILED"

        verdicts[name] = verdict

        tr_str = f"{tr.total_trades}t WR={tr.win_rate:.1%} E={tr.expectancy:+.3f}R"
        te_str = (f"{te.total_trades}t WR={te.win_rate:.1%} E={te.expectancy:+.3f}R"
                  if te else "no data")
        print(f"{name:30s} {tr_str:35s} {te_str:30s} [{verdict}]")

    print()
    validated = [n for n, v in verdicts.items() if v == "VALIDATED"]
    pending   = [n for n, v in verdicts.items() if v == "PENDING"]
    failed    = [n for n, v in verdicts.items() if v == "FAILED"]
    print(f"  VALIDATED : {', '.join(validated) or 'none'}")
    print(f"  PENDING   : {', '.join(pending) or 'none'}")
    print(f"  FAILED    : {', '.join(failed) or 'none'}")
    overall = len(validated) > 0
    print(f"\n  Overall: {'ADVANCE TO PHASE 3 ✓' if overall else 'NOT READY FOR PHASE 3 ✗'}")
    print("=" * 100)
