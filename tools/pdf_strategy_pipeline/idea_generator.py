"""Step 5: Match strategies to live signals and generate trade ideas via Claude."""

from __future__ import annotations

import json

import anthropic

from .config import ANTHROPIC_API_KEY
from .market_connector import get_live_signals

_CLIENT = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        _CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _CLIENT


_SYSTEM_PROMPT = """\
You are a professional trading analyst. Given a set of trading strategies extracted from books \
and current live market signals for a stock, generate specific, actionable trade ideas.

For each strategy provided:
- State clearly whether conditions are MET, PARTIAL, or NOT MET based on the live signals.
- If MET or PARTIAL: give a concrete trade idea with entry zone, stop-loss level, and price target.
- Reference exact signal values (price, RSI, nearest support/resistance, ADX, etc.).
- Note any conflicts between signals and the strategy's requirements.
- Keep it to one focused paragraph per strategy.

Close with a one-paragraph conviction ranking that orders the ideas strongest to weakest.
Tone: direct, factual, no hedging phrases.\
"""


# ── Scoring ──────────────────────────────────────────────────────────────────

def _score_strategy(strategy: dict, signals: dict) -> int:
    """Heuristic relevance score — higher means better fit for current conditions."""
    score = 0
    pattern_type = strategy.get("pattern_type", "")
    indicators = [i.lower() for i in strategy.get("indicators", [])]
    timeframe = strategy.get("timeframe", "any").lower()

    trend = signals.get("trend", {})
    momentum = signals.get("momentum", {})
    volume = signals.get("volume", {})
    swing = signals.get("swing_setup") or {}
    weekly = signals.get("weekly_trend") or {}

    # Pullback strategy → reward when swing setup is actionable
    if pattern_type == "pullback":
        if swing.get("verdict") in ("ENTRY", "WATCH"):
            score += 10

    # Trend-following → reward when daily + weekly trend agree
    if pattern_type == "trend_following":
        if trend.get("signal") == "BULLISH":
            score += 8
        if weekly.get("weekly_trend") == "BULLISH":
            score += 5

    # Breakout → reward when BB squeeze is active (volatility contraction)
    if pattern_type == "breakout":
        if signals.get("volatility", {}).get("bb_squeeze"):
            score += 10

    # Mean reversion → reward extreme RSI
    if pattern_type == "mean_reversion":
        rsi_sig = momentum.get("rsi_signal", "")
        if rsi_sig in ("OVERBOUGHT", "OVERSOLD"):
            score += 10

    # Indicator alignment bonuses
    if any("rsi" in i for i in indicators):
        rsi_sig = momentum.get("rsi_signal", "")
        if rsi_sig not in ("NEUTRAL",):
            score += 5
    if any("macd" in i for i in indicators):
        if momentum.get("macd_crossover") != "none":
            score += 5
    if any("volume" in i for i in indicators):
        if volume.get("volume_signal") == "HIGH":
            score += 5

    # Timeframe match
    if timeframe in ("daily", "any"):
        score += 5

    return score


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_user_message(ticker: str, signals: dict, top_strategies: list[dict]) -> str:
    price = signals.get("price", 0)
    trend = signals.get("trend", {})
    momentum = signals.get("momentum", {})
    volatility = signals.get("volatility", {})
    volume = signals.get("volume", {})
    sr = signals.get("support_resistance", {})
    swing = signals.get("swing_setup") or {}
    weekly = signals.get("weekly_trend") or {}
    candlestick = signals.get("candlestick", [])

    pattern_strs = ", ".join(
        f"{p['pattern']} ({p['pattern_type']})" for p in candlestick
    ) or "none"

    lines = [
        f"TICKER: {ticker} | PRICE: ${price:.2f}",
        "",
        "=== LIVE SIGNALS ===",
        (
            f"TREND: {trend.get('signal')} | "
            f"vs SMA50={trend.get('price_vs_sma50')} | "
            f"vs SMA200={trend.get('price_vs_sma200')} | "
            f"golden_cross={trend.get('golden_cross')} | death_cross={trend.get('death_cross')}"
        ),
        (
            f"MOMENTUM: RSI={momentum.get('rsi')} ({momentum.get('rsi_signal')}) | "
            f"MACD crossover={momentum.get('macd_crossover')} | "
            f"Stochastic K={momentum.get('stochastic_k')}"
        ),
        (
            f"VOLATILITY: BB position={volatility.get('bb_position')}% | "
            f"ATR%={volatility.get('atr_vs_price_pct')}% | "
            f"BB squeeze={volatility.get('bb_squeeze')}"
        ),
        (
            f"VOLUME: ratio={volume.get('volume_ratio')}x vs 20d avg | "
            f"signal={volume.get('volume_signal')} | OBV trend={volume.get('obv_trend')}"
        ),
        (
            f"SUPPORT/RESISTANCE: "
            f"support={sr.get('nearest_support')} ({sr.get('distance_to_support_pct')}% away, "
            f"strength={sr.get('support_strength')}) | "
            f"resistance={sr.get('nearest_resistance')} ({sr.get('distance_to_resistance_pct')}% away, "
            f"strength={sr.get('resistance_strength')})"
        ),
        (
            f"SWING SETUP: verdict={swing.get('verdict', 'N/A')} | "
            f"score={swing.get('setup_score', 'N/A')}/100 | "
            f"uptrend_confirmed={swing.get('conditions', {}).get('uptrend_confirmed', 'N/A')}"
        ),
        (
            f"WEEKLY TREND: {weekly.get('weekly_trend', 'N/A')} "
            f"(strength={weekly.get('weekly_trend_strength', 'N/A')}) | "
            f"SMA10 vs SMA40={weekly.get('weekly_sma10_vs_sma40', 'N/A')}"
        ),
        f"CANDLESTICK PATTERNS: {pattern_strs}",
        "",
        f"=== APPLICABLE STRATEGIES (top {len(top_strategies)} matches) ===",
    ]

    for i, s in enumerate(top_strategies, 1):
        lines.append(f"\n--- Strategy {i}: {s.get('name', 'unnamed')} ---")
        lines.append(json.dumps(s, indent=2))

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_trade_ideas(
    ticker: str,
    strategies: list[dict],
    top_n: int = 3,
) -> str:
    """Fetch live signals, pick the best-matching strategies, generate ideas.

    Args:
        ticker:     Stock symbol (e.g. "AAPL").
        strategies: List of strategy dicts from strategy_store.
        top_n:      How many top-scoring strategies to send to Claude.

    Returns:
        Formatted trade idea narrative as a string.
    """
    print(f"  Fetching live signals for {ticker}…")
    signals = get_live_signals(ticker)

    scored = sorted(
        strategies,
        key=lambda s: _score_strategy(s, signals),
        reverse=True,
    )
    top_strategies = scored[:top_n]

    print(f"  Generating ideas using top {len(top_strategies)} strategies…")
    user_message = _build_user_message(ticker, signals, top_strategies)

    response = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        temperature=0.2,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text.strip()
