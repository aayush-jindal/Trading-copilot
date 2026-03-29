# Phase 7 — Hypothesis layer: backplayer extension + empirical strategy tuning

## What this phase is

Phase 7 is the evidence pipeline. Before changing any strategy parameter,
every hypothesis must pass through three stages:

1. **Backplayer** — run on real history, query condition-outcome DB
2. **Factory backtest** — prove generalisation across 39 tickers and two regimes
3. **Validated gate** — update validated_strategies.json and deploy

No strategy parameter changes without passing all three stages.
No code is written in Tasks 7.1–7.3. Code only starts at Task 7.4.

## Before starting

Confirm Phase 6 complete checklist is fully checked off.
The scanner, trade tracker, and analysis page must all be working.

Verify backtest_signals table is populated:

```bash
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT COUNT(*) as total_signals,
       COUNT(DISTINCT ticker) as tickers,
       MIN(signal_date) as earliest,
       MAX(signal_date) as latest
FROM backtest_signals;"
```

Must return at least 3,000 signals across at least 15 tickers.
If not: run the backplayer manually on the quality tickers before proceeding.

## Gate to advance to Phase 8

- [ ] Hypothesis agent completed all 6 experiments (277 runs)
- [ ] hypothesis_results.json copied out of container
- [ ] All findings documented in `.claude/hypothesis_findings.md`
- [ ] Each implemented change has a factory backtest result
- [ ] validated_strategies.json updated with new baselines
- [ ] All 382+ existing tests still passing
- [ ] No frozen files modified (ta_engine.py, market_data.py existing functions)

---

## Task 7.1 — Extend backplayer to support all registry strategies

READS FIRST:
- app/services/backtester.py (full file — understand current S1-only architecture)
- app/routers/player.py (full file — understand how runs are stored)
- app/database.py (backtest_runs and backtest_signals table schemas)
- backtesting/registry.py (STRATEGY_REGISTRY — understand registered strategies)
- backtesting/base.py (StrategyResult, Condition, RiskLevels — the factory contract)

GOAL:
Make the backplayer support any strategy from STRATEGY_REGISTRY, not just S1.
The backplayer currently calls compute_swing_setup_pullback() directly.
Replace this with a call to strategy.should_enter() + strategy.evaluate().

SCHEMA CHANGES — additive only, backward compatible:

In app/database.py init_db(), add these columns with IF NOT EXISTS:

```sql
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS
  strategy_name VARCHAR(50) DEFAULT 'S1_TrendPullback';

ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS
  strategy_name VARCHAR(50) DEFAULT 'S1_TrendPullback';

ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS
  conditions JSONB;
```

Existing rows default to S1_TrendPullback. No data migration needed.

BACKTESTER CHANGES in app/services/backtester.py:

Add strategy_name to BacktestConfig:
```python
strategy_name: str = 'S1_TrendPullback'
```

In the main backtest loop, replace the direct compute_swing_setup_pullback() call:

```python
from backtesting.registry import STRATEGY_REGISTRY

strategy = STRATEGY_REGISTRY.get(config.strategy_name)
if strategy is None:
    raise ValueError(f'Unknown strategy: {config.strategy_name}')

# Call factory contract
if not strategy.should_enter(snapshot):
    continue

result = strategy.evaluate(snapshot)
if result.verdict not in ('ENTRY', 'WATCH'):
    continue
```

Store conditions as JSONB — serialise result.conditions list:
```python
conditions_json = json.dumps([
    {'label': c.label, 'passed': bool(c.passed),
     'value': c.value, 'required': c.required}
    for c in result.conditions
])
```

For S1 specifically: also populate the existing S1-specific columns
(trigger_ok, near_support, reversal_found etc.) from the conditions list
by matching condition labels. This preserves backward compatibility —
existing S1 queries on specific columns still work.

For non-S1 strategies: leave S1-specific columns as NULL.
All condition data lives in the conditions JSONB column.

PLAYER ROUTER CHANGES in app/routers/player.py:

Add strategy_name to BacktestConfigBody:
```python
strategy_name: str = 'S1_TrendPullback'
```

Pass it through to BacktestConfig.
Store it in the backtest_runs INSERT.

VERIFY:
```bash
# Run S1 (should produce identical results to before)
curl -s -X POST http://localhost:8000/player/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"SPY","strategy_name":"S1_TrendPullback","lookback_years":1}' \
  | python3 -m json.tool

# Run S7
curl -s -X POST http://localhost:8000/player/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"SPY","strategy_name":"S7_MACDCross","lookback_years":1}' \
  | python3 -m json.tool
```

Both must return run_id and complete successfully.
S1 results must be numerically identical to pre-task results — no regression.

CHANGELOG entry: backplayer extended to support all registry strategies

---

## Task 7.2 — Add strategy selector to PlayerPage

READS FIRST:
- frontend/src/pages/PlayerPage.tsx (full file)
- frontend/src/types/index.ts (existing types)

GOAL:
Add a strategy dropdown to the PlayerPage run config panel.
When a run completes, show the strategy name in the runs list.

MODIFY: frontend/src/pages/PlayerPage.tsx

Add strategy_name to the run config form state, defaulting to S1_TrendPullback.

Strategy dropdown — static list, same as TradeTrackerPage:
```typescript
const STRATEGIES = [
  { value: 'S1_TrendPullback',    label: 'S1 Trend Pullback' },
  { value: 'S2_RSIMeanReversion', label: 'S2 RSI Mean Reversion' },
  { value: 'S3_BBSqueeze',        label: 'S3 BB Squeeze' },
  { value: 'S7_MACDCross',        label: 'S7 MACD Cross' },
  { value: 'S8_StochasticCross',  label: 'S8 Stochastic Cross' },
  { value: 'S9_EMACross',         label: 'S9 EMA Cross' },
]
```

Include strategy_name in the POST /player/run body.
Show strategy name as a badge in the runs list alongside the ticker.

In the signals table: add a CONDITIONS column that renders the JSONB
conditions array when strategy is not S1. For S1, the existing
specific columns (trigger_ok, near_support etc.) still render as before.

DO NOT change any existing layout or existing columns.
Additive only.

VERIFY:
Navigate to /player. Select S7 from dropdown. Run on SPY 1yr.
Run appears in list with S7 badge. Signals table shows conditions.

CHANGELOG entry: strategy selector added to PlayerPage

---

## Task 7.3 — Run hypothesis agent and document findings

This task has no code. It is data collection and analysis.

STEP 1: Copy hypothesis_agent.py to container and run:
```bash 

# Dry run first
docker-compose exec api python3 /app/hypothesis_agent.py --dry-run

# Run all experiments (allow 9+ hours)
docker-compose exec api python3 /app/hypothesis_agent.py \
  --workers 4--username admin --password yourpassword
```

STEP 2: Copy results out:

```bash
docker cp $(docker-compose ps -q api):/app/hypothesis_results.json .
```

STEP 3: Run cross-experiment analysis queries:

```bash
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT
  r.ticker,
  r.require_weekly_aligned,
  r.min_rr_ratio,
  r.entry_score_threshold,
  COUNT(s.id) as signals,
  ROUND(AVG(CASE WHEN s.outcome='WIN' THEN 1.0 ELSE 0.0 END)*100,1) as win_rate,
  ROUND(AVG(s.return_pct::numeric),3) as avg_return
FROM backtest_runs r
JOIN backtest_signals s ON s.run_id = r.run_id
WHERE s.outcome IS NOT NULL
  AND r.ticker NOT IN ('MSTR','TSLA','COIN','INTC','ORCL')
GROUP BY r.ticker, r.require_weekly_aligned, r.min_rr_ratio, r.entry_score_threshold
ORDER BY avg_return DESC
LIMIT 30;"
```

```bash
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT
  s.trigger_ok,
  s.rr_label,
  s.four_h_confirmed,
  COUNT(*) as signals,
  ROUND(AVG(CASE WHEN s.outcome='WIN' THEN 1.0 ELSE 0.0 END)*100,1) as win_rate,
  ROUND(AVG(s.return_pct::numeric),3) as avg_return
FROM backtest_signals s
JOIN backtest_runs r ON r.run_id = s.run_id
WHERE s.outcome IS NOT NULL
  AND r.ticker NOT IN ('MSTR','TSLA','COIN','INTC','ORCL')
GROUP BY s.trigger_ok, s.rr_label, s.four_h_confirmed
ORDER BY avg_return DESC;"
```

STEP 4: Create .claude/hypothesis_findings.md documenting:
- Best parameter value per experiment (weekly, lookback, entry, RR, support)
- Whether findings are consistent with the original 6,285-signal dataset
- Which findings are statistically reliable (n >= 200) vs tentative (n < 200)
- Recommended new defaults for each parameter
- Which strategy changes are justified by the data

Do not proceed to Task 7.4 until hypothesis_findings.md is written.

CHANGELOG entry: hypothesis agent completed, findings documented

Document the R:R for good bad and ugly with relevant info for user to understand, add in suggestion that may make the result better.
---

## Task 7.4 — Implement 1A: exclude poor R:R

READS FIRST:
- .claude/hypothesis_findings.md (confirm poor R:R finding holds in expanded data)
- backtesting/strategies/s1_trend_pullback.py (full file)
- backtesting/strategies/s2_rsi_reversion.py (full file)
- backtesting/strategies/s8_stochastic_cross.py (full file)
- backtesting/base.py (_stop_is_valid, RiskLevels)

PREREQUISITE: hypothesis_findings.md must confirm poor R:R avg_return is
negative or near-zero on quality tickers. If it shows positive: do not
implement this task, document the contradiction and stop.

GOAL:
Exclude poor R:R setups from S1, S2, S8 — the three strategies that read
R:R from swing_setup. S3, S7, S9 compute their own ATR-based targets
and are not affected.

CHANGE — identical pattern in all three strategy files:

In _compute_risk(), after computing R:R, add:

```python
rr_label = (snapshot.swing_setup or {}).get('conditions', {}).get('rr_label')
if rr_label == 'poor':
    return None
```

Add a corresponding Condition in _check_conditions() so the scanner
panel shows it:

```python
Condition(
    label='R:R quality',
    passed=rr_label not in ('poor', 'bad'),
    value=rr_label or 'unavailable',
    required='marginal or better',
)
```

Affected files: s1_trend_pullback.py, s2_rsi_reversion.py, s8_stochastic_cross.py

After modifying all three files:

```bash
docker cp backtesting/strategies/s1_trend_pullback.py \
  $(docker-compose ps -q api):/app/backtesting/strategies/s1_trend_pullback.py
docker cp backtesting/strategies/s2_rsi_reversion.py \
  $(docker-compose ps -q api):/app/backtesting/strategies/s2_rsi_reversion.py
docker cp backtesting/strategies/s8_stochastic_cross.py \
  $(docker-compose ps -q api):/app/backtesting/strategies/s8_stochastic_cross.py
```

VERIFY:
```bash
python -m pytest tests/test_strategies.py -v -k "S1 or S2 or S8"
```

All tests pass. Then smoke test the scanner:
```bash
curl -s http://localhost:8000/strategies/SPY \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | grep -A3 "R:R"
```

R:R quality condition must appear in the conditions list for S1, S2, S8.

FACTORY BACKTEST: Run factory backtest for S1, S2, S8 after this change.
Record before/after expectancy in the changelog.
If any strategy's test expectancy drops below zero: revert that strategy only.

CHANGELOG entry: 1A implemented — poor R:R excluded from S1, S2, S8

---

## Task 7.5 — Implement 1C: cap S1 target distance

READS FIRST:
- .claude/hypothesis_findings.md (confirm ENTRY avg_rr finding in expanded data)
- backtesting/strategies/s1_trend_pullback.py (full file, after Task 7.4)
- backtesting/base.py

PREREQUISITE: hypothesis_findings.md must confirm ENTRY+trigger avg_rr > 3.0
causing negative avg_return. If expanded data shows ENTRY avg_rr < 2.5
or avg_return is positive: do not implement, document and stop.

GOAL:
Cap S1's target at entry + 1.5×ATR when nearest_resistance is further
than entry + 2×ATR. This reduces the ENTRY group's avg_rr from ~3.5x
toward the WATCH+trigger group's ~1.8x.

CHANGE in s1_trend_pullback.py _compute_risk():

Find where target is set from nearest_resistance. Add:

```python
atr = snapshot.volatility.get('atr', 0)
max_target = entry_price + 2.0 * atr
if target > max_target:
    target = entry_price + 1.5 * atr
```

This only caps targets that are unrealistically far.
Targets already within 2×ATR are untouched.

VERIFY:
```bash
python -m pytest tests/test_strategies.py -v -k "S1"
```

FACTORY BACKTEST: Run factory backtest for S1 only.
Expected result: ENTRY win rate improves, test expectancy stays positive.
If test expectancy drops below zero: revert.

CHANGELOG entry: 1C implemented — S1 target capped at 1.5×ATR when resistance too far

---

## Task 7.6 — Implement 1B: add trigger condition to S8

READS FIRST:
- .claude/hypothesis_findings.md (confirm trigger finding holds for S8 signals)
- backtesting/strategies/s8_stochastic_cross.py (full file, after 7.4)
- backtesting/base.py

PREREQUISITE:
After Task 7.1, run the backplayer on S8 for 5+ quality tickers.
Query trigger_ok vs outcome for S8 signals specifically:

```bash
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT s.trigger_ok, COUNT(*),
  ROUND(AVG(CASE WHEN s.outcome='WIN' THEN 1.0 ELSE 0.0 END)*100,1) as win_rate
FROM backtest_signals s
JOIN backtest_runs r ON r.run_id = s.run_id
WHERE r.strategy_name = 'S8_StochasticCross'
  AND s.outcome IS NOT NULL
GROUP BY s.trigger_ok;"
```

If trigger_ok=True shows >= 10pp WR improvement for S8 specifically:
proceed. If not: do not implement, document and stop.

GOAL:
Add trigger condition as score bonus to S8. Not a hard gate — S8 can
still fire WATCH without trigger. Trigger adds +15 points to score.

CHANGE in s8_stochastic_cross.py:

In _check_conditions(), add:
```python
trigger_ok = snapshot.trend.get('trigger_ok', False)
Condition(
    label='Trigger bar',
    passed=bool(trigger_ok),
    value='fired' if trigger_ok else 'not fired',
    required='optional — adds score',
)
```

In scoring logic, add 15 points when trigger fires.
Do NOT add trigger to should_enter() — it must not gate the backtest.
Only _check_conditions() and score weighting change.

VERIFY:
```bash
python -m pytest tests/test_strategies.py -v -k "S8"
```

FACTORY BACKTEST: Run S8 factory backtest.
Gate: test expectancy must stay positive, trade count >= 20 on test.
If count drops below gate: remove trigger from score weighting, keep
the condition display only.

CHANGELOG entry: 1B implemented — trigger condition added to S8

---

## Task 7.7 — Update validated_strategies.json

READS FIRST:
- backtesting/validated_strategies.json (current file)
- All factory backtest results from Tasks 7.4, 7.5, 7.6

GOAL:
Update validated_strategies.json with new backtest results after the
three changes. Record before/after for each affected strategy.

For each strategy that was modified (S1, S2, S8):
- Update train.expectancy, test.expectancy, train.win_rate, test.win_rate
- Add a tuning_log entry:
```json
{
  "date": "2026-MM-DD",
  "change": "1A: excluded poor R:R",
  "train_before": ...,
  "train_after": ...,
  "test_before": ...,
  "test_after": ...,
  "decision": "shipped | reverted"
}
```

If any strategy's test expectancy dropped after the change:
- Set status to "watch" with a note
- Do not mark as validated until a full re-run confirms

VERIFY:
```bash
python scripts/smoke_test.py
```

All smoke tests pass.

CHANGELOG entry: validated_strategies.json updated with Phase 7 results

---

## Phase 7 complete checklist

- [ ] backtest_signals has strategy_name + conditions JSONB columns
- [ ] backplayer accepts all 6 registered strategies
- [ ] PlayerPage has strategy dropdown
- [ ] Hypothesis agent completed 277 runs across 6 experiments
- [ ] hypothesis_findings.md written with all conclusions
- [ ] 1A: poor R:R excluded from S1, S2, S8
- [ ] 1B: trigger condition added to S8 (if backplayer data supports)
- [ ] 1C: S1 target capped (if backplayer data supports)
- [ ] Factory backtest run for each changed strategy
- [ ] validated_strategies.json updated with before/after results
- [ ] All 382+ existing tests still passing
- [ ] No frozen file existing functions modified
- [ ] `cd frontend && npx tsc --noEmit` zero errors

## Ticker quality guideline (document in CLAUDE.md after this phase)

S1-compatible tickers (steady trend, reliable S/R):
  SPY QQQ AAPL MSFT COST WMT MCD TXN NOW AVGO JPM V MA UNH HD

S1-incompatible (volatile, unreliable S/R — use S2/S8 if at all):
  MSTR TSLA COIN INTC ORCL SNAP

These are empirical findings from 6,285 backplayer signals.
S1-incompatible tickers show negative EV across all parameter combinations.