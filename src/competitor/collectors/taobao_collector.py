"""
Taobao (淘宝/Tmall) competitor price collector
- Keyword search + product detail extraction
- Ad placement identification (直通车/钻展)
- Price extraction (current/original/coupon)
- Anti-detection: random delays, UA rotation, login wall handling

Usage:
    from collectors.taobao_collector import TaobaoCollector

    task = {
        "task_uuid": "abc123",
        "competitor_id": 1,
        "keywords": '["蓝牙耳机", "无线耳机"]',
        "taobao_url": "https://item.taobao.com/item.htm?id=123456",
        "region": "domestic",
    }
    collector = TaobaoCollector(task, headless=True)
    results = collector.collect()
"""

import re
import time
import random
import traceback
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from playwright.sync_api import Page

from collectors.base_collector import BaseCompetitorCollector, logger


class TaobaoCollector(BaseCompetitorCollector):
    """
    Taobao/Tmall platform competitor collector

    Features:
        - Keyword search on s.taobao.com
        - Direct product URL extraction (for known items)
        - Ad placement detection (直通车 / 钻展 / 海景房)
        - Login wall handling (skip gated pages gracefully)
        - Stealth mode: random delays, UA rotation

    Note:
        Taobao has aggressive anti-bot protection. This collector:
        - Uses realistic viewport + user-agent
        - Adds human-like delays between actions
        - Skips items behind login walls
        - May return partial results during high anti-bot periods
    """

    platform_name = "taobao"
    base_url = "https://www.taobao.com"
    currency = "CNY"

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    ]

    def __init__(self, task: dict, headless: bool = True):
        super().__init__(task, headless)
        self._taobao_url = task.get("taobao_url", "")
        self._jd_sku = task.get("jd_sku", "")

    # ============================================================
    # Abstract method implementations
    # ============================================================

    def search_product(self, keyword: str, page: Page) -> list:
        """
        Search Taobao for keyword and parse product list.

        Taobao search URLs:
            - s.taobao.com/search?q=keyword
            - May redirect to login / verification

        Search result structure (2026):
            - Product card: div.item, div.ctx-box, div[data-category="auctions"]
            - Title: div.title a, div.row-2 a
            - Price: div.price strong, span.price
            - Original: div.price del
            - Sales: div.deal-cnt
            - Shop: div.shop a
            - Ad label: span.icon-service-zhitongche

        Parameters:
            keyword: search keyword
            page: Playwright Page

        Returns:
            list[dict]: product search results
        """
        products = []
        search_url = f"https://s.taobao.com/search?q={quote(keyword)}&imgfile=&commend=all&ssid=s5-e&search_type=item"
        logger.info(f"[TB Search] URL: {search_url[:120]}", self.task_uuid)

        if not self._safe_goto(search_url):
            self._rotate_context(page, mobile=True)
            if not self._safe_goto(search_url):
                logger.warning(f"[TB Search] Page load failed (possible login wall): {keyword}", self.task_uuid)
                return products

        self._random_delay(3, 6)

        # Check if redirected to login
        current_url = page.url
        if "login.taobao.com" in current_url:
            logger.warning(f"[TB Search] Redirected to login page for '{keyword}' — skipping", self.task_uuid)
            return products

        # Scroll for lazy loading
        self._scroll_page(page, 4)

        # Extract product cards
        try:
            card_selectors = [
                "div[data-category='auctions'] div.item",
                "div.ctx-box div.item",
                "div.items div.item",
                "div.J_Itemlist div[data-spm-anchor-id]",
            ]

            cards = []
            for sel in card_selectors:
                cards = page.query_selector_all(sel)
                if cards:
                    break

            # Fallback: generic card detection
            if not cards:
                cards = page.query_selector_all("div[data-nid], a[data-nid]")

            max_results = self.task.get("max_results", 50) or 50
            logger.info(f"[TB Search] Found {len(cards)} cards for '{keyword}'", self.task_uuid)

            for i, card in enumerate(cards[:max_results]):
                try:
                    product = self._parse_search_card(card, i + 1)
                    if product and product.get("title"):
                        products.append(product)
                except Exception as e:
                    logger.debug(f"[TB Search] Card {i} parse error: {e}", self.task_uuid)

        except Exception as e:
            logger.error(f"[TB Search] Parse error: {e}", self.task_uuid)

        logger.info(f"[TB Search] Parsed {len(products)} products for '{keyword}'", self.task_uuid)
        return products

    def get_product_detail(self, product_url: str, page: Page) -> dict:
        """
        Get Taobao product detail page information.

        Parameters:
            product_url: product detail URL (item.taobao.com or detail.tmall.com)
            page: Playwright Page

        Returns:
            dict: product detail
        """
        detail = {}
        self._random_delay(2, 5)

        if not self._safe_goto(product_url, timeout=20000):
            logger.warning(f"[TB Detail] Load failed: {product_url[:80]}", self.task_uuid)
            return detail

        # Check for login wall
        if "login.taobao.com" in page.url:
            logger.warning(f"[TB Detail] Login wall hit — skipping", self.task_uuid)
            return detail

        self._random_delay(1, 3)

        try:
            # Detect page type: taobao vs tmall
            is_tmall = "tmall.com" in product_url

            # Title
            title_sel = ".tb-main-title" if not is_tmall else "div.tb-detail-hd h1"
            title_el = page.query_selector(title_sel)
            if not title_el:
                title_el = page.query_selector("h1, h3.tb-main-title, div.tb-title h3")
            if title_el:
                detail["title"] = (title_el.inner_text() or "").strip().replace("\n", " ")

            # Current price
            price_sel = ".tb-rmb-num" if not is_tmall else "span.tm-price"
            price_el = page.query_selector(price_sel)
            if not price_el:
                price_el = page.query_selector(
                    "strong.tb-rmb-num, span.price, em.tb-rmb-num, "
                    "span.tm-count span, div.tb-price span"
                )
            if price_el:
                price_text = (price_el.inner_text() or "").strip()
                detail["current_price"] = self._safe_extract_float(price_text)

            # Original price
            orig_el = page.query_selector(
                "del.tb-market-price, span.original-price, "
                "span.suggest-price, span.tb-original-price"
            )
            if orig_el:
                orig_text = (orig_el.inner_text() or "").strip()
                detail["original_price"] = self._safe_extract_float(orig_text)

            # Sales / review count
            sales_el = page.query_selector(
                "span.tb-sell-counter a, strong.tb-count, "
                "em.tb-sell-counter, span.deal-cnt"
            )
            if sales_el:
                sales_text = (sales_el.inner_text() or "").strip()
                detail["review_count"] = self._safe_extract_int(sales_text)

            # Seller name
            seller_el = page.query_selector(
                "div.tb-shop-name a, a.shop-name, "
                "div.shop-info a, a.J_ShopName"
            )
            if seller_el:
                detail["seller_name"] = (seller_el.inner_text() or "").strip()

            # Product ID from URL
            id_match = re.search(r'[?&]id=(\d+)', product_url)
            if id_match:
                detail["product_id"] = id_match.group(1)

            detail["raw_data"] = {"source": "tmall" if is_tmall else "taobao"}

        except Exception as e:
            logger.error(f"[TB Detail] Parse error: {e}", self.task_uuid)

        return detail

    def get_advert_info(self, keyword: str, page: Page) -> list:
        """
        Identify ad placements in Taobao search results.

        Taobao ad markers:
            - 直通车 (Zhitongche) — P4P search ads
            - 钻展 (Zuanzhan) — display/banner ads
            - 海景房 (HaiJingFang) — premium banner position
            - Icon classes: icon-service-zhitongche, icon-ad

        Parameters:
            keyword: search keyword
            page: Playwright Page (must be on search results)

        Returns:
            list[dict]: ad placement info
        """
        ads = []

        ad_selectors = [
            "span.icon-service-zhitongche",
            "span.icon-ad",
            "span.icon-service-zuanzhan",
            "span:has-text('广告')",
            "div.ad-text",
            "span.ad-icon",
        ]

        try:
            for sel in ad_selectors:
                elements = page.query_selector_all(sel)
                for el in elements:
                    try:
                        text = (el.inner_text() or "").strip()
                        card = el.evaluate("el => el.closest('div.item, div[data-nid]')")
                        if card:
                            ads.append({
                                "label": text or "ad",
                                "ad_type": "sponsored" if "直通车" in (text or "广告") else "display",
                                "selector": sel,
                            })
                    except Exception:
                        continue

        except Exception as e:
            logger.debug(f"[TB Ads] Detection error: {e}", self.task_uuid)

        logger.info(f"[TB Ads] Detected {len(ads)} ad placements", self.task_uuid)
        return ads

    # ============================================================
    # Override: detail URL builder
    # ============================================================

    def _build_detail_url(self, product_id: str) -> str:
        """Build Taobao product detail URL from item ID."""
        return f"https://item.taobao.com/item.htm?id={product_id}"

    # ============================================================
    # Override: collect (adds direct URL mode)
    # ============================================================

    def collect(self) -> list:
        """
        Override collect to support direct Taobao URL collection.

        If taobao_url is provided in the task, scrape that URL directly
        instead of keyword search.
        """
        if self._taobao_url:
            logger.info(f"[TB Direct] Scraping URL: {self._taobao_url[:80]}", self.task_uuid)
            try:
                self._launch_browser()
                detail = self.get_product_detail(self._taobao_url, self._page)
                if detail:
                    self.results.append({
                        "competitor_id": self.task.get("competitor_id"),
                        "task_uuid": self.task_uuid,
                        "platform": self.platform_name,
                        "product_url": self._taobao_url,
                        "title": detail.get("title", ""),
                        "current_price": detail.get("current_price"),
                        "original_price": detail.get("original_price"),
                        "currency": self.currency,
                        "rank_position": None,
                        "is_ad": 0,
                        "ad_type": "",
                        "review_count": detail.get("review_count"),
                        "rating": detail.get("rating"),
                        "seller_name": detail.get("seller_name", ""),
                        "snapshot_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "raw_json": self._safe_json_dumps(detail),
                    })
                return self.results
            except Exception as e:
                logger.error(f"[TB Direct] Failed: {e}", self.task_uuid, exc_info=True)
            finally:
                self._close_browser()

        # Default: keyword search flow
        return super().collect()

    # ============================================================
    # Search card parsing
    # ============================================================

    def _parse_search_card(self, card, rank: int) -> Optional[dict]:
        """Parse a single Taobao search result card with multiple fallback strategies."""
        try:
            # ---- Strategy 1: Standard selectors ----
            title_el = card.query_selector(
                "div.title a, div.row-2 a, a.title, "
                "div.p-title a, span.title-text, .title a"
            )
            title = ""
            if title_el:
                title = (title_el.get_attribute("title") or title_el.inner_text() or "").strip()

            # Strategy 2: Any link with item ID
            if not title or len(title) < 3:
                link_el = card.query_selector("a[href*='item.taobao.com'], a[href*='detail.tmall.com']")
                if link_el:
                    title = (link_el.get_attribute("title") or link_el.inner_text() or "").strip()

            # Strategy 3: Extract all visible text
            if not title or len(title) < 3:
                try:
                    all_text = (card.inner_text() or "").strip()
                    lines = [l.strip() for l in all_text.split("\n") if l.strip() and len(l.strip()) > 3]
                    non_price = [l for l in lines if not l.startswith("\uffe5") and len(l) > 3]
                    if non_price:
                        title = non_price[0][:200]
                except Exception:
                    pass

            if not title or len(title) < 3:
                return None

            # ---- URL ----
            product_url = ""
            url_el = card.query_selector(
                "div.pic a, a.pic-link, div.title a, div.row-2 a, "
                "a[href*='item.taobao'], a[href*='detail.tmall']"
            )
            if url_el:
                product_url = url_el.get_attribute("href") or ""
                if product_url.startswith("//"):
                    product_url = "https:" + product_url

            # ---- Product ID ----
            nid = card.get_attribute("data-nid") or ""
            if not nid and product_url:
                import re
                id_match = re.search(r'[?&]id=(\d+)', product_url)
                nid = id_match.group(1) if id_match else ""

            # ---- Price ----
            current_price = None
            for price_sel in [
                "div.price strong", "span.price", "div.price span",
                "strong.sprice", "em.price-num", "[class*='price'] strong",
            ]:
                price_el = card.query_selector(price_sel)
                if price_el:
                    price_text = (price_el.inner_text() or "").strip()
                    current_price = self._safe_extract_float(price_text)
                    if current_price:
                        break

            # ---- Original price ----
            original_price = None
            orig_el = card.query_selector("div.price del, span.original-price, del.original, .market-price")
            if orig_el:
                orig_text = (orig_el.inner_text() or "").strip()
                original_price = self._safe_extract_float(orig_text)

            # ---- Ad ----
            is_ad = card.query_selector(
                "span.icon-service-zhitongche, span.icon-ad, span.icon-service-zuanzhan"
            ) is not None
            ad_type = "sponsored" if is_ad else ""

            # ---- Sales ----
            review_count = None
            sales_el = card.query_selector("div.deal-cnt, span.deal-cnt, div.sales, [class*='sale']")
            if sales_el:
                sales_text = (sales_el.inner_text() or "").strip()
                review_count = self._safe_extract_int(sales_text)

            # ---- Shop ----
            seller_name = ""
            shop_el = card.query_selector("div.shop a, a.shopname, span.shop-name, [class*='shop'] a")
            if shop_el:
                seller_name = (shop_el.inner_text() or "").strip()

            return {
                "title": title[:200],
                "product_url": product_url or self._build_detail_url(nid),
                "product_id": nid,
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
            logger.debug(f"[TB Card] Parse error at rank {rank}: {e}", self.task_uuid)
            return None

    # ============================================================
    # Anti-detection helpers
    # ============================================================

    def _random_delay(self, min_sec: float, max_sec: float):
        """Add random delay between requests."""
        delay = random.uniform(min_sec, max_sec)
        if self._page:
            self._page.wait_for_timeout(int(delay * 1000))
        else:
            time.sleep(delay)

    def _scroll_page(self, page: Page, times: int = 3):
        """Human-like scrolling to trigger lazy loading (safe against navigation)."""
        for i in range(times):
            scroll_to = random.randint(300, 800) * (i + 1)
            try:
                page.evaluate(f"window.scrollTo({{top: {scroll_to}, behavior: 'smooth'}})")
            except Exception:
                return  # Page navigated away, stop scrolling
            page.wait_for_timeout(600 + random.randint(200, 600))

    def _rotate_context(self, page: Page, mobile: bool = False):
        """Rotate UA and viewport."""
        ua = random.choice(self.USER_AGENTS)
        if mobile:
            page.set_viewport_size({"width": 375, "height": 812})
        else:
            page.set_viewport_size({"width": 1366, "height": 768})
        try:
            page.evaluate(f"Object.defineProperty(navigator, 'userAgent', {{get: () => '{ua}'}})")
        except Exception:
            pass  # May fail if page already navigated

    @staticmethod
    def _safe_extract_int(value) -> Optional[int]:
        """Safely extract integer (handle 万+ format)."""
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
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
        """URL-encode for search queries."""
        return quote(text, safe="")
