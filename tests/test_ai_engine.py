import sqlite3
from unittest.mock import patch

import pytest

from app.services.ai_engine import (
    build_user_message,
    get_cached_narrative,
    save_narrative,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

class _MockConn:
    """Wraps a sqlite3 connection to accept psycopg2-style %s placeholders."""

    def __init__(self, sqlite_conn: sqlite3.Connection) -> None:
        sqlite_conn.row_factory = sqlite3.Row
        self._conn = sqlite_conn

    def execute(self, sql: str, params=None):
        return self._conn.execute(sql.replace("%s", "?"), params)

    def executemany(self, sql: str, seq_of_params):
        return self._conn.executemany(sql.replace("%s", "?"), seq_of_params)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_analysis():
    return {
        "ticker": "AAPL",
        "price": 175.50,
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "trend": {
            "signal": "BULLISH",
            "price_vs_sma20": "above",
            "distance_from_sma20_pct": 2.1,
            "price_vs_sma50": "above",
            "distance_from_sma50_pct": 5.3,
            "price_vs_sma200": "above",
            "distance_from_sma200_pct": 12.4,
            "golden_cross": False,
            "death_cross": False,
        },
        "momentum": {
            "rsi": 58.3,
            "rsi_signal": "MODERATE_BULLISH",
            "macd": 1.234,
            "macd_signal": 0.987,
            "macd_histogram": 0.247,
            "macd_crossover": "none",
            "stochastic_k": 65.2,
            "stochastic_d": 62.1,
            "stochastic_signal": "NEUTRAL",
            "signal": "NEUTRAL",
        },
        "volatility": {
            "bb_upper": 180.0,
            "bb_middle": 172.0,
            "bb_lower": 164.0,
            "bb_width": 9.3,
            "bb_position": 55.0,
            "bb_squeeze": False,
            "atr": 2.8,
            "atr_vs_price_pct": 1.6,
            "signal": "NORMAL",
        },
        "volume": {
            "current_volume": 75_000_000,
            "avg_volume_20d": 60_000_000,
            "volume_ratio": 1.25,
            "volume_signal": "NORMAL",
            "obv": 1_200_000_000,
            "obv_trend": "RISING",
        },
        "support_resistance": {
            "high_52w": 198.0,
            "low_52w": 142.0,
            "distance_from_52w_high_pct": -11.4,
            "distance_from_52w_low_pct": 23.6,
            "swing_highs": [182.0, 179.0],
            "swing_lows": [168.0, 162.0],
            "nearest_resistance": 179.0,
            "nearest_support": 168.0,
            "distance_to_resistance_pct": 2.0,
            "distance_to_support_pct": 4.3,
        },
        "candlestick": [],
    }


@pytest.fixture
def in_memory_db(tmp_path):
    """Create an in-memory SQLite DB with the syntheses table."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS syntheses (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker_symbol  TEXT NOT NULL,
            generated_date TEXT NOT NULL,
            provider       TEXT NOT NULL,
            narrative      TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            UNIQUE(ticker_symbol, generated_date)
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def _make_mock_conn(db_path):
    return _MockConn(sqlite3.connect(str(db_path)))


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBuildUserMessage:
    def test_contains_ticker_and_price(self, sample_analysis):
        msg = build_user_message(sample_analysis)
        assert "AAPL" in msg
        assert "175.50" in msg

    def test_contains_trend_signal(self, sample_analysis):
        msg = build_user_message(sample_analysis)
        assert "BULLISH" in msg

    def test_contains_rsi_value(self, sample_analysis):
        msg = build_user_message(sample_analysis)
        assert "58.3" in msg

    def test_no_candlestick_section_says_none(self, sample_analysis):
        msg = build_user_message(sample_analysis)
        assert "none" in msg.lower()

    def test_candlestick_patterns_included(self, sample_analysis):
        sample_analysis["candlestick"] = [
            {"pattern": "hammer", "pattern_type": "bullish", "significance": "HIGH",
             "at_support": True, "at_resistance": False}
        ]
        msg = build_user_message(sample_analysis)
        assert "hammer" in msg


class TestCacheOperations:
    def test_get_cached_narrative_returns_none_on_miss(self, in_memory_db):
        with patch("app.services.ai_engine.get_db", side_effect=lambda: _make_mock_conn(in_memory_db)):
            result = get_cached_narrative("AAPL", "2099-01-01")
            assert result is None

    def test_save_and_retrieve_narrative(self, in_memory_db):
        with patch("app.services.ai_engine.get_db", side_effect=lambda: _make_mock_conn(in_memory_db)):
            save_narrative("AAPL", "2024-01-15", "anthropic", "Test narrative text.")
            result = get_cached_narrative("AAPL", "2024-01-15")

        assert result == "Test narrative text."

    def test_save_narrative_upserts_on_conflict(self, in_memory_db):
        with patch("app.services.ai_engine.get_db", side_effect=lambda: _make_mock_conn(in_memory_db)):
            save_narrative("AAPL", "2024-01-15", "anthropic", "First version.")
            save_narrative("AAPL", "2024-01-15", "anthropic", "Updated version.")
            result = get_cached_narrative("AAPL", "2024-01-15")

        assert result == "Updated version."
