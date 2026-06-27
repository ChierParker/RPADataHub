"""Tests for services/ai_analyzer.py module."""

import pytest
from unittest.mock import patch, MagicMock
from services.ai_analyzer import AIAnalyzer


class TestAIAnalyzer:

    @pytest.fixture
    def analyzer(self):
        """Create AIAnalyzer with mocked config."""
        with patch("services.ai_analyzer.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.ai.api_key = "sk-test-key"
            mock_cfg.ai.api_url = "https://api.deepseek.com/v1/chat/completions"
            mock_cfg.ai.model = "deepseek-chat"
            mock_config.return_value = mock_cfg
            return AIAnalyzer()

    def test_init_loads_config(self, analyzer):
        """Should load config from get_config()."""
        assert analyzer.api_key == "sk-test-key"
        assert "deepseek" in analyzer.api_url

    def test_init_warns_on_placeholder_key(self):
        """Should log warning when API key is placeholder."""
        with patch("services.ai_analyzer.get_config") as mock_config:
            with patch("services.ai_analyzer.logger") as mock_logger:
                mock_cfg = MagicMock()
                mock_cfg.ai.api_key = "sk-your-api-key-here"
                mock_cfg.ai.api_url = "https://api.example.com"
                mock_cfg.ai.model = "test"
                mock_config.return_value = mock_cfg

                AIAnalyzer()
                mock_logger.warning.assert_called_once()

    def test_rule_based_detection_price_drop(self, analyzer):
        """Should detect price drop >20%."""
        recent_data = [
            {"current_price": 100, "original_price": 100},
            {"current_price": 70, "original_price": 100},
        ]
        anomalies = analyzer._rule_based_detection("TestCo", recent_data, {})
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "price_drop"

    def test_rule_based_detection_no_anomaly(self, analyzer):
        """Should return empty when no anomaly."""
        recent_data = [
            {"current_price": 100, "original_price": 100},
            {"current_price": 95, "original_price": 100},
        ]
        anomalies = analyzer._rule_based_detection("TestCo", recent_data, {})
        assert len(anomalies) == 0

    def test_rule_based_detection_price_below_baseline(self, analyzer):
        """Should detect price significantly below historical avg."""
        recent_data = [{"current_price": 50}]
        baseline = {"avg_price": 100}
        anomalies = analyzer._rule_based_detection("TestCo", recent_data, baseline)
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "price_below_baseline"

    def test_rule_based_detection_rank_volatility(self, analyzer):
        """Should detect ranking spike."""
        recent_data = [
            {"rank_position": 10},
            {"rank_position": 80},
        ]
        anomalies = analyzer._rule_based_detection("TestCo", recent_data, {})
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "rank_volatility"

    def test_rule_based_detection_ad_emergence(self, analyzer):
        """Should detect new ad placement."""
        recent_data = [
            {"is_ad": 0},
            {"is_ad": 1},
        ]
        anomalies = analyzer._rule_based_detection("TestCo", recent_data, {})
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "ad_placement_emerged"

    def test_rule_based_detection_empty(self, analyzer):
        """Should return empty with no data."""
        anomalies = analyzer._rule_based_detection("TestCo", [], {})
        assert len(anomalies) == 0

    def test_call_api_no_key(self, analyzer):
        """Should return None when API key is missing."""
        analyzer.api_key = ""
        result = analyzer._call_api("test prompt")
        assert result is None

    def test_call_api_success(self, analyzer):
        """Should return content on successful API call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "AI analysis result"}}]
        }

        with patch("services.ai_analyzer.requests.post", return_value=mock_response):
            result = analyzer._call_api("test")
            assert result == "AI analysis result"

    def test_call_api_retry_on_429(self, analyzer):
        """Should retry on rate limit."""
        mock_rate_limit = MagicMock()
        mock_rate_limit.status_code = 429

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {
            "choices": [{"message": {"content": "Retry success"}}]
        }

        with patch("services.ai_analyzer.requests.post", side_effect=[mock_rate_limit, mock_success]):
            with patch("services.ai_analyzer.time.sleep", return_value=None):
                result = analyzer._call_api("test")
                assert result == "Retry success"

    def test_parse_report_response_none(self, analyzer):
        """Should return fallback when response is None."""
        result = analyzer._parse_report_response(None, "daily")
        assert result["alert_level"] == "info"
        assert "failed" in result["summary"].lower()

    def test_parse_report_response_normal(self, analyzer):
        """Should parse normal Markdown report."""
        response = "## Daily Report\nPrice is stable today.\nNo significant changes."
        result = analyzer._parse_report_response(response, "daily")
        assert result["alert_level"] == "info"
        assert "Price is stable" in result["summary"]

    def test_parse_report_response_warning(self, analyzer):
        """Should detect warning keywords."""
        response = "Price dropped significantly. Risk detected."
        result = analyzer._parse_report_response(response, "daily")
        assert result["alert_level"] == "warning"

    def test_detect_anomaly_integration(self, analyzer):
        """Integration: detect_anomaly should combine rules and AI."""
        recent_data = [
            {"current_price": 100, "original_price": 100, "rank_position": 5, "is_ad": 0},
            {"current_price": 70, "original_price": 100, "rank_position": 5, "is_ad": 0},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Price war alert!"}}]
        }

        with patch("services.ai_analyzer.requests.post", return_value=mock_response):
            result = analyzer.detect_anomaly("TestCo", "amazon", recent_data)
            assert result["has_anomaly"] is True
            assert len(result["anomalies"]) == 1
