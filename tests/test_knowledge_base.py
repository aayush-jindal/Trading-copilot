"""Unit tests for tools/knowledge_base — no DB, no API, no models needed."""

# ── pdf_ingester: _chunk_text & _vec_str ──────────────────────────────────────

from tools.knowledge_base.pdf_ingester import _chunk_text, _vec_str


class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        chunks = _chunk_text("A" * 500, size=1500, overlap=200)
        assert len(chunks) == 1

    def test_long_text_splits_into_multiple_chunks(self):
        chunks = _chunk_text("A" * 5000, size=1500, overlap=200)
        assert len(chunks) > 1

    def test_each_chunk_does_not_exceed_size(self):
        chunks = _chunk_text("A" * 5000, size=1500, overlap=200)
        assert all(len(c) <= 1500 for c in chunks)

    def test_empty_text_returns_empty_list(self):
        assert _chunk_text("", size=1500, overlap=200) == []

    def test_whitespace_only_returns_empty_list(self):
        assert _chunk_text("   \n\t   ", size=1500, overlap=200) == []

    def test_tiny_chunks_filtered_out(self):
        # Chunks under 50 chars are dropped by the filter
        chunks = _chunk_text("A" * 5000, size=1500, overlap=200)
        assert all(len(c) >= 50 for c in chunks)

    def test_overlap_produces_more_chunks_than_no_overlap(self):
        text = "X" * 4000
        with_overlap    = _chunk_text(text, size=1500, overlap=400)
        without_overlap = _chunk_text(text, size=1500, overlap=0)
        assert len(with_overlap) >= len(without_overlap)

    def test_returns_list_of_strings(self):
        chunks = _chunk_text("Hello world " * 200, size=1500, overlap=100)
        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)


class TestVecStr:
    def test_bracket_delimited(self):
        result = _vec_str([0.1, 0.2, 0.3])
        assert result.startswith("[") and result.endswith("]")

    def test_values_comma_separated(self):
        result = _vec_str([0.1, 0.2])
        assert "," in result

    def test_eight_decimal_places(self):
        result = _vec_str([0.123456789])
        inner = result[1:-1]           # strip brackets
        decimal_part = inner.split(".")[1]
        assert len(decimal_part) == 8

    def test_single_value(self):
        result = _vec_str([1.0])
        assert result == "[1.00000000]"

    def test_empty_list(self):
        result = _vec_str([])
        assert result == "[]"


# ── retriever: build_signal_query ─────────────────────────────────────────────

from tools.knowledge_base.retriever import build_signal_query  # noqa: E402


class TestBuildSignalQuery:
    """build_signal_query is pure Python — no DB or embedding calls."""

    def _q(self, signals: dict) -> str:
        return build_signal_query(signals).lower()

    def test_returns_string(self):
        assert isinstance(build_signal_query({}), str)

    def test_empty_signals_returns_non_empty_string(self):
        # Empty dict still produces output via the neutral/sideways branch
        q = self._q({})
        assert len(q) > 0

    # Trend signals
    def test_bullish_trend(self):
        q = self._q({"trend": {"signal": "BULLISH", "golden_cross": False, "death_cross": False}})
        assert "bullish" in q or "uptrend" in q

    def test_golden_cross(self):
        q = self._q({"trend": {"signal": "BULLISH", "golden_cross": True}})
        assert "golden cross" in q

    def test_bearish_trend(self):
        q = self._q({"trend": {"signal": "BEARISH", "golden_cross": False, "death_cross": False}})
        assert "bearish" in q or "downtrend" in q

    def test_death_cross(self):
        q = self._q({"trend": {"signal": "BEARISH", "death_cross": True}})
        assert "death cross" in q

    def test_neutral_trend(self):
        q = self._q({"trend": {"signal": "NEUTRAL", "golden_cross": False, "death_cross": False}})
        assert "sideways" in q or "consolidation" in q or "ranging" in q

    # Momentum signals
    def test_rsi_oversold_by_signal(self):
        q = self._q({"momentum": {"rsi": 50, "rsi_signal": "OVERSOLD"}})
        assert "oversold" in q

    def test_rsi_oversold_by_value(self):
        q = self._q({"momentum": {"rsi": 28, "rsi_signal": "NEUTRAL"}})
        assert "oversold" in q

    def test_rsi_overbought_by_signal(self):
        q = self._q({"momentum": {"rsi": 50, "rsi_signal": "OVERBOUGHT"}})
        assert "overbought" in q

    def test_rsi_overbought_by_value(self):
        q = self._q({"momentum": {"rsi": 75, "rsi_signal": "NEUTRAL"}})
        assert "overbought" in q

    def test_macd_bullish_crossover(self):
        q = self._q({"momentum": {"macd_crossover": "bullish_crossover", "rsi": 50}})
        assert "macd" in q and "bullish" in q

    def test_macd_bearish_crossover(self):
        q = self._q({"momentum": {"macd_crossover": "bearish_crossover", "rsi": 50}})
        assert "macd" in q and "bearish" in q

    # Volatility
    def test_bb_squeeze(self):
        q = self._q({"volatility": {"bb_squeeze": True, "bb_position": 50}})
        assert "squeeze" in q or "bollinger" in q

    def test_bb_at_lower_band(self):
        q = self._q({"volatility": {"bb_squeeze": False, "bb_position": 10}})
        assert "lower bollinger" in q or "oversold" in q

    def test_bb_at_upper_band(self):
        q = self._q({"volatility": {"bb_squeeze": False, "bb_position": 85}})
        assert "upper bollinger" in q or "overbought" in q

    # Volume
    def test_high_volume(self):
        q = self._q({"volume": {"volume_signal": "HIGH", "obv_trend": "FLAT"}})
        assert "volume" in q

    def test_obv_rising(self):
        q = self._q({"volume": {"volume_signal": "NORMAL", "obv_trend": "RISING"}})
        assert "obv" in q or "accumulation" in q

    def test_obv_falling(self):
        q = self._q({"volume": {"volume_signal": "NORMAL", "obv_trend": "FALLING"}})
        assert "obv" in q or "distribution" in q

    # Swing setup
    def test_swing_entry(self):
        q = self._q({"swing_setup": {"verdict": "ENTRY"}})
        assert "pullback" in q or "entry" in q or "swing" in q

    def test_swing_watch(self):
        q = self._q({"swing_setup": {"verdict": "WATCH"}})
        assert "pullback" in q or "watch" in q or "swing" in q

    # Weekly trend
    def test_weekly_bullish(self):
        q = self._q({"weekly_trend": {"weekly_trend": "BULLISH"}})
        assert "weekly" in q or "uptrend" in q

    def test_weekly_bearish(self):
        q = self._q({"weekly_trend": {"weekly_trend": "BEARISH"}})
        assert "weekly" in q or "bearish" in q

    # Candlestick patterns
    def test_candlestick_pattern_included(self):
        q = self._q({"candlestick": [{"pattern": "hammer", "pattern_type": "bullish"}]})
        assert "hammer" in q

    def test_multiple_candlestick_patterns(self):
        signals = {
            "candlestick": [
                {"pattern": "doji", "pattern_type": "neutral"},
                {"pattern": "engulfing", "pattern_type": "bullish"},
            ]
        }
        q = self._q(signals)
        assert "doji" in q
        assert "engulfing" in q


# ── strategy_gen: _format_signals & _format_passages ──────────────────────────

from tools.knowledge_base.strategy_gen import _format_passages, _format_signals  # noqa: E402

_SAMPLE_SIGNALS = {
    "price": 213.45,
    "trend": {
        "signal": "BULLISH",
        "price_vs_sma50": "above",
        "price_vs_sma200": "above",
        "golden_cross": True,
        "death_cross": False,
    },
    "momentum": {
        "rsi": 54.2,
        "rsi_signal": "MODERATE_BULLISH",
        "macd_crossover": "none",
        "stochastic_k": 62.0,
    },
    "volatility": {"bb_position": 48.0, "atr_vs_price_pct": 1.2, "bb_squeeze": False},
    "volume": {"volume_ratio": 1.1, "volume_signal": "NORMAL", "obv_trend": "RISING"},
    "support_resistance": {
        "nearest_support": 208.0,
        "distance_to_support_pct": 2.6,
        "support_strength": "STRONG",
        "nearest_resistance": 220.0,
        "distance_to_resistance_pct": 3.1,
        "resistance_strength": "MODERATE",
    },
    "swing_setup": {"verdict": "WATCH", "setup_score": 62, "conditions": {"uptrend_confirmed": True}},
    "weekly_trend": {"weekly_trend": "BULLISH", "weekly_trend_strength": "STRONG", "weekly_sma10_vs_sma40": "above"},
    "candlestick": [{"pattern": "hammer", "pattern_type": "bullish"}],
}


class TestFormatSignals:
    def test_ticker_in_output(self):
        result = _format_signals("AAPL", _SAMPLE_SIGNALS)
        assert "AAPL" in result

    def test_price_in_output(self):
        result = _format_signals("AAPL", _SAMPLE_SIGNALS)
        assert "213.45" in result

    def test_live_market_signals_header(self):
        result = _format_signals("AAPL", _SAMPLE_SIGNALS)
        assert "LIVE MARKET SIGNALS" in result

    def test_trend_signal_present(self):
        result = _format_signals("AAPL", _SAMPLE_SIGNALS)
        assert "BULLISH" in result

    def test_rsi_value_present(self):
        result = _format_signals("AAPL", _SAMPLE_SIGNALS)
        assert "54.2" in result

    def test_candlestick_pattern_present(self):
        result = _format_signals("AAPL", _SAMPLE_SIGNALS)
        assert "hammer" in result

    def test_empty_signals_does_not_crash(self):
        result = _format_signals("TEST", {})
        assert isinstance(result, str)
        assert "TEST" in result

    def test_returns_string(self):
        assert isinstance(_format_signals("X", _SAMPLE_SIGNALS), str)


class TestFormatPassages:
    def test_empty_chunks_returns_fallback(self):
        result = _format_passages([])
        assert len(result) > 0
        # Should mention the empty state
        assert any(word in result.lower() for word in ("empty", "ingest", "no relevant", "knowledge base"))

    def test_chunk_source_file_shown(self):
        chunks = [{"source_file": "murphy.pdf", "page_num": 47, "content": "text", "similarity": 0.85}]
        result = _format_passages(chunks)
        assert "murphy.pdf" in result

    def test_chunk_page_number_shown(self):
        chunks = [{"source_file": "book.pdf", "page_num": 99, "content": "text", "similarity": 0.9}]
        result = _format_passages(chunks)
        assert "99" in result

    def test_chunk_content_shown(self):
        chunks = [{"source_file": "book.pdf", "page_num": 1, "content": "RSI oversold bounce", "similarity": 0.88}]
        result = _format_passages(chunks)
        assert "RSI oversold bounce" in result

    def test_similarity_score_shown(self):
        chunks = [{"source_file": "book.pdf", "page_num": 1, "content": "text", "similarity": 0.912}]
        result = _format_passages(chunks)
        assert "0.912" in result

    def test_multiple_chunks_numbered(self):
        chunks = [
            {"source_file": "a.pdf", "page_num": 1, "content": "first",  "similarity": 0.9},
            {"source_file": "b.pdf", "page_num": 2, "content": "second", "similarity": 0.8},
            {"source_file": "c.pdf", "page_num": 3, "content": "third",  "similarity": 0.7},
        ]
        result = _format_passages(chunks)
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result

    def test_chunks_separated_by_dashes(self):
        chunks = [
            {"source_file": "a.pdf", "page_num": 1, "content": "text1", "similarity": 0.9},
            {"source_file": "b.pdf", "page_num": 2, "content": "text2", "similarity": 0.8},
        ]
        result = _format_passages(chunks)
        assert "---" in result
