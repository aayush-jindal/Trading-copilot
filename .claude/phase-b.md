# Phase B — Strategy Template Mapping

## Goal

Bridge the chain scanner's output (IV regime, edge, direction, Greeks)
to concrete options structures. When a user runs `/options/chain-scan`,
the response currently returns individual contract signals with conviction
scores. Phase B adds a `recommended_strategy` field to each signal that
maps the scanner's findings to a specific trade structure (spread, straddle,
single leg, etc.) with strike selection, DTE guidance, and risk parameters.

This does NOT replace the existing `POST /options/scan` pipeline
(bias_detector → strategy_selector → opportunity_builder). That system
starts from TA signals. Phase B starts from IV rank + edge — a different
entry point yielding different (sometimes overlapping) recommendations.

---

## How the existing system works (DO NOT MODIFY)

```
TA signals → _adapt_signals() → bias_detector.detect_bias()
  → (bias, outlook) → STRATEGY_MAP → select_strikes()
  → opportunity_builder → fully priced opportunity
```

Bias detector uses trend + momentum to determine direction.
Strategy selector uses a static (bias, outlook) → strategy map.
IV plays a minor role: it only affects the neutral sub-label
(neutral_high_iv vs neutral_low_iv).

## How Phase B works (NEW)

```
Chain scanner → OptionSignal (with iv_regime, edge_pct, direction, Greeks)
  → strategy_mapper.map_signal() → StrategyRecommendation
  → attached to chain-scan response
```

The chain scanner already knows:
- **iv_regime**: LOW / NORMAL / ELEVATED / HIGH
- **direction**: BUY (underpriced) / SELL (overpriced)
- **edge_pct**: how much mispricing exists
- **delta**: directional exposure of the scanned contract
- **conviction**: composite score

Phase B uses these to recommend a strategy structure that
exploits the specific edge found.

---

## Strategy mapping logic

The key insight: IV regime + direction → strategy family.

| IV Regime | Direction | Strategy | Rationale |
|-----------|-----------|----------|-----------|
| HIGH | SELL | Short put spread (bullish bias) | Sell rich premium with defined risk |
| HIGH | SELL | Short call spread (bearish bias) | Sell rich premium with defined risk |
| HIGH | SELL | Iron condor (neutral) | Sell premium both sides |
| HIGH | BUY | Avoid or long put (hedging only) | Buying expensive vol rarely has edge |
| ELEVATED | SELL | Short put spread / short call spread | Same as HIGH but narrower spreads |
| ELEVATED | BUY | Calendar spread | Buy cheap back-month, sell rich front |
| NORMAL | BUY | Long call / long put (directional) | Fair vol, ride directional edge |
| NORMAL | SELL | No strong recommendation | Not enough premium to sell |
| LOW | BUY | Long straddle / long strangle | Buy cheap vol before expansion |
| LOW | BUY | Long call / long put (directional) | Cheap options, directional bet |
| LOW | SELL | Avoid | Selling cheap premium has no edge |

Directional bias for BUY signals comes from the sign of delta on the
scanned contract. For SELL signals, it comes from whether the overpriced
contract is a call (sell call spread) or put (sell put spread).

---

## New file: `app/services/options/chain_scanner/strategy_mapper.py`

```python
"""
Strategy template mapper for chain scanner signals.

Maps (iv_regime, direction, option_type, delta) → StrategyRecommendation.
Does NOT price legs — just recommends the structure, strikes, and DTE.
Pricing happens downstream if the user clicks through.

Options Analytics Team — 2026-04
"""
```

### Data structures

```python
@dataclass
class StrategyRecommendation:
    """Recommended trade structure for a scanned signal."""
    strategy: str           # e.g. "short_put_spread", "long_straddle"
    strategy_label: str     # Human-readable: "Short Put Spread"
    rationale: str          # Why this structure fits the signal
    legs: list[dict]        # [{"action": "buy"|"sell", "option_type": ..., "strike_method": ...}]
    suggested_dte: int      # Recommended DTE for this structure
    risk_profile: str       # "defined" or "undefined"
    max_risk_method: str    # How to compute max risk: "spread_width", "premium_paid", "unlimited"
    edge_source: str        # "iv_overpriced", "iv_underpriced", "directional"
```

### Core function

```python
def map_signal(signal: OptionSignal) -> Optional[StrategyRecommendation]:
    """Map a chain scanner signal to a strategy recommendation.

    Returns None if no high-conviction mapping exists (e.g. NORMAL regime
    + SELL direction has no edge).
    """
```

### Implementation rules

1. **strike_method** in legs uses relative references, not absolute prices:
   - `"atm"` — nearest to spot
   - `"otm_1"` — one strike increment OTM from spot
   - `"otm_2"` — two increments OTM
   - `"signal_strike"` — the strike the scanner actually flagged
   - `"signal_strike + width"` — for the protective leg of a spread

2. **suggested_dte** depends on strategy family:
   - Credit spreads: 30–45 DTE (theta decay sweet spot)
   - Debit spreads: 45–60 DTE (time to be right)
   - Straddles/strangles: 45–60 DTE
   - Single legs: match the scanned contract's DTE

3. **Return None** for low-conviction mappings:
   - HIGH regime + BUY → None (buying expensive vol)
   - LOW regime + SELL → None (selling cheap vol)
   - NORMAL regime + SELL → None (not enough premium)
   - conviction < 30 → None

---

## Changes to existing chain scanner output

### Modify `app/routers/chain_scan.py`

In the `_to_dict()` function, add the strategy recommendation:

```python
from app.services.options.chain_scanner.strategy_mapper import map_signal

def _to_dict(s: OptionSignal) -> dict:
    rec = map_signal(s)
    base = { ... existing fields ... }
    base["recommended_strategy"] = {
        "strategy": rec.strategy,
        "label": rec.strategy_label,
        "rationale": rec.rationale,
        "legs": rec.legs,
        "suggested_dte": rec.suggested_dte,
        "risk_profile": rec.risk_profile,
        "edge_source": rec.edge_source,
    } if rec else None
    return base
```

### Response shape after Phase B

```json
{
  "signals": [
    {
      "ticker": "AAPL",
      "strike": 250.0,
      "expiry": "2026-05-15",
      "option_type": "put",
      "edge_pct": -8.5,
      "direction": "SELL",
      "iv_regime": "HIGH",
      "conviction": 72.5,
      "recommended_strategy": {
        "strategy": "short_put_spread",
        "label": "Short Put Spread",
        "rationale": "IV rank 85% — premium is rich. Sell the flagged put, buy protection one strike below.",
        "legs": [
          {"action": "sell", "option_type": "put", "strike_method": "signal_strike"},
          {"action": "buy", "option_type": "put", "strike_method": "signal_strike - width"}
        ],
        "suggested_dte": 35,
        "risk_profile": "defined",
        "edge_source": "iv_overpriced"
      }
    }
  ]
}
```

---

## Task sequence

### Task 1: Create strategy_mapper.py

Create `app/services/options/chain_scanner/strategy_mapper.py` with:
- `StrategyRecommendation` dataclass
- `map_signal(signal: OptionSignal) -> Optional[StrategyRecommendation]`
- Complete mapping table covering all (iv_regime, direction) combinations
- Returns None for low-conviction / no-edge combinations

The mapping logic:

```
if conviction < 30:
    return None

if iv_regime == "HIGH":
    if direction == "SELL":
        if option_type == "put":  → short_put_spread
        if option_type == "call": → short_call_spread
        # If |delta| < 0.20 (near-neutral): → iron_condor
    if direction == "BUY":
        return None  # don't buy expensive vol

if iv_regime == "ELEVATED":
    if direction == "SELL":
        if option_type == "put":  → short_put_spread (narrower)
        if option_type == "call": → short_call_spread (narrower)
    if direction == "BUY":
        → calendar_spread (buy back-month, sell front-month)

if iv_regime == "NORMAL":
    if direction == "BUY":
        if option_type == "call": → long_call
        if option_type == "put":  → long_put
    if direction == "SELL":
        return None  # not enough premium

if iv_regime == "LOW":
    if direction == "BUY":
        if |delta| < 0.25:  → long_straddle (vol expansion play)
        if option_type == "call": → long_call
        if option_type == "put":  → long_put
    if direction == "SELL":
        return None  # selling cheap vol
```

**Acceptance criteria:**
- Every (iv_regime, direction) combination is handled
- Returns None for the 3 no-edge combos (HIGH+BUY, NORMAL+SELL, LOW+SELL)
- Returns a valid StrategyRecommendation for all other combos
- Each recommendation has a human-readable rationale string
- No pricing or live data calls — pure mapping logic

### Task 2: Wire into endpoint

Modify `app/routers/chain_scan.py`:
- Import `map_signal` from strategy_mapper
- Add `recommended_strategy` field to `_to_dict()` output
- Handle None case (no recommendation)

**Acceptance criteria:**
- `GET /options/chain-scan?tickers=AAPL` returns signals with
  `recommended_strategy` field (either an object or null)
- Existing signal fields unchanged
- smoke_test.py passes

### Task 3: Tests

Create `tests/test_strategy_mapper.py`:

Test cases:
- HIGH + SELL + put → short_put_spread
- HIGH + SELL + call → short_call_spread
- HIGH + SELL + low delta → iron_condor
- HIGH + BUY → None
- ELEVATED + SELL + put → short_put_spread
- ELEVATED + BUY → calendar_spread
- NORMAL + BUY + call → long_call
- NORMAL + BUY + put → long_put
- NORMAL + SELL → None
- LOW + BUY + low delta → long_straddle
- LOW + BUY + call → long_call
- LOW + SELL → None
- conviction < 30 → None
- All recommendations have non-empty rationale
- All recommendations have at least 1 leg
- risk_profile is "defined" for spreads, varies for others

At least 15 test cases.

**Acceptance criteria:**
- All tests pass
- No network calls (all mocked OptionSignal inputs)
- smoke_test.py passes

### Task 4: Update CHANGELOG

Append entries for all new/modified files.

---

## What NOT to do

- Do NOT modify `strategy_selector.py` — that serves the existing pipeline
- Do NOT modify `bias_detector.py` — frozen
- Do NOT modify `opportunity_builder.py` — that's the existing pricing pipeline
- Do NOT add pricing calls to strategy_mapper — it's a pure mapping layer
- Do NOT modify the existing `/options/scan` endpoint
- Do NOT add new pip dependencies
- Do NOT price the recommended legs (that's Phase C — pricing + execution)

---

## Frozen files reminder

| File | Status |
|------|--------|
| `app/services/options/pricing/src/**` | FROZEN |
| `app/services/options/bias_detector.py` | FROZEN |
| `app/services/options/scanner.py` | DO NOT TOUCH |
| `app/services/options/strategy_selector.py` | DO NOT TOUCH |
| `app/services/options/opportunity_builder.py` | DO NOT TOUCH |
| `app/routers/options.py` | DO NOT TOUCH |
| `app/routers/synthesis.py` | FROZEN |
| `app/services/ai_engine.py` | FROZEN |
| `app/services/ta_engine.py` | FROZEN |
| `app/services/market_data.py` | FROZEN |