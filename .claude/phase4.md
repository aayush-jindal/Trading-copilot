# Phase 4 — RAG upgrade + morning briefing

## Before starting
Confirm phase3.md complete checklist is fully checked off.
GET /strategies/scan/watchlist must be working before this phase.

## Gate to advance to Phase 5
- strategy_gen.py returns valid JSON dict matching the schema (no price fields)
- retrieve_relevant_chunks() filters correctly by book_type
- generate_strategy_briefing(user_id, db) returns non-empty string for a
  user with a watchlist when at least one ENTRY setup is firing
- Morning briefing cron job output includes the strategy section
- `python -m pytest tests/` still passes

---

## Task 4.1 — Split RAG retrieval by book type

READS FIRST:
- tools/knowledge_base/retriever.py (FULL FILE — then you may modify it)
- tools/knowledge_base/strategy_gen.py (full file)
- docker/knowledge_chunks.sql (current schema)
- tools/knowledge_base/pdf_ingester.py (ingestion logic)

GOAL:
Tag each ingested book as equity_ta or options_strategy so retrieval
can be filtered. Two changes only.

Equity TA books (book_type = 'equity_ta') — 9 books:
  Technical Analysis of Stock Trends, Technical Analysis Complete Resource,
  New Frontiers in Technical Analysis, Evidence-Based Technical Analysis,
  Encyclopedia of Chart Patterns, Complete Guide to Technical Trading Tactics,
  Algorithmic Trading, Harmonic Trading Vol 1, Harmonic Trading Vol 2

Options books (book_type = 'options_strategy') — 2 books:
  Option Spread Strategies, Option Volatility & Pricing

MODIFY: docker/knowledge_chunks.sql
  Add: book_type VARCHAR(20) DEFAULT 'equity_ta'
  Add: CREATE INDEX IF NOT EXISTS idx_book_type ON knowledge_chunks(book_type)

MODIFY: tools/knowledge_base/pdf_ingester.py
  Add OPTIONS_BOOKS list at top.
  Detect book_type from source_file name before INSERT.
  Pass book_type into INSERT statement.

MODIFY: tools/knowledge_base/retriever.py
  Add optional book_type: str | None = None param to retrieve_relevant_chunks().
  Add WHERE book_type = %s clause ONLY when book_type is not None.
  Default behaviour (book_type=None) unchanged — retrieves from all books.

HANDLING EXISTING DATA:
  If knowledge_chunks table already has rows, the ALTER TABLE will add the
  column with DEFAULT 'equity_ta' — correct for most rows. Options book
  chunks still need to be tagged. Two paths:

  Path A (fast, no re-ingest): run after ALTER TABLE:
  ```sql
  UPDATE knowledge_chunks
  SET book_type = 'options_strategy'
  WHERE source_file ILIKE '%option%spread%'
     OR source_file ILIKE '%option%volatility%';
  ```
  Verify the UPDATE hit the right rows before committing.

  Path B (clean, re-ingest from scratch):
  ```bash
  docker compose exec db psql -U postgres -c "TRUNCATE knowledge_chunks;"
  python tools/knowledge_base/pdf_ingester.py
  ```
  Takes longer but guarantees all chunks have correct book_type from source.

  Use Path A if ingestion is slow. Use Path B if in doubt.

DO NOT change any other retrieval logic.

VERIFY:
```bash
docker compose exec db psql -U postgres -c \
  "SELECT book_type, COUNT(*) FROM knowledge_chunks GROUP BY book_type;"
```
Must show two rows after re-ingesting.

CHANGELOG:
```
## YYYY-MM-DD — Task 4.1: book_type column + retrieval filter
### Modified
- docker/knowledge_chunks.sql: book_type column + index
- tools/knowledge_base/pdf_ingester.py: tags book type on ingest
- tools/knowledge_base/retriever.py: optional book_type filter param
```

---

## Task 4.2 — Upgrade strategy_gen.py: JSON output + equity filter

READS FIRST:
- tools/knowledge_base/strategy_gen.py (FULL FILE)
- tools/knowledge_base/retriever.py (after Task 4.1)

GOAL:
Two changes to strategy_gen.py only:
1. Pass book_type='equity_ta' to retrieve_relevant_chunks()
2. Replace _SYSTEM_PROMPT with one that returns JSON

New system prompt instructs Claude to return ONLY this JSON:
```json
{
  "strategies": [{
    "name": "string",
    "conditions_status": "MET | PARTIAL | NOT MET",
    "conditions_detail": "string — explain which conditions are met and why",
    "conviction": "HIGH | MEDIUM | LOW",
    "sources": [{"book": "string", "page": 0, "rule": "string"}],
    "confirmation_signals": ["string — what else to look for before entering"],
    "invalidation_signals": ["string — what would make this setup fail"]
  }],
  "best_opportunity": {
    "strategy_name": "string",
    "rationale": "string",
    "conviction": "HIGH | MEDIUM | LOW"
  },
  "signals_to_watch": ["string"]
}
```

Note: no entry_zone, stop_loss, or target price fields. Those are computed
by the scanner (ADR-005: RAG is explainer not decision-maker). The scanner
already produces entry/stop/target in RiskLevels. RAG explains WHY the setup
is valid and what the books say about it — it does not reproduce the math.

DO NOT touch retriever.py beyond Task 4.1 change.

VERIFY:
```bash
python -m tools.knowledge_base.run query --ticker SPY
```
Must return valid JSON dict. Must not contain options book references.

CHANGELOG:
```
## YYYY-MM-DD — Task 4.2: strategy_gen.py returns JSON + equity filter
### Modified
- tools/knowledge_base/strategy_gen.py: JSON prompt + equity_ta filter
```

---

## Task 4.3 — Upgrade morning briefing (digest.py)

READS FIRST:
- app/services/digest.py (FULL FILE — understand how existing functions
  get their DB connection. Follow the SAME pattern exactly.)
- app/routers/strategies.py (FULL FILE — find the exact names of the
  watchlist and settings helper functions before writing any imports.
  They may be _get_user_watchlist/_get_user_settings or named differently
  if inlined. Confirm before importing.)
- app/services/market_data.py (understand data shape)

GOAL:
Add generate_strategy_briefing(user_id: int) -> str to digest.py.
Uses the same parallel scan pattern built in Phase 3 Task 3.4.
Open trade status is NOT included here — that is added in Phase 5.

IMPORTANT — DB connection in cron context:
digest.py is called from a cron job, NOT from a FastAPI request.
FastAPI's Depends(get_db) is not available here.
Look at how existing digest.py functions get their DB connection.
generate_strategy_briefing must follow the SAME pattern — do not
add a db parameter to the function signature.

IMPORTANT — helper function names:
Read app/routers/strategies.py before writing any import statements.
Confirm the exact names of the watchlist and settings helper functions.
If they are module-level functions, import them.
If they are inlined inside route functions, extract the DB query logic
directly in digest.py following the same SQL pattern.

MODIFY: app/services/digest.py

Add function: generate_strategy_briefing(user_id: int) -> str

```python
def generate_strategy_briefing(user_id: int) -> str:
    """
    Scan user's watchlist for ENTRY setups. Returns formatted plain text.
    Uses parallel ThreadPoolExecutor — same pattern as /scan/watchlist endpoint.
    Returns empty string if watchlist is empty or no ENTRY setups found.
    DB connection follows same pattern as rest of digest.py.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from backtesting.scanner import StrategyScanner
    # Import helper functions from strategies.py if they are module-level.
    # If not, replicate the DB query following digest.py's existing DB pattern.
    # READ strategies.py FIRST to determine which applies.

    # Get watchlist and settings using digest.py's DB pattern (not FastAPI Depends)
    # ...fetch tickers and account_size/risk_pct...

    if not tickers:
        return ""

    scanner = StrategyScanner()
    all_results = []

    def _scan_one(ticker):
        try:
            results = scanner.scan(ticker, account_size, risk_pct)
            for r in results:
                r.ticker = ticker
            return results
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=min(len(tickers), 10)) as pool:
        for future in as_completed(pool.submit(_scan_one, t) for t in tickers):
            all_results.extend(future.result())

    entries = [r for r in all_results if r.verdict == "ENTRY"]
    entries.sort(key=lambda r: r.score, reverse=True)

    if not entries:
        return ""

    from datetime import date
    lines = [f"STRATEGY SETUPS — {date.today()}", ""]
    for r in entries:
        lines.append(f"{r.ticker}  {r.name} — Score {r.score}/100")
        if r.risk:
            lines.append(
                f"  Entry: ${r.risk.entry_price:.2f}  "
                f"Stop: ${r.risk.stop_loss:.2f}  "
                f"Target: ${r.risk.target:.2f}  "
                f"R:R: {r.risk.risk_reward:.1f}x"
            )
            if r.risk.position_size:
                lines.append(
                    f"  Shares: {r.risk.position_size} "
                    f"(${account_size:,.0f} account, {risk_pct:.0%} risk)"
                )
        lines.append("")

    return "\n".join(lines)
```

The existing digest generation logic must remain completely unchanged.
This function is additive — called alongside existing logic in the cron job.

DO NOT add open trade status here. That section is added in Phase 5
when the open_trades table exists.

VERIFY:
```python
from app.services.digest import generate_strategy_briefing
# Requires docker stack running
briefing = generate_strategy_briefing(user_id=1)
print(briefing)
print("4.3 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 4.3: Morning briefing upgraded with strategy setups
### Modified
- app/services/digest.py: added generate_strategy_briefing() function
```

---

## Phase 4 complete checklist

- [ ] knowledge_chunks has book_type column with data
- [ ] Both equity_ta and options_strategy rows present in knowledge_chunks
- [ ] retrieve_relevant_chunks() accepts optional book_type filter
- [ ] strategy_gen.py returns dict not string
- [ ] strategy_gen.py JSON schema has no price fields (entry_zone, stop_loss, targets removed)
- [ ] generate_strategy_briefing(user_id, db) uses parallel scan (ThreadPoolExecutor)
- [ ] generate_strategy_briefing imports _get_user_watchlist, _get_user_settings from strategies.py
- [ ] generate_strategy_briefing returns empty string gracefully when no ENTRY setups
- [ ] Open trade status NOT in generate_strategy_briefing (Phase 5 adds it)
- [ ] Existing digest logic unchanged
- [ ] `python -m pytest tests/` still passes
- [ ] `python scripts/smoke_test.py` passes
- [ ] All existing routes return same responses as before