"""
Amazon 竞品采集器
- 支持按关键词搜索或 ASIN 直采
- 识别 Sponsored 广告位和 Banner 广告
- 提取价格（current/prime/original）、排名、评分、评论数
- 适配 Amazon 多站点（.com/.co.uk/.de/.co.jp 等）
- 复用 RPADataHub 的 Playwright 浏览器管理方式

使用示例:
    from collectors.amazon_collector import AmazonCollector

    task = {
        "task_uuid": "abc123",
        "competitor_id": 1,
        "keywords": '["anker charger", "power bank"]',
        "asin_list": '["B0XXXXXXX"]',
        "region": "international",
        "marketplace": "amazon.com",
    }
    collector = AmazonCollector(task, headless=True)
    results = collector.collect()
"""

import re
import time
import traceback
from datetime import datetime
from typing import Optional

from playwright.sync_api import Page

from collectors.base_collector import BaseCompetitorCollector, logger


class AmazonCollector(BaseCompetitorCollector):
    """
    Amazon 平台竞品采集器

    功能:
        - 关键词搜索 + 搜索结果解析
        - ASIN 直接采集商品详情
        - 广告位（Sponsored/Banner）自动识别
        - 多站点支持（通过 marketplace 切换域名）
    """

    platform_name = "amazon"
    currency = "USD"

    # 多站点域名映射
    MARKETPLACE_DOMAINS = {
        "amazon.com":     {"base": "https://www.amazon.com",     "currency": "USD"},
        "amazon.co.uk":   {"base": "https://www.amazon.co.uk",   "currency": "GBP"},
        "amazon.de":      {"base": "https://www.amazon.de",      "currency": "EUR"},
        "amazon.co.jp":   {"base": "https://www.amazon.co.jp",   "currency": "JPY"},
        "amazon.ca":      {"base": "https://www.amazon.ca",      "currency": "CAD"},
        "amazon.fr":      {"base": "https://www.amazon.fr",      "currency": "EUR"},
        "amazon.it":      {"base": "https://www.amazon.it",      "currency": "EUR"},
        "amazon.es":      {"base": "https://www.amazon.es",      "currency": "EUR"},
        "amazon.com.au":  {"base": "https://www.amazon.com.au",  "currency": "AUD"},
        "amazon.in":      {"base": "https://www.amazon.in",      "currency": "INR"},
        "amazon.com.mx":  {"base": "https://www.amazon.com.mx",  "currency": "MXN"},
        "amazon.com.br":  {"base": "https://www.amazon.com.br",  "currency": "BRL"},
    }

    def __init__(self, task: dict, headless: bool = True):
        super().__init__(task, headless)

        # 根据 marketplace 设置站点信息
        marketplace = task.get("marketplace", "amazon.com")
        site_info = self.MARKETPLACE_DOMAINS.get(
            marketplace,
            self.MARKETPLACE_DOMAINS["amazon.com"]
        )
        self.base_url = site_info["base"]
        self.currency = site_info["currency"]
        self.marketplace = marketplace

        logger.info(
            f"[Amazon] 初始化: marketplace={marketplace}, site={self.base_url}, "
            f"currency={self.currency}",
            self.task_uuid
        )

    # ============================================================
    # 抽象方法实现
    # ============================================================

    def search_product(self, keyword: str, page: Page) -> list:
        """
        在 Amazon 搜索关键词，解析搜索结果列表

        Amazon 搜索结果页结构（2026年）:
            - 每个商品卡片: div[data-component-type="s-search-result"]
            - 标题: h2 a span
            - 价格: span.a-price span.a-offscreen
            - 原价: span.a-text-price span.a-offscreen
            - 评分: span.a-icon-alt
            - 评论数: span.a-size-base.s-underline-text
            - 赞助标识: span[data-component-type="s-sponsored-label-text"]

        参数:
            keyword: 搜索关键词
            page: Playwright Page 对象

        返回:
            list[dict]: 商品搜索结果列表
        """
        products = []

        # 构建搜索 URL
        search_url = f"{self.base_url}/s?k={self._url_encode(keyword)}"
        logger.info(f"[Amazon搜索] URL: {search_url[:120]}", self.task_uuid)

        if not self._safe_goto(search_url):
            logger.error(f"[Amazon搜索] 搜索页面加载失败: {keyword}", self.task_uuid)
            return products

        # 等待搜索结果加载
        try:
            page.wait_for_selector(
                '[data-component-type="s-search-result"], .s-result-item',
                timeout=10000
            )
        except Exception:
            logger.warning(
                f"[Amazon搜索] 搜索结果加载超时或无结果: {keyword}",
                self.task_uuid
            )
            # 检查是否有验证码/拦截页面
            if self._detect_captcha(page):
                logger.error("[Amazon搜索] 检测到验证码页面!", self.task_uuid)
            return products

        # 滚动加载更多（模拟真实用户行为）
        self._scroll_page(page, times=2)

        # 解析商品卡片
        cards = page.query_selector_all(
            '[data-component-type="s-search-result"], div.s-result-item[data-asin]'
        )

        logger.info(f"[Amazon搜索] 找到 {len(cards)} 个商品卡片", self.task_uuid)

        for rank, card in enumerate(cards):
            try:
                # 跳过非商品行（如标题行、横幅广告等）
                asin = card.get_attribute("data-asin")
                if not asin or asin == "":
                    continue

                product = self._parse_search_card(card, rank + 1)
                if product and product.get("title"):
                    products.append(product)

            except Exception as e:
                # 单卡片解析失败不影响其他卡片
                logger.debug(
                    f"[Amazon搜索] 第{rank+1}个卡片解析失败: {e}",
                    self.task_uuid
                )
                continue

        return products

    def get_product_detail(self, product_url: str, page: Page) -> dict:
        """
        获取 Amazon 商品详情页信息

        参数:
            product_url: 商品详情页URL
            page: Playwright Page 对象

        返回:
            dict: 包含 title/current_price/review_count/rating 等
        """
        detail = {}

        if not self._safe_goto(product_url):
            return detail

        try:
            # 商品标题
            title_el = page.query_selector("#productTitle, #title")
            if title_el:
                detail["title"] = title_el.inner_text().strip()

            # 当前价格（多种选择器降级匹配）
            price_selectors = [
                "span.a-price span.a-offscreen",            # 标准价格
                "#priceblock_ourprice",                     # 老版
                ".a-price .a-offscreen",                    # 通用
                "#corePrice_desktop span.a-offscreen",      # 新版详情页
                "span#price_inside_buybox",                 # 购买框
            ]
            for sel in price_selectors:
                price_el = page.query_selector(sel)
                if price_el:
                    price_text = price_el.inner_text().strip()
                    detail["current_price"] = self._safe_extract_float(price_text)
                    if detail["current_price"]:
                        break

            # 原价/划线价
            orig_selectors = [
                "span.a-text-price span.a-offscreen",
                "span.list-price span.a-offscreen",
                "span.basisPrice span.a-offscreen",
            ]
            for sel in orig_selectors:
                orig_el = page.query_selector(sel)
                if orig_el:
                    orig_text = orig_el.inner_text().strip()
                    detail["original_price"] = self._safe_extract_float(orig_text)
                    if detail["original_price"]:
                        break

            # 评分
            rating_el = page.query_selector(
                "span.a-icon-alt, #acrPopover a span.a-declarative span.a-icon-alt"
            )
            if rating_el:
                rating_text = rating_el.inner_text().strip()
                rating_match = re.search(r'[\d.]+', rating_text)
                if rating_match:
                    detail["rating"] = float(rating_match.group())

            # 评论数
            review_el = page.query_selector("#acrCustomerReviewText, span#acrCustomerReviewText")
            if review_el:
                review_text = review_el.inner_text().strip()
                review_match = re.search(r'[\d,]+', review_text)
                if review_match:
                    detail["review_count"] = int(review_match.group().replace(",", ""))

            # 卖家名称
            seller_el = page.query_selector(
                "#merchant-info a, #sellerProfileTriggerId, a#bylineInfo"
            )
            if seller_el:
                detail["seller_name"] = seller_el.inner_text().strip()

            # 额外元数据保存到 raw_data
            detail["raw_data"] = {
                "asin": self._extract_asin_from_url(product_url),
                "marketplace": self.marketplace,
            }

        except Exception as e:
            logger.warning(
                f"[Amazon详情] 解析异常: {e}",
                self.task_uuid
            )

        return detail

    def get_advert_info(self, keyword: str, page: Page) -> list:
        """
        识别 Amazon 搜索结果中的广告位

        Amazon 广告类型:
            - Sponsored Products: 带有 "Sponsored" 标签的商品卡片
            - Sponsored Brands: 顶部品牌横幅广告
            - Sponsored Display: 侧边栏/底部展示广告

        参数:
            keyword: 搜索关键词
            page: Playwright Page 对象（需已在搜索结果页）

        返回:
            list[dict]: 广告位信息列表
        """
        ad_products = []

        try:
            # 1. 识别 Sponsored Products（搜索结果列表中的广告）
            ad_cards = page.query_selector_all(
                '[data-component-type="s-search-result"]:has(span[data-component-type="s-sponsored-label-text"]), '
                'div.s-result-item:has(.s-sponsored-label-text), '
                'div[data-component-type="s-search-result"]:has(.a-color-secondary:has-text("Sponsored"))'
            )

            # 如果以上选择器未能匹配，用更通用的方式
            if not ad_cards:
                all_cards = page.query_selector_all(
                    '[data-component-type="s-search-result"], div.s-result-item[data-asin]'
                )
                for card in all_cards:
                    try:
                        sponsored = card.query_selector(
                            'span[data-component-type="s-sponsored-label-text"], '
                            '.s-sponsored-label-text, '
                            'span:has-text("Sponsored"), '
                            'span:has-text("赞助")'
                        )
                        if sponsored:
                            ad_cards.append(card)
                    except Exception:
                        continue

            for card in ad_cards:
                try:
                    asin = card.get_attribute("data-asin")
                    if not asin:
                        continue

                    link_el = card.query_selector(
                        "a.a-link-normal.s-link-style, h2 a.a-link-normal"
                    )
                    url = ""
                    if link_el:
                        href = link_el.get_attribute("href") or ""
                        if href.startswith("/"):
                            url = self.base_url + href
                        else:
                            url = href

                    # 判断广告类型
                    ad_type = "sponsored_product"  # 默认

                    # 检查是否为品牌推广横幅
                    banner_check = card.query_selector(
                        '[data-component-type="s-sponsored-brand"], '
                        '.s-sponsored-brand, '
                        'span:has-text("Sponsored Brand")'
                    )
                    if banner_check:
                        ad_type = "sponsored_brand"

                    ad_products.append({
                        "product_id": asin,
                        "product_url": url,
                        "ad_type": ad_type,
                        "is_ad": True,
                    })

                except Exception:
                    continue

            # 2. 识别顶部/底部品牌横幅
            banner_ads = page.query_selector_all(
                '[data-component-type="s-sponsored-banner"], '
                'div.s-sponsored-brand-banner, '
                'div[data-component-type="s-sponsored-brand"]'
            )
            for banner in banner_ads:
                try:
                    href_el = banner.query_selector("a")
                    if href_el:
                        href = href_el.get_attribute("href") or ""
                        ad_products.append({
                            "product_id": "",
                            "product_url": href if href.startswith("http") else self.base_url + href,
                            "ad_type": "sponsored_brand",
                            "is_ad": True,
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"[Amazon广告] 广告识别异常: {e}", self.task_uuid)

        logger.info(
            f"[Amazon广告] 关键词 '{keyword}': 识别 {len(ad_products)} 个广告位",
            self.task_uuid
        )
        return ad_products

    # ============================================================
    # 内部解析方法
    # ============================================================

    def _parse_search_card(self, card, rank: int) -> Optional[dict]:
        """
        解析单个搜索结果卡片

        参数:
            card: Playwright ElementHandle（商品卡片）
            rank: 搜索排名序号

        返回:
            dict 或 None（解析失败时返回）
        """
        asin = card.get_attribute("data-asin")
        if not asin:
            return None

        product = {
            "product_id": asin,
            "rank_position": rank,
            "is_ad": False,
            "ad_type": "",
        }

        # ---- 标题 ----
        title_el = card.query_selector("h2 a span, h2 span.a-text-normal")
        if title_el:
            product["title"] = title_el.inner_text().strip()

        # ---- 商品链接 ----
        link_el = card.query_selector(
            "a.a-link-normal.s-link-style, h2 a.a-link-normal, a.a-link-normal.s-underline-text"
        )
        if link_el:
            href = link_el.get_attribute("href") or ""
            if href.startswith("/"):
                product["product_url"] = self.base_url + href.split("?")[0]
            else:
                product["product_url"] = href

        # ---- 当前价格 ----
        price_el = card.query_selector("span.a-price span.a-offscreen")
        if price_el:
            price_text = price_el.inner_text().strip()
            product["current_price"] = self._safe_extract_float(price_text)

        # ---- 原价 ----
        orig_el = card.query_selector("span.a-text-price span.a-offscreen")
        if orig_el:
            orig_text = orig_el.inner_text().strip()
            product["original_price"] = self._safe_extract_float(orig_text)

        # ---- 评分 ----
        rating_el = card.query_selector("span.a-icon-alt")
        if rating_el:
            rating_text = rating_el.inner_text().strip()
            match = re.search(r'[\d.]+', rating_text)
            if match:
                product["rating"] = float(match.group())

        # ---- 评论数 ----
        review_el = card.query_selector("span.a-size-base.s-underline-text, span.a-size-base.color-base")
        if review_el:
            review_text = review_el.inner_text().strip()
            match = re.search(r'[\d,]+', review_text)
            if match:
                product["review_count"] = int(match.group().replace(",", ""))

        # ---- 广告标识 ----
        sponsored_el = card.query_selector(
            'span[data-component-type="s-sponsored-label-text"], '
            'span.s-sponsored-label-text, '
            'span:has-text("Sponsored"), '
            'span:has-text("赞助")'
        )
        if sponsored_el:
            product["is_ad"] = True
            product["ad_type"] = "sponsored_product"

        return product

    def _build_detail_url(self, product_id: str) -> str:
        """通过 ASIN 构建商品详情页URL"""
        if not product_id:
            return ""
        return f"{self.base_url}/dp/{product_id}"

    # ============================================================
    # 辅助方法
    # ============================================================

    @staticmethod
    def _url_encode(keyword: str) -> str:
        """URL编码关键词（空格→+，符合Amazon搜索格式）"""
        import urllib.parse
        return urllib.parse.quote_plus(keyword)

    @staticmethod
    def _extract_asin_from_url(url: str) -> str:
        """从商品URL中提取ASIN"""
        if not url:
            return ""
        # 匹配 /dp/B0XXXXXXX 或 /product/B0XXXXXXX
        match = re.search(r'/(?:dp|product|gp/product)/([A-Z0-9]{10})', url)
        if match:
            return match.group(1)
        # 匹配 asin=B0XXXXXXX
        match = re.search(r'asin[=]([A-Z0-9]{10})', url, re.IGNORECASE)
        if match:
            return match.group(1)
        return ""

    def _scroll_page(self, page: Page, times: int = 2):
        """模拟页面滚动，触发懒加载"""
        for _ in range(times):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(0.8)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)

    def _detect_captcha(self, page: Page) -> bool:
        """检测是否遇到 Amazon 验证码页面"""
        captcha_indicators = [
            "Type the characters you see",
            "Enter the characters",
            "validate your request",
            "Sorry, we just need to make sure",
            "Robot Check",
            "CAPTCHA",
        ]
        try:
            body_text = page.inner_text("body")
            return any(indicator.lower() in body_text.lower() for indicator in captcha_indicators)
        except Exception:
            return False
