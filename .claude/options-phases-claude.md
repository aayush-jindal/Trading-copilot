# Options Development Phases — Claude Code Instructions

## Active phase files

Read the active phase file before starting any work. Execute one task
at a time. Do not start the next task until the current one is verified.

| File | Status | Description |
|------|--------|-------------|
| `.claude/frontend_update.md` | Done | Frontend UI for chain scanner |
| `.claude/nightly-cron.md` | Done | Nightly scan + rate limit throttle |
| `.claude/phase-d-option-trades.md` | Active | Options trade tracker |
| `.claude/phase-e-iv-history.md` | Queued | Historical IV tracking |
| `.claude/phases-f-g-h.md` | Queued | Signal correlation, alerts, backtesting |

Work through files in order. When a phase file is complete, mark it
done in this table and move to the next.

---

## Commit rules

After completing each numbered task within a phase file:

1. Run verification command specified in the task's acceptance criteria
2. If verification passes, commit all changed files with this format:

```
git add -A
git commit -m "<type>(<scope>): <description>

Phase: <phase-letter>
Task: <task-number>
Files: <count> created, <count> modified"
```

### Commit type conventions

| Type | When |
|------|------|
| `feat` | New file or endpoint or component |
| `fix` | Bug fix (e.g. the knowledge_strategies 500 fix) |
| `refactor` | Import rewiring, code moves with no behavior change |
| `test` | New or modified test files |
| `docs` | CHANGELOG, CLAUDE.md, README updates |
| `chore` | Config changes, dependency updates |

### Scope conventions

| Scope | When |
|-------|------|
| `chain-scanner` | Phase A/B/C chain scanner work |
| `frontend` | Any frontend change |
| `options` | Options-related backend |
| `trades` | Trade tracker work |
| `cron` | Nightly job changes |
| `db` | Database schema changes |

### Examples

```
feat(frontend): add ChainScannerPanel component

Phase: frontend
Task: 4
Files: 1 created, 0 modified

fix(options): change knowledge_strategies type to Optional[Any]

Phase: frontend
Task: 1
Files: 1 modified (app/routers/options.py)

feat(db): add option_trades table for position tracking

Phase: D
Task: 1
Files: 1 modified (app/database.py)

feat(cron): add nightly chain scan with throttled provider

Phase: nightly-cron
Task: 2-3
Files: 2 created, 1 modified
```

3. After committing, update CHANGELOG.md if the task says to
4. Then proceed to the next task

---

## Verification before commit

Always run before committing:

```bash
# Backend:
docker exec docker-api-1 python scripts/smoke_test.py

# If new tests were added:
docker exec docker-api-1 python -m pytest tests/<new_test_file>.py -v

# Frontend (if frontend files changed):
# Check for TypeScript errors in the Vite console
```

If smoke test fails, fix the issue before committing. Do not commit
broken code.

---

## Rate limit recovery

If yfinance returns 429 (Too Many Requests) during a live scan:

1. The CachedProvider should return cached data if available
2. The YFinanceProvider's `_throttle()` method adds delay between calls
3. If rate-limited during nightly cron, log warning and continue with
   whatever tickers succeeded
4. The frontend falls back to `GET /options/chain-signals` (cached DB
   results) when live scan fails

Do NOT retry aggressively — yfinance rate limits escalate with retries.
Wait for the cache TTL to expire or the next nightly run.

---

## Non-negotiable rules (inherited from main CLAUDE.md)

1. Never modify `app/services/ta_engine.py` existing functions or weights
2. Never modify `app/services/options/bias_detector.py`
3. Never modify `app/services/options/pricing/src/**`
4. Never modify `app/routers/synthesis.py` or `app/services/ai_engine.py`
5. Never modify existing functions in `app/services/market_data.py`
6. After every task: append to `CHANGELOG.md` then stop
7. After every task: run `python scripts/smoke_test.py` and confirm pass
8. Never work on more than one numbered task at a time
9. Do not add any feature, field, file, or dependency not explicitly
   listed in the active task
10. When in doubt about a file: read it, do not edit it
