# Phase 4 — RAG upgrade + morning briefing

## Before starting
Confirm phase3.md complete checklist is fully checked off.
GET /strategies/scan/watchlist must be working before this phase.

## Gate to advance to Phase 5
- strategy_gen.py returns JSON not markdown
- Morning briefing fires on cron and includes scanner results
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
    "conditions_detail": "string",
    "entry_zone": {"low": 0.0, "high": 0.0},
    "stop_loss": 0.0,
    "targets": {"tp1": 0.0, "tp2": 0.0},
    "risk_reward": 0.0,
    "conviction": "HIGH | MEDIUM | LOW",
    "sources": [{"book": "string", "page": 0, "rule": "string"}],
    "confirmation_signals": ["string"],
    "invalidation_signals": ["string"]
  }],
  "best_opportunity": {
    "strategy_name": "string",
    "rationale": "string",
    "conviction": "HIGH | MEDIUM | LOW"
  },
  "signals_to_watch": ["string"]
}
```

Update generate_strategies() to return dict, not string.
Parse the JSON response. Return dict.

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
- app/services/digest.py (FULL FILE)
- app/routers/strategies.py (scan/watchlist endpoint from phase 3)
- app/services/market_data.py (understand data shape)

GOAL:
Upgrade digest.py to include strategy scanner results in the briefing.
The briefing now has three sections:
  1. Strategy setups firing today (from scanner)
  2. Open trade status (from open_trades table — will be empty until phase 5)
  3. Market context (existing narrative — unchanged)

MODIFY: app/services/digest.py

Add function: generate_strategy_briefing(user_id) -> str
  1. Fetch user's watchlist
  2. Fetch user's account_size and risk_pct
  3. Run StrategyScanner.scan() on each watchlist ticker
  4. Filter to ENTRY verdicts only for the briefing
  5. Format as plain text:
     "STRATEGY SETUPS — [date]\n"
     For each ENTRY result:
       "[TICKER] [strategy name] — Score [X]/100\n"
       "  Entry: $X.XX  Stop: $X.XX  Target: $X.XX  R:R: X.Xx\n"
       "  Shares: X (based on $X account, X% risk)\n"

Do NOT call Claude or RAG in this function. Plain text only.
Claude narrative is separate and already exists in digest.py.

The existing digest generation logic must remain unchanged.
This function is additive — called alongside existing logic.

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
- [ ] retrieve_relevant_chunks() accepts optional book_type filter
- [ ] strategy_gen.py returns dict not string
- [ ] generate_strategy_briefing() produces plain text with ENTRY setups
- [ ] `python -m pytest tests/` still passes
- [ ] `python scripts/smoke_test.py` passes
- [ ] All existing routes return same responses as before
