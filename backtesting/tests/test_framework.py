"""
Task 1.7 — Integration test: prove the full framework wires together.

Uses a trivial always-enter strategy; no real strategy logic required.
"""

import pytest

from backtesting.base import BaseStrategy, StopConfig, Trade
from backtesting.engine import BacktestEngine
from backtesting.signals import SignalSnapshot


class TrivialStrategy(BaseStrategy):
    name = "trivial"

    def should_enter(self, snapshot: SignalSnapshot) -> bool:
        return True  # always enter

    def should_exit(self, snapshot: SignalSnapshot, trade: Trade) -> bool:
        return False  # never exit on signal — rely on stop/target

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        price = snapshot.price
        return StopConfig(
            entry_price=price,
            stop_loss=round(price * 0.95, 4),   # 5% stop
            target_1=round(price * 1.10, 4),    # 10% target
        )


def test_framework_wires_together():
    engine = BacktestEngine()
    results = engine.run(TrivialStrategy(), ["SPY"], "2023-01-01", "2024-01-01")

    assert isinstance(results, list), "run() must return a list"
    assert len(results) > 0, "must have at least one TradeLog"
    log = results[0]
    assert hasattr(log, "trades"), "TradeLog must have .trades"
    assert isinstance(log.trades, list), ".trades must be a list"
    assert log.ticker == "SPY"
    assert log.strategy_name == "trivial"
