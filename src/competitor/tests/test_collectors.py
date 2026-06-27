"""Tests for collectors: JD and Taobao collector units (no browser)."""

import pytest
from unittest.mock import patch, MagicMock


class TestJDCollector:
    """Unit tests for JDCollector (mocked Playwright)."""

    @pytest.fixture
    def jd(self):
        import sys, os
        sys.path.insert(0, r"C:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor")
        os.chdir(r"C:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor")
        from collectors.jd_collector import JDCollector
        task = {
            "task_uuid": "test-jd-001",
            "competitor_id": 1,
            "keywords": '["test charger"]',
            "region": "domestic",
        }
        return JDCollector(task, headless=True)

    def test_init(self, jd):
        assert jd.platform_name == "jd"
        assert jd.currency == "CNY"
        assert jd.base_url == "https://www.jd.com"

    def test_build_detail_url(self, jd):
        url = jd._build_detail_url("123456")
        assert url == "https://item.jd.com/123456.html"

    def test_url_encode(self, jd):
        encoded = jd._url_encode("手机充电器")
        assert len(encoded) > 5

    def test_safe_extract_int_plain(self, jd):
        assert jd._safe_extract_int("12345") == 12345
        assert jd._safe_extract_int("1,234") == 1234

    def test_safe_extract_int_wan(self, jd):
        result = jd._safe_extract_int("1.5万+")
        assert result == 15000

    def test_safe_extract_int_none(self, jd):
        assert jd._safe_extract_int(None) is None

    def test_parse_search_card_with_title(self, jd):
        """Card parsing should extract title."""
        mock_card = MagicMock()
        mock_card.get_attribute.return_value = ""
        mock_card.inner_text.return_value = "Test Product JD Title"

        title_el = MagicMock()
        title_el.inner_text.return_value = "Test Product JD Title Here"
        title_el.get_attribute.return_value = ""

        mock_card.query_selector.return_value = None
        def mock_query(selector):
            if "p-name" in selector and "em" in selector:
                return title_el
            return None
        mock_card.query_selector.side_effect = mock_query

        result = jd._parse_search_card(mock_card, 1)
        assert result is not None
        assert "JD Title" in result["title"]
        assert result["rank_position"] == 1
        assert result["currency"] == "CNY"


class TestTaobaoCollector:
    """Unit tests for TaobaoCollector (mocked Playwright)."""

    @pytest.fixture
    def tb(self):
        import sys, os
        sys.path.insert(0, r"C:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor")
        os.chdir(r"C:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor")
        from collectors.taobao_collector import TaobaoCollector
        task = {
            "task_uuid": "test-tb-001",
            "competitor_id": 2,
            "keywords": '["蓝牙耳机"]',
            "region": "domestic",
        }
        return TaobaoCollector(task, headless=True)

    def test_init(self, tb):
        assert tb.platform_name == "taobao"
        assert tb.currency == "CNY"
        assert tb.base_url == "https://www.taobao.com"

    def test_build_detail_url(self, tb):
        url = tb._build_detail_url("789012")
        assert url == "https://item.taobao.com/item.htm?id=789012"

    def test_url_encode(self, tb):
        encoded = tb._url_encode("蓝牙耳机")
        assert len(encoded) > 5

    def test_safe_extract_int(self, tb):
        assert tb._safe_extract_int("2000") == 2000
        assert tb._safe_extract_int("3.2万+") == 32000
        assert tb._safe_extract_int(None) is None

    def test_parse_search_card_with_title(self, tb):
        """Card parsing should extract title and return dict."""
        mock_card = MagicMock()
        mock_card.get_attribute.return_value = ""
        mock_card.inner_text.return_value = "JD Test Product ??????"

        title_el = MagicMock()
        title_el.get_attribute.return_value = None
        title_el.inner_text.return_value = "Taobao蓝牙耳机 Pro 降噪版"

        def mock_query(sel):
            if "title" in sel and "a" in sel:
                return title_el
            return None

        mock_card.query_selector.side_effect = mock_query

        result = tb._parse_search_card(mock_card, 3)
        assert result is not None
        assert "Taobao蓝牙耳机" in result["title"]
        assert result["rank_position"] == 3


class TestWorkerCollectorFactory:
    """Test worker.py get_collector_for_platform with all platforms."""

    @pytest.fixture
    def factory(self):
        import sys, os
        sys.path.insert(0, r"C:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor")
        os.chdir(r"C:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor")
        from worker import get_collector_for_platform
        return get_collector_for_platform

    def test_amazon_international(self, factory):
        c = factory({"platform": "amazon", "region": "international", "keywords": "[]"})
        assert c.platform_name == "amazon"
        assert c.currency == "USD"

    def test_amazon_domestic(self, factory):
        c = factory({"platform": "amazon", "region": "domestic", "keywords": "[]"})
        assert c.platform_name == "amazon"

    def test_jd_domestic(self, factory):
        c = factory({"platform": "jd", "region": "domestic", "keywords": "[]"})
        assert c.platform_name == "jd"
        assert c.currency == "CNY"

    def test_taobao_domestic(self, factory):
        c = factory({"platform": "taobao", "region": "domestic", "keywords": "[]"})
        assert c.platform_name == "taobao"
        assert c.currency == "CNY"

    def test_pdd_raises(self, factory):
        with pytest.raises(NotImplementedError):
            factory({"platform": "pdd", "region": "domestic", "keywords": "[]"})

    def test_unknown_raises(self, factory):
        with pytest.raises(ValueError):
            factory({"platform": "unknown", "region": "domestic", "keywords": "[]"})
