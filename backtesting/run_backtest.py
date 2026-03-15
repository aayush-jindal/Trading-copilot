"""
Task 2.4 — Full backtest run across all three strategies and the full universe.

Universe : SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, JPM, XLF, XLK, XLE, GLD
Window   : 2019-01-01 → 2024-01-01  (5 years, covers COVID crash/recovery,
           2021 bull run, 2022 bear market, 2023 recovery)

Gate     : total_trades >= 30 AND expectancy > 0 (aggregated across all tickers)

Run:
    python backtesting/run_backtest.py
"""

import os
import sys

# Ensure repo root is on path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.engine import BacktestEngine
from backtesting.results import ResultsAnalyzer, StrategyStats
from backtesting.strategies.s1_trend_pullback import TrendPullbackStrategy
from backtesting.strategies.s2_rsi_reversion import RSIMeanReversionStrategy
from backtesting.strategies.s3_bb_squeeze import BBSqueezeStrategy

UNIVERSE = [
    "SPY", "QQQ", "AAPL", "MSFT", "GOOGL",
    "AMZN", "JPM", "XLF", "XLK", "XLE", "GLD",
]
START = "2019-01-01"
END   = "2024-01-01"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backtest_results")


def _aggregate_gate(stats: list[StrategyStats]) -> tuple[int, float]:
    """Sum trades and compute aggregate expectancy across all tickers."""
    total = sum(s.total_trades for s in stats)
    if total == 0:
        return 0, 0.0
    # Weighted expectancy by trade count
    weighted = sum(s.expectancy * s.total_trades for s in stats)
    return total, round(weighted / total, 4)


def run_strategy(strategy, label: str, csv_name: str) -> tuple[list[StrategyStats], bool]:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Universe: {', '.join(UNIVERSE)}")
    print(f"  Window  : {START} → {END}")
    print(f"{'='*60}")

    engine = BacktestEngine()
    logs = engine.run(strategy, UNIVERSE, START, END)

    analyzer = ResultsAnalyzer(logs)
    stats = analyzer.compute()
    analyzer.summary()

    # Export CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, csv_name)
    analyzer.to_csv(csv_path)
    print(f"\n  → Exported: {csv_path}")

    total, agg_expectancy = _aggregate_gate(stats)
    passed = ResultsAnalyzer.passes_gate(
        type("_G", (), {"total_trades": total, "expectancy": agg_expectancy})()
    )
    status = "PASS ✓" if passed else "FAIL ✗"
    print(f"\n  Aggregate: {total} trades · Expectancy={agg_expectancy:.4f}R → {status}")

    return stats, passed


def main():
    results = {}

    results["S1"] = run_strategy(TrendPullbackStrategy(),  "S1 — TrendPullbackStrategy",    "S1.csv")
    results["S2"] = run_strategy(RSIMeanReversionStrategy(), "S2 — RSIMeanReversionStrategy", "S2.csv")
    results["S3"] = run_strategy(BBSqueezeStrategy(),        "S3 — BBSqueezeStrategy",        "S3.csv")

    # ── Final verdict ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 2 GATE SUMMARY")
    print(f"{'='*60}")
    passing = []
    failing = []
    for key, (stats, passed) in results.items():
        total, agg_exp = _aggregate_gate(stats)
        label = {
            "S1": "TrendPullback",
            "S2": "RSIMeanReversion",
            "S3": "BBSqueeze",
        }[key]
        line = f"  {key} {label:<22} {total:>4} trades  E={agg_exp:>+.4f}R"
        if passed:
            passing.append(label)
            print(f"{line}  PASS ✓")
        else:
            failing.append(label)
            print(f"{line}  FAIL ✗")

    print()
    if passing:
        print(f"  Strategies passing gate : {', '.join(passing)}")
    if failing:
        print(f"  Strategies failing gate : {', '.join(failing)}")

    overall = len(passing) > 0
    print(f"\n  Overall: {'ADVANCE TO PHASE 3 ✓' if overall else 'NOT READY FOR PHASE 3 ✗'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
