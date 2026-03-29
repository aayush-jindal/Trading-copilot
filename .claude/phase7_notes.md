# Phase 7 — Complete Reference Notes

## What phase 7 is

The evidence pipeline for strategy improvement. Every hypothesis about
improving a strategy must pass through three stages before any code changes:

1. Backplayer — test on real history, query condition-outcome DB
2. Factory backtest — prove generalisation across 39 tickers, two regimes  
3. Validated gate — update validated_strategies.json, deploy to scanner

No code changes without passing all three stages.

---

## The six experiments (hypothesis agent)

Each experiment varies ONE parameter, holds all others at default.
Default config: entry=70, watch=55, rr=1.5, support=LOW, weekly=ON, lookback=3yr

| ID | Parameter varied | Values tested | Tickers | Runs |
|----|-----------------|---------------|---------|------|
| A  | require_weekly_aligned | True, False | 18 quality | 36 |
| B  | lookback_years | 1, 2, 3, 5 | 12 trend | 48 |
| C  | entry_score_threshold | 60, 65, 70, 75, 80 | 12 trend | 60 |
| D  | min_rr_ratio | 1.0, 1.5, 2.0, 2.5 | 18 quality | 72 |
| E  | min_support_strength | LOW, MEDIUM, HIGH | 18 quality | 54 |
| F  | sector ETFs baseline | default config | 7 ETFs | 7 |

Total: 277 runs, ~9 hours sequential, ~3 hours with 3 workers

## Ticker universe

Quality tickers (S1-compatible, steady trend, reliable S/R):
  SPY QQQ AAPL MSFT COST WMT MCD TXN NOW AVGO JPM V
  MU PYPL AMD NFLX CRM SHOP

Sector ETFs:
  XLK XLF XLE XLV XLY GLD TLT

S1-incompatible (volatile, unreliable S/R — avoid on S1):
  MSTR TSLA COIN INTC ORCL SNAP

Empirically validated: these tickers show negative EV across all
parameter combinations in 6,285 backplayer signals.

---

## Key findings from existing data (6,285 signals)

Source: backplayer runs on quality tickers excluding MSTR/TSLA/COIN/INTC/ORCL

### Trigger finding (STRONG — 335 samples)
WATCH + trigger=True:  WR=85.5%, avg_return=+0.138, avg_rr=1.82x
ENTRY + trigger=True:  WR=64.9%, avg_return=-0.139, avg_rr=3.64x
WATCH + trigger=False: WR=64.7%, avg_return=+0.141

Implication: ENTRY signals fail because targets are too ambitious (avg_rr=3.64x).
Fix: cap S1 target at entry + 1.5×ATR when resistance > entry + 2×ATR.
WATCH+trigger is the highest quality signal. Surface prominently in scanner.

### R:R label finding (STRONG — 5,477 samples)
good:     WR=57.2%, avg_return=+0.225 (best EV despite lower WR)
marginal: WR=74.4%, avg_return=+0.125
poor:     WR=76.1%, avg_return=+0.007 (classic low-RR trap)

Implication: exclude poor R:R from S1/S2/S8 _compute_risk().
Poor R:R barely breaks even — not worth the risk.

### 4H confirmation finding (WEAK — 973/2791 samples)
four_h_confirmed=True:  WR=66.8%, avg_return=+0.04
four_h_confirmed=False: WR=64.0%, avg_return=-0.03

Implication: only +2.8pp WR. Use as score bonus only, never gate.

### WATCH without trigger (NEW — 5,123 samples)
WR=64.7%, avg_return=+0.141 on quality tickers.
WATCH signals have real edge on good tickers. Do not demote them.

---

## The three planned strategy changes

### 1A — Exclude poor R:R (HIGH confidence, implement now)
Files: s1_trend_pullback.py, s2_rsi_reversion.py, s8_stochastic_cross.py
Change: in _compute_risk(), return None when rr_label == 'poor'
Add Condition to _check_conditions() showing R:R quality
Evidence: 1,856 poor-RR signals, avg_return=+0.007, near-zero EV
No factory rerun required — backplayer data sufficient

### 1B — Add trigger to S8 (MEDIUM confidence, verify first)
File: s8_stochastic_cross.py
Change: add trigger_ok as score bonus (+15 pts) in _check_conditions()
NOT in should_enter() — must not gate the backtest
Prerequisite: run S8 through backplayer on 5+ tickers after Task 7.1
Query trigger_ok vs outcome for S8 signals specifically
Only implement if trigger adds >= 10pp WR for S8 signals

### 1C — Cap S1 target distance (MEDIUM confidence, verify first)  
File: s1_trend_pullback.py
Change: if target > entry + 2×ATR, set target = entry + 1.5×ATR
Prerequisite: hypothesis agent Exp D results confirm ENTRY avg_rr > 3.0
Expected: ENTRY win rate improves, test expectancy stays positive

---

## Task sequence

Task 7.1: Extend backplayer to support all registry strategies
  - Schema: add strategy_name + conditions JSONB to backtest_signals
  - backtester.py: call strategy.should_enter() + evaluate() instead of S1 direct
  - player.py: accept strategy_name in BacktestConfigBody
  - No frontend changes in this task

Task 7.2: Add strategy selector to PlayerPage
  - Dropdown: static list of 6 validated strategies
  - Pass strategy_name in POST /player/run
  - Show strategy badge in runs list
  - Render conditions JSONB in signals table for non-S1 strategies

Task 7.3: Run hypothesis agent and document findings
  - Copy hypothesis_agent.py to container
  - Run all 6 experiments (~9 hours or ~3 hours with --workers 3)
  - Copy hypothesis_results.json out
  - Write .claude/hypothesis_findings.md
  - Gate: findings must be written before 7.4 starts

Task 7.4: Implement 1A (poor R:R exclusion)
  - Prerequisite: hypothesis_findings.md confirms poor R:R near-zero EV
  - Modify S1, S2, S8 _compute_risk()
  - Add R:R quality Condition to _check_conditions()
  - Run factory backtest for all three
  - Update validated_strategies.json

Task 7.5: Implement 1C (S1 target cap)
  - Prerequisite: hypothesis_findings.md confirms ENTRY avg_rr > 3.0
  - Modify S1 _compute_risk() only
  - Run factory backtest for S1
  - Revert if test expectancy drops below zero

Task 7.6: Implement 1B (trigger to S8)
  - Prerequisite: backplayer S8 data shows trigger adds >= 10pp WR
  - Modify S8 _check_conditions() and scoring only
  - Not in should_enter()
  - Run factory backtest for S8
  - Revert if trade count drops below gate

Task 7.7: Update validated_strategies.json
  - Record before/after for each modified strategy
  - Add tuning_log entry per strategy
  - Run smoke tests

---

## Commands reference

### Auth
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=yourpassword" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Check backtest_signals health
```bash
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT COUNT(*) as signals, COUNT(DISTINCT ticker) as tickers
FROM backtest_signals;"
```

### Core analysis queries (run after any backplayer batch)
```bash
# Trigger vs outcome
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT trigger_ok, verdict, COUNT(*),
  ROUND(AVG(CASE WHEN outcome='WIN' THEN 1.0 ELSE 0.0 END)*100,1) as win_rate,
  ROUND(AVG(return_pct::numeric),3) as avg_return,
  ROUND(AVG(rr_ratio::numeric),2) as avg_rr
FROM backtest_signals
WHERE outcome IS NOT NULL
  AND ticker NOT IN ('MSTR','TSLA','COIN','INTC','ORCL')
GROUP BY trigger_ok, verdict ORDER BY trigger_ok DESC, verdict;"

# R:R label vs outcome
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT rr_label, COUNT(*),
  ROUND(AVG(CASE WHEN outcome='WIN' THEN 1.0 ELSE 0.0 END)*100,1) as win_rate,
  ROUND(AVG(return_pct::numeric),3) as avg_return
FROM backtest_signals
WHERE outcome IS NOT NULL
  AND ticker NOT IN ('MSTR','TSLA','COIN','INTC','ORCL')
GROUP BY rr_label ORDER BY avg_return DESC;"

# 4H confirmation vs outcome
docker-compose exec db psql -U postgres -d trading_copilot -c "
SELECT four_h_confirmed, COUNT(*),
  ROUND(AVG(CASE WHEN outcome='WIN' THEN 1.0 ELSE 0.0 END)*100,1) as win_rate,
  ROUND(AVG(return_pct::numeric),3) as avg_return
FROM backtest_signals
WHERE outcome IS NOT NULL
  AND ticker NOT IN ('MSTR','TSLA','COIN','INTC','ORCL')
GROUP BY four_h_confirmed;"
```

### Run hypothesis agent
```bash
# Copy script
docker cp hypothesis_agent.py $(docker-compose ps -q api):/app/hypothesis_agent.py

# Dry run
docker-compose exec api python3 /app/hypothesis_agent.py --dry-run

# Run single experiment
docker-compose exec api python3 /app/hypothesis_agent.py --exp A \
  --username admin --password yourpassword

# Run all (sequential, ~9 hours)
docker-compose exec api python3 /app/hypothesis_agent.py \
  --username admin --password yourpassword

# Run all (parallel, ~3 hours)
docker-compose exec api python3 /app/hypothesis_agent.py \
  --workers 3 --username admin --password yourpassword

# View summary of existing results
docker-compose exec api python3 /app/hypothesis_agent.py --summary

# Copy results out
docker cp $(docker-compose ps -q api):/app/hypothesis_results.json .
```

### Factory backtest
```bash
# Run from project root (not inside docker)
cd /Users/sirius/projects/tech_analyzer/Trading-copilot
python backtesting/run_backtest.py

# Results in:
# backtesting/train_results.csv
# backtesting/test_results.csv
```

### docker cp strategy files after editing
```bash
docker cp backtesting/strategies/s1_trend_pullback.py \
  $(docker-compose ps -q api):/app/backtesting/strategies/s1_trend_pullback.py
docker cp backtesting/strategies/s2_rsi_reversion.py \
  $(docker-compose ps -q api):/app/backtesting/strategies/s2_rsi_reversion.py
docker cp backtesting/strategies/s8_stochastic_cross.py \
  $(docker-compose ps -q api):/app/backtesting/strategies/s8_stochastic_cross.py
```

### Run tests
```bash
docker-compose exec api python -m pytest tests/test_strategies.py -v
docker-compose exec api python scripts/smoke_test.py
```

---

## Architecture decisions recorded

ADR-016: Backplayer merge frozen file exceptions
ADR-017: Three new signal layers pending integration (4H, RR label, provisional S/R)
ADR-018: (pending) Parallel hypothesis agent design

## Files produced

/app/hypothesis_agent.py      — 6-experiment parameter sweep agent
/app/run_backplayer.py        — simple multi-ticker backplayer runner
.claude/phase7.md             — Claude Code instructions for Phase 7
.claude/hypothesis_findings.md — (written during Task 7.3)
hypothesis_results.json       — (produced by hypothesis agent)