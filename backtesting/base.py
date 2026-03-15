"""
BaseStrategy ABC and shared dataclasses used by all strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Factory dataclasses (Task 2.1) ────────────────────────────────────────────

@dataclass
class Condition:
    label: str       # human readable e.g. "Price above SMA200"
    passed: bool
    value: str       # actual value e.g. "above (+4.2%)"
    required: str    # what was needed e.g. "above"


@dataclass
class RiskLevels:
    entry_price: float
    stop_loss: float
    target: float
    risk_reward: float
    atr: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    position_size: int | None = None   # shares, computed by scanner


@dataclass
class StrategyResult:
    name: str
    type: str                          # "trend" | "reversion" | "breakout" | "rotation"
    verdict: str                       # "ENTRY" | "WATCH" | "NO_TRADE"
    score: int                         # 0-100
    conditions: list                   # list[Condition]
    risk: Any = None                   # RiskLevels | None
    strategy_instance: Any = None      # for scanner use


@dataclass
class StopConfig:
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float | None = None
    target_3: float | None = None
    risk_reward: float = 0.0


@dataclass
class Trade:
    ticker: str
    entry_date: Any          # datetime or date
    entry_price: float
    stop_loss: float
    target_1: float
    exit_date: Any = None    # datetime or date
    exit_price: float | None = None
    exit_reason: str | None = None   # "target_1" | "stop" | "signal"
    pnl_r: float | None = None       # P&L in R-multiples
    signal_snapshot: dict | None = None  # snapshot dict at entry


class BaseStrategy(ABC):
    """Abstract base for all backtesting strategies.

    Subclasses must:
    - Set class attributes `name` and `type`
    - Implement should_enter, should_exit, get_stops (BacktestEngine)
    - Implement evaluate, _check_conditions, _compute_risk (Scanner)
    """

    name: str = ""
    type: str = ""   # "trend" | "reversion" | "breakout" | "rotation"

    # ── BacktestEngine interface ───────────────────────────────────────────────

    @abstractmethod
    def should_enter(self, snapshot) -> bool:
        """Return True if conditions warrant a new long entry."""

    @abstractmethod
    def should_exit(self, snapshot, trade: Trade) -> bool:
        """Return True if the open trade should be closed on signal."""

    @abstractmethod
    def get_stops(self, snapshot) -> StopConfig:
        """Return StopConfig for a new trade entered at this snapshot."""

    # ── Scanner / factory interface ───────────────────────────────────────────

    @abstractmethod
    def evaluate(self, snapshot) -> StrategyResult:
        """Run full evaluation and return a StrategyResult."""

    @abstractmethod
    def _check_conditions(self, snapshot) -> list:
        """Return list[Condition] for the current snapshot."""

    @abstractmethod
    def _compute_risk(self, snapshot) -> Any:
        """Return RiskLevels | None for the current snapshot."""

    def _verdict(self, conditions: list) -> tuple:
        """Default verdict logic based on proportion of passed conditions.

        Returns (verdict, score) where:
          all passed   → "ENTRY",    score = 100
          >= 50% passed → "WATCH",   score proportional
          < 50% passed  → "NO_TRADE", score proportional
        """
        if not conditions:
            return "NO_TRADE", 0
        total = len(conditions)
        passed = sum(1 for c in conditions if c.passed)
        score = int(passed / total * 100)
        if passed == total:
            verdict = "ENTRY"
        elif passed / total >= 0.5:
            verdict = "WATCH"
        else:
            verdict = "NO_TRADE"
        return verdict, score

    def describe(self) -> str:
        return f"Strategy: {self.name or self.__class__.__name__}"
