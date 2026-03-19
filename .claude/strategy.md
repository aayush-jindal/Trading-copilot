# Strategy consistency pass — s2, s3, s7, s8, s9

S1 (s1_trend_pullback.py) is the canonical reference implementation.
Read it in full before touching any other strategy file.
This pass makes all five remaining strategies consistent with S1 in
structure, guards, and entry zone coverage.

Do one strategy file at a time. After each file run the full test suite
and confirm it passes before moving on.

---

## Before starting

Read these files in full before writing anything:
- backtesting/strategies/s1_trend_pullback.py — canonical reference
- backtesting/base.py — BaseStrategy, RiskLevels, Condition, _stop_is_valid
- backtesting/signals.py — SignalSnapshot field names

The goal is consistency with S1, not reimplementation. If S1 does
something a specific way, the other strategies must do it the same way
unless there is a documented reason not to.

---

## Rules that apply to every strategy

**_compute_risk():**
- Return None early if the primary signal source is absent
- Return None early if stop or target cannot be determined
- Call _stop_is_valid() and return None if it returns False — this guard
  is what prevented the +662R artefact in S8's backtest results
- Do not set position_size — the scanner sets it after _compute_risk() returns
- Set atr from the correct snapshot field for that strategy
- Set entry_zone_low and entry_zone_high (rules per strategy below)

**_check_conditions():**
- Every condition must have label, passed, value, and required populated
- passed must always be a bool — never a string, number, or None
- Use .get() with safe defaults on all dict accesses — never assume a key exists
- Every filter applied in should_enter() must have a matching Condition here
  (ADR-015 — scanner must see everything the backtest validated)

**should_exit():**
- Handle None gracefully on every snapshot field — rsi and nearest_resistance
  are both None sometimes and must not cause a TypeError
- Exit thresholds by strategy type:
  trend (S7, S9): RSI >= 70
  reversion (S2, S8): RSI >= 65
  breakout (S3): RSI >= 70
- All strategies also exit when price >= nearest_resistance (when not None)

**evaluate():**
- Structure must be identical to S1 — _check_conditions, _verdict, _compute_risk
- Only call _compute_risk when verdict is not NO_TRADE
- Never set ticker on the returned StrategyResult — scanner sets it

---

## Per-strategy changes

### s2_rsi_reversion.py

_compute_risk():
- Add _stop_is_valid() guard
- Add entry_zone_low and entry_zone_high — read from swing_setup.risk.entry_zone,
  same nested path as S1. Rationale: RSI < 30 means price is at support.
  The swing_setup support zone is the correct zone for a reversion bounce.
- Confirm atr is set in the returned RiskLevels

_check_conditions():
- Confirm these three conditions are present:
  RSI crossed above 30, price above SMA200, BB position below 20
- Add any that are missing

should_exit():
- RSI exit threshold must be >= 65

### s3_bb_squeeze.py

_compute_risk():
- Add _stop_is_valid() guard
- Add entry_zone_low and entry_zone_high — the breakout entry zone sits
  above the upper Bollinger Band. Low is bb_upper, high is bb_upper plus
  a fraction of ATR. Read bb_upper and atr from snapshot.volatility.
- Confirm atr is set in the returned RiskLevels

_check_conditions():
- Confirm these four conditions are present:
  BB squeeze resolved, price above upper band, volume confirmation, price above SMA200
- Add any that are missing

should_exit():
- RSI exit threshold must be >= 70

### s7_macd_cross.py

_compute_risk():
- Add _stop_is_valid() guard
- Add entry_zone_low and entry_zone_high — momentum entry, tight zone
  around the crossover price. Use a fraction of ATR above and below entry.
  Read atr from snapshot.volatility.
- Confirm atr is set in the returned RiskLevels

_check_conditions():
- Confirm these four conditions are present:
  MACD bullish crossover, price above SMA200, RSI not extended, weekly trend bullish
- Add any that are missing

should_exit():
- RSI exit threshold must be >= 70

### s8_stochastic_cross.py

_compute_risk():
- Add _stop_is_valid() guard — this is the fix that corrected the +662R artefact
- Add entry_zone_low and entry_zone_high — read from swing_setup.risk.entry_zone,
  same nested path as S1 and S2. Rationale: stochastic cross below 20 fires when
  price is at support. Same conceptual entry as S1 and S2.
- Confirm atr is set in the returned RiskLevels

_check_conditions():
- ADR-015: should_enter() already filters on price > SMA200. This condition
  must be an explicit Condition here or the scanner fires signals on stocks
  below SMA200 that the backtest never validated.
- Confirm these conditions are present:
  price above SMA200 (add if missing), stochastic K crossed above D from below 20,
  RSI not overbought
- Add any that are missing

should_exit():
- RSI exit threshold must be >= 65

### s9_ema_cross.py

_compute_risk():
- Add _stop_is_valid() guard
- Add entry_zone_low and entry_zone_high — after an EMA cross, the ideal
  entry zone is between the two EMAs. Read ema_9 and ema_21 from
  snapshot.trend. Use min/max to handle whichever is lower.
- Confirm atr is set in the returned RiskLevels

_check_conditions():
- Confirm these four conditions are present:
  EMA9 crossed above EMA21, price above both EMAs, price above SMA200,
  volume not weak
- Add any that are missing

should_exit():
- RSI exit threshold must be >= 70

---

## Tests

CREATE: tests/test_strategies.py

Read the existing tests/ directory first to understand the project's
test style, fixtures, and conventions before writing anything.

Write a test file that covers every strategy in STRATEGY_REGISTRY.
Use pytest.mark.parametrize so each test runs once per strategy.
Build a minimal mock SignalSnapshot fixture that satisfies all strategy
entry conditions — adjust individual fields per test to trigger specific
code paths.

Tests to include:

Contract tests (run for every strategy):
- evaluate() returns a StrategyResult instance
- result.name matches strategy.name, result.type matches strategy.type
- result.verdict is one of ENTRY, WATCH, NO_TRADE
- result.score is between 0 and 100
- result.ticker is None — scanner sets it, strategy must not
- result.risk is None when verdict is NO_TRADE
- result.conditions is a non-empty list

Condition tests:
- Every item in _check_conditions() output is a Condition instance
- Every Condition has label (non-empty str), passed (bool), value (str), required (non-empty str)
- _check_conditions() does not raise when swing_setup is None
- _check_conditions() does not raise when numeric snapshot fields are zero
- At least 3 conditions returned

_compute_risk() tests:
- Returns RiskLevels or None — nothing else
- When it returns RiskLevels: stop_loss < entry_price
- When it returns RiskLevels: target > entry_price
- When it returns RiskLevels: risk_reward > 0
- When it returns RiskLevels: position_size is None
- When it returns RiskLevels and entry_zone_low is not None:
  entry_zone_low <= entry_zone_high and both are positive floats
- Returns None when stop is within 0.5×ATR of entry (_stop_is_valid guard)

should_enter() / get_stops() tests:
- Returns bool
- When should_enter() returns True, get_stops() returns a StopConfig
  where stop_loss < entry_price and target_1 > entry_price

should_exit() tests:
- Returns bool
- Returns True when RSI is 80 (well above all thresholds)
- Returns True when price equals nearest_resistance
- Returns False under normal conditions (RSI ~55, price between support and resistance)
- Does not raise when rsi is None
- Does not raise when nearest_resistance is None

ADR-015 test:
- For each strategy whose should_enter() source contains price_vs_sma200:
  call _check_conditions() with price_vs_sma200 set to "above" and again
  with it set to "below". The passed values must differ between the two
  calls — if they are identical, the SMA200 filter is hidden from the scanner.

VERIFY:
```bash
python -m pytest tests/test_strategies.py -v
python -m pytest tests/ -q
```

All tests must pass before opening phase6.md.
If a test fails: fix the strategy file, re-run, confirm pass.
Do not skip failing tests.