"""
BacktestEngine — bar-by-bar replay engine.

No look-ahead bias: on each bar i, only df.iloc[:i+1] is visible.

Performance note: use run_batch() when running multiple strategies on the same
ticker — it computes the SignalSnapshot once per bar and replays all strategies
against it, avoiding O(strategies) redundant ta_engine calls.
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


# Fixed rolling lookback — prevents O(n²) signal recomputation.
# 500 daily ≈ 2 years; sufficient for SMA200 + meaningful S/R history.
# 104 weekly ≈ 2 years of weekly trend context.
_DAILY_LOOKBACK  = 500
_WEEKLY_LOOKBACK = 104

_TICKER_STATE_ATTRS = ("_prev_rsi", "_prev_squeeze", "_prev_k", "_prev_ema9", "_bars_since_cross")


class BacktestEngine:
    def __init__(self, provider: DataProvider | None = None, min_bars: int = 200):
        self._provider = provider or YFinanceProvider()
        self._min_bars = min_bars
        self._signal_engine = SignalEngine()

    # ── Single-strategy entry point (kept for compatibility) ──────────────────
    def run(self, strategy: BaseStrategy, universe: list[str], start: str, end: str) -> list[TradeLog]:
        """Run one strategy over every ticker in universe."""
        logs = []
        for ticker in universe:
            try:
                df = self._provider.fetch_daily(ticker, start, end)
                try:
                    weekly_df = self._provider.fetch_weekly(ticker, start, end)
                except Exception:
                    weekly_df = None
                logs.append(self._run_ticker(strategy, ticker, df, weekly_df))
            except Exception:
                logs.append(TradeLog(
                    trades=[],
                    ticker=ticker,
                    strategy_name=strategy.name or strategy.__class__.__name__,
                    start_date=start,
                    end_date=end,
                ))
        return logs

    # ── Batch entry point: all strategies on one ticker ───────────────────────
    def run_batch(
        self,
        strategies: list[BaseStrategy],
        ticker: str,
        start: str,
        end: str,
    ) -> list[TradeLog]:
        """
        Fetch data once, compute SignalSnapshot once per bar, replay all
        strategies against the same snapshot stream.  ~7× faster than calling
        run() separately for each strategy.
        """
        try:
            df = self._provider.fetch_daily(ticker, start, end)
            try:
                weekly_df = self._provider.fetch_weekly(ticker, start, end)
            except Exception:
                weekly_df = None
            return self._run_ticker_batch(strategies, ticker, df, weekly_df)
        except Exception:
            return [
                TradeLog(trades=[], ticker=ticker,
                         strategy_name=s.name or s.__class__.__name__,
                         start_date=start, end_date=end)
                for s in strategies
            ]

    # ── Internal: one strategy, one ticker ───────────────────────────────────
    def _run_ticker(
        self,
        strategy: BaseStrategy,
        ticker: str,
        df: pd.DataFrame,
        weekly_df: pd.DataFrame | None,
    ) -> TradeLog:
        trades: list[Trade] = []
        open_trade: Trade | None = None

        for i in range(self._min_bars, len(df)):
            bar   = df.iloc[i]
            close = float(bar["close"])
            date  = df.index[i]

            window   = df.iloc[max(0, i - _DAILY_LOOKBACK + 1): i + 1]
            w_window = self._weekly_window(weekly_df, date)
            snapshot = self._signal_engine.compute(window, w_window)

            open_trade = self._manage_trade(strategy, ticker, snapshot, close, date, open_trade, trades)

        self._force_close(open_trade, df, trades)

        return TradeLog(
            trades=trades,
            ticker=ticker,
            strategy_name=strategy.name or strategy.__class__.__name__,
            start_date=df.index[self._min_bars] if len(df) > self._min_bars else df.index[0],
            end_date=df.index[-1],
        )

    # ── Internal: all strategies, one ticker (shared snapshot per bar) ────────
    def _run_ticker_batch(
        self,
        strategies: list[BaseStrategy],
        ticker: str,
        df: pd.DataFrame,
        weekly_df: pd.DataFrame | None,
    ) -> list[TradeLog]:
        n = len(strategies)
        trades_lists: list[list[Trade]] = [[] for _ in range(n)]
        open_trades: list[Trade | None] = [None] * n

        for i in range(self._min_bars, len(df)):
            bar   = df.iloc[i]
            close = float(bar["close"])
            date  = df.index[i]

            # Compute snapshot ONCE — shared by all strategies this bar
            window   = df.iloc[max(0, i - _DAILY_LOOKBACK + 1): i + 1]
            w_window = self._weekly_window(weekly_df, date)
            snapshot = self._signal_engine.compute(window, w_window)

            for idx, strategy in enumerate(strategies):
                open_trades[idx] = self._manage_trade(
                    strategy, ticker, snapshot, close, date,
                    open_trades[idx], trades_lists[idx],
                )

        for idx, strategy in enumerate(strategies):
            self._force_close(open_trades[idx], df, trades_lists[idx])

        start_date = df.index[self._min_bars] if len(df) > self._min_bars else df.index[0]
        return [
            TradeLog(
                trades=trades_lists[idx],
                ticker=ticker,
                strategy_name=strategies[idx].name or strategies[idx].__class__.__name__,
                start_date=start_date,
                end_date=df.index[-1],
            )
            for idx in range(n)
        ]

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _weekly_window(self, weekly_df: pd.DataFrame | None, date) -> pd.DataFrame | None:
        if weekly_df is None:
            return None
        w_all = weekly_df[weekly_df.index <= date]
        return w_all.iloc[-_WEEKLY_LOOKBACK:] if len(w_all) >= 42 else None

    def _manage_trade(
        self,
        strategy: BaseStrategy,
        ticker: str,
        snapshot,
        close: float,
        date,
        open_trade: Trade | None,
        trades: list[Trade],
    ) -> Trade | None:
        """Apply exit logic then entry logic; returns the (possibly new) open_trade."""
        if open_trade is not None:
            stop   = open_trade.stop_loss
            target = open_trade.target_1
            entry  = open_trade.entry_price

            hit_stop   = close <= stop
            hit_target = close >= target
            hit_signal = not hit_stop and not hit_target and strategy.should_exit(snapshot, open_trade)

            if hit_stop or hit_target or hit_signal:
                open_trade.exit_date   = date
                open_trade.exit_price  = close
                open_trade.exit_reason = "stop" if hit_stop else ("target_1" if hit_target else "signal")
                open_trade.pnl_r = (close - entry) / (entry - stop) if entry != stop else 0.0
                trades.append(open_trade)
                open_trade = None

        # Always call should_enter to keep per-ticker strategy state current
        _enter_kwargs = {"ticker": ticker} if any(hasattr(strategy, a) for a in _TICKER_STATE_ATTRS) else {}
        _want_entry = strategy.should_enter(snapshot, **_enter_kwargs)

        if open_trade is None and _want_entry:
            stops: StopConfig = strategy.get_stops(snapshot)
            open_trade = Trade(
                ticker=ticker,
                entry_date=date,
                entry_price=close,
                stop_loss=stops.stop_loss,
                target_1=stops.target_1,
                signal_snapshot={
                    "trend_signal":    snapshot.trend.get("signal"),
                    "momentum_signal": snapshot.momentum.get("signal"),
                    "rsi":             snapshot.momentum.get("rsi"),
                    "swing_verdict":   (snapshot.swing_setup or {}).get("verdict"),
                },
            )

        return open_trade

    def _force_close(self, open_trade: Trade | None, df: pd.DataFrame, trades: list[Trade]) -> None:
        if open_trade is None:
            return
        last_close = float(df["close"].iloc[-1])
        last_date  = df.index[-1]
        entry = open_trade.entry_price
        stop  = open_trade.stop_loss
        open_trade.exit_date   = last_date
        open_trade.exit_price  = last_close
        open_trade.exit_reason = "signal"
        open_trade.pnl_r = (last_close - entry) / (entry - stop) if entry != stop else 0.0
        trades.append(open_trade)
