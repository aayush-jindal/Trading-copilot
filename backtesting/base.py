"""
BaseStrategy ABC and shared dataclasses used by all strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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
    - Set the class attribute `name`
    - Implement should_enter, should_exit, get_stops
    """

    name: str = ""

    @abstractmethod
    def should_enter(self, snapshot) -> bool:
        """Return True if conditions warrant a new long entry."""

    @abstractmethod
    def should_exit(self, snapshot, trade: Trade) -> bool:
        """Return True if the open trade should be closed on signal."""

    @abstractmethod
    def get_stops(self, snapshot) -> StopConfig:
        """Return StopConfig for a new trade entered at this snapshot."""

    def describe(self) -> str:
        return f"Strategy: {self.name or self.__class__.__name__}"
