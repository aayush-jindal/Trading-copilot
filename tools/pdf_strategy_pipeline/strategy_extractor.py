"""Step 2: Text chunks → structured trading strategies via Claude."""

from __future__ import annotations

import json
import re

import anthropic

from .config import ANTHROPIC_API_KEY

_CLIENT = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        _CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _CLIENT


_SYSTEM_PROMPT = """\
You are a technical analysis expert extracting structured trading strategies from educational material.

For each distinct strategy or setup you identify, output a JSON object with exactly these fields:
  - name:             short strategy name (string)
  - entry_conditions: list of specific entry rules (list of strings)
  - exit_conditions:  list of exit / stop-loss rules (list of strings)
  - indicators:       list of technical indicators used (list of strings)
  - timeframe:        intended timeframe — "intraday", "daily", "weekly", or "any" (string)
  - pattern_type:     one of "trend_following" | "mean_reversion" | "breakout" | "pullback" | "other"
  - notes:            any important caveats or context (string)

Return a JSON array of strategy objects. If no strategies are found in the excerpt, return [].
Do not include any text outside the JSON array.\
"""


def _extract_from_chunk(chunk: str, chunk_idx: int) -> list[dict]:
    """Send one chunk to Claude and return parsed strategy list."""
    user_message = (
        f"Analyze this excerpt (chunk {chunk_idx + 1}) and extract all trading strategies:\n\n{chunk}"
    )
    try:
        response = _client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            temperature=0.1,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        # Claude sometimes wraps JSON in markdown fences — strip them
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, IndexError, anthropic.APIError) as exc:
        print(f"  [warn] chunk {chunk_idx + 1} skipped: {exc}")
        return []


def extract_strategies_from_chunks(chunks: list[str]) -> list[dict]:
    """Process all chunks, deduplicate by name, return merged strategy list."""
    all_strategies: list[dict] = []
    seen_names: set[str] = set()

    for idx, chunk in enumerate(chunks):
        print(f"  Extracting from chunk {idx + 1}/{len(chunks)}…")
        strategies = _extract_from_chunk(chunk, idx)
        for s in strategies:
            name = str(s.get("name", "")).strip().lower()
            if name and name not in seen_names:
                seen_names.add(name)
                all_strategies.append(s)

    return all_strategies
