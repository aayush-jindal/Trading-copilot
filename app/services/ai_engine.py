from __future__ import annotations

import datetime
from typing import AsyncGenerator

import anthropic
import openai

from app.config import ANTHROPIC_API_KEY, OPENAI_API_KEY, SYNTHESIS_PROVIDER
from app.database import get_db


def get_cached_narrative(symbol: str, date_str: str) -> str | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT narrative FROM syntheses WHERE ticker_symbol = %s AND generated_date = %s",
            (symbol, date_str),
        ).fetchone()
        return row["narrative"] if row else None
    finally:
        conn.close()


def save_narrative(symbol: str, date_str: str, provider: str, narrative: str) -> None:
    created_at = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO syntheses (ticker_symbol, generated_date, provider, narrative, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (ticker_symbol, generated_date)
            DO UPDATE SET narrative = EXCLUDED.narrative, created_at = EXCLUDED.created_at
            """,
            (symbol, date_str, provider, narrative, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def build_system_prompt() -> str:
    return (
        "You are a trading copilot — a concise, professional technical analyst who synthesizes "
        "quantitative signals into clear, readable narrative.\n\n"
        "Guidelines:\n"
        "- Write 3–4 short paragraphs, staying within 600 tokens total\n"
        "- Lead with the overall directional bias (bullish / bearish / neutral) and the primary reason\n"
        "- Reference specific numbers: price, key moving averages, RSI level, nearest support/resistance\n"
        "- Note any confirming or conflicting signals across categories (e.g. bullish trend but overbought RSI)\n"
        "- If candlestick patterns are present and significant, mention them\n"
        "- Close with a one-sentence actionable takeaway\n"
        "- Tone: direct, confident, factual — no hedging phrases, no markdown headers or bullet points"
    )


def build_user_message(analysis: dict) -> str:
    ticker = analysis.get("ticker", "N/A")
    price = analysis.get("price", 0)
    company_name = analysis.get("company_name")
    sector = analysis.get("sector")

    trend = analysis.get("trend", {})
    momentum = analysis.get("momentum", {})
    volatility = analysis.get("volatility", {})
    volume = analysis.get("volume", {})
    sr = analysis.get("support_resistance", {})
    candlestick = analysis.get("candlestick", [])

    lines = [f"Ticker: {ticker} | Price: ${price:.2f}"]
    if company_name:
        lines.append(f"Company: {company_name}" + (f" | Sector: {sector}" if sector else ""))

    lines.append(
        f"\nTREND: signal={trend.get('signal')} | "
        f"vs SMA20={trend.get('price_vs_sma20')} ({trend.get('distance_from_sma20_pct')}%) | "
        f"vs SMA50={trend.get('price_vs_sma50')} ({trend.get('distance_from_sma50_pct')}%) | "
        f"vs SMA200={trend.get('price_vs_sma200')} ({trend.get('distance_from_sma200_pct')}%) | "
        f"golden_cross={trend.get('golden_cross')} | death_cross={trend.get('death_cross')}"
    )

    lines.append(
        f"\nMOMENTUM: RSI={momentum.get('rsi')} ({momentum.get('rsi_signal')}) | "
        f"MACD={momentum.get('macd')} / signal={momentum.get('macd_signal')} / hist={momentum.get('macd_histogram')} | "
        f"MACD crossover={momentum.get('macd_crossover')} | "
        f"Stochastic K={momentum.get('stochastic_k')} D={momentum.get('stochastic_d')} ({momentum.get('stochastic_signal')})"
    )

    lines.append(
        f"\nVOLATILITY: BB position={volatility.get('bb_position')}% | "
        f"ATR%={volatility.get('atr_vs_price_pct')}% | "
        f"BB squeeze={volatility.get('bb_squeeze')} | signal={volatility.get('signal')}"
    )

    lines.append(
        f"\nVOLUME: ratio vs 20d avg={volume.get('volume_ratio')}x | "
        f"signal={volume.get('volume_signal')} | OBV trend={volume.get('obv_trend')}"
    )

    lines.append(
        f"\nSUPPORT/RESISTANCE: nearest resistance={sr.get('nearest_resistance')} "
        f"({sr.get('distance_to_resistance_pct')}% away) | "
        f"nearest support={sr.get('nearest_support')} ({sr.get('distance_to_support_pct')}% away)"
    )

    if candlestick:
        pattern_strs = [
            f"{p['pattern']} ({p['pattern_type']}, significance={p['significance']})"
            for p in candlestick
        ]
        lines.append(f"\nCANDLESTICK PATTERNS: {', '.join(pattern_strs)}")
    else:
        lines.append("\nCANDLESTICK PATTERNS: none")

    return "\n".join(lines)


async def stream_narrative(analysis: dict) -> AsyncGenerator[str, None]:
    ticker = analysis.get("ticker", "")
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    cached = get_cached_narrative(ticker, date_str)
    if cached is not None:
        yield cached
        yield "[DONE]"
        return

    provider = SYNTHESIS_PROVIDER
    if provider not in {"anthropic", "openai"}:
        raise ValueError(f"Unknown SYNTHESIS_PROVIDER: {provider!r}. Must be 'anthropic' or 'openai'.")

    if provider == "anthropic" and not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    if provider == "openai" and not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    system_prompt = build_system_prompt()
    user_message = build_user_message(analysis)
    full_narrative: list[str] = []

    if provider == "anthropic":
        try:
            async with anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY).messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=600,
                temperature=0.3,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                async for text in stream.text_stream:
                    full_narrative.append(text)
                    yield text
        except anthropic.BadRequestError as e:
            if "content filtering policy" in str(e).lower() or "output blocked" in str(e).lower():
                raise RuntimeError(
                    f"AI narrative unavailable for {ticker} — the content was flagged by "
                    "Anthropic's safety policy. Try switching to OpenAI (SYNTHESIS_PROVIDER=openai)."
                )
            raise
    else:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=600,
            temperature=0.3,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content or ""
            if text:
                full_narrative.append(text)
                yield text

    save_narrative(ticker, date_str, provider, "".join(full_narrative))
    yield "[DONE]"
