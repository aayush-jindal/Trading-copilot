# Phase 6 — Frontend: strategy panels, scanner page, trade tracker

## Before starting
Confirm phase5.md complete checklist is fully checked off.
All backend endpoints must be working before touching the frontend.

## Gate to advance to paper trading
- StrategyPanel renders correctly for each strategy type
- ScannerPage loads and displays ranked results from /scan/watchlist
- TradeTrackerPage shows open trades with live R and exit alerts
- AnalysisPage shows strategy panels below SwingSetupPanel
- `./scripts/build.sh test` all original tests passing

---

## Task 6.1 — Add TypeScript types for strategy responses

READS FIRST:
- frontend/src/types/index.ts (full file — do not duplicate existing types)
- app/routers/strategies.py (response shapes from phase 3)
- app/routers/trades.py (TradeResponse shape from phase 5)

GOAL:
Add types only. No components yet.

MODIFY: frontend/src/types/index.ts

Add:
```typescript
export interface Condition {
  label: string;
  passed: boolean;
  value: string;
  required: string;
}

export interface RiskLevels {
  entry_price: number;
  stop_loss: number;
  target: number;
  risk_reward: number;
  atr?: number;
  entry_zone_low?: number;
  entry_zone_high?: number;
  position_size?: number;
}

export type StrategyType = 'trend' | 'reversion' | 'breakout' | 'rotation';
export type Verdict = 'ENTRY' | 'WATCH' | 'NO_TRADE';

export interface StrategyResult {
  name: string;
  type: StrategyType;
  verdict: Verdict;
  score: number;
  conditions: Condition[];
  risk: RiskLevels | null;
  ticker?: string;   // present in watchlist scan results
}

export interface OpenTrade {
  id: number;
  ticker: string;
  strategy_name: string;
  strategy_type: StrategyType;
  entry_price: number;
  stop_loss: number;
  target: number;
  shares: number;
  entry_date: string;
  current_price?: number;
  current_r?: number;
  exit_alert?: 'APPROACHING_STOP' | 'AT_TARGET' | null;
}

export interface UserSettings {
  account_size: number;
  risk_pct: number;
}
```

DO NOT modify any existing types.

VERIFY:
```bash
cd frontend && npx tsc --noEmit
```
Must pass with zero errors.

CHANGELOG:
```
## YYYY-MM-DD — Task 6.1: Strategy + trade TypeScript types
### Modified
- frontend/src/types/index.ts: added Condition, RiskLevels, StrategyResult,
  OpenTrade, UserSettings, StrategyType, Verdict
```

---

## Task 6.2 — Add API calls

READS FIRST:
- frontend/src/api/client.ts (full file — use existing patterns exactly)
- frontend/src/types/index.ts (after Task 6.1)

GOAL:
Add API call functions only. No components.

MODIFY: frontend/src/api/client.ts

Add these functions following the exact pattern of existing functions:
```typescript
// Strategy scanner
export async function fetchStrategies(ticker: string): Promise<StrategyResult[]>
export async function scanWatchlist(): Promise<StrategyResult[]>

// User settings
export async function fetchUserSettings(): Promise<UserSettings>
export async function updateUserSettings(settings: UserSettings): Promise<UserSettings>

// Trade tracker
export async function fetchOpenTrades(): Promise<OpenTrade[]>
export async function logTrade(trade: Omit<OpenTrade, 'id' | 'entry_date' | 'current_price' | 'current_r' | 'exit_alert'>): Promise<OpenTrade>
export async function closeTrade(tradeId: number): Promise<void>
```

DO NOT modify any existing API functions.

VERIFY:
```bash
cd frontend && npx tsc --noEmit
```
Zero errors.

CHANGELOG:
```
## YYYY-MM-DD — Task 6.2: API call functions added
### Modified
- frontend/src/api/client.ts: fetchStrategies, scanWatchlist,
  fetchUserSettings, updateUserSettings, fetchOpenTrades, logTrade, closeTrade
```

---

## Task 6.3 — Build StrategyPanel component

READS FIRST:
- frontend/src/components/SwingSetupPanel.tsx (FULL FILE — use as template)
- frontend/src/types/index.ts (StrategyResult, Condition, RiskLevels)

GOAL:
One reusable component that renders any strategy result.
Color coded by strategy type. Same layout as SwingSetupPanel.

CREATE: frontend/src/components/StrategyPanel.tsx

Props: `{ result: StrategyResult; onLogTrade?: () => void }`

Color map (use Tailwind classes matching existing dark theme):
```
trend:     teal border/badge   — border-teal-500, bg-teal-900/20
reversion: purple border/badge — border-purple-500, bg-purple-900/20
breakout:  amber border/badge  — border-amber-500, bg-amber-900/20
rotation:  blue border/badge   — border-blue-500, bg-blue-900/20
```

Layout (match SwingSetupPanel structure exactly):
```
[Header: strategy name + type badge]          [verdict badge]
[Score bar: 0-100 with color]

CONDITIONS                    (left col)
  ✓/✗ label          value    required
  ... one row per condition

RISK LEVELS                   (right col)
  Entry zone          $X.XX – $X.XX
  Stop loss           $X.XX  (red)
  Target              $X.XX  (green)
  R:R                 X.Xx
  ATR 14              $X.XX
  Position size       X shares

[Log Trade button — only shown when verdict = ENTRY and onLogTrade provided]
```

Verdict badge colors:
  ENTRY   → green
  WATCH   → amber
  NO_TRADE → gray (should never render — scanner filters these out)

DO NOT build any modal or form in this task.
DO NOT call any API from this component — it is purely presentational.

VERIFY:
```bash
cd frontend && npx tsc --noEmit
```
Zero type errors. Component exists and imports cleanly.

CHANGELOG:
```
## YYYY-MM-DD — Task 6.3: StrategyPanel component
### Added
- frontend/src/components/StrategyPanel.tsx
```

---

## Task 6.4 — Add strategy panels to AnalysisPage

READS FIRST:
- frontend/src/pages/AnalysisPage.tsx (FULL FILE)
- frontend/src/components/SwingSetupPanel.tsx (where it sits in the layout)
- frontend/src/components/StrategyPanel.tsx (after Task 6.3)
- frontend/src/api/client.ts (fetchStrategies)

GOAL:
When a ticker is analysed, fetch strategy results and render them
below SwingSetupPanel. Ranked by score, ENTRY first.

MODIFY: frontend/src/pages/AnalysisPage.tsx

Add:
  - State: `const [strategies, setStrategies] = useState<StrategyResult[]>([])`
  - Fetch: call fetchStrategies(ticker) alongside existing analysis fetch
  - Render: map strategies to StrategyPanel components below SwingSetupPanel
  - Loading state: show skeleton while fetching (use existing LoadingSkeleton)

DO NOT remove or modify SwingSetupPanel.
DO NOT change any existing state or fetch logic.
Only add the new state, fetch, and render — nothing else.

VERIFY:
Open http://localhost:5173, search SPY.
Strategy panels must appear below SwingSetupPanel.
Each panel shows conditions, risk levels, verdict.

CHANGELOG:
```
## YYYY-MM-DD — Task 6.4: Strategy panels added to AnalysisPage
### Modified
- frontend/src/pages/AnalysisPage.tsx: strategy panels below SwingSetupPanel
```

---

## Task 6.5 — Build ScannerPage

READS FIRST:
- frontend/src/pages/WatchlistPage.tsx (use as layout reference)
- frontend/src/components/StrategyPanel.tsx (after Task 6.3)
- frontend/src/api/client.ts (scanWatchlist)
- frontend/src/types/index.ts (StrategyResult)

GOAL:
New page. Calls /scan/watchlist on load. Shows ranked list.
Click on a result navigates to AnalysisPage for that ticker.

CREATE: frontend/src/pages/ScannerPage.tsx

Layout:
```
[Page header: "Morning Scan" + last run time + Refresh button]

[For each result in ranked order:]
  [Ticker badge] [Strategy type color chip] [Strategy name]
  [Score: XX/100] [Verdict badge]
  [Entry $X.XX  Stop $X.XX  Target $X.XX  R:R X.Xx  Shares X]
  [Click row → navigate to /analysis/{ticker}]

[Empty state if no results: "No setups found in watchlist"]
[Loading skeleton while fetching]
```

This is a compact list view — NOT the full StrategyPanel.
Full detail is on AnalysisPage when you click through.

MODIFY: frontend/src/App.tsx
  Add route: /scanner → ScannerPage
  Add nav link to Scanner page alongside existing nav items.

DO NOT modify WatchlistPage, AnalysisPage, or any other existing page.

VERIFY:
Navigate to /scanner. Page loads. Shows results (or empty state).
Clicking a result navigates to /analysis/{ticker}.

CHANGELOG:
```
## YYYY-MM-DD — Task 6.5: ScannerPage
### Added
- frontend/src/pages/ScannerPage.tsx
### Modified
- frontend/src/App.tsx: /scanner route + nav link
```

---

## Task 6.6 — Build TradeTrackerPage

READS FIRST:
- frontend/src/pages/ScannerPage.tsx (use layout conventions)
- frontend/src/api/client.ts (fetchOpenTrades, closeTrade, logTrade)
- frontend/src/types/index.ts (OpenTrade)
- frontend/src/components/StrategyPanel.tsx (Log Trade button pattern)

GOAL:
Page showing open trades with live R and exit alerts.
Log trade form. Close trade button.

CREATE: frontend/src/pages/TradeTrackerPage.tsx

Sections:

1. Open trades table:
```
Ticker | Strategy | Entry | Stop | Target | Shares | R:R | Current R | Alert | Action
AAPL   | S2 RSI   | $189  | $175 | $201   | 22     | 1.4x| +0.84R ✓  |       | Close
JPM    | S1 Trend | $224  | $218 | $231   | 18     | 1.2x| -0.31R    | ⚠ Stop| Close
```
Current R: green if > 0, red if < 0.
Exit alert: amber ⚠ if APPROACHING_STOP, green ✓ if AT_TARGET.

2. Log trade form (below table):
```
[Ticker input] [Strategy dropdown — validated strategies only]
[Entry $] [Stop $] [Target $] [Shares]
[Log Trade button]
```
Strategy dropdown populated from fetchStrategies — only ENTRY verdicts.
Or allow manual entry with free text strategy name.

MODIFY: frontend/src/App.tsx
  Add route: /trades → TradeTrackerPage
  Add nav link.

DO NOT build any chart or visualisation. Table only.
DO NOT add editing of existing trades — close only.

VERIFY:
Navigate to /trades. Table shows open trades (or empty state).
Log a test trade. It appears in the table with live R.
Close button removes it from the table.

CHANGELOG:
```
## YYYY-MM-DD — Task 6.6: TradeTrackerPage
### Added
- frontend/src/pages/TradeTrackerPage.tsx
### Modified
- frontend/src/App.tsx: /trades route + nav link
```

---

## Phase 6 complete checklist

- [ ] StrategyPanel renders correctly for all 4 strategy types
- [ ] AnalysisPage shows strategy panels below SwingSetupPanel
- [ ] ScannerPage loads /scan/watchlist and shows ranked list
- [ ] Clicking scanner result navigates to AnalysisPage
- [ ] TradeTrackerPage shows open trades with live R and alerts
- [ ] Log trade form works
- [ ] Close trade removes from open trades
- [ ] `./scripts/build.sh test` — all original tests passing
- [ ] `cd frontend && npx tsc --noEmit` — zero type errors
- [ ] SwingSetupPanel untouched
- [ ] All existing pages and routes still work
