"""Step 3: Retrieved book passages + live signals → Claude → actionable strategies."""

from __future__ import annotations

from .config import ANTHROPIC_API_KEY, TOP_K_RETRIEVAL  # noqa: F401 (used inside fns)

_CLIENT = None


def _client():
    """Lazy Anthropic client — imported inside function so the module loads without anthropic installed."""
    global _CLIENT
    if _CLIENT is None:
        import anthropic  # noqa: PLC0415
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        _CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _CLIENT


_SYSTEM_PROMPT = """\
You are a professional trading strategist with deep knowledge of technical analysis literature.

You have been given two inputs:
1. LIVE MARKET SIGNALS — current technical data for a specific stock.
2. KNOWLEDGE BASE PASSAGES — excerpts retrieved from equity technical analysis books that are \
semantically relevant to the current market conditions.

Your task is to synthesize these into a JSON response. Return ONLY valid JSON — no markdown, \
no prose outside the JSON object.

Return exactly this structure:
{
  "strategies": [
    {
      "name": "string — strategy name from the book context",
      "conditions_status": "MET | PARTIAL | NOT MET",
      "conditions_detail": "string — which conditions are met and why, referencing the live signals",
      "conviction": "HIGH | MEDIUM | LOW",
      "sources": [{"book": "string", "page": 0, "rule": "string — specific rule or principle cited"}],
      "confirmation_signals": ["string — what else to look for before entering"],
      "invalidation_signals": ["string — what would make this setup fail"]
    }
  ],
  "best_opportunity": {
    "strategy_name": "string",
    "rationale": "string — why this is the strongest setup right now",
    "conviction": "HIGH | MEDIUM | LOW"
  },
  "signals_to_watch": ["string — key levels or conditions to monitor"]
}

Rules:
- Return ONLY the JSON object. No text before or after it.
- Ground every strategy in the retrieved passages — cite book and page in sources.
- Do not include entry_zone, stop_loss, or target price fields — those are computed elsewhere.
- Do not invent strategies not supported by the retrieved passages.
- If no strategies apply, return strategies as an empty array and best_opportunity as null.\
"""


# ── Signal formatter (adapted from idea_generator.py) ─────────────────────────

def _format_signals(ticker: str, signals: dict) -> str:
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
        f"TICKER: {ticker.upper()} | PRICE: ${price:.2f}",
        "",
        "=== LIVE MARKET SIGNALS ===",
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
    ]
    return "\n".join(lines)


def _format_passages(chunks: list[dict]) -> str:
    if not chunks:
        return "(No relevant passages found — knowledge base may be empty. Run 'ingest' first.)"
    lines: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_file", "unknown")
        page = chunk.get("page_num", "?")
        sim = chunk.get("similarity", 0)
        lines.append(f"[{i}] Source: {source}, p.{page}  (similarity: {sim:.3f})")
        lines.append(chunk.get("content", ""))
        lines.append("---")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_strategies(ticker: str, top_k: int = TOP_K_RETRIEVAL) -> dict:
    """Full RAG pipeline: signals → retrieve (equity_ta only) → Claude → JSON dict.

    Args:
        ticker: Stock symbol, e.g. "AAPL".
        top_k:  Number of book passages to retrieve.

    Returns:
        Parsed JSON dict with keys: strategies, best_opportunity, signals_to_watch.
    """
    import json  # noqa: PLC0415
    from tools.pdf_strategy_pipeline.market_connector import get_live_signals  # lazy
    from .retriever import retrieve_relevant_chunks  # local

    print(f"  Fetching live signals for {ticker.upper()}…")
    signals = get_live_signals(ticker)

    print(f"  Retrieving top {top_k} equity_ta passages…")
    chunks = retrieve_relevant_chunks(signals, top_k=top_k, book_type="equity_ta")
    print(f"  Retrieved {len(chunks)} passages.")

    user_message = "\n\n".join([
        _format_signals(ticker, signals),
        "=== KNOWLEDGE BASE (retrieved passages) ===",
        _format_passages(chunks),
    ])

    print("  Generating strategies via Claude…")
    response = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        temperature=0.2,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if the model wraps the JSON despite instructions
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]          # drop opening fence line
        raw = raw.rsplit("```", 1)[0].strip()  # drop closing fence
    return json.loads(raw)
