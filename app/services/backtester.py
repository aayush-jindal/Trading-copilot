"""Backtesting player: historical replay of the swing engine with configurable thresholds."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from statistics import mean
from typing import Callable
from uuid import UUID

import pandas as pd

from app.services.market_data import get_or_refresh_data, get_or_refresh_hourly_data
from app.services.ta_engine import (
    _NEUTRAL_4H,
    _prepare_dataframe,
    analyze_ticker,
)

LOOKAHEAD_CAP_DAYS = 30
MIN_HISTORY_BARS = 200


@dataclass
class BacktestConfig:
    ticker: str
    lookback_years: int = 3
    entry_score_threshold: int = 70
    watch_score_threshold: int = 55
    min_rr_ratio: float = 1.5
    min_support_strength: str = "LOW"  # LOW | MEDIUM | HIGH
    require_weekly_aligned: bool = True
    run_label: str = ""
    date_from: str | None = None
    date_to: str | None = None


@dataclass
class BacktestSignal:
    ticker: str
    signal_date: pd.Timestamp
    verdict: str
    setup_score: int
    score_decile: int
    uptrend_confirmed: bool
    weekly_trend_aligned: bool
    near_support: bool
    support_strength: str | None
    reversal_found: bool
    trigger_ok: bool
    rr_ratio: float | None
    rr_label: str | None
    support_is_provisional: bool
    entry_price: float
    stop_loss: float | None
    target: float | None
    four_h_available: bool = False
    four_h_confirmed: bool = False
    four_h_reversal: bool = False
    four_h_trigger: bool = False
    four_h_rsi: float | None = None
    four_h_upgrade: bool = False


@dataclass
class BacktestOutcome:
    outcome: str  # WIN | LOSS | EXPIRED
    outcome_date: pd.Timestamp
    days_to_outcome: int
    exit_price: float
    return_pct: float
    mae: float
    mfe: float


@dataclass
class BacktestResult:
    signal: BacktestSignal
    outcome: BacktestOutcome


def _resample_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    return daily_df.resample("W-FRI").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()


def analyze_ticker_from_df(
    symbol: str,
    daily_df: pd.DataFrame,
    config: BacktestConfig,
    weekly_df: pd.DataFrame | None = None,
    hourly_df: pd.DataFrame | None = None,
) -> dict:
    """Variant of analyze_ticker that uses a pre-sliced dataframe and config thresholds.

    Applies config.entry_score_threshold, config.watch_score_threshold,
    config.min_rr_ratio, config.min_support_strength, and config.require_weekly_aligned
    in verdict and gate logic (no post-filtering).

    When hourly_df is provided it must already be sliced to the same time cutoff
    as daily_df (no future bars) — the caller is responsible for that invariant.
    """
    if weekly_df is None:
        weekly_df = _resample_weekly(daily_df)
    w = weekly_df.reset_index()
    if w.columns[0] != "date":
        w = w.rename(columns={w.columns[0]: "date"})
    w["date"] = pd.to_datetime(w["date"]).dt.strftime("%Y-%m-%d")
    weekly_list = w.to_dict("records")

    price = float(daily_df["close"].iloc[-1])
    return analyze_ticker(
        daily_df,
        symbol,
        price,
        weekly_list,
        hourly_df=hourly_df,
        entry_score_threshold=config.entry_score_threshold,
        watch_score_threshold=config.watch_score_threshold,
        min_rr_ratio=config.min_rr_ratio,
        require_weekly_aligned=config.require_weekly_aligned,
        min_support_strength=config.min_support_strength or None,
    )


def _build_signal(
    ticker: str,
    run_id: UUID,
    full_df: pd.DataFrame,
    signal_bar_index: int,
    result: dict,
) -> BacktestSignal:
    swing = result.get("swing_setup") or {}
    cond = swing.get("conditions") or {}
    levels = swing.get("levels") or {}
    risk = swing.get("risk") or {}
    sr = result.get("support_resistance") or {}
    signal_date = full_df.index[signal_bar_index]
    score = int(swing.get("setup_score") or 0)
    score_decile = 10 if score >= 100 else max(1, min(10, (score // 10) + 1))

    four_h = result.get("four_h_confirmation") or _NEUTRAL_4H

    return BacktestSignal(
        ticker=ticker,
        signal_date=signal_date,
        verdict=str(swing.get("verdict", "NO_TRADE")),
        setup_score=score,
        score_decile=score_decile,
        uptrend_confirmed=bool(cond.get("uptrend_confirmed")),
        weekly_trend_aligned=bool(cond.get("weekly_trend_aligned")),
        near_support=bool(cond.get("near_support")),
        support_strength=sr.get("support_strength"),
        reversal_found=bool((cond.get("reversal_candle") or {}).get("found")),
        trigger_ok=bool(cond.get("trigger_ok")),
        rr_ratio=risk.get("rr_ratio") if risk.get("rr_ratio") is not None else cond.get("rr_ratio"),
        rr_label=cond.get("rr_label"),
        support_is_provisional=bool(levels.get("support_is_provisional")),
        entry_price=float(result.get("price", 0)),
        stop_loss=risk.get("stop_loss"),
        target=risk.get("target"),
        four_h_available=bool(four_h.get("four_h_available")),
        four_h_confirmed=bool(four_h.get("four_h_confirmed")),
        four_h_reversal=bool(four_h.get("four_h_reversal")),
        four_h_trigger=bool(four_h.get("four_h_trigger")),
        four_h_rsi=four_h.get("four_h_rsi"),
        four_h_upgrade=bool(result.get("four_h_upgrade")),
    )


def _resolve_outcome(
    signal: BacktestSignal,
    full_df: pd.DataFrame,
    signal_bar_index: int,
) -> BacktestOutcome:
    future = full_df.iloc[
        signal_bar_index + 1 : signal_bar_index + 1 + LOOKAHEAD_CAP_DAYS
    ]
    if future.empty:
        last_idx = full_df.index[-1] if signal_bar_index + 1 >= len(full_df) else full_df.index[signal_bar_index + 1]
        return BacktestOutcome(
            outcome="EXPIRED",
            outcome_date=last_idx,
            days_to_outcome=0,
            exit_price=signal.entry_price,
            return_pct=0.0,
            mae=0.0,
            mfe=0.0,
        )

    mae = 0.0
    mfe = 0.0

    for day_offset, (dt, row) in enumerate(future.iterrows()):
        high = float(row["high"])
        low = float(row["low"])
        mae = max(mae, (signal.entry_price - low) / signal.entry_price * 100)
        mfe = max(mfe, (high - signal.entry_price) / signal.entry_price * 100)

        if signal.stop_loss is not None and low <= signal.stop_loss:
            return BacktestOutcome(
                outcome="LOSS",
                outcome_date=dt,
                days_to_outcome=day_offset + 1,
                exit_price=signal.stop_loss,
                return_pct=round(
                    (signal.stop_loss - signal.entry_price) / signal.entry_price * 100, 4
                ),
                mae=round(mae, 2),
                mfe=round(mfe, 2),
            )
        if signal.target is not None and high >= signal.target:
            return BacktestOutcome(
                outcome="WIN",
                outcome_date=dt,
                days_to_outcome=day_offset + 1,
                exit_price=signal.target,
                return_pct=round(
                    (signal.target - signal.entry_price) / signal.entry_price * 100, 4
                ),
                mae=round(mae, 2),
                mfe=round(mfe, 2),
            )

    last = future.iloc[-1]
    return BacktestOutcome(
        outcome="EXPIRED",
        outcome_date=future.index[-1],
        days_to_outcome=LOOKAHEAD_CAP_DAYS,
        exit_price=round(float(last["close"]), 2),
        return_pct=round(
            (float(last["close"]) - signal.entry_price) / signal.entry_price * 100, 4
        ),
        mae=round(mae, 2),
        mfe=round(mfe, 2),
    )


def _aggregate_results(results: list[BacktestResult]) -> dict:
    def _win_rate_pct(sigs: list[BacktestResult]) -> float:
        resolved = [s for s in sigs if s.outcome.outcome != "EXPIRED"]
        if not resolved:
            return 0.0
        return len([s for s in resolved if s.outcome.outcome == "WIN"]) / len(resolved) * 100

    entry_sigs = [r for r in results if r.signal.verdict == "ENTRY"]
    watch_sigs = [r for r in results if r.signal.verdict == "WATCH"]
    resolved = [r for r in results if r.outcome.outcome != "EXPIRED"]
    wins = [r for r in resolved if r.outcome.outcome == "WIN"]
    losses = [r for r in resolved if r.outcome.outcome == "LOSS"]
    expired = [r for r in results if r.outcome.outcome == "EXPIRED"]

    win_rate_all = _win_rate_pct(results)
    avg_win = mean([r.outcome.return_pct for r in wins]) if wins else 0.0
    avg_loss = mean([r.outcome.return_pct for r in losses]) if losses else 0.0
    loss_rate = 1 - (win_rate_all / 100)

    # P&L calculations — ENTRY signals only, sorted by date
    entry_results = sorted(entry_sigs, key=lambda r: r.signal.signal_date)

    fixed_pnl = 0.0
    position_size = 1000.0

    for r in entry_results:
        trade_return = r.outcome.return_pct / 100
        fixed_pnl += position_size * trade_return

    compound_pot = 1000.0
    for r in entry_results:
        trade_return = r.outcome.return_pct / 100
        trade_profit = compound_pot * trade_return
        compound_pot += trade_profit
    compound_pnl = compound_pot - 1000.0

    return {
        "total_signals": len(results),
        "entry_signals": len(entry_sigs),
        "watch_signals": len(watch_sigs),
        "win_count": len(wins),
        "loss_count": len(losses),
        "expired_count": len(expired),
        "win_rate":       round(win_rate_all, 2),  # kept for backward compat
        "win_rate_entry": round(_win_rate_pct(entry_sigs), 2),
        "win_rate_watch": round(_win_rate_pct(watch_sigs), 2),
        "win_rate_all":   round(win_rate_all, 2),
        "expected_value": round(
            ((win_rate_all / 100) * avg_win) - (loss_rate * abs(avg_loss)), 4
        ),
        "avg_return_pct": round(mean([r.outcome.return_pct for r in results]), 4)
        if results
        else 0.0,
        "avg_mae": round(mean([r.outcome.mae for r in results]), 4) if results else 0.0,
        "avg_mfe": round(mean([r.outcome.mfe for r in results]), 4) if results else 0.0,
        "avg_days_to_outcome": round(
            mean([r.outcome.days_to_outcome for r in results]), 2
        )
        if results
        else 0.0,
        "expired_pct": round(len(expired) / len(results) * 100, 2) if results else 0.0,
        # P&L fields
        "entry_signal_count": len(entry_results),
        "fixed_pnl":          round(fixed_pnl,    2),
        "compound_pnl":       round(compound_pnl, 2),
        "compound_final_pot": round(compound_pot, 2),
    }


def _auto_label(config: BacktestConfig) -> str:
    ws = "W-ON" if config.require_weekly_aligned else "W-OFF"
    return (
        f"{config.ticker} · "
        f"E{config.entry_score_threshold} · "
        f"W{config.watch_score_threshold} · "
        f"RR{config.min_rr_ratio} · "
        f"S-{config.min_support_strength} · "
        f"{ws}"
    )


async def run_backtest(
    config: BacktestConfig,
    run_id: UUID,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[BacktestResult]:
    def _fetch_all():
        ti, pl, src = get_or_refresh_data(config.ticker)
        hdf = get_or_refresh_hourly_data(config.ticker)
        return ti, pl, src, hdf

    ticker_info, price_list, _, full_hourly_df = await asyncio.get_running_loop().run_in_executor(
        None, _fetch_all
    )

    full_df = _prepare_dataframe(price_list)
    if config.date_from and config.date_to:
        full_df = full_df[
            (full_df.index >= pd.Timestamp(config.date_from)) &
            (full_df.index <= pd.Timestamp(config.date_to))
        ].copy()
    else:
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=config.lookback_years)
        full_df = full_df[full_df.index >= cutoff].copy()

    results: list[BacktestResult] = []
    total_bars = len(full_df)

    for i in range(MIN_HISTORY_BARS, total_bars):
        window_df = full_df.iloc[:i].copy()
        assert window_df.index[-1] < full_df.index[i], (
            f"Lookahead bias detected at bar {i} for {config.ticker}"
        )
        if progress_callback and i % 10 == 0:
            progress_callback(i, total_bars, config.ticker)
        if i % 10 == 0:
            await asyncio.sleep(0)

        # Slice hourly data to the same cutoff as the daily window — no future bars
        cutoff_ts = window_df.index[-1]
        if full_hourly_df is not None and not full_hourly_df.empty:
            # Daily index is tz-naive; hourly index is UTC-aware — align comparison
            cutoff_aware = cutoff_ts.tz_localize("UTC") if cutoff_ts.tzinfo is None else cutoff_ts
            cutoff_end = cutoff_aware + pd.Timedelta(days=1)
            window_hourly: pd.DataFrame | None = full_hourly_df[
                full_hourly_df.index < cutoff_end
            ].copy()
        else:
            window_hourly = None


        try:
            result = analyze_ticker_from_df(config.ticker, window_df, config, hourly_df=window_hourly)
        except Exception:
            continue

        if result.get("swing_setup", {}).get("verdict") not in ("ENTRY", "WATCH"):
            continue

        signal_bar_index = i - 1
        signal = _build_signal(config.ticker, run_id, full_df, signal_bar_index, result)
        outcome = _resolve_outcome(signal, full_df, signal_bar_index)
        results.append(BacktestResult(signal=signal, outcome=outcome))

    if progress_callback:
        progress_callback(total_bars, total_bars, config.ticker)

    return results
