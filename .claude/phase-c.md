# Phase C — Price Recommended Strategies

## Goal

Take the Phase B strategy recommendation (strategy type + leg structure)
and produce a fully priced opportunity with entry, stops, targets, net
Greeks, max profit/loss, and probability of profit — using the existing
pricing machinery (`pricer.py`).

After Phase C, the `/options/chain-scan` response includes everything
a trader needs to execute: not just "sell a put spread" but "sell the
250/245 put spread for $1.82 credit, max loss $3.18, 68% prob profit,
exit at $0.91, stop at $3.64".

---

## What exists and what's needed

**Already built (DO NOT MODIFY):**
- `pricer.py` — `price_bs()`, `price_mc()`, `reprice_at()` wrappers
- `opportunity_builder.py` — full pricing pipeline (reference, not called directly)
- `strategy_mapper.py` (Phase B) — `map_signal()` → `StrategyRecommendation`
- `chain_scan.py` endpoint — returns signals + recommended_strategy

**What Phase C adds:**
- `strategy_pricer.py` — new module that resolves abstract legs
  (`strike_method: "signal_strike"`) to concrete strikes, prices
  every leg via `price_bs()`, computes net premium/Greeks/stops/targets,
  and runs MC for probability of profit.

**Key difference from opportunity_builder.py:**
The existing builder starts from TA signals → bias → strategy map → S/R
anchored strikes. Phase C starts from the chain scanner signal which
already has: spot, strike, expiry, chain IV, DTE, and the strategy
mapper recommendation. We don't need bias detection or S/R lookups —
the scanner already did that work. We just need to resolve strikes,
price legs, and compute risk parameters.

---

## New file: `app/services/options/chain_scanner/strategy_pricer.py`

### Core function

```python
def price_recommendation(
    signal: OptionSignal,
    recommendation: StrategyRecommendation,
) -> Optional[dict]:
    """
    Resolve abstract legs to concrete strikes, price via BS,
    compute net premium, Greeks, stops, targets, and P(profit).

    Returns None if pricing fails or entry < $0.05.
    """
```

### What it does step by step

1. **Resolve strikes** — Convert `strike_method` references to actual prices:
   - `"signal_strike"` → `signal.strike` (the contract the scanner flagged)
   - `"atm"` → `_round_strike(signal.spot)`
   - `"otm_1"` → one strike increment from spot
   - `"signal_strike - width"` / `"signal_strike + width"` → protective
     leg of a spread, using standard increment (5 for stocks >$100,
     2.5 for >$50, 1 for cheaper)

2. **Price each leg** — Call `price_bs(spot, strike, T, iv, option_type)`
   for every leg. Use `signal.chain_iv` as the base IV. For the
   protective leg of a spread, use the same IV (conservative; vol
   surface lookup is optional enhancement).

3. **Compute net position** — Sum premiums with sign convention
   (sell = +credit, buy = -debit). Sum Greeks the same way.

4. **Determine entry** — `abs(net_premium)`. If < $0.05, return None.

5. **Compute max profit / max loss** — Based on strategy type:
   - Credit spreads: max_profit = entry, max_loss = spread_width - entry
   - Debit spreads: max_loss = entry, max_profit = spread_width - entry
   - Single legs (long): max_loss = entry, max_profit = None (unlimited for calls)
   - Single legs (short): would need margin, not applicable here
   - Iron condor: max_profit = net credit, max_loss = wider_wing - net credit
   - Straddle/strangle: max_loss = entry, max_profit = None

6. **Set exit target** —
   - Credit strategies: exit when you can buy back at 50% of credit received
   - Debit strategies: exit at 50% profit (entry × 1.5) or when underlying
     hits a target derived from the spread width

7. **Set stop** —
   - Credit strategies: stop at 2× credit received (loss = credit)
   - Debit strategies: stop at 50% of premium paid (entry × 0.5)

8. **Run MC for probability of profit** — Build an MC config from the
   signal data, run `price_mc()` on the primary leg, compute
   `P(payoff > entry)`. Use `signal.chain_iv` as vol, jump-diffusion on.

9. **Return priced opportunity dict** matching the shape of
   `opportunity_builder.py`'s output (for frontend compatibility).

### Output shape

```python
{
    "strategy": "short_put_spread",
    "strategy_label": "Short Put Spread",
    "is_credit": True,
    "legs": [
        {
            "action": "sell",
            "option_type": "put",
            "strike": 250.0,
            "iv": 32.5,
            "price": 4.12,
            "delta": -0.301,
            "theta": 0.045,
        },
        {
            "action": "buy",
            "option_type": "put",
            "strike": 245.0,
            "iv": 33.1,
            "price": 2.30,
            "delta": 0.198,
            "theta": -0.032,
        },
    ],
    "spread_width": 5.0,
    "entry": 1.82,              # net credit received
    "exit_target": 0.91,         # buy back at 50% of credit
    "exit_pct": 50.0,
    "option_stop": 3.64,         # 2x credit = max acceptable loss
    "max_profit": 1.82,
    "max_loss": 3.18,            # spread_width - entry
    "net_delta": -0.103,
    "net_gamma": -0.008,
    "net_theta": 0.013,
    "net_vega": -0.052,
    "prob_profit": 68.2,
    "expected_payoff": 1.24,
    "risk_reward": "1:1.75",     # max_loss / max_profit
    "edge_source": "iv_overpriced",
    "rationale": "IV rank 85% — premium is rich. ...",
}
```

---

## Changes to endpoint

### Modify `app/routers/chain_scan.py`

Add optional `?price=true` query parameter. When set, the endpoint
resolves and prices the recommended strategy for each signal.

Default is `price=false` — Phase A/B behavior unchanged.

```python
@router.get("/chain-scan")
def chain_scan(
    tickers: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=100),
    price: bool = Query(False, description="Price recommended strategies"),
    user: dict = Depends(get_current_user),
):
```

When `price=true`:
- For each signal that has a `recommended_strategy`, call
  `price_recommendation(signal, recommendation)`
- Attach the result as `priced_strategy` in the response
- Signals without recommendations or failed pricing get `priced_strategy: null`

This makes pricing opt-in because it's slower (BS + MC per signal).

### Response shape with pricing

```json
{
  "signals": [
    {
      "ticker": "AAPL",
      "strike": 250.0,
      "edge_pct": -8.5,
      "direction": "SELL",
      "iv_regime": "HIGH",
      "conviction": 72.5,
      "recommended_strategy": {
        "strategy": "short_put_spread",
        "label": "Short Put Spread",
        "rationale": "...",
        "legs": [...]
      },
      "priced_strategy": {
        "strategy": "short_put_spread",
        "is_credit": true,
        "legs": [
          {"action": "sell", "option_type": "put", "strike": 250.0, "iv": 32.5, "price": 4.12, "delta": -0.301, "theta": 0.045},
          {"action": "buy", "option_type": "put", "strike": 245.0, "iv": 33.1, "price": 2.30, "delta": 0.198, "theta": -0.032}
        ],
        "spread_width": 5.0,
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
    }
  ]
}
```

---

## Task sequence

### Task 1: Create strategy_pricer.py

Create `app/services/options/chain_scanner/strategy_pricer.py` with:

- `_round_strike(price)` — same logic as strategy_selector.py
  (5 for ≥$100, 2.5 for ≥$50, 1 otherwise). Copy the function,
  don't import from strategy_selector (keep chain_scanner self-contained).

- `_resolve_strikes(signal, recommendation)` → list of concrete leg dicts
  with actual strike prices. Converts `strike_method` references.
  For spread width, use one strike increment from the signal strike.

- `_classify_credit(strategy)` → bool. Credit strategies:
  short_put_spread, short_call_spread, iron_condor.

- `price_recommendation(signal, recommendation)` → Optional[dict]
  The main function. Calls `price_bs()` for each leg, computes
  net premium/Greeks, sets stops/targets, runs MC, returns the
  priced opportunity dict or None.

**Import pattern** (same sys.path shim as other chain_scanner files):
```python
from pathlib import Path
import sys

_SRC = str(Path(__file__).resolve().parent.parent / "pricing" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from models.black_scholes import black_scholes_price, calculate_greeks
from monte_carlo.gbm_simulator import run_monte_carlo
```

Also import from config:
```python
from app.services.options.config import MC_NUM_PATHS, MC_NUM_STEPS, MC_SEED, RISK_FREE_RATE, OPTION_STOP_PCT
```

**Acceptance criteria:**
- `price_recommendation()` returns a fully populated dict for a
  credit spread signal (short_put_spread)
- Returns a fully populated dict for a debit single leg (long_call)
- Returns None when entry < $0.05
- All legs have price, iv, delta, theta
- net_delta/gamma/theta/vega are correctly signed sums
- max_profit and max_loss are correct for credit vs debit
- prob_profit is between 0 and 100
- No modifications to existing files

### Task 2: Wire into endpoint

Modify `app/routers/chain_scan.py`:
- Add `price: bool = Query(False)` parameter
- When `price=true`, import and call `price_recommendation()`
  for each signal with a recommendation
- Add `priced_strategy` field to response dict
- When `price=false` (default), don't call pricer, return
  `priced_strategy: null` — existing behavior unchanged

**Acceptance criteria:**
- `GET /options/chain-scan?tickers=AAPL&top=5` returns same response
  as before (priced_strategy is null or absent)
- `GET /options/chain-scan?tickers=AAPL&top=5&price=true` returns
  signals with `priced_strategy` populated where recommendations exist
- smoke_test.py passes

### Task 3: Tests

Create `tests/test_strategy_pricer.py` with at least 15 test cases:

- `_round_strike` returns correct increments (5/2.5/1)
- `_resolve_strikes` for short_put_spread → 2 legs with correct strikes
- `_resolve_strikes` for long_call → 1 leg at signal_strike
- `_resolve_strikes` for iron_condor → 4 legs
- `_resolve_strikes` for long_straddle → 2 legs at ATM
- `_classify_credit` → True for credit strategies, False for debit
- `price_recommendation` for credit spread → entry > 0, is_credit True
- `price_recommendation` for long call → entry > 0, is_credit False
- `price_recommendation` returns None for tiny entry
- Max profit = entry for credit, max loss = entry for debit
- Spread width correct for spreads
- Net Greeks are signed sums of individual legs
- prob_profit is 0-100
- exit_target = 50% of credit for credit strategies
- stop = 2x credit for credit strategies

Use mock OptionSignal and StrategyRecommendation inputs.
BS pricing calls are real (they're pure math, no network).
MC calls should be mocked (or use very low path count for speed).

**Acceptance criteria:**
- All tests pass
- smoke_test.py passes

### Task 4: Update CHANGELOG

Append entries for strategy_pricer.py, chain_scan.py modification,
and test file.

---

## What NOT to do

- Do NOT modify `opportunity_builder.py` — that serves the existing pipeline
- Do NOT modify `pricer.py` — use its functions, don't change them
- Do NOT modify `strategy_selector.py`
- Do NOT modify `strategy_mapper.py` (Phase B) — it stays a pure mapping layer
- Do NOT modify the existing `/options/scan` endpoint
- Do NOT fetch vol surface data — use `signal.chain_iv` for simplicity.
  Vol surface lookup is a future enhancement.
- Do NOT add new pip dependencies

## Frozen files reminder

| File | Status |
|------|--------|
| `app/services/options/pricing/src/**` | FROZEN |
| `app/services/options/pricing/pricer.py` | DO NOT MODIFY |
| `app/services/options/bias_detector.py` | FROZEN |
| `app/services/options/scanner.py` | DO NOT TOUCH |
| `app/services/options/strategy_selector.py` | DO NOT TOUCH |
| `app/services/options/opportunity_builder.py` | DO NOT TOUCH |
| `app/routers/options.py` | DO NOT TOUCH |
| `app/routers/synthesis.py` | FROZEN |
| `app/services/ai_engine.py` | FROZEN |
| `app/services/ta_engine.py` | FROZEN |
| `app/services/market_data.py` | FROZEN |

## Files summary

| Action | File |
|--------|------|
| CREATE | `app/services/options/chain_scanner/strategy_pricer.py` |
| CREATE | `tests/test_strategy_pricer.py` |
| MODIFY | `app/routers/chain_scan.py` — add `?price=true` param + priced_strategy field |
| MODIFY | `CHANGELOG.md` |