"""Backtesting player: start runs, stream progress via SSE, list runs and signals."""

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.services.auth import decode_token
from app.services.market_data import get_or_refresh_data
from app.services.backtester import (
    BacktestConfig,
    BacktestResult,
    _aggregate_results,
    _auto_label,
    run_backtest,
)

router = APIRouter(prefix="/player", tags=["player"])

# Separate router for the SSE stream endpoint — registered WITHOUT the global
# JWT dependency because EventSource cannot set Authorization headers.
stream_router = APIRouter(prefix="/player", tags=["player"])

# In-memory progress store for SSE only; DB is source of truth
_runs: dict[str, dict] = {}


class BacktestConfigBody(BaseModel):
    ticker: str
    lookback_years: int = 3
    entry_score_threshold: int = 70
    watch_score_threshold: int = 55
    min_rr_ratio: float = 1.5
    min_support_strength: str = "LOW"
    require_weekly_aligned: bool = True
    run_label: str = ""
    date_from: str | None = None
    date_to: str | None = None
    strategy_name: str = "S1_TrendPullback"


class LabelBody(BaseModel):
    label: str


def _sse(data: dict | str, event: str = "message") -> str:
    payload = json.dumps(data) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


def _signal_row(r: BacktestResult, run_id: str) -> tuple:
    s, o = r.signal, r.outcome
    signal_date = s.signal_date.date() if hasattr(s.signal_date, "date") else s.signal_date
    outcome_date = o.outcome_date.date() if hasattr(o.outcome_date, "date") else o.outcome_date
    return (
        run_id,
        s.ticker,
        signal_date,
        s.verdict,
        s.setup_score,
        s.score_decile,
        s.uptrend_confirmed,
        s.weekly_trend_aligned,
        s.near_support,
        s.support_strength or None,
        s.reversal_found,
        s.trigger_ok,
        float(s.rr_ratio) if s.rr_ratio is not None else None,
        s.rr_label or None,
        s.support_is_provisional,
        s.entry_price,
        float(s.stop_loss) if s.stop_loss is not None else None,
        float(s.target) if s.target is not None else None,
        o.outcome,
        outcome_date,
        o.days_to_outcome,
        o.exit_price,
        o.return_pct,
        o.mae,
        o.mfe,
        s.four_h_available,
        s.four_h_confirmed,
        s.four_h_reversal,
        s.four_h_trigger,
        float(s.four_h_rsi) if s.four_h_rsi is not None else None,
        s.four_h_upgrade,
        s.strategy_name,
        s.conditions_json,
    )


@router.post("/run")
async def start_run(
    config: BacktestConfigBody,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> dict:
    run_id = str(uuid4())
    label = config.run_label.strip() or _auto_label(
        BacktestConfig(
            ticker=config.ticker,
            lookback_years=config.lookback_years,
            entry_score_threshold=config.entry_score_threshold,
            watch_score_threshold=config.watch_score_threshold,
            min_rr_ratio=config.min_rr_ratio,
            min_support_strength=config.min_support_strength,
            require_weekly_aligned=config.require_weekly_aligned,
            date_from=config.date_from,
            date_to=config.date_to,
            strategy_name=config.strategy_name,
        )
    )
    conn = get_db()
    conn.execute(
        """
        INSERT INTO backtest_runs
            (run_id, ticker, run_label, lookback_years,
             entry_score_threshold, watch_score_threshold,
             min_rr_ratio, min_support_strength,
             require_weekly_aligned, strategy_name, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'running')
        """,
        (
            run_id,
            config.ticker.upper(),
            label,
            config.lookback_years,
            config.entry_score_threshold,
            config.watch_score_threshold,
            config.min_rr_ratio,
            config.min_support_strength,
            config.require_weekly_aligned,
            config.strategy_name,
        ),
    )
    conn.commit()
    conn.close()

    _runs[run_id] = {"status": "running", "progress": 0, "total": 0}
    background_tasks.add_task(
        _execute_run,
        run_id,
        BacktestConfig(
            ticker=config.ticker.upper(),
            lookback_years=config.lookback_years,
            entry_score_threshold=config.entry_score_threshold,
            watch_score_threshold=config.watch_score_threshold,
            min_rr_ratio=config.min_rr_ratio,
            min_support_strength=config.min_support_strength,
            require_weekly_aligned=config.require_weekly_aligned,
            date_from=config.date_from,
            date_to=config.date_to,
            strategy_name=config.strategy_name,
        ),
    )
    return {"run_id": run_id, "label": label}


@stream_router.get("/stream/{run_id}")
async def stream_progress(
    run_id: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    # SSE via EventSource cannot send Authorization headers — accept token as query param.
    # Fall back to Authorization header for non-browser clients.
    raw_token = token
    if not raw_token and authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization.split(" ", 1)[1]
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        decode_token(raw_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    async def event_generator():
        while True:
            run = _runs.get(run_id)
            if not run:
                yield _sse("run not found", event="error")
                break
            if run["status"] == "running":
                total = max(run.get("total", 1), 1)
                pct = round(run.get("progress", 0) / total * 100, 1)
                yield _sse(
                    {
                        "progress": run.get("progress", 0),
                        "total": run["total"],
                        "pct": pct,
                    },
                    event="progress",
                )
                await asyncio.sleep(0.5)
            elif run["status"] == "complete":
                yield _sse(run["summary"], event="complete")
                break
            elif run["status"] == "error":
                yield _sse({"message": run.get("error", "Unknown error")}, event="error")
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/runs/{run_id}/label")
def rename_run(
    run_id: str,
    body: LabelBody,
    user: dict = Depends(get_current_user),
) -> dict:
    label = body.label.strip()
    conn = get_db()
    conn.execute(
        "UPDATE backtest_runs SET run_label = %s WHERE run_id = %s",
        (label, run_id),
    )
    conn.commit()
    conn.close()
    return {"run_id": run_id, "label": label}


@router.get("/chart/{run_id}/markers")
def get_run_markers(
    run_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Returns entry/exit markers and two ENTRY-only P&L series (fixed + compound)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM backtest_signals WHERE run_id = %s ORDER BY signal_date",
        (run_id,),
    ).fetchall()
    conn.close()

    def _date_str(d) -> str:
        if d is None:
            return ""
        if hasattr(d, "strftime"):
            return d.strftime("%Y-%m-%d")
        return str(d)[:10]

    markers = []
    fixed_running = 0.0
    compound_pot = 1000.0
    position_size = 1000.0
    pnl_series_fixed: list[dict] = []
    pnl_series_compound: list[dict] = []

    for s in rows:
        s = dict(s)
        signal_date = _date_str(s.get("signal_date"))
        entry_price = s.get("entry_price")
        if entry_price is not None:
            entry_price = float(entry_price)
        rr = s.get("rr_ratio")
        rr = float(rr) if rr is not None else None

        markers.append({
            "time": signal_date,
            "type": "entry",
            "verdict": s.get("verdict") or "",
            "score": int(s.get("setup_score") or 0),
            "price": entry_price,
            "rr_ratio": rr,
        })

        outcome_date = s.get("outcome_date")
        outcome = s.get("outcome")
        exit_price = s.get("exit_price")
        return_pct = s.get("return_pct")

        if outcome_date:
            days_to_outcome = s.get("days_to_outcome")
            markers.append({
                "time": _date_str(outcome_date),
                "type": "exit",
                "outcome": outcome or "EXPIRED",
                "price": float(exit_price) if exit_price is not None else None,
                "return_pct": float(return_pct) if return_pct is not None else 0.0,
                "days_to_outcome": int(days_to_outcome) if days_to_outcome is not None else None,
            })

        # P&L series — ENTRY signals only
        if s.get("verdict") == "ENTRY" and return_pct is not None and outcome_date:
            trade_return = float(return_pct) / 100
            trade_pnl_fixed = position_size * trade_return
            fixed_running += trade_pnl_fixed
            pnl_series_fixed.append({
                "time": _date_str(outcome_date),
                "value": round(fixed_running, 2),
            })

            trade_pnl_compound = compound_pot * trade_return
            compound_pot += trade_pnl_compound
            pnl_series_compound.append({
                "time": _date_str(outcome_date),
                "value": round(compound_pot - 1000, 2),
            })

    return {
        "run_id": run_id,
        "markers": markers,
        "pnl_series": pnl_series_fixed,       # backward compat alias
        "pnl_series_fixed": pnl_series_fixed,
        "pnl_series_compound": pnl_series_compound,
        "final_pnl": round(fixed_running, 2),
        "total_trades": len(rows),
    }


@router.get("/runs/{run_id}/signals/pnl")
def get_signals_with_pnl(
    run_id: str,
    user: dict = Depends(get_current_user),
) -> list:
    """Returns ENTRY signals sorted by date with running P&L for both models."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM backtest_signals
        WHERE run_id = %s AND verdict = 'ENTRY'
        ORDER BY signal_date ASC
        """,
        (run_id,),
    ).fetchall()
    conn.close()

    fixed_running = 0.0
    compound_pot = 1000.0
    position_size = 1000.0
    enriched = []

    for r in rows:
        s = dict(r)
        if s.get("run_id") is not None:
            s["run_id"] = str(s["run_id"])
        return_pct = float(s["return_pct"] or 0)
        trade_return = return_pct / 100

        trade_pnl_fixed = position_size * trade_return
        fixed_running += trade_pnl_fixed

        trade_pnl_compound = compound_pot * trade_return
        compound_pot += trade_pnl_compound

        enriched.append({
            **s,
            "trade_pnl_fixed":      round(trade_pnl_fixed,    2),
            "running_pnl_fixed":    round(fixed_running,      2),
            "trade_pnl_compound":   round(trade_pnl_compound, 2),
            "running_pot":          round(compound_pot,       2),
            "running_pnl_compound": round(compound_pot - 1000, 2),
        })

    # Return in descending date order for display
    return list(reversed(enriched))


@router.get("/chart/{ticker}")
async def get_chart_data(
    ticker: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Returns full OHLCV history for the candlestick chart (ticker-level)."""
    loop = asyncio.get_event_loop()
    try:
        _ticker_info, price_list, _ = await loop.run_in_executor(
            None, lambda: get_or_refresh_data(ticker.upper())
        )
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    candles = [
        {
            "time": (p["date"] if isinstance(p["date"], str) else p["date"].strftime("%Y-%m-%d")),
            "open": round(float(p["open"]), 2),
            "high": round(float(p["high"]), 2),
            "low": round(float(p["low"]), 2),
            "close": round(float(p["close"]), 2),
        }
        for p in price_list
    ]
    return {"candles": candles}


@router.get("/runs/{ticker}")
def get_runs_for_ticker(
    ticker: str,
    user: dict = Depends(get_current_user),
) -> list:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT run_id, ticker, run_label, lookback_years,
               entry_score_threshold, watch_score_threshold,
               min_rr_ratio, min_support_strength, require_weekly_aligned,
               status, total_signals, entry_signals, watch_signals,
               win_count, loss_count, expired_count,
               win_rate, win_rate_entry, win_rate_watch, win_rate_all,
               expected_value, avg_return_pct, avg_mae, avg_mfe,
               avg_days_to_outcome, expired_pct,
               entry_signal_count, fixed_pnl, compound_pnl, compound_final_pot,
               created_at, completed_at
        FROM backtest_runs
        WHERE ticker = %s AND status = 'complete'
        ORDER BY created_at DESC
        """,
        (ticker.upper(),),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("run_id") is not None:
            d["run_id"] = str(d["run_id"])
        out.append(d)
    return out


@router.get("/runs/{run_id}/signals")
def get_signals(
    run_id: str,
    user: dict = Depends(get_current_user),
) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM backtest_signals WHERE run_id = %s ORDER BY signal_date",
        (run_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("run_id") is not None:
            d["run_id"] = str(d["run_id"])
        out.append(d)
    return out


@router.delete("/runs/{run_id}")
def delete_run(
    run_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    conn = get_db()
    conn.execute("DELETE FROM backtest_runs WHERE run_id = %s", (run_id,))
    conn.commit()
    conn.close()
    if run_id in _runs:
        del _runs[run_id]
    return {"run_id": run_id, "deleted": True}


async def _execute_run(run_id: str, config: BacktestConfig) -> None:
    def on_progress(current: int, total: int, ticker: str) -> None:
        if run_id in _runs:
            _runs[run_id]["progress"] = current
            _runs[run_id]["total"] = total

    try:
        from uuid import UUID

        results = await run_backtest(config, UUID(run_id), on_progress)
        agg = _aggregate_results(results)

        conn = get_db()
        conn.execute(
            """
            UPDATE backtest_runs SET
                status = 'complete', completed_at = NOW(),
                total_signals = %s, entry_signals = %s, watch_signals = %s,
                win_count = %s, loss_count = %s, expired_count = %s,
                win_rate = %s, win_rate_entry = %s, win_rate_watch = %s, win_rate_all = %s,
                expected_value = %s, avg_return_pct = %s,
                avg_mae = %s, avg_mfe = %s, avg_days_to_outcome = %s,
                expired_pct = %s,
                entry_signal_count = %s, fixed_pnl = %s,
                compound_pnl = %s, compound_final_pot = %s
            WHERE run_id = %s
            """,
            (
                agg["total_signals"],
                agg["entry_signals"],
                agg["watch_signals"],
                agg["win_count"],
                agg["loss_count"],
                agg["expired_count"],
                agg["win_rate"],
                agg["win_rate_entry"],
                agg["win_rate_watch"],
                agg["win_rate_all"],
                agg["expected_value"],
                agg["avg_return_pct"],
                agg["avg_mae"],
                agg["avg_mfe"],
                agg["avg_days_to_outcome"],
                agg["expired_pct"],
                agg["entry_signal_count"],
                agg["fixed_pnl"],
                agg["compound_pnl"],
                agg["compound_final_pot"],
                run_id,
            ),
        )
        conn.commit()

        for r in results:
            row = _signal_row(r, run_id)
            conn.execute(
                """
                INSERT INTO backtest_signals
                    (run_id, ticker, signal_date, verdict, setup_score, score_decile,
                     uptrend_confirmed, weekly_trend_aligned, near_support, support_strength,
                     reversal_found, trigger_ok, rr_ratio, rr_label, support_is_provisional,
                     entry_price, stop_loss, target,
                     outcome, outcome_date, days_to_outcome, exit_price, return_pct, mae, mfe,
                     four_h_available, four_h_confirmed, four_h_reversal, four_h_trigger,
                     four_h_rsi, four_h_upgrade, strategy_name, conditions)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                row,
            )
        conn.commit()
        conn.close()

        _runs[run_id]["status"] = "complete"
        _runs[run_id]["summary"] = agg
    except Exception as e:
        _runs[run_id]["status"] = "error"
        _runs[run_id]["error"] = str(e)
        conn = get_db()
        conn.execute("UPDATE backtest_runs SET status = 'error' WHERE run_id = %s", (run_id,))
        conn.commit()
        conn.close()
