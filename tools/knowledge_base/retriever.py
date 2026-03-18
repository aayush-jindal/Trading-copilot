"""Step 2: Translate live signals into a semantic query, retrieve relevant book passages."""

from __future__ import annotations

from .config import EMBED_MODEL, OPENAI_API_KEY, TOP_K_RETRIEVAL


# ── Query builder ─────────────────────────────────────────────────────────────

def build_signal_query(signals: dict) -> str:
    """Convert live signal dict into a natural-language retrieval query.

    The query is designed to match book passages that discuss the same
    market conditions — so retrieval is contextually relevant, not generic.
    """
    parts: list[str] = []

    trend = signals.get("trend", {})
    momentum = signals.get("momentum", {})
    volatility = signals.get("volatility", {})
    volume = signals.get("volume", {})
    swing = signals.get("swing_setup") or {}
    weekly = signals.get("weekly_trend") or {}
    candlestick = signals.get("candlestick", [])

    # Trend context
    trend_sig = trend.get("signal", "")
    if trend_sig == "BULLISH":
        parts.append("uptrend bullish trend following price above moving averages")
        if trend.get("golden_cross"):
            parts.append("golden cross SMA50 SMA200 crossover")
    elif trend_sig == "BEARISH":
        parts.append("downtrend bearish price below moving averages")
        if trend.get("death_cross"):
            parts.append("death cross bearish crossover")
    else:
        parts.append("sideways consolidation ranging market")

    # Weekly trend alignment
    weekly_trend = weekly.get("weekly_trend", "")
    if weekly_trend == "BULLISH":
        parts.append("weekly uptrend multi-timeframe alignment higher timeframe bullish")
    elif weekly_trend == "BEARISH":
        parts.append("weekly downtrend higher timeframe bearish")

    # Swing setup
    verdict = swing.get("verdict", "")
    if verdict == "ENTRY":
        parts.append("pullback in uptrend entry signal swing trade setup near support")
    elif verdict == "WATCH":
        parts.append("pullback setup developing watch for entry swing trade")

    # RSI / momentum
    rsi = momentum.get("rsi", 50)
    rsi_sig = momentum.get("rsi_signal", "")
    if rsi_sig == "OVERSOLD" or rsi < 35:
        parts.append("RSI oversold bounce mean reversion buying opportunity")
    elif rsi_sig == "OVERBOUGHT" or rsi > 70:
        parts.append("RSI overbought extended momentum reversal risk")
    elif rsi_sig in ("MODERATE_BULLISH", "BULLISH"):
        parts.append("RSI pullback from overbought momentum reset")

    # MACD
    macd_cross = momentum.get("macd_crossover", "none")
    if macd_cross == "bullish_crossover":
        parts.append("MACD bullish crossover momentum entry signal")
    elif macd_cross == "bearish_crossover":
        parts.append("MACD bearish crossover sell signal")

    # Volatility
    if volatility.get("bb_squeeze"):
        parts.append("Bollinger Band squeeze volatility contraction breakout setup")
    bb_pos = volatility.get("bb_position", 50)
    if bb_pos < 20:
        parts.append("price at lower Bollinger Band support oversold")
    elif bb_pos > 80:
        parts.append("price at upper Bollinger Band resistance overbought")

    # Volume
    vol_sig = volume.get("volume_signal", "")
    if vol_sig == "HIGH":
        parts.append("high volume confirmation institutional buying climax")
    obv_trend = volume.get("obv_trend", "")
    if obv_trend == "RISING":
        parts.append("OBV rising accumulation on-balance volume bullish")
    elif obv_trend == "FALLING":
        parts.append("OBV falling distribution selling pressure bearish")

    # Candlestick patterns
    for pattern in candlestick:
        name = pattern.get("pattern", "")
        ptype = pattern.get("pattern_type", "")
        if name:
            parts.append(f"{name} candlestick pattern {ptype}")

    return " ".join(parts) if parts else "technical analysis trading strategy setup"


# ── Embedding + retrieval ─────────────────────────────────────────────────────

def _embed_query(query: str) -> list[float]:
    """Embed a single query string via OpenAI text-embedding-3-small."""
    from openai import OpenAI  # noqa: PLC0415
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(model=EMBED_MODEL, input=[query])
    return response.data[0].embedding


def _vec_str(embedding: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


def retrieve_relevant_chunks(
    signals: dict,
    top_k: int = TOP_K_RETRIEVAL,
    book_type: str | None = None,
) -> list[dict]:
    """Return the top-k most relevant book passages for the current signals.

    Each result dict has keys: source_file, page_num, content, similarity.

    Args:
        book_type: Optional filter — 'equity_ta' or 'options_strategy'.
                   When None (default), retrieves from all books.
    """
    from app.database import get_db  # lazy import

    query = build_signal_query(signals)
    print(f"  Retrieval query: {query[:120]}…")

    query_vec = _embed_query(query)
    vec_literal = _vec_str(query_vec)

    conn = get_db()
    try:
        if book_type is not None:
            rows = conn.execute(
                """
                SELECT source_file,
                       page_num,
                       content,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM   knowledge_chunks
                WHERE  book_type = %s
                ORDER BY embedding <=> %s::vector
                LIMIT  %s
                """,
                (vec_literal, book_type, vec_literal, top_k),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT source_file,
                       page_num,
                       content,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM   knowledge_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT  %s
                """,
                (vec_literal, vec_literal, top_k),
            ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows] if rows else []
