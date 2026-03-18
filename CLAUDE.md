# CLAUDE.md

## What this application is
A personal trading decision support tool. It scans the user's watchlist,
surfaces validated strategy setups ranked by conviction, provides exact
entry/stop/target/position sizing, and tracks open trades for exit alerts.

## Current active phase
Read `.claude/phase3.md` before doing any work.
Complete one numbered task at a time. Do not start the next task until
the current one is verified and CHANGELOG.md is updated.

---

## Non-negotiable rules

1. Never modify `app/services/ta_engine.py`
2. Never modify `app/services/options/bias_detector.py`
3. Never modify `app/services/options/pricing/src/**`
4. Never modify `app/routers/synthesis.py` or `app/services/ai_engine.py`
5. Never modify `tools/knowledge_base/retriever.py` unless the active
   phase file explicitly says to
6. After every task: append to `CHANGELOG.md` then stop
7. After every task: run `python scripts/smoke_test.py` and confirm pass
8. Never work on more than one numbered task at a time
9. Do not add any feature, field, file, or dependency not explicitly
   listed in the active task. If something seems missing, stop and ask.
10. When in doubt about a file: read it, do not edit it

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

| File | Why frozen |
|------|-----------|
| app/services/ta_engine.py | swing_setup weights + all signal logic |
| app/services/options/bias_detector.py | options scoring weights |
| app/services/options/pricing/src/** | bundled pricing library |
| app/routers/synthesis.py | SSE narrative stream |
| app/services/ai_engine.py | prose narrative |
| app/services/market_data.py | data fetching |
| docker/docker-compose.yml | infrastructure |
| tests/ | all existing tests must keep passing |

## Architecture reference
See `.claude/architecture.md`

## Code Search
This repo is indexed with qmd. Always search the index before reading files.
- Use `qmd_search` for keyword lookups (fast)
- Use `qmd_vector_search` for conceptual/semantic queries
- Use `qmd_deep_search` for complex questions needing best accuracy
- Only fall back to Read/Glob if qmd returns insufficient results

Collection name: trading-copilot
