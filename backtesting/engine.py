"""
BacktestEngine — bar-by-bar replay engine.

No look-ahead bias: on each bar i, only df.iloc[:i+1] is visible.
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backtesting.base import BaseStrategy, StopConfig, Trade
from backtesting.data import YFinanceProvider, DataProvider
from backtesting.signals import SignalEngine


@dataclass
class TradeLog:
    trades: list[Trade]
    ticker: str
    strategy_name: str
    start_date: Any
    end_date: Any


class BacktestEngine:
    def __init__(self, provider: DataProvider | None = None, min_bars: int = 200):
        self._provider = provider or YFinanceProvider()
        self._min_bars = min_bars
        self._signal_engine = SignalEngine()

    def run(self, strategy: BaseStrategy, universe: list[str], start: str, end: str) -> list[TradeLog]:
        """Run strategy over every ticker in universe. Returns one TradeLog per ticker."""
        logs = []
        for ticker in universe:
            try:
                df = self._provider.fetch_daily(ticker, start, end)
                try:
                    weekly_df = self._provider.fetch_weekly(ticker, start, end)
                except Exception:
                    weekly_df = None
                log = self._run_ticker(strategy, ticker, df, weekly_df)
                logs.append(log)
            except Exception as e:
                # Log an empty TradeLog so callers always get one entry per ticker
                logs.append(TradeLog(
                    trades=[],
                    ticker=ticker,
                    strategy_name=strategy.name or strategy.__class__.__name__,
                    start_date=start,
                    end_date=end,
                ))
        return logs

    def _run_ticker(
        self,
        strategy: BaseStrategy,
        ticker: str,
        df: pd.DataFrame,
        weekly_df: pd.DataFrame | None,
    ) -> TradeLog:
        strategy_name = strategy.name or strategy.__class__.__name__
        trades: list[Trade] = []
        open_trade: Trade | None = None

        # Warm-up: need min_bars before the first signal can be computed
        for i in range(self._min_bars, len(df)):
            bar = df.iloc[i]
            close = float(bar["close"])
            date = df.index[i]

            # Slice up to and including bar i (no look-ahead)
            window = df.iloc[: i + 1]

            # Weekly slice: all weekly bars whose date <= bar date
            w_window: pd.DataFrame | None = None
            if weekly_df is not None:
                w_window = weekly_df[weekly_df.index <= date]
                if len(w_window) < 42:
                    w_window = None

            snapshot = self._signal_engine.compute(window, w_window)

            # ── Manage open trade ─────────────────────────────────────────
            if open_trade is not None:
                stop = open_trade.stop_loss
                target = open_trade.target_1
                entry = open_trade.entry_price

                if close <= stop:
                    open_trade.exit_date = date
                    open_trade.exit_price = close
                    open_trade.exit_reason = "stop"
                    open_trade.pnl_r = (close - entry) / (entry - stop) if entry != stop else 0.0
                    trades.append(open_trade)
                    open_trade = None

                elif close >= target:
                    open_trade.exit_date = date
                    open_trade.exit_price = close
                    open_trade.exit_reason = "target_1"
                    open_trade.pnl_r = (close - entry) / (entry - stop) if entry != stop else 0.0
                    trades.append(open_trade)
                    open_trade = None

                elif strategy.should_exit(snapshot, open_trade):
                    open_trade.exit_date = date
                    open_trade.exit_price = close
                    open_trade.exit_reason = "signal"
                    open_trade.pnl_r = (close - entry) / (entry - stop) if entry != stop else 0.0
                    trades.append(open_trade)
                    open_trade = None

            # ── Check for new entry (only when flat) ──────────────────────
            if open_trade is None and strategy.should_enter(snapshot):
                stops: StopConfig = strategy.get_stops(snapshot)
                open_trade = Trade(
                    ticker=ticker,
                    entry_date=date,
                    entry_price=close,
                    stop_loss=stops.stop_loss,
                    target_1=stops.target_1,
                    signal_snapshot={
                        "trend_signal": snapshot.trend.get("signal"),
                        "momentum_signal": snapshot.momentum.get("signal"),
                        "rsi": snapshot.momentum.get("rsi"),
                        "swing_verdict": (snapshot.swing_setup or {}).get("verdict"),
                    },
                )

        # Force-close any trade still open at end of data
        if open_trade is not None:
            last_close = float(df["close"].iloc[-1])
            last_date = df.index[-1]
            entry = open_trade.entry_price
            stop = open_trade.stop_loss
            open_trade.exit_date = last_date
            open_trade.exit_price = last_close
            open_trade.exit_reason = "signal"
            open_trade.pnl_r = (last_close - entry) / (entry - stop) if entry != stop else 0.0
            trades.append(open_trade)

        return TradeLog(
            trades=trades,
            ticker=ticker,
            strategy_name=strategy_name,
            start_date=df.index[self._min_bars] if len(df) > self._min_bars else df.index[0],
            end_date=df.index[-1],
        )
