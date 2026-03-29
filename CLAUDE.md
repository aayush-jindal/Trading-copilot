# CLAUDE.md

## What this application is
A personal trading decision support tool. It scans the user's watchlist,
surfaces validated strategy setups ranked by conviction, provides exact
entry/stop/target/position sizing, and tracks open trades for exit alerts.

## Current active phase
Read `.claude/phase7.md` before doing any work.
Complete one numbered task at a time. Do not start the next task until
the current one is verified and CHANGELOG.md is updated.

---

## Non-negotiable rules

1. Never modify `app/services/ta_engine.py` existing functions or weights
2. Never modify `app/services/options/bias_detector.py`
3. Never modify `app/services/options/pricing/src/**`
4. Never modify `app/routers/synthesis.py` or `app/services/ai_engine.py`
5. Never modify `tools/knowledge_base/retriever.py` unless the active
   phase file explicitly says to
6. Never modify existing functions in `app/services/market_data.py`
7. After every task: append to `CHANGELOG.md` then stop
8. After every task: run `python scripts/smoke_test.py` and confirm pass
9. Never work on more than one numbered task at a time
10. Do not add any feature, field, file, or dependency not explicitly
    listed in the active task. If something seems missing, stop and ask.
11. When in doubt about a file: read it, do not edit it

---

## The strategy factory contract
Every strategy must follow this exact pattern — no exceptions:

```
backtesting/strategies/sN_name.py
  class XxxStrategy(BaseStrategy):
      name = "SN_Name"
      type = "trend" | "reversion" | "breakout" | "rotation"
      _check_conditions(snapshot) -> list[Condition]
      _compute_risk(snapshot)     -> RiskLevels
```

Adding a strategy = one new file + one line in registry.py. Zero other changes.

---

## Frozen files

| File | Why frozen | Freeze scope |
|------|-----------|--------------|
| app/services/ta_engine.py | swing_setup weights + all signal logic | All existing compute_* functions and weights. four_h_confirmation addition (backplayer merge) is also frozen. |
| app/services/options/bias_detector.py | options scoring weights | Entire file |
| app/services/options/pricing/src/** | bundled pricing library | Entire directory |
| app/routers/synthesis.py | SSE narrative stream | Entire file |
| app/services/ai_engine.py | prose narrative | Entire file |
| app/services/market_data.py | data fetching | All existing functions. Hourly data functions (backplayer merge) are also frozen. |
| docker/docker-compose.yml | infrastructure | Entire file |
| tests/ | all existing tests must keep passing | Never delete or modify existing tests |

## Signal layers available in SignalSnapshot

The following signals are computed on every analysis call and available
to strategy factory code. Do not recompute them — read them from snapshot.

**Daily signals (always available):**
- `snapshot.trend` — SMA50, SMA200, EMA9, EMA21, golden/death cross
- `snapshot.momentum` — RSI, MACD, stochastic
- `snapshot.volatility` — ATR, Bollinger Bands, squeeze
- `snapshot.volume` — volume ratio, OBV trend
- `snapshot.support_resistance` — nearest support/resistance, provisional flags
- `snapshot.swing_setup` — full swing setup output including risk levels and R:R
- `snapshot.candlestick` — all 61 TA-Lib patterns on last bar
- `snapshot.weekly` — weekly trend direction and strength

**4H signals (available when hourly data exists — check four_h_available):**
- `snapshot.four_h_confirmation.four_h_upgrade` — True when daily + 4H aligned
- `snapshot.four_h_confirmation.four_h_confirmed` — all 4H conditions met
- `snapshot.four_h_confirmation.four_h_available` — False means no hourly data

**R:R quality (available in swing_setup.conditions):**
- `swing_setup.conditions.rr_label` — good/marginal/poor/bad/unavailable
- `swing_setup.conditions.rr_gate_pass` — False means R:R is too poor to trade

**Provisional S/R (available in support_resistance):**
- `support_resistance.support_is_provisional` — True means unconfirmed swing low
- `support_resistance.resistance_is_provisional` — same for resistance

These three new signal groups (4H, R:R quality, provisional S/R) are
NOT yet integrated into any strategy. Integration requires querying
backtest_signals outcome data first. See ADR-017.

## Architecture reference
See `.claude/architecture.md`
See `.claude/ARCHITECTURE_DECISIONS.md` for all ADRs including ADR-016
(backplayer merge freeze exceptions) and ADR-017 (new signal integration plan)