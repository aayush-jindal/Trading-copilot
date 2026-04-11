# Frontend — Chain Scanner UI

## Goal

Replace the broken Options tab with a working UI that calls the chain
scanner endpoint (`GET /options/chain-scan`). Show ranked signals with
IV regime badges, conviction scores, edge metrics, recommended strategies,
and optionally priced strategy details.

Also fix the existing `POST /options/scan` 500 error so it doesn't crash
if someone navigates to `/options` directly.

---

## Current state

**What's broken:**
- Options tab in AnalysisPage calls `POST /options/scan` via `scanOptions()`
- This hits the bias-detector pipeline which 500s with a Pydantic
  `ValidationError` (`knowledge_strategies` typed as `Optional[str]`
  but receives a dict)
- The standalone `/options` route uses the same `OptionsContent` component

**What exists:**
- `OptionsPage.tsx` — renders `OptionsContent` component
- `OptionsContent` — input field + scan button, calls `scanOptions()`,
  renders `TickerBlock` → `OpportunityCard` for each result
- `AnalysisPage.tsx` — has a tab bar with "Analysis" and "Options Scanner"
  tabs; the Options tab renders `<OptionsContent />`
- `client.ts` — `scanOptions()` function calls `POST /api/options/scan`
- `types/index.ts` — `OptionsLeg`, `OptionsOpportunity`, `OptionsTickerResult`,
  `OptionsScanResponse` interfaces

**New endpoint (built in Phases A-C):**
```
GET /options/chain-scan?tickers=AAPL,MSFT&top=20&price=true
```
Returns:
```json
{
  "signals": [{
    "ticker": "AAPL",
    "strike": 250.0,
    "expiry": "2026-05-15",
    "option_type": "put",
    "dte": 35,
    "spot": 255.92,
    "bid": 4.10, "ask": 4.30, "mid": 4.20,
    "open_interest": 3200,
    "bid_ask_spread_pct": 4.76,
    "chain_iv": 0.2850,
    "iv_rank": 78.5,
    "iv_percentile": 82.3,
    "iv_regime": "ELEVATED",
    "garch_vol": 0.2340,
    "theo_price": 3.45,
    "edge_pct": -17.86,
    "direction": "SELL",
    "delta": -0.3012,
    "gamma": 0.0198,
    "theta": -0.0412,
    "vega": 0.3872,
    "conviction": 72.5,
    "recommended_strategy": {
      "strategy": "short_put_spread",
      "label": "Short Put Spread",
      "rationale": "IV rank 78% — premium is rich...",
      "legs": [...],
      "suggested_dte": 35,
      "risk_profile": "defined",
      "edge_source": "iv_overpriced"
    },
    "priced_strategy": {
      "strategy": "short_put_spread",
      "is_credit": true,
      "legs": [...],
      "entry": 1.82,
      "exit_target": 0.91,
      "option_stop": 3.64,
      "max_profit": 1.82,
      "max_loss": 3.18,
      "net_delta": -0.103,
      "net_theta": 0.013,
      "prob_profit": 68.2,
      "risk_reward": "1:1.75"
    }
  }],
  "total": 47,
  "tickers_scanned": 3
}
```

---

## Task sequence

### Task 1: Fix the existing 500 error

**Backend fix** (one line in `app/routers/options.py`):

In the `TickerResult` model, change:
```python
knowledge_strategies: Optional[str]       = None
```
to:
```python
knowledge_strategies: Optional[Any]       = None
```

`Any` is already imported at the top of the file.

**Frontend type fix** (`frontend/src/types/index.ts`):

Change:
```typescript
knowledge_strategies?: string | null
```
to:
```typescript
knowledge_strategies?: unknown
```

**Verify:** `POST /options/scan` with a ticker no longer 500s.

### Task 2: Add chain scanner types

Add to `frontend/src/types/index.ts`:

```typescript
// ── Chain scanner (Phase A-C) ─────────────────────────────────────────────

export interface ChainSignalLeg {
  action: 'buy' | 'sell'
  option_type: 'call' | 'put'
  strike: number
  iv: number
  price: number
  delta: number
  theta: number
}

export interface StrategyRecommendation {
  strategy: string
  label: string
  rationale: string
  legs: { action: string; option_type: string; strike_method: string }[]
  suggested_dte: number
  risk_profile: 'defined' | 'undefined'
  edge_source: string
}

export interface PricedStrategy {
  strategy: string
  is_credit: boolean
  legs: ChainSignalLeg[]
  spread_width?: number | null
  entry: number
  exit_target: number
  exit_pct: number
  option_stop: number
  max_profit: number | null
  max_loss: number | null
  net_delta: number
  net_gamma: number
  net_theta: number
  net_vega: number
  prob_profit: number
  expected_payoff: number
  risk_reward: string
}

export interface ChainSignal {
  ticker: string
  strike: number
  expiry: string
  option_type: 'call' | 'put'
  dte: number
  spot: number
  bid: number
  ask: number
  mid: number
  open_interest: number
  bid_ask_spread_pct: number
  chain_iv: number
  iv_rank: number
  iv_percentile: number
  iv_regime: 'LOW' | 'NORMAL' | 'ELEVATED' | 'HIGH'
  garch_vol: number
  theo_price: number
  edge_pct: number
  direction: 'BUY' | 'SELL'
  delta: number
  gamma: number
  theta: number
  vega: number
  conviction: number
  recommended_strategy?: StrategyRecommendation | null
  priced_strategy?: PricedStrategy | null
}

export interface ChainScanResponse {
  signals: ChainSignal[]
  total: number
  tickers_scanned: number
}
```

### Task 3: Add API client function

Add to `frontend/src/api/client.ts`:

```typescript
// ── Chain scanner ─────────────────────────────────────────────────────────

export async function chainScan(
  tickers: string[],
  options: { top?: number; price?: boolean } = {}
): Promise<ChainScanResponse> {
  const params = new URLSearchParams()
  params.set('tickers', tickers.join(','))
  if (options.top) params.set('top', String(options.top))
  if (options.price) params.set('price', 'true')

  const res = await apiFetch(`/api/options/chain-scan?${params}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(
      (detail as { detail?: string })?.detail ?? `Chain scan failed (${res.status})`
    )
  }
  return res.json()
}
```

Import `ChainScanResponse` from types at the top.

### Task 4: Create ChainScannerPanel component

Create `frontend/src/components/ChainScannerPanel.tsx`.

This is the main UI component. It should:

1. **Input** — Text field for tickers (comma-separated) with a "Scan" button.
   Also a "Use Watchlist" button that calls scan with no tickers param
   (defaults to user's watchlist). Toggle for "Price strategies" (maps to
   `?price=true`).

2. **Signal cards** — Each signal rendered as a card showing:
   - **Header row:** ticker, strike, expiry, DTE, option_type (call/put chip)
   - **IV context row:** IV regime badge (color-coded: LOW=blue, NORMAL=gray,
     ELEVATED=yellow, HIGH=red), IV rank bar or number, IV percentile
   - **Edge row:** edge_pct with color (green if BUY, red if SELL),
     direction badge, conviction score (0-100 with color gradient)
   - **Greeks row:** delta, gamma, theta, vega in monospace
   - **Recommended strategy** (if present): strategy label, rationale text,
     edge_source badge
   - **Priced strategy** (if present and `price=true`): expandable section
     showing legs table, entry/exit/stop, max profit/loss, prob_profit,
     risk_reward — same layout as the existing `OpportunityCard`

3. **Summary bar** — "47 signals from 3 tickers · showing top 20"

4. **Sorting** — Default sort by conviction descending. Optional sort
   buttons: by edge%, by IV rank, by conviction.

**UI style:** Match existing dark theme (bg-black, glass effects,
border-white/10, text-gray-400/300/500, font-mono for numbers).
Follow the patterns in `ScannerPage.tsx` and `OptionsPage.tsx`.

**Color scheme for IV regime badges:**
- LOW: `bg-blue-500/15 text-blue-300 border-blue-500/30`
- NORMAL: `bg-white/5 text-gray-400 border-white/10`
- ELEVATED: `bg-yellow-500/15 text-yellow-300 border-yellow-500/30`
- HIGH: `bg-red-500/15 text-red-300 border-red-500/30`

**Color for direction badges:**
- BUY: `bg-green-500/15 text-green-400 border-green-500/30`
- SELL: `bg-orange-500/15 text-orange-400 border-orange-500/30`

**Conviction score display:**
- 0-30: gray
- 30-60: yellow
- 60-80: green
- 80+: bright green with subtle glow

### Task 5: Wire into AnalysisPage tabs

In `frontend/src/pages/AnalysisPage.tsx`:

1. Add a third tab: `'analysis' | 'options' | 'chain'`
   Tab labels: "Analysis", "Options", "Chain Scanner"

2. Import ChainScannerPanel and render it when `activeTab === 'chain'`

3. Keep the existing "Options Scanner" tab as-is (it will work once
   the 500 fix from Task 1 is deployed).

```typescript
// Tab bar update:
{(['analysis', 'options', 'chain'] as const).map((tab) => (
  <button key={tab} onClick={() => setActiveTab(tab)} ...>
    {tab === 'analysis' ? 'Analysis'
     : tab === 'options' ? 'Options'
     : 'Chain Scanner'}
  </button>
))}

// Tab content:
{activeTab === 'chain' && <ChainScannerPanel />}
{activeTab === 'options' && <OptionsContent />}
{activeTab === 'analysis' && <> ... existing ... </>}
```

### Task 6: Update standalone OptionsPage

Update `OptionsPage.tsx` to also include a link or tab for the chain
scanner, or add the ChainScannerPanel as a second section below the
existing OptionsContent.

Alternatively, if the standalone `/options` route isn't heavily used,
just keep it as-is (it will work after the 500 fix).

---

## Files summary

| Action | File |
|--------|------|
| MODIFY | `app/routers/options.py` — fix knowledge_strategies type to `Optional[Any]` |
| CREATE | `frontend/src/components/ChainScannerPanel.tsx` |
| MODIFY | `frontend/src/api/client.ts` — add `chainScan()` function |
| MODIFY | `frontend/src/types/index.ts` — add chain scanner types, fix knowledge_strategies |
| MODIFY | `frontend/src/pages/AnalysisPage.tsx` — add "Chain Scanner" tab |
| MODIFY | `CHANGELOG.md` |

## What NOT to modify

- `frontend/src/pages/ScannerPage.tsx` — equity scanner, unrelated
- `frontend/src/components/SignalPanel.tsx` — equity TA signals
- `frontend/src/components/StrategyPanel.tsx` — equity strategies
- Backend frozen files (same list as always)
- Don't delete or replace `OptionsContent` — fix it and keep it as a tab

## Notes for Claude Code

- The frontend uses React 18 + TypeScript + Tailwind CSS
- No component library — all components are custom
- Dark theme throughout — black backgrounds, glass effects, white/gray text
- Font mono for all numbers and financial data
- The `apiFetch` wrapper handles auth headers and 401 redirects automatically
- All API calls go through `/api/*` prefix (Vite proxy in dev, Vercel rewrites in prod)
- Hot reload is active — changes take effect immediately