# Options Opportunity Scanner — System Documentation

## Overview

The options scanner is a sub-service of Trading Copilot that scans a watchlist of tickers and surfaces actionable options trade setups. For each ticker it produces up to three opportunities (short / medium / long outlook) complete with multi-leg pricing, Greeks, entry/exit/stop levels, Monte Carlo statistics, and an optional AI narrative synthesis.

The scanner runs entirely within the Trading Copilot process — it reuses TC's market data cache, TA engine, AI config, and knowledge base. No separate process or HTTP dependency is needed.

---

## Architecture

```
POST /options/scan  (app/routers/options.py)
         │
         ▼
  run_scan(tickers)
  app/services/options/scanner.py
         │
         ├─── Market data ──────────► app/services/market_data.py
         │                            get_or_refresh_data()  (DB-cached yfinance)
         │
         ├─── TA signals ───────────► app/services/ta_engine.py
         │                            analyze_ticker()  +  _adapt_signals()
         │
         ├─── IV surface ───────────► app/services/options/pricing/pricer.py
         │                            get_vol_surface()  →  bundled analytics/vol_surface.py
         │
         ├─── Opportunity builder ──► app/services/options/opportunity_builder.py
         │     │
         │     ├── Bias detection ──► app/services/options/bias_detector.py
         │     ├── Strategy map ────► app/services/options/strategy_selector.py
         │     └── Multi-leg pricing► app/services/options/pricing/pricer.py
         │                            Black-Scholes + Monte Carlo (jump-diffusion)
         │                            American LSMC (puts)
         │
         ├─── Knowledge base ───────► tools/knowledge_base/strategy_gen.py
         │                            RAG: pgvector retrieval + Claude synthesis
         │
         └─── AI narrative ─────────► app/services/options/ai_narrative.py
                                       Summarises all opportunities via SYNTHESIS_PROVIDER
```

---

## File Structure

```
app/
  routers/
    options.py                  FastAPI router  (POST /options/scan, GET /options/scan/{ticker})
  services/
    options/
      __init__.py
      config.py                 Options-specific settings (DTE windows, stop %, MC params)
      scanner.py                Orchestrator; signal adapter; TC data/TA integration
      bias_detector.py          TA signal → directional bias (bullish/bearish/neutral)
      strategy_selector.py      (bias, outlook) → strategy + strike/expiry selection
      opportunity_builder.py    Multi-leg pricing, Greeks, exit/stop levels, MC stats
      formatter.py              Terminal-style ASCII output renderer
      ai_narrative.py           AI synthesis using SYNTHESIS_PROVIDER
      pricing/
        __init__.py
        pricer.py               Wrapper: BS, MC, IV surface, reprice_at
        src/                    Bundled pricing source (no external path dependency)
          models/
            black_scholes.py    Black-Scholes price + Greeks
          monte_carlo/
            gbm_simulator.py    GBM paths + run_monte_carlo orchestrator
            jump_diffusion.py   Merton jump-diffusion
            american_mc.py      Longstaff-Schwartz LSMC (American options)
            garch_vol.py        GARCH(1,1) fit + vol path simulation
            risk_metrics.py     VaR, CVaR, distribution stats
            mc_greeks.py        Bump-and-reprice MC Greeks
          analytics/
            vol_surface.py      Live IV surface from yfinance option chains
```

---

## Signal Adapter

TC's `ta_engine.analyze_ticker()` returns a richer signal dict than the standalone scanner's `ta_signals.py`. The adapter in `scanner._adapt_signals()` bridges the two formats without modifying either:

| TC Signal Key | Scanner Expects | Adapter Logic |
|---|---|---|
| `trend.price_vs_sma20 == "above"` | `trend.above_sma20` (bool) | string comparison |
| `trend.price_vs_sma50 == "above"` | `trend.above_sma50` (bool) | string comparison |
| `trend.price_vs_sma200 == "above"` | `trend.above_sma200` (bool) | string comparison |
| `trend.sma_20 > sma_50` | `trend.sma20_above_sma50` (bool) | value comparison |
| `trend.sma_50 > sma_200` | `trend.sma50_above_sma200` (bool) | value comparison |
| top-level `price` | `trend.current_price` | copy down |
| `momentum.macd > macd_signal` | `momentum.macd_bullish` (bool) | value comparison |
| `momentum.macd_crossover == "bullish_crossover"` | `momentum.macd_crossover` (bool) | string comparison |
| `momentum.macd_crossover == "bearish_crossover"` | `momentum.macd_crossunder` (bool) | string comparison |
| `momentum.stochastic_k < 20` | `momentum.stoch_oversold` (bool) | threshold |
| `momentum.stochastic_k > 80` | `momentum.stoch_overbought` (bool) | threshold |
| `volatility.atr_vs_price_pct` | `volatility.atr_pct` | rename |
| computed from prices | `volatility.hist_vol` | 20-day log-return std × √252 |
| computed from ATR series | `volatility.atr_percentile` | rolling percentile rank |
| `sr.swing_highs[1].price` | `sr.next_resistance` | index into list (fallback: +5%) |
| `sr.swing_lows[1].price` | `sr.next_support` | index into list (fallback: −5%) |

---

## Strategy Logic

### Bias Detection (`bias_detector.py`)

Scores TA signals to a net integer:

| Signal | Bullish | Bearish |
|--------|---------|---------|
| Above SMA 20/50/200 (each) | +1 | −1 |
| SMA 20 > SMA 50 | +1 | −1 |
| SMA 50 > SMA 200 | +1 | −1 |
| Golden cross | +2 | — |
| Death cross | — | −2 |
| RSI > 60 | +1 | — |
| RSI < 40 | — | −1 |
| RSI > 70 (overbought penalty) | −1 | — |
| RSI < 30 (oversold bonus) | +1 | — |
| MACD above signal | +1 | −1 |
| MACD bullish crossover | +2 | — |
| MACD bearish crossover | — | −2 |
| Stochastic oversold | +1 | — |
| Stochastic overbought | — | −1 |

`score ≥ 3` → **BULLISH** · `score ≤ −3` → **BEARISH** · else → **NEUTRAL**
Neutral sub-label: `atr_percentile ≥ 50` or `bb_squeeze` → `neutral_high_iv`; else → `neutral_low_iv`

### Strategy Map

| Bias | Short (7–21 DTE) | Medium (30–60 DTE) | Long (61–120 DTE) |
|------|------------------|--------------------|-------------------|
| Bullish | Long Call | Bull Call Spread | Long Call |
| Bearish | Long Put | Bear Put Spread | Long Put |
| Neutral (High IV) | Iron Condor | Short Strangle | Iron Condor |
| Neutral (Low IV) | Long Straddle | Long Strangle | Long Strangle |

### Strike Selection

| Strategy | Leg Structure |
|----------|--------------|
| Long Call | Buy call at nearest resistance |
| Long Put | Buy put at nearest support |
| Bull Call Spread | Buy ATM call · sell call at resistance |
| Bear Put Spread | Buy ATM put · sell put at support |
| Iron Condor | Buy put (next_support) · sell put (support) · sell call (resistance) · buy call (next_resistance) |
| Short Strangle | Sell put at support · sell call at resistance |
| Long Straddle | Buy put + call at ATM |
| Long Strangle | Buy put at support · buy call at resistance |

---

## Pricing

### Black-Scholes
Standard European BSM. Used for all per-leg entry pricing and Greek calculation.

### Monte Carlo (jump-diffusion, 5 000 paths)
Merton model: GBM + compound Poisson jump component (λ=0.1, μ_J=−0.05, σ_J=0.15). Antithetic variates for variance reduction. Produces: `prob_profit`, `expected_payoff`.

### American LSMC (puts)
Longstaff-Schwartz regression on ITM paths. Degree-3 polynomial basis normalised by strike. Reports `american_price` and `early_exercise_premium` separately.

### IV Surface
Live yfinance option chains, Brent root-finding for IV per strike. Filters: bid/ask > 0, open interest > 0, moneyness 0.70–1.40. Up to 6 expiries per ticker. Falls back to historical vol when unavailable.

---

## Exit / Stop Framework

### Credit strategies (Iron Condor, Short Strangle)
| Level | Calculation |
|-------|------------|
| Entry | Net credit received |
| Take-profit | Buy back at 50% of credit (lock half the premium) |
| Stop | Buy back at 2× credit (100% loss on initial credit) |
| Underlying stop | Break of short leg's S/R level |
| Max profit | Net credit |
| Max loss | Spread width − credit (condor) · Unlimited (strangle) |

### Debit strategies (all others)
| Level | Calculation |
|-------|------------|
| Entry | Net debit paid |
| Target exit | Reprice all legs at S/R target, assuming 60% of DTE elapsed |
| Option stop | 50% of entry premium lost |
| Underlying stop | Break of nearest S/R level that invalidates the thesis |
| Max profit | Spread width − debit (spread) · Unlimited (single leg) |
| Max loss | Net debit |

---

## API Reference

### `POST /options/scan`

**Request body:**
```json
{
  "tickers": ["AAPL", "NVDA", "SPY"],
  "settings": { "risk_free_rate": 0.045 },
  "include_ai": true,
  "include_formatted": false
}
```

**Response:**
```json
{
  "results": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "sector": "Technology",
      "current_price": 213.49,
      "opportunities": [
        {
          "outlook": "short",
          "dte": 14,
          "expiry": "2026-03-27",
          "strategy": "iron_condor",
          "is_credit": true,
          "bias": "neutral_high_iv",
          "bias_score": 1,
          "legs": [
            {"action": "buy",  "option_type": "put",  "strike": 200.0, "iv": 28.4, "price": 1.23, "delta": -0.14, "theta": -0.02},
            {"action": "sell", "option_type": "put",  "strike": 205.0, "iv": 29.1, "price": 2.10, "delta":  0.21, "theta":  0.03},
            {"action": "sell", "option_type": "call", "strike": 220.0, "iv": 27.8, "price": 1.95, "delta": -0.19, "theta":  0.03},
            {"action": "buy",  "option_type": "call", "strike": 225.0, "iv": 26.5, "price": 1.05, "delta":  0.13, "theta": -0.02}
          ],
          "entry": 1.77,
          "exit_target": 0.89,
          "option_stop": 3.54,
          "underlying_stop": 205.0,
          "max_profit": 1.77,
          "max_loss": 3.23,
          "delta": 0.01, "gamma": -0.0012, "theta": 0.02, "vega": -0.04,
          "prob_profit": 64.2,
          "expected_payoff": 0.93
        }
      ],
      "knowledge_strategies": "...",
      "error": null,
      "formatted": null
    }
  ],
  "ai_narrative": "AAPL — Neutral with slight bullish lean..."
}
```

### `GET /options/scan/{ticker}`

Query parameters: `include_formatted` (bool, default false), `risk_free_rate` (float, default 0.045).

Returns a single `TickerResult`.

---

## Configuration

All options-specific settings are in `app/services/options/config.py` and read from environment variables. Add to your `.env` / `docker/.env`:

```env
# Options scanner (all optional — shown with defaults)
OPTIONS_RISK_FREE_RATE=0.045
OPTIONS_MC_PATHS=5000
OPTIONS_MC_STEPS=252
OPTIONS_MC_SEED=42
OPTIONS_STOP_PCT=0.50
OPTIONS_BIAS_THRESHOLD=3
```

The AI narrative uses the existing `SYNTHESIS_PROVIDER` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — no new vars needed.

---

## Knowledge Base Integration

The scanner calls `tools.knowledge_base.strategy_gen.generate_strategies(ticker)` directly — no HTTP. This means:

- The pgvector Docker container must be running and chunks must be ingested.
- `OPENAI_API_KEY` must be set (TC uses OpenAI for embeddings).
- Any failure is caught and logged; `knowledge_strategies` will be `null` in the response.
- The AI narrative's system prompt instructs Claude to incorporate knowledge strategies when present and to note alignment or conflict with the quantitative scan output.

---

## Pricing Source Bundle

The Black-Scholes / Monte Carlo / IV surface code is bundled verbatim under `app/services/options/pricing/src/` from `State_Estimators/misc/stonks/options/src/`. A minimal `sys.path` shim in `pricer.py` adds `src/` to the path so the source files' internal imports resolve without modification. This eliminates the external repository dependency and makes TC self-contained for deployment.

If the pricing source is ever packaged as a proper pip library, replace the shim with a normal package import and delete the `src/` tree.

---

## Authentication

The `/options/*` endpoints are protected by TC's existing JWT authentication (same as `/analysis`, `/synthesis`, etc.). Include the `Authorization: Bearer <token>` header obtained from `POST /auth/login`.
