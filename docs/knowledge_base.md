# How the RAG Knowledge Base Works

## The Big Picture

The system has two phases: **ingestion** (one-time setup) and **querying** (every time you want strategies).

```
INGESTION (one-time):
  PDFs → extract text → chunk → embed locally → store in PostgreSQL

QUERYING (per ticker):
  Live signals → build query → embed → vector search → top-8 passages → Claude → strategies
```

---

## Phase 1: Ingestion

**`tools/knowledge_base/pdf_ingester.py`**

```
your-book.pdf
    │
    ▼
PyMuPDF extracts raw text page by page
    │
    ▼
Sliding window chunker splits into ~1,500-char chunks (200-char overlap)
    │
    ▼
sentence-transformers (all-MiniLM-L6-v2) converts each chunk to a 384-dim vector
    │
    ▼
PostgreSQL / pgvector stores: source_file, page_num, chunk_text, embedding[384]
```

**Why chunking with overlap?**
A strategy description in a book might span a page boundary. The 200-char overlap means no concept gets cut off cleanly at a chunk boundary.

**Why is it idempotent?**
The DB has a `UNIQUE(source_file, chunk_idx)` constraint. Re-running `ingest` skips files already in the DB — safe to run again when you add new books.

---

## Phase 2: Querying

### Step 1 — Fetch live signals
```python
get_live_signals("AAPL")
# returns: RSI=42, trend=BULLISH, bb_squeeze=True, swing=ENTRY, ...
```

### Step 2 — Translate signals → natural language query
**`tools/knowledge_base/retriever.py: build_signal_query()`**

The signals dict is converted into a keyword-rich string that describes the current market condition in language a trading book would use:

```
"uptrend bullish trend following price above moving averages
 pullback in uptrend entry signal swing trade setup near support
 RSI oversold bounce mean reversion buying opportunity
 Bollinger Band squeeze volatility contraction breakout setup"
```

This query is dynamically built from actual signal values — not hardcoded. Different tickers, different conditions → different queries.

### Step 3 — Embed the query + cosine similarity search
```sql
SELECT source_file, page_num, content,
       1 - (embedding <=> '[0.12, -0.03, ...]'::vector) AS similarity
FROM knowledge_chunks
ORDER BY embedding <=> '[0.12, -0.03, ...]'::vector
LIMIT 8
```

pgvector finds the 8 book passages whose embedding is geometrically closest to the query embedding — meaning they're about the same market concept.

### Step 4 — Claude synthesizes everything
**`tools/knowledge_base/strategy_gen.py`**

Claude receives two blocks in a single prompt:

```
TICKER: AAPL | PRICE: $213.45

=== LIVE MARKET SIGNALS ===
TREND: BULLISH | vs SMA50=above | vs SMA200=above | golden_cross=True ...
MOMENTUM: RSI=42 (MODERATE_BULLISH) | MACD crossover=bullish_crossover ...
...

=== KNOWLEDGE BASE (retrieved passages) ===
[1] Source: murphy-technical-analysis.pdf, p.247  (similarity: 0.891)
"When price pulls back to the 50-day moving average in an uptrend and RSI..."
---
[2] Source: elder-trading-for-a-living.pdf, p.103  (similarity: 0.876)
"The MACD histogram turning up from below zero while price holds above..."
---
...
```

Claude is instructed to output:
- **Applicable Strategies** — for each book passage: MET / PARTIAL / NOT MET, with exact entry/stop/target from the live numbers
- **Best Current Opportunity** — single strongest setup with full reasoning
- **Signals to Watch** — what to monitor for the thesis to develop or fail

---

## Why This Is Better Than Just Asking Claude

Without the knowledge base, Claude generates strategies from its general training — vague and not grounded in specific techniques.

With RAG, every strategy Claude outputs is **traceable to a specific page of a specific book** you chose. The recommendations are:
- Grounded in proven techniques from your curated library
- Applied to the exact current numbers (RSI=42, not "RSI is moderate")
- Source-cited (you can look up the passage yourself)

---

## Option A — API + Frontend Integration

```
[Frontend] "Book Strategies" tab
    │  HTTP GET /analysis/knowledge-strategies/AAPL
    ▼
[FastAPI router: app/routers/analysis.py]
    │  calls generate_strategies("AAPL")
    ▼
[tools/knowledge_base/strategy_gen.py]  ← already built
    │  returns formatted markdown string
    ▼
[Frontend] renders the markdown in a panel
```

One new endpoint + one new UI panel. The backend logic is already complete.

---

## CLI Usage

```bash
# Index all PDFs in resources/
docker-compose -f docker/docker-compose.yml exec api python -m tools.knowledge_base.run ingest

# Show indexed files and chunk counts
docker-compose -f docker/docker-compose.yml exec api python -m tools.knowledge_base.run status

# Generate book-grounded strategies for a ticker
docker-compose -f docker/docker-compose.yml exec api python -m tools.knowledge_base.run query --ticker AAPL
```

---

## Recommended Books (5–10 ideal)

| Pillar | Book |
|--------|------|
| Trend / moving averages | *Technical Analysis of the Financial Markets* — Murphy |
| Candlestick patterns | *Japanese Candlestick Charting Techniques* — Nison |
| Volume / accumulation | *How to Trade in Stocks* — Livermore |
| Swing trading setups | *The Art and Science of Technical Analysis* — Grimes |
| Momentum / RSI/MACD | *Trading for a Living* — Elder |
| Support / resistance | *Trading Price Action* — Brooks |
