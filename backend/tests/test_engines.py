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
        from core.legacy_adapters import ranking
        assert hasattr(ranking, "load_best_setup_map")
        assert hasattr(ranking, "invalidate_best_setup_cache")

    def test_load_best_setup_map_returns_dict(self):
        from core.legacy_adapters.ranking import load_best_setup_map
        result = load_best_setup_map()
        assert isinstance(result, dict)

    def test_invalidate_cache(self):
        from core.legacy_adapters.ranking import invalidate_best_setup_cache, load_best_setup_map
        # Should not raise
        invalidate_best_setup_cache()
        result = load_best_setup_map()
        assert isinstance(result, dict)

    def test_safe_float(self):
        from core.legacy_adapters.ranking import safe_float
        assert safe_float("1.5") == 1.5
        assert safe_float(None, 0.0) == 0.0
        assert safe_float("bad", 99.0) == 99.0
        assert safe_float("", 0.0) == 0.0

    def test_safe_int(self):
        from core.legacy_adapters.ranking import safe_int
        assert safe_int("5") == 5
        assert safe_int(None, 0) == 0
        assert safe_int("bad", 10) == 10

    def test_signal_bias(self):
        from core.legacy_adapters.ranking import signal_bias
        assert signal_bias({"enhanced_signal": "BUY"}) == 1
        assert signal_bias({"enhanced_signal": "SELL"}) == -1
        assert signal_bias({"enhanced_signal": "HOLD"}) == 0
        assert signal_bias({"signal": "BUY"}) == 1
        assert signal_bias({}) == 0


# ---------------------------------------------------------------------------
# technical_engine tests
# ---------------------------------------------------------------------------

class TestTechnicalEngine:
    def test_import(self):
        from core.legacy_adapters import technical
        assert hasattr(technical, "calculate_technical_indicators")

    def test_calculate_with_minimal_data(self):
        import pandas as pd
        from core.legacy_adapters.technical import calculate_technical_indicators

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
        from core.legacy_adapters import analysis
        assert hasattr(analysis, "safe_round")
        assert hasattr(analysis, "combined_signal")

    def test_safe_round(self):
        from core.legacy_adapters.analysis import safe_round
        assert safe_round(1.23456, 2) == 1.23
        assert safe_round(None) is None
        assert safe_round(float("nan")) is None

    def test_combined_signal(self):
        from core.legacy_adapters.analysis import combined_signal
        assert combined_signal(5) == "BUY"
        assert combined_signal(-5) == "SELL"
        assert combined_signal(0) == "HOLD"
        assert combined_signal(3) == "BUY"
        assert combined_signal(-3) == "SELL"
        assert combined_signal(2) == "HOLD"

    def test_fallback_news_payload(self):
        from core.legacy_adapters.analysis import fallback_news_payload
        result = fallback_news_payload("test error")
        assert result["news_score"] == 0
        assert result["news_sentiment"] == "NEUTRAL"
        assert result["ai_enabled"] is False
        assert "test error" in result["ai_error"]

    def test_ml_score_from_result(self):
        from core.legacy_adapters.analysis import ml_score_from_result
        assert ml_score_from_result(None) == 0
        assert ml_score_from_result({"error": "oops"}) == 0
        assert ml_score_from_result({}) == 0


# ---------------------------------------------------------------------------
# backtest_engine tests
# ---------------------------------------------------------------------------

class TestBacktestEngine:
    def test_import(self):
        from core.legacy_adapters import backtest
        # Just verify it imports without error
        assert backtest is not None
