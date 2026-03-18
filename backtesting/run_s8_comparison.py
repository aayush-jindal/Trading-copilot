"""
S8 vs S8v2 comparison backtest.

Runs both strategies over the full universe / train+test windows using
only the local SQLite cache (no yfinance network calls).

Decision rules applied after the run:
  SUPERSEDE  — S8v2 passes both gates AND expectancy > S8 on both phases
  NO_CHANGE  — S8v2 passes both gates but expectancy ≤ S8 (no improvement)
  FAILED     — S8v2 fails either gate → keep S8, do not register S8v2

Run:
    python backtesting/run_s8_comparison.py
"""

import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.engine import BacktestEngine
from backtesting.data import SQLiteProvider
from backtesting.results import ResultsAnalyzer

UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA", "EEM", "EFA",
    "XLF", "XLK", "XLE", "XLV", "XLY", "XLI", "XLB", "XLP",
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "AMD", "TSLA", "META", "NFLX",
    "JPM", "BAC", "XOM", "V", "MA", "UNH", "HD",
    "CRM", "SQ", "SHOP", "BRK-B",
    "GLD", "SLV", "USO", "TLT",
    "VNQ", "XLRE",
]

TRAIN_START = "2005-01-01"
TRAIN_END   = "2021-01-01"
TEST_START  = "2021-01-01"
TEST_END    = "2026-01-01"

TICKER_STARTS = {
    "TSLA":  "2010-06-29",
    "META":  "2012-05-18",
    "V":     "2008-03-19",
    "SQ":    "2015-11-19",
    "SHOP":  "2015-05-21",
    "XLRE":  "2015-10-08",
}

VALIDATED_JSON = os.path.join(os.path.dirname(__file__), "validated_strategies.json")


def _get_start(ticker: str, phase: str) -> str:
    if phase == "train":
        return TICKER_STARTS.get(ticker, TRAIN_START)
    return TEST_START


def _run_one(args: tuple) -> dict:
    """Worker — S8 + S8v2 × one ticker × one phase, read-only SQLite."""
    from backtesting.strategies.s8_stochastic_cross import StochasticCrossStrategy
    from backtesting.strategies.s8v2_stochastic_sma_filter import StochasticSmaTrendStrategy

    ticker, start, end, phase = args
    strategies = [StochasticCrossStrategy(), StochasticSmaTrendStrategy()]
    engine = BacktestEngine(provider=SQLiteProvider())
    try:
        logs = engine.run_batch(strategies, ticker, start, end)
        return {"ticker": ticker, "phase": phase, "logs": logs, "error": None}
    except Exception as e:
        return {"ticker": ticker, "phase": phase, "logs": [], "error": str(e)}


def _aggregate(logs: list) -> dict:
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
    import multiprocessing

    jobs = []
    for ticker in UNIVERSE:
        jobs.append((ticker, _get_start(ticker, "train"), TRAIN_END, "train"))
        jobs.append((ticker, TEST_START, TEST_END, "test"))

    MAX_WORKERS = min(multiprocessing.cpu_count(), 8)
    print(f"S8 vs S8v2 comparison — {len(jobs)} jobs, {MAX_WORKERS} workers")
    print("Data source: local SQLite cache (no network calls)")
    print("=" * 80)

    train_logs, test_logs = [], []
    n_failed = 0

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_run_one, job): job for job in jobs}
        for future in as_completed(futures):
            r = future.result()
            if r["error"]:
                n_failed += 1
                print(f"  FAIL {r['ticker']:8s} [{r['phase']}]: {r['error'][:80]}")
            else:
                for log in r["logs"]:
                    if r["phase"] == "train":
                        train_logs.append(log)
                    else:
                        test_logs.append(log)
                print(f"  OK   {r['ticker']:8s} [{r['phase']}] → {len(r['logs'])} logs")

    train_stats = _aggregate(train_logs)
    test_stats  = _aggregate(test_logs)

    TRAIN_GATE = lambda s: s.total_trades >= 30 and s.expectancy > 0
    TEST_GATE  = lambda s: s.total_trades >= 20 and s.expectancy > 0

    S8_NAME   = "S8_StochasticCross"
    S8V2_NAME = "S8v2_StochasticSmaTrend"

    s8_tr  = train_stats.get(S8_NAME)
    s8_te  = test_stats.get(S8_NAME)
    v2_tr  = train_stats.get(S8V2_NAME)
    v2_te  = test_stats.get(S8V2_NAME)

    print(f"\n{'Strategy':30s} {'TRAIN':35s} {'TEST':30s}")
    print("-" * 95)
    for nm, tr, te in [(S8_NAME, s8_tr, s8_te), (S8V2_NAME, v2_tr, v2_te)]:
        tr_str = f"{tr.total_trades}t WR={tr.win_rate:.1%} E={tr.expectancy:+.3f}R" if tr else "no data"
        te_str = f"{te.total_trades}t WR={te.win_rate:.1%} E={te.expectancy:+.3f}R" if te else "no data"
        print(f"{nm:30s} {tr_str:35s} {te_str}")

    # ── Decision logic ──────────────────────────────────────────────────────
    v2_train_pass = v2_tr and TRAIN_GATE(v2_tr)
    v2_test_pass  = v2_te and TEST_GATE(v2_te)

    if v2_train_pass and v2_test_pass:
        s8_better = (s8_tr and s8_te and
                     s8_tr.expectancy >= v2_tr.expectancy and
                     s8_te.expectancy >= v2_te.expectancy)
        if s8_better:
            decision = "NO_IMPROVEMENT"
            note = (f"S8v2 passes gates but expectancy ≤ S8 on both phases. "
                    f"Keep S8 in registry; do not register S8v2.")
        else:
            decision = "SUPERSEDE"
            note = (f"S8v2 passes both gates and outperforms S8 on expectancy. "
                    f"Replace S8 with S8v2 in registry.")
    else:
        decision = "FAILED"
        note = (f"S8v2 failed gate(s): train={'PASS' if v2_train_pass else 'FAIL'}, "
                f"test={'PASS' if v2_test_pass else 'FAIL'}. Keep S8.")

    print(f"\nDecision: {decision}")
    print(f"Note    : {note}")

    # ── Update validated_strategies.json ───────────────────────────────────
    with open(VALIDATED_JSON) as f:
        registry = json.load(f)

    today = str(date.today())

    v2_result = {
        "train": {
            "trades": v2_tr.total_trades if v2_tr else 0,
            "win_rate": v2_tr.win_rate if v2_tr else 0.0,
            "expectancy": v2_tr.expectancy if v2_tr else 0.0,
            "gate": "PASS" if v2_train_pass else "FAIL",
        },
        "test": {
            "trades": v2_te.total_trades if v2_te else 0,
            "win_rate": v2_te.win_rate if v2_te else 0.0,
            "expectancy": v2_te.expectancy if v2_te else 0.0,
            "gate": "PASS" if v2_test_pass else "FAIL",
        },
        "verdict": "VALIDATED" if (v2_train_pass and v2_test_pass) else "FAILED",
        "notes": note,
    }
    registry["results"][S8V2_NAME] = v2_result

    tuning_entry = {
        "date": today,
        "strategy": S8V2_NAME,
        "base": S8_NAME,
        "change": "Added SMA200 uptrend gate as first required condition",
        "decision": decision,
        "note": note,
    }
    registry.setdefault("tuning_log", []).append(tuning_entry)

    if decision == "SUPERSEDE":
        # Move S8 to retired, promote S8v2 to validated
        if S8_NAME in registry.get("validated", []):
            registry["validated"].remove(S8_NAME)
            registry.setdefault("retired", []).append(S8_NAME)
        registry["validated"].append(S8V2_NAME)
        if S8V2_NAME in registry.get("pending", []):
            registry["pending"].remove(S8V2_NAME)
        print(f"\nRegistry: {S8_NAME} → retired, {S8V2_NAME} → validated")
    else:
        # S8v2 result recorded but S8 stays; S8v2 not added to validated
        print(f"\nRegistry: {S8_NAME} unchanged (keeps VALIDATED status)")

    registry["last_run"] = today

    with open(VALIDATED_JSON, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"Updated {VALIDATED_JSON}")

    if n_failed > 0:
        print(f"\nWarning: {n_failed} jobs failed (likely tickers not in SQLite cache).")
