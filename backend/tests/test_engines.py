"""Smoke tests for root analysis engines.

These tests verify the core engines can be imported and their main
functions produce valid output structures — without requiring live
market data or database connectivity.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Ensure project root is importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# ranking_engine tests
# ---------------------------------------------------------------------------

class TestRankingEngine:
    def test_import(self):
        import ranking_engine
        assert hasattr(ranking_engine, "_load_best_setup_map")
        assert hasattr(ranking_engine, "invalidate_best_setup_cache")

    def test_load_best_setup_map_returns_dict(self):
        from ranking_engine import _load_best_setup_map
        result = _load_best_setup_map()
        assert isinstance(result, dict)

    def test_invalidate_cache(self):
        from ranking_engine import invalidate_best_setup_cache, _load_best_setup_map
        # Should not raise
        invalidate_best_setup_cache()
        result = _load_best_setup_map()
        assert isinstance(result, dict)

    def test_safe_float(self):
        from ranking_engine import _safe_float
        assert _safe_float("1.5") == 1.5
        assert _safe_float(None, 0.0) == 0.0
        assert _safe_float("bad", 99.0) == 99.0
        assert _safe_float("", 0.0) == 0.0

    def test_safe_int(self):
        from ranking_engine import _safe_int
        assert _safe_int("5") == 5
        assert _safe_int(None, 0) == 0
        assert _safe_int("bad", 10) == 10

    def test_signal_bias(self):
        from ranking_engine import _signal_bias
        assert _signal_bias({"enhanced_signal": "BUY"}) == 1
        assert _signal_bias({"enhanced_signal": "SELL"}) == -1
        assert _signal_bias({"enhanced_signal": "HOLD"}) == 0
        assert _signal_bias({"signal": "BUY"}) == 1
        assert _signal_bias({}) == 0


# ---------------------------------------------------------------------------
# technical_engine tests
# ---------------------------------------------------------------------------

class TestTechnicalEngine:
    def test_import(self):
        import technical_engine
        assert hasattr(technical_engine, "calculate_technical_indicators")

    def test_calculate_with_minimal_data(self):
        import pandas as pd
        from technical_engine import calculate_technical_indicators

        # Create minimal OHLCV dataframe in the common yfinance-style format:
        # datetime index with capitalized OHLCV column names.
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        df = pd.DataFrame({
            "Open": [100 + i * 0.5 for i in range(60)],
            "High": [101 + i * 0.5 for i in range(60)],
            "Low": [99 + i * 0.5 for i in range(60)],
            "Close": [100.5 + i * 0.5 for i in range(60)],
            "Volume": [1000000] * 60,
        }, index=dates)

        result = calculate_technical_indicators(df)
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert {"datetime", "close", "rsi14", "technical_score", "final_signal"}.issubset(result.columns)


# ---------------------------------------------------------------------------
# analysis_engine tests
# ---------------------------------------------------------------------------

class TestAnalysisEngine:
    def test_import(self):
        import analysis_engine
        assert hasattr(analysis_engine, "_safe_round")
        assert hasattr(analysis_engine, "_combined_signal")

    def test_safe_round(self):
        from analysis_engine import _safe_round
        assert _safe_round(1.23456, 2) == 1.23
        assert _safe_round(None) is None
        assert _safe_round(float("nan")) is None

    def test_combined_signal(self):
        from analysis_engine import _combined_signal
        assert _combined_signal(5) == "BUY"
        assert _combined_signal(-5) == "SELL"
        assert _combined_signal(0) == "HOLD"
        assert _combined_signal(3) == "BUY"
        assert _combined_signal(-3) == "SELL"
        assert _combined_signal(2) == "HOLD"

    def test_fallback_news_payload(self):
        from analysis_engine import _fallback_news_payload
        result = _fallback_news_payload("test error")
        assert result["news_score"] == 0
        assert result["news_sentiment"] == "NEUTRAL"
        assert result["ai_enabled"] is False
        assert "test error" in result["ai_error"]

    def test_ml_score_from_result(self):
        from analysis_engine import _ml_score_from_result
        assert _ml_score_from_result(None) == 0
        assert _ml_score_from_result({"error": "oops"}) == 0
        assert _ml_score_from_result({}) == 0


# ---------------------------------------------------------------------------
# backtest_engine tests
# ---------------------------------------------------------------------------

class TestBacktestEngine:
    def test_import(self):
        import backtest_engine
        # Just verify it imports without error
        assert backtest_engine is not None
