# Phase 6 — Frontend: strategy panels, scanner page, trade tracker

## Before starting

Confirm phase5.md complete checklist is fully checked off.
Verify all backend endpoints work before touching any frontend file:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=changeme" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://localhost:8000/trades/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"ticker":"SPY","strategy_name":"S7_MACDCross","strategy_type":"trend",
       "entry_price":560.0,"stop_loss":551.0,"target":572.0,"shares":10}' \
  | python3 -m json.tool

curl -s http://localhost:8000/trades/ -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool

curl -s -X DELETE http://localhost:8000/trades/1 -H "Authorization: Bearer $TOKEN"

curl -s http://localhost:8000/trades/ -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool
```

All four must succeed. If any fail: fix Phase 5 first.

## Gate to advance to paper trading
- StrategyPanel renders correctly for each strategy type
- ScannerPage loads and displays ranked results from /scan/watchlist
- TradeTrackerPage shows open trades with live R and exit alerts
- AnalysisPage shows strategy panels below SwingSetupPanel
- `cd frontend && npx tsc --noEmit` zero errors
- All existing pages and routes still work

---

## Task 6.1 — Add TypeScript types

READS FIRST:
- frontend/src/types/index.ts (full file — do not duplicate existing types)
- app/routers/strategies.py (read the actual response shapes)
- app/routers/trades.py (read the actual response shapes)
- backtesting/base.py (Condition, RiskLevels, StrategyResult field names)

GOAL:
Add TypeScript interfaces that match the Python response shapes exactly.
Derive field names and optionality directly from the Python dataclasses
and Pydantic models — do not invent names or add fields that do not exist
in the backend response.

Types to add to frontend/src/types/index.ts:
- Condition — mirrors backtesting/base.py Condition dataclass
- RiskLevels — mirrors backtesting/base.py RiskLevels dataclass.
  entry_zone_low, entry_zone_high, atr, position_size are optional
  because not all strategies set them.
- StrategyType union — the four valid strategy type strings
- Verdict union — the three valid verdict strings
- StrategyResult — mirrors StrategyResult dataclass.
  ticker is optional — only present in watchlist scan results.
- OpenTrade — mirrors TradeResponse from app/models.py.
  risk_reward is optional — matches TradeCreate definition.
  current_price, current_r, exit_alert are optional — computed fields.
- UserSettings — mirrors UserSettings from app/models.py

DO NOT modify any existing types.

VERIFY:
```bash
cd frontend && npx tsc --noEmit
```

CHANGELOG entry: types added to frontend/src/types/index.ts

---

## Task 6.2 — Add API call functions

READS FIRST:
- frontend/src/api/client.ts (full file — follow existing patterns exactly)
- frontend/src/types/index.ts (after Task 6.1)
- app/routers/strategies.py (endpoint paths and HTTP methods)
- app/routers/trades.py (endpoint paths and HTTP methods)

GOAL:
Add API functions to client.ts that call the Phase 3 and Phase 5 endpoints.
Follow the exact same pattern as existing functions in client.ts — same
error handling, same auth header approach, same response parsing.

Functions to add:
- fetchStrategies(ticker) — GET /strategies/{ticker}
- scanWatchlist() — GET /strategies/scan/watchlist
- fetchUserSettings() — GET /strategies/settings
- updateUserSettings(settings) — PATCH /strategies/settings
- fetchOpenTrades() — GET /trades/
- logTrade(trade) — POST /trades/. The request body is OpenTrade minus
  the server-computed fields (id, entry_date, current_price, current_r,
  exit_alert). Use the Omit utility type to derive this.
- closeTrade(tradeId) — DELETE /trades/{id}

DO NOT modify any existing API functions.

VERIFY:
```bash
cd frontend && npx tsc --noEmit
```

CHANGELOG entry: API functions added to frontend/src/api/client.ts

---

## Task 6.3 — Build StrategyPanel component

READS FIRST:
- frontend/src/components/SwingSetupPanel.tsx (full file — this is the
  visual and structural template. Match its layout, spacing, and style exactly.)
- frontend/src/types/index.ts (StrategyResult, Condition, RiskLevels)

GOAL:
A single reusable component that renders any StrategyResult.
Color coded by strategy type. Purely presentational — no API calls.

Props: result (StrategyResult) and optional onLogTrade callback.

Color scheme by strategy type — match the existing dark theme in SwingSetupPanel:
- trend: teal
- reversion: purple
- breakout: amber
- rotation: blue

Layout — match SwingSetupPanel structure:
- Header row: strategy name, type badge, verdict badge
- Score bar: 0–100
- Two-column body:
  Left: conditions list. Each row shows pass/fail icon, label, value, required threshold.
  Right: risk levels. Entry zone shown only when both entry_zone_low and
  entry_zone_high are present. ATR shown only when present. Position size
  shown only when present. All optional fields must be null-guarded.
- Log Trade button: shown only when verdict is ENTRY and onLogTrade is provided.

Verdict badge colors: ENTRY green, WATCH amber, NO_TRADE gray.

DO NOT build any modal, form, or API call in this task.

VERIFY:
```bash
cd frontend && npx tsc --noEmit
```

CHANGELOG entry: StrategyPanel.tsx created

---

## Task 6.4 — Add strategy panels to AnalysisPage

READS FIRST:
- frontend/src/pages/AnalysisPage.tsx (full file — understand the existing
  fetch pattern completely before adding anything)
- frontend/src/components/SwingSetupPanel.tsx (understand where it sits)
- frontend/src/components/StrategyPanel.tsx (after Task 6.3)
- frontend/src/api/client.ts (fetchStrategies)

GOAL:
When a ticker is analysed, show strategy results below SwingSetupPanel.

Add to AnalysisPage.tsx:
- State for strategies list, initialised to empty array
- Fetch: call fetchStrategies(ticker) in the SAME effect or hook call as
  the existing analysis fetch — same dependency array, fires together.
  Do not create a separate effect. A separate effect on the same ticker
  dependency causes a race where strategies from one ticker show alongside
  analysis from another.
- Render StrategyPanel for each result below SwingSetupPanel, sorted by
  score descending with ENTRY verdicts first
- Show loading skeleton while fetching (use the existing loading component)
- If fetchStrategies fails, show nothing — do not break the analysis panel

DO NOT remove or modify SwingSetupPanel.
DO NOT change any existing state or fetch logic.
Additive only.

VERIFY:
Open http://localhost:5173, search SPY.
Strategy panels appear below SwingSetupPanel.

CHANGELOG entry: strategy panels added to AnalysisPage.tsx

---

## Task 6.5 — Build ScannerPage

READS FIRST:
- frontend/src/pages/WatchlistPage.tsx (layout and style reference)
- frontend/src/App.tsx (understand routing and nav patterns)
- frontend/src/api/client.ts (scanWatchlist)
- frontend/src/types/index.ts (StrategyResult)

GOAL:
New page at /scanner. Fetches /scan/watchlist on load. Shows ranked list.
This is the primary morning workflow — compact list view, not full panels.

Page structure:
- Header: "Morning Scan", last run time (tracked client-side when fetch
  resolves — not from the API response which has no timestamp), Refresh button
- For each result: ticker, strategy type colour chip, strategy name, score,
  verdict badge, entry/stop/target/R:R/shares on one line
- Clicking a result navigates to /analysis/{ticker}
- Empty state when watchlist has no setups firing
- Loading skeleton while fetching
- The /scan/watchlist call can take 5–10 seconds — the loading state must
  be visible and the UI must not appear frozen

Add to App.tsx: /scanner route and nav link following existing patterns.

DO NOT use the full StrategyPanel here — compact list rows only.
DO NOT modify any existing page.

VERIFY:
Navigate to /scanner. Page loads with skeleton then results or empty state.
Clicking a row navigates to /analysis/{ticker}.

CHANGELOG entry: ScannerPage.tsx created, /scanner route added to App.tsx

---

## Task 6.6 — Build TradeTrackerPage

READS FIRST:
- frontend/src/pages/ScannerPage.tsx (layout conventions from Task 6.5)
- frontend/src/App.tsx (routing and nav patterns)
- frontend/src/api/client.ts (fetchOpenTrades, logTrade, closeTrade)
- frontend/src/types/index.ts (OpenTrade)

GOAL:
New page at /trades. Shows open trades with live R and exit alerts.
Log trade form below the table.

Open trades table columns:
Ticker, Strategy, Entry, Stop, Target, Shares, R:R, Current R, Alert, Action.
Current R: green when positive, red when negative.
Exit alert: amber warning icon for APPROACHING_STOP, green check for AT_TARGET.

Log trade form:
- Ticker input (free text)
- Strategy dropdown — static list, do not call fetchStrategies.
  The six validated strategy names are known at build time: S1_TrendPullback,
  S2_RSIMeanReversion, S3_BBSqueeze, S7_MACDCross, S8_StochasticCross,
  S9_EMACross. When a strategy is selected, auto-populate strategy_type.
- Entry, Stop, Target (price inputs), Shares (integer input)
- Log Trade button

After closing a trade: call fetchOpenTrades() to re-fetch from the server.
Do not filter local state optimistically — re-fetch is the source of truth.

Add to App.tsx: /trades route and nav link.

DO NOT build charts. Table only.
DO NOT allow editing trades — close only.

VERIFY:
Navigate to /trades. Empty state shown.
Log a test trade. It appears in the table with live R.
Close it. Table returns to empty state.

CHANGELOG entry: TradeTrackerPage.tsx created, /trades route added to App.tsx

---

## Phase 6 complete checklist

- [ ] `cd frontend && npx tsc --noEmit` — zero type errors
- [ ] StrategyPanel renders for all 4 strategy type colours
- [ ] Optional risk fields (entry_zone, atr, position_size) null-guarded in panel
- [ ] AnalysisPage shows strategy panels below SwingSetupPanel
- [ ] Strategy fetch fires in same effect as existing analysis fetch
- [ ] ScannerPage loads and shows ranked compact results
- [ ] ScannerPage shows loading state during /scan/watchlist call
- [ ] Clicking scanner result navigates to AnalysisPage
- [ ] TradeTrackerPage shows open trades with live R and alerts
- [ ] Log trade form works with static strategy dropdown
- [ ] Close trade re-fetches from server
- [ ] SwingSetupPanel untouched
- [ ] All existing pages and routes still work
- [ ] `./scripts/build.sh test` passes