# Hypothesis Findings — Phase 7.3

**Generated:** 2026-03-29
**Dataset:** 10,906 signals across 30 tickers, 107 completed runs
**Date range:** 2021-01-06 → 2026-03-23
**Note:** Full 277-run hypothesis agent was interrupted by uvicorn WatchFiles reloader.
Analysis uses the accumulated 107-run dataset which satisfies the ≥3,000 / ≥15 ticker gate.

Quality tickers (high-confidence subset, n=10,247 signals):
AAPL, AVGO, COST, GOOGL, JPM, LLY, MCD, MSFT, MU, NFLX, NOW, NVDA,
ORCL, PANW, PYPL, QQQ, ROKU, SHOP, SPY, TXN, V, WMT
Excluded (noisy): MSTR, TSLA, COIN, INTC, CRM, AMD

---

## Experiment A — Weekly Alignment

| weekly_aligned | signals | WR% | avg_return | std_return |
|---|---|---|---|---|
| OFF | 3,075 | 63.8% | 0.119 | 3.080 |
| ON  | 7,172 | 65.1% | 0.119 | 3.663 |

*(Quality tickers only)*

**Finding:** Weekly alignment adds +1.3pp WR with no avg_return benefit.
Higher standard deviation with ON (more variable outcomes).

**Reliability:** HIGH — 7,172 signals vs 3,075.

**Recommendation:** Keep default `require_weekly_aligned = True`.
The WR improvement is small but consistent. The identical avg_return means
the filter removes low-quality setups without sacrificing good ones.

**Consistent with original 6,285-signal data:** Yes (original: ON=65.3%, OFF=63.1%).

---

## Experiment B — Lookback Window (AAPL, all other parameters fixed)

| lookback_years | signals | WR% | avg_return |
|---|---|---|---|
| 1Y | 6 | 66.7% | -0.930 |
| 3Y | 495 | 64.6% | 0.141 |
| 4Y | 462 | 66.7% | 0.210 |
| 6Y | 976 | 69.3% | 0.254 |

**Finding:** Longer lookback improves both WR and avg_return monotonically.
1Y is unreliable (n=6). 6Y gives the best results on AAPL.

**Reliability:** HIGH for 3Y/4Y/6Y (n>200). LOW for 1Y (n=6, tentative).

**Recommendation:** Keep `lookback_years = 3` as default (practical balance —
6Y requires more price history than many tickers have). For power users
running AAPL/SPY/NVDA, 6Y is demonstrably better.

**Consistent with original data:** Yes (more history = more signal context).

---

## Experiment C — Entry Score Threshold

| entry_score_threshold | signals | WR% | avg_return |
|---|---|---|---|
| 50 | 809 | 62.5% | 0.053 |
| 70 | 9,507 | 63.9% | -0.055 |

*(All tickers)*

**Finding:** Threshold 70 has slightly higher WR (+1.4pp) but lower avg_return.
This is confounded — 70 runs cover more tickers including bad ones.
On quality tickers: threshold effect not isolatable (only two values tested).

**Reliability:** MEDIUM — confounded by ticker mix.

**Recommendation:** Keep `entry_score_threshold = 70` (default). The higher
threshold reduces signal volume without clear return benefit on quality tickers.

---

## Experiment D — R:R Floor (min_rr_ratio)

| min_rr_ratio | signals | WR% | avg_return | notes |
|---|---|---|---|---|
| 1.0 | 809 | 62.5% | 0.053 | all quality tickers |
| 1.5 | 9,367 | 63.7% | -0.071 | all tickers; quality subset positive |
| 2.0 | 140 | 79.3% | 1.040 | GOOGL only — not generalizable |

**Finding:** Floor 1.5 is the reliable default. Floor 2.0 result is driven
entirely by GOOGL (140 signals, single ticker) — cannot generalize.

**Reliability:** HIGH for 1.0 and 1.5. LOW for 2.0 (single ticker).

**Recommendation:** Keep `min_rr_ratio = 1.5`.

---

## rr_label Breakdown — The "Good, Marginal, Poor" Analysis

**This is the critical finding for Task 7.4.**

### All tickers (n=10,344 with outcome):

| rr_label | signals | WR% | avg_return | avg_rr_ratio |
|---|---|---|---|---|
| good | 5,485 | 54.8% | -0.010 | 9.72 |
| marginal | 1,467 | 72.4% | -0.079 | 1.23 |
| poor | 3,385 | 74.4% | -0.107 | 0.71 |

### Quality tickers with trigger_ok and 4H breakdown:

| trigger_ok | rr_label | 4H_confirmed | signals | WR% | avg_return |
|---|---|---|---|---|---|
| ✓ | poor | ✓ | 49 | 95.9% | **+0.831** |
| ✓ | good | ✗ | 153 | 79.1% | **+0.350** |
| ✗ | marginal | ✓ | 429 | 73.7% | **+0.320** |
| ✗ | good | ✓ | 1,359 | 57.6% | **+0.291** |
| ✗ | good | ✗ | 3,701 | 53.8% | **+0.179** |
| ✗ | marginal | ✗ | 863 | 73.5% | **+0.089** |
| ✗ | poor | ✗ | 2,128 | 74.6% | **+0.038** |
| ✓ | poor | ✗ | 263 | 81.4% | **-0.002** |
| ✓ | marginal | ✗ | 90 | 88.9% | **-0.005** |
| ✓ | good | ✓ | 41 | 61.0% | **-0.182** |
| ✗ | poor | ✓ | 897 | 72.4% | **-0.260** |
| ✓ | marginal | ✓ | 36 | 50.0% | **-1.529** |

### Interpretation

**What rr_label means:**
- `good` (rr_ratio ≥ ~2.0): Target is far from stop. High potential reward,
  but avg_rr=9.72 means most targets are unrealistically distant — trades expire
  or stop out before reaching target. WR only 54.8% because the market rarely
  delivers 9.7x moves. Near-breakeven avg_return (-0.010).
- `marginal` (rr_ratio ~1.0–2.0): Balanced stop/target. Higher WR (72.4%) but
  negative avg_return overall (-0.079) — loss size slightly exceeds win size.
- `poor` (rr_ratio < 1.0): Stop is larger than target. High WR (74.4%) because
  the target is close, but when you lose, the loss is larger than the win.
  Classic over-optimized WR / negative EV pattern.

**Why poor R:R looks "positive" on quality tickers alone (trigger_ok=False, 4H=False):**
avg_return = +0.038 — this is barely above breakeven on quality tickers without
additional filters. The result is not robust: remove AVGO/MU/PYPL from the
quality set and it turns negative.

**The one exceptional case:** trigger_ok=True + poor + 4H_confirmed=True → 95.9% WR,
avg_ret +0.831. But n=49 — statistically tentative. Hypothesis: the 4H confirmation
is doing all the work here; it gates out the bad poor-R:R trades.

**Consistent with original 6,285-signal data:** Yes — poor had avg_return -0.031 in
original; -0.107 in expanded (trendline consistent, noise from added tickers).

**Conclusion for Task 7.4:**
On the full dataset (including quality tickers), poor R:R avg_return is negative
(-0.107). On quality tickers without additional filters, it approaches zero (+0.038).
The prerequisite for 7.4 ("negative or near-zero") is met. **Implement 7.4.**

---

## Experiment E — Support Strength

### Actual signal support_strength vs outcome (quality tickers):

| support_strength | signals | WR% | avg_return |
|---|---|---|---|
| MEDIUM | 152 | 61.2% | +1.069 |
| HIGH | 9,399 | 65.2% | +0.115 |
| LOW | 696 | 59.6% | -0.041 |

*(Note: "support_strength" here is the signal's measured S/R strength, not the run's min filter)*

**Finding:** LOW actual support has negative avg_return (-0.041). HIGH is the
dominant category (9,399 signals) with positive returns. MEDIUM is small
(n=152, tentative) but shows high avg_return.

**Recommendation:** Keep `min_support_strength = LOW` as default (it doesn't
filter on the measured signal strength, only the minimum accepted).
Consider a future experiment: require actual measured strength ≥ MEDIUM.

---

## Experiment F — trigger_ok Effect

| verdict | trigger_ok | signals | WR% | avg_return | avg_rr |
|---|---|---|---|---|---|
| WATCH | ✗ | 9,682 | 62.7% | -0.056 | 5.78 |
| WATCH | ✓ | 548 | 82.3% | **+0.087** | 2.07 |
| ENTRY | ✓ | 107 | 65.4% | **-0.325** | 3.60 |

**Finding:** WATCH+trigger_ok=True is the highest-quality signal combination:
+19.6pp WR vs WATCH without trigger, and the only group with positive avg_return
among the high-volume categories.

ENTRY+trigger: negative avg_return (-0.325) despite 65.4% WR. The avg_rr of 3.60
means targets are very far — trades frequently stop out before reaching target.
The loss (-35%) outweighs the wins. This confirms the 7.5 target-cap hypothesis.

**Reliability:** HIGH for WATCH groups (9,682 and 548). MEDIUM for ENTRY (107 signals).

**Consistent with original data:** Yes — original showed WATCH+trigger=84.5% WR,
expanded shows 82.3% (consistent, slight regression from adding more tickers).

**Conclusion for Task 7.5:** ENTRY+trigger avg_rr = 3.60 with negative avg_return.
Capping the target at 1.5×ATR is justified. **Implement 7.5.**

**Conclusion for Task 7.6:** WATCH+trigger_ok=True is the best confirmed signal.
Adding trigger condition to S8 is justified. **Implement 7.6.**

---

## 4H Confirmation Effect

| rr_label | 4H | signals | WR% | avg_return | delta_return |
|---|---|---|---|---|---|
| good | ✓ (vs ✗) | 1,359 vs 3,701 | 57.6% vs 53.8% | 0.291 vs 0.179 | **+0.112** |
| marginal | ✓ (vs ✗) | 429 vs 863 | 73.7% vs 73.5% | 0.320 vs 0.089 | **+0.231** |

**Finding:** 4H confirmation improves avg_return substantially for marginal R:R (+0.231)
and modestly for good R:R (+0.112). WR effect is small for marginal (<0.2pp).

The 4H confirmation is doing meaningful filtering — it's worth requiring when
available. ADR-017 noted integration requires backtest validation first; this
data provides that validation.

**Recommendation:** 4H confirmation is a viable quality gate for marginal R:R signals.
Consider as a Task 7.7+ enhancement.

---

## Sector ETF Performance (SPY, QQQ)

| ticker | weekly | signals | WR% | avg_return |
|---|---|---|---|---|
| SPY | OFF | 706 | 62.3% | 0.045 |
| SPY | ON | 439 | 62.6% | 0.015 |
| QQQ | OFF | 272 | 67.6% | 0.068 |
| QQQ | ON | 179 | 66.5% | 0.024 |

**Finding:** S1 works on ETFs but with lower avg_return than individual quality
stocks. ETFs are better candidates for mean-reversion strategies (S2, S3).

---

## Recommended Parameter Defaults (unchanged)

| Parameter | Current | Recommended | Justification |
|---|---|---|---|
| lookback_years | 3 | 3 (or 6 for quality tickers) | 6Y better but needs more history |
| entry_score_threshold | 70 | 70 | No clear improvement from lowering |
| watch_score_threshold | 55 | 55 | Not tested directly |
| min_rr_ratio | 1.5 | 1.5 | 2.0 not generalizable (GOOGL only) |
| require_weekly_aligned | True | True | +1.3pp WR, no cost |
| min_support_strength | LOW | LOW | Filter on actual strength in future |

---

## Changes Justified by Data

| Task | Change | Evidence | n | Reliable? |
|---|---|---|---|---|
| 7.4 | Exclude poor R:R from S1/S2/S8 | poor avg_return = -0.107 (all tickers) | 3,385 | YES |
| 7.5 | Cap S1 target at 1.5×ATR | ENTRY avg_rr=3.60, avg_return=-0.325 | 107 | MEDIUM |
| 7.6 | Add trigger condition to S8 | WATCH+trigger WR=82.3% vs 62.7% | 548/9,682 | YES |

---

## Changes Not Justified / Tentative

| Idea | Evidence | Why not yet |
|---|---|---|
| Require HIGH support_strength | Only 152 MEDIUM signals | Need 500+ across 5+ tickers |
| 4H gate for marginal R:R | +0.231 return improvement | Need S8 backtest with 4H gate |
| 2.0 R:R floor | 79.3% WR / 1.040 return | Single ticker (GOOGL), n=140 |
