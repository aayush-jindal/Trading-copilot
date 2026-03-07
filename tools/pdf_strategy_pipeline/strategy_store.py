"""Step 3: Persist and retrieve extracted strategies as JSON."""

from __future__ import annotations

import json
import os


def save_strategies(strategies: list[dict], path: str) -> None:
    """Write strategy list to a JSON file, creating parent dirs if needed."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(strategies, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(strategies)} strategies → {path}")


def load_strategies(path: str) -> list[dict]:
    """Load strategies from JSON file. Returns [] if file is missing."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def list_strategies(path: str) -> None:
    """Print a numbered summary of all stored strategies."""
    strategies = load_strategies(path)
    if not strategies:
        print(f"No strategies found at {path}")
        return
    print(f"\n{len(strategies)} strategies in {path}:\n")
    for i, s in enumerate(strategies, 1):
        name = s.get("name", "unnamed")
        ptype = s.get("pattern_type", "?")
        tf = s.get("timeframe", "?")
        indicators = ", ".join(s.get("indicators", [])) or "—"
        print(f"  {i:2}. [{ptype} / {tf}]  {name}")
        print(f"       indicators: {indicators}")
