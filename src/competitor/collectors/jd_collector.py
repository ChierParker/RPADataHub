"""
JD (Jingdong / 京东) competitor price collector
- Keyword search + product detail extraction
- Ad placement identification (京东快车/推荐位)
- Price extraction (current/original/coupon)
- Anti-detection measures for Chinese e-commerce platforms

Usage:
    from collectors.jd_collector import JDCollector

    task = {
        "task_uuid": "abc123",
        "competitor_id": 1,
        "keywords": '["手机充电器", "快充头"]',
        "region": "domestic",
    }
    collector = JDCollector(task, headless=True)
    results = collector.collect()
"""

import re
import time
import traceback
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from playwright.sync_api import Page

from collectors.base_collector import BaseCompetitorCollector, logger


class JDCollector(BaseCompetitorCollector):
    """
    JD platform competitor collector

    Features:
        - Keyword search on search.jd.com
        - Product detail extraction (price, title, reviews)
        - Ad placement detection (京东快车 / 精选推荐)
        - Auto-retry on anti-bot challenges
    """

    platform_name = "jd"
    base_url = "https://www.jd.com"
    currency = "CNY"

    # Random user agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    ]

    def __init__(self, task: dict, headless: bool = True):
        super().__init__(task, headless)
        self._request_count = 0
        self._last_request_time = 0

    # ============================================================
    # Abstract method implementations
    # ============================================================

    def search_product(self, keyword: str, page: Page) -> list:
        """
        Search JD for keyword and parse product list.

        JD search result structure (2026):
            - Product card: li.gl-item or div.gl-i-wrap
            - Title: div.p-name a em
            - Price: div.p-price strong i  or  div.p-price span
            - Original price: div.p-price del
            - Review count: div.p-commit strong a
            - Ad label: span.promo-icons (京东广告)
            - Shop name: div.p-shop span a

        Parameters:
            keyword: search keyword
            page: Playwright Page

        Returns:
            list[dict]: product search results
        """
        products = []
        search_url = f"https://search.jd.com/Search?keyword={quote(keyword)}&enc=utf-8&wq={quote(keyword)}"
        logger.info(f"[JD Search] URL: {search_url[:120]}", self.task_uuid)

        if not self._safe_goto(search_url):
            # Retry with mobile user-agent
            self._rotate_context(page, mobile=True)
            if not self._safe_goto(search_url):
                logger.error(f"[JD Search] Page load failed: {keyword}", self.task_uuid)
                return products

        self._random_delay(2, 4)

        # Scroll to trigger lazy loading
        self._scroll_page(page, 3)

        # Extract product cards
        try:
            cards = page.query_selector_all("li.gl-item, div.gl-i-wrap, div[data-sku]")
            logger.info(f"[JD Search] Page 1: {len(cards)} cards for '{keyword}'", self.task_uuid)

            max_results = self.task.get("max_results", 50) or 50

            for i, card in enumerate(cards[:max_results]):
                try:
                    product = self._parse_search_card(card, i + 1)
                    if product and product.get("title"):
                        products.append(product)
                except Exception as e:
                    logger.debug(f"[JD Search] Card {i} parse error: {e}", self.task_uuid)

        except Exception as e:
            logger.error(f"[JD Search] Parse error: {e}", self.task_uuid)

        logger.info(f"[JD Search] Parsed {len(products)} products for '{keyword}'", self.task_uuid)
        return products

    def get_product_detail(self, product_url: str, page: Page) -> dict:
        """
        Get JD product detail page information.

        Parameters:
            product_url: product detail URL
            page: Playwright Page

        Returns:
            dict: product detail
        """
        detail = {}
        self._random_delay(2, 4)

        if not self._safe_goto(product_url, timeout=20000):
            logger.warning(f"[JD Detail] Load failed: {product_url[:80]}", self.task_uuid)
            return detail

        self._random_delay(1, 2)

        try:
            # Title
            title_el = page.query_selector(".sku-name, #itemName, .title-name")
            if title_el:
                detail["title"] = (title_el.inner_text() or "").strip().replace("\n", " ")

            # Current price
            price_el = page.query_selector(".p-price span, #jd-price .price, .summary-price .price")
            if price_el:
                price_text = (price_el.inner_text() or "").strip()
                detail["current_price"] = self._safe_extract_float(price_text)

            # Original price (MSRP / crossed-out)
            orig_el = page.query_selector(".p-price del, #page_maprice, .market-price")
            if orig_el:
                orig_text = (orig_el.inner_text() or "").strip()
                detail["original_price"] = self._safe_extract_float(orig_text)

            # Review count
            review_el = page.query_selector("#comment-count a, #J_comment_count, .comment-count")
            if review_el:
                review_text = (review_el.inner_text() or "").strip()
                detail["review_count"] = self._safe_extract_int(review_text)

            # Rating
            rating_el = page.query_selector(".percent-con, #comment .percent")
            if rating_el:
                rating_text = (rating_el.inner_text() or "").strip().replace("%", "")
                try:
                    detail["rating"] = float(rating_text) / 20  # Convert 0-100% to 0-5
                except ValueError:
                    pass

            # Seller name
            seller_el = page.query_selector(".J-hove-wrap a, .seller-name, .shop-name a")
            if seller_el:
                detail["seller_name"] = (seller_el.inner_text() or "").strip()

            # SKU from URL
            sku_match = re.search(r'/(\d+)\.html', product_url)
            if sku_match:
                detail["product_id"] = sku_match.group(1)

            detail["raw_data"] = {"source": "jd_item_detail"}

        except Exception as e:
            logger.error(f"[JD Detail] Parse error: {e}", self.task_uuid)

        return detail

    def get_advert_info(self, keyword: str, page: Page) -> list:
        """
        Identify ad placements in JD search results.

        JD ad markers:
            - Spans with class containing "promo" or "ad"
            - Data attributes: data-spu-type="ad"
            - Ad keywords like "广告" / "推广"

        Parameters:
            keyword: search keyword
            page: Playwright Page (must be on search results)

        Returns:
            list[dict]: ad placement info
        """
        ads = []
        try:
            # Look for sponsored / ad labels
            ad_selectors = [
                "span.promo-icons",
                "span.ad-label",
                "div[data-spu-type='ad']",
                "span:has-text('广告')",
                "span:has-text('推广')",
                "em.promo",
            ]

            for sel in ad_selectors:
                try:
                    elements = page.query_selector_all(sel)
                    for el in elements:
                        card = el.evaluate("el => el.closest('li.gl-item, div.gl-i-wrap')")
                        if card:
                            ads.append({
                                "label": (el.inner_text() or "").strip(),
                                "ad_type": "sponsored" if "广告" in (el.inner_text() or "") else "recommended",
                                "selector": sel,
                            })
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"[JD Ads] Detection error: {e}", self.task_uuid)

        logger.info(f"[JD Ads] Detected {len(ads)} ad placements", self.task_uuid)
        return ads

    # ============================================================
    # Override: detail URL builder
    # ============================================================

    def _build_detail_url(self, product_id: str) -> str:
        """Build JD product detail URL from SKU."""
        return f"https://item.jd.com/{product_id}.html"

    # ============================================================
    # Search card parsing
    # ============================================================

    def _parse_search_card(self, card, rank: int) -> Optional[dict]:
        """Parse a single JD search result card with multiple fallback strategies."""
        try:
            # ---- Strategy 1: Try standard selectors ----
            title_el = card.query_selector(
                "div.p-name a em, div.p-name em, a[title] em, "
                ".p-name em, .p-name a, .gl-i-wrap .p-name em"
            )
            title = ""
            if title_el:
                title = (title_el.inner_text() or "").strip()

            # Strategy 2: Try link text
            if not title or len(title) < 3:
                link_el = card.query_selector("a[href*='item.jd.com'], a[href*='item.m.jd.com']")
                if link_el:
                    title = (link_el.get_attribute("title") or link_el.inner_text() or "").strip()

            # Strategy 3: Extract all visible text from the card
            if not title or len(title) < 3:
                try:
                    all_text = (card.inner_text() or "").strip()
                    # Take the longest non-price line as title
                    lines = [l.strip() for l in all_text.split("\n") if l.strip() and len(l.strip()) > 5]
                    # Filter out price-like lines
                    non_price = [l for l in lines if not l.startswith("\uffe5") and not l.startswith("$") and len(l) > 5]
                    if non_price:
                        title = non_price[0][:200]
                except Exception:
                    pass

            if not title or len(title) < 3:
                return None

            # ---- URL extraction ----
            product_url = ""
            url_el = card.query_selector("a[href*='item.jd.com'], a[href*='item.m.jd.com'], div.p-img a, .p-name a")
            if url_el:
                product_url = url_el.get_attribute("href") or ""
                if product_url.startswith("//"):
                    product_url = "https:" + product_url

            # ---- SKU ----
            sku = card.get_attribute("data-sku") or ""
            if not sku and product_url:
                import re
                sku_match = re.search(r'/(\d+)\.html', product_url)
                if sku_match:
                    sku = sku_match.group(1)

            # ---- Price (try multiple patterns) ----
            current_price = None
            for price_sel in [
                "div.p-price strong i", "div.p-price span", "div.p-price em",
                ".p-price i", ".p-price span", "strong.J_price",
                "[class*='price'] i", "[class*='price'] span",
            ]:
                price_el = card.query_selector(price_sel)
                if price_el:
                    price_text = (price_el.inner_text() or "").strip()
                    current_price = self._safe_extract_float(price_text)
                    if current_price:
                        break

            # ---- Original price ----
            original_price = None
            orig_el = card.query_selector("div.p-price del, .p-price .J_originPrice, del[class*='price']")
            if orig_el:
                orig_text = (orig_el.inner_text() or "").strip()
                original_price = self._safe_extract_float(orig_text)

            # ---- Ad check ----
            is_ad = card.query_selector("span.promo-icons, span.ad-label, em.promo") is not None
            ad_type = "sponsored" if is_ad else ""

            # ---- Review count ----
            review_count = None
            review_el = card.query_selector("div.p-commit strong a, div.p-commit a, [class*='commit'] a")
            if review_el:
                review_text = (review_el.inner_text() or "").strip()
                review_count = self._safe_extract_int(review_text)

            # ---- Shop name ----
            seller_name = ""
            shop_el = card.query_selector("div.p-shop span a, div.p-shopnum a, [class*='shop'] a")
            if shop_el:
                seller_name = (shop_el.inner_text() or "").strip()

            return {
                "title": title[:200],
                "product_url": product_url or self._build_detail_url(sku),
                "product_id": sku,
                "current_price": current_price,
                "original_price": original_price,
                "rank_position": rank,
                "is_ad": is_ad,
                "ad_type": ad_type,
                "thumbnail": "",
                "review_count": review_count,
                "seller_name": seller_name,
                "currency": self.currency,
            }

        except Exception as e:
            logger.debug(f"[JD Card] Parse error at rank {rank}: {e}", self.task_uuid)
            return None


    def _random_delay(self, min_sec: float, max_sec: float):
        """Add random delay between requests to avoid detection."""
        import random
        delay = random.uniform(min_sec, max_sec)
        self._page.wait_for_timeout(int(delay * 1000)) if self._page else time.sleep(delay)

    def _scroll_page(self, page: Page, times: int = 3):
        """Scroll page to trigger lazy loading."""
        for i in range(times):
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/times})")
            page.wait_for_timeout(800 + i * 400)

    def _rotate_context(self, page: Page, mobile: bool = False):
        """Rotate user agent and viewport to evade detection."""
        import random
        ua = random.choice(self.USER_AGENTS)
        if mobile:
            page.set_viewport_size({"width": 375, "height": 812})
        page.evaluate(f"Object.defineProperty(navigator, 'userAgent', {{get: () => '{ua}'}})")

    @staticmethod
    def _safe_extract_int(value) -> Optional[int]:
        """Safely extract integer from text (handle 万+ format)."""
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        # Handle Chinese "万+" (10k+) format
        if "万" in text:
            num = re.sub(r'[^\d.]', '', text)
            try:
                return int(float(num) * 10000)
            except ValueError:
                pass
        num = re.sub(r'[^\d]', '', text)
        try:
            return int(num) if num else None
        except ValueError:
            return None

    # ============================================================
    # URL encoding
    # ============================================================

    @staticmethod
    def _url_encode(text: str) -> str:
        """URL-encode a text string for search queries."""
        return quote(text, safe="")
