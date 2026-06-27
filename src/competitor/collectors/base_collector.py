"""
竞品采集器抽象基类
- 定义竞品采集的统一接口
- 封装 Playwright 浏览器生命周期管理
- 提供异常隔离（单条数据错误不影响整体流程）
- 集成 TraceLogger 结构化日志

所有平台采集器必须继承此类并实现抽象方法。
参考 RPADataHub 的 BaseCollector 模式设计。
"""

import sys
import os
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

# 确保项目路径可引用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
except ImportError:
    sync_playwright = None

from logger_config import setup_logger

# 初始化采集器专用日志器
logger = setup_logger("CompetitorCollector")


class BaseCompetitorCollector(ABC):
    """
    竞品采集器抽象基类

    子类必须实现:
        - search_product(keyword: str) -> list[dict]
        - get_product_detail(product_url: str) -> dict
        - get_advert_info(keyword: str) -> list[dict]

    钩子方法（可选覆写）:
        - on_search_start()
        - on_search_complete()
        - on_error()
    """

    # ---- 子类必须覆写的属性 ----
    platform_name: str = "base"          # 平台名称（amazon/walmart/shopee等）
    base_url: str = ""                    # 平台首页/搜索首页URL
    currency: str = "USD"                 # 默认币种

    def __init__(self, task: dict, headless: bool = True):
        """
        初始化采集器

        参数:
            task: 采集任务字典，包含 competitor_id, keywords, asin_list, region 等
            headless: 是否使用无头浏览器模式
        """
        self.task = task
        self.task_uuid = task.get("task_uuid", uuid.uuid4().hex[:16])
        # headless can be overridden by task param (frontend toggle)
        self.headless = task.get("headless", headless) if isinstance(task.get("headless"), bool) else headless
        self.results = []          # 采集结果列表
        self.errors = []           # 错误记录列表
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ============================================================
    # 抽象方法（子类必须实现）
    # ============================================================

    @abstractmethod
    def search_product(self, keyword: str, page: Page) -> list:
        """
        搜索关键词并返回商品列表

        参数:
            keyword: 搜索关键词
            page: Playwright Page 对象

        返回:
            list[dict]: 商品搜索结果列表，每个元素包含:
                {
                    "title": str,           # 商品标题
                    "product_url": str,     # 商品详情页URL
                    "product_id": str,      # 平台商品ID（如ASIN）
                    "current_price": float, # 当前售价
                    "original_price": float,# 原价/划线价
                    "rank_position": int,   # 搜索排名位置
                    "is_ad": bool,          # 是否为广告位
                    "ad_type": str,         # 广告类型（sponsored/banner等）
                    "thumbnail": str,       # 缩略图URL
                }
        """
        raise NotImplementedError

    @abstractmethod
    def get_product_detail(self, product_url: str, page: Page) -> dict:
        """
        获取商品详情页信息

        参数:
            product_url: 商品详情页链接
            page: Playwright Page 对象

        返回:
            dict: 商品详情，包含:
                {
                    "title": str,
                    "current_price": float,
                    "original_price": float,
                    "review_count": int,
                    "rating": float,
                    "seller_name": str,
                    "raw_data": dict,       # 其他平台特有字段
                }
        """
        raise NotImplementedError

    @abstractmethod
    def get_advert_info(self, keyword: str, page: Page) -> list:
        """
        识别搜索结果中的广告位信息

        参数:
            keyword: 搜索关键词
            page: Playwright Page 对象（需已在搜索结果页）

        返回:
            list[dict]: 广告位信息列表
        """
        raise NotImplementedError

    # ============================================================
    # 模板方法：统一采集流程
    # ============================================================

    def collect(self) -> list:
        """
        执行完整的竞品采集流程（模板方法）

        流程:
            1. 启动浏览器
            2. 逐关键词搜索商品
            3. 识别广告位
            4. 获取商品详情（可选）
            5. 汇总结果

        返回:
            list[dict]: 采集结果列表，可直接写入 ods_price_snapshot
        """
        start_time = time.time()
        logger.info(f"[采集开始] task_uuid={self.task_uuid}, platform={self.platform_name}",
                     self.task_uuid)

        if sync_playwright is None:
            error_msg = "Playwright 未安装，请执行: pip install playwright && playwright install chromium"
            logger.error(error_msg, self.task_uuid)
            raise ImportError(error_msg)

        try:
            # 1. 启动浏览器
            self._launch_browser()
            self._report_status("browser_started", "Browser ready")

            # Bot challenge check
            challenge = self._detect_bot_challenge(self._page)
            if challenge:
                if challenge == "login":
                    ok = self._wait_for_login(self._page, timeout_sec=30)
                    if not ok:
                        self._close_browser()
                        return self.results
                elif challenge == "captcha":
                    self._report_status("bot_captcha", "验证码，建议有头模式下处理")
                    logger.error(f"[Bot] captcha - manual intervention needed", self.task_uuid)
                else:
                    self._report_status(f"bot_{challenge}", f"检测到{challenge}")
                    logger.warning(f"[Bot] {challenge} detected", self.task_uuid)

            # 2. 获取搜索关键词列表
            keywords = self._get_keywords()

            # 3. 如果提供了 ASIN/商品ID 列表，直接抓取商品详情
            asin_list = self._get_asin_list()
            if asin_list:
                logger.info(f"[直接采集] 跳过搜索，直接采集 {len(asin_list)} 个ASIN",
                            self.task_uuid)
                for asin in asin_list:
                    self._safe_collect_detail_by_id(asin)

            # 4. 逐关键词搜索
            if keywords:
                logger.info(f"[关键词搜索] 共 {len(keywords)} 个关键词", self.task_uuid)
                self._report_status("searching", f"Searching {len(keywords)} keywords")
                for idx, keyword in enumerate(keywords):
                    self._safe_search_and_collect(keyword, rank_offset=idx * 10)

            status_msg = "completed" if len(self.errors) == 0 else "completed_with_errors"
            self._report_status(status_msg, f"{len(self.results)} results, {len(self.errors)} errors")
            duration = int(time.time() - start_time)
            logger.info(
                f"[采集完成] 共采集 {len(self.results)} 条结果, "
                f"{len(self.errors)} 条错误, 耗时 {duration}s",
                self.task_uuid
            )

        except Exception as e:
            logger.error(f"[采集异常] {e}", self.task_uuid, exc_info=True)
            raise
        finally:
            self._close_browser()

        return self.results

    # ============================================================
    # 浏览器管理（复用 RPADataHub Playwright 模式）
    # ============================================================

    def _launch_browser(self):
        """Start Playwright browser with cookie persistence."""
        logger.info("[Browser] Starting Chromium...", self.task_uuid)
        self._playwright = sync_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]

        region = self.task.get("region", "domestic")
        if region == "international":
            http_proxy = os.environ.get("HTTP_PROXY", "")
            if http_proxy:
                launch_args.append(f"--proxy-server={http_proxy}")
                logger.info(f"[Browser] Using proxy: {http_proxy[:50]}...", self.task_uuid)

        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args
        )

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
        locale_str = "en-US" if region == "international" else "zh-CN"

        # Cookie persistence
        cookie_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies")
        os.makedirs(cookie_dir, exist_ok=True)
        self._cookie_file = os.path.join(cookie_dir, f"{self.platform_name}.json")

        if os.path.exists(self._cookie_file):
            try:
                self._context = self._browser.new_context(
                    viewport={"width": 1366, "height": 768},
                    user_agent=user_agent,
                    locale=locale_str,
                    storage_state=self._cookie_file,
                )
                logger.info(f"[Browser] Cookies loaded from {self._cookie_file}", self.task_uuid)
            except Exception:
                logger.debug("[Browser] Cookie load failed, using fresh context", self.task_uuid)
                self._context = self._browser.new_context(
                    viewport={"width": 1366, "height": 768},
                    user_agent=user_agent,
                    locale=locale_str,
                )
        else:
            self._context = self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=user_agent,
                locale=locale_str,
            )

        self._page = self._context.new_page()
        logger.info("[Browser] Chromium ready", self.task_uuid)

    def _close_browser(self):
        """Close browser, save cookies for future reuse."""
        try:
            # Save cookies before closing
            if hasattr(self, '_cookie_file') and self._context:
                try:
                    self._context.storage_state(path=self._cookie_file)
                    logger.info(f"[Browser] Cookies saved to {self._cookie_file}", self.task_uuid)
                except Exception as e:
                    logger.debug(f"[Browser] Cookie save failed: {e}", self.task_uuid)
        except Exception:
            pass

        try:
            if self._browser:
                self._browser.close()
                logger.info("[Browser] Closed", self.task_uuid)
            if hasattr(self, '_playwright') and self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning(f"[Browser] Close error: {e}", self.task_uuid)

    def _safe_goto(self, url: str, timeout: int = 30000) -> bool:
        """
        安全导航到指定URL（带超时和重试）

        返回:
            bool: 是否成功加载
        """
        for attempt in range(3):
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                # Wait for page to stabilize (prevent mid-navigation detection failures)
                self._page.wait_for_timeout(2000)
                self._page.wait_for_load_state("networkidle", timeout=5000) if False else None  # best-effort
                # Check for login wall after navigation
                nav_challenge = self._detect_bot_challenge(self._page)
                if nav_challenge == "login":
                    logger.info(f"[Nav] Login page after goto, waiting...", self.task_uuid)
                    ok = self._wait_for_login(self._page, timeout_sec=30)
                    if not ok:
                        return False
                return True
            except Exception as e:
                logger.warning(
                    f"[页面加载] 第{attempt+1}次重试失败: {url[:80]}... 原因: {e}",
                    self.task_uuid
                )
                time.sleep(2 ** attempt)  # 指数退避
        logger.error(f"[页面加载] 3次重试后仍失败: {url}", self.task_uuid)
        return False

    # ============================================================
    # 安全采集包装（异常隔离）
    # ============================================================

    def _safe_search_and_collect(self, keyword: str, rank_offset: int = 0):
        """
        安全执行关键词搜索并采集（单关键词异常不影响其他关键词）

        参数:
            keyword: 搜索关键词
            rank_offset: 排名偏移量（分页用）
        """
        keyword_start = time.time()
        try:
            logger.info(f"[搜索] 关键词: '{keyword}'", self.task_uuid)
            self.on_search_start(keyword)

            # 执行搜索（子类实现）
            products = self.search_product(keyword, self._page)
            if not products:
                logger.warning(f"[搜索] 关键词 '{keyword}' 无结果", self.task_uuid)
                return

            # 修正排名偏移
            for i, product in enumerate(products):
                product["rank_position"] = i + 1 + rank_offset

            # 识别广告位
            try:
                ad_products = self.get_advert_info(keyword, self._page)
                ad_urls = {ad.get("product_url", "") for ad in ad_products}
                for product in products:
                    if product.get("product_url", "") in ad_urls:
                        product["is_ad"] = True
                        # 匹配广告类型
                        for ad in ad_products:
                            if ad.get("product_url") == product.get("product_url"):
                                product["ad_type"] = ad.get("ad_type", "sponsored")
                                break
            except Exception as e:
                logger.warning(f"[广告识别] 关键词 '{keyword}' 广告识别失败: {e}",
                               self.task_uuid)

            # 构建快照记录
            snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for product in products:
                self.results.append({
                    "competitor_id": self.task.get("competitor_id"),
                    "task_uuid": self.task_uuid,
                    "platform": self.platform_name,
                    "product_url": product.get("product_url", ""),
                    "title": product.get("title", ""),
                    "current_price": product.get("current_price"),
                    "original_price": product.get("original_price"),
                    "currency": self.currency,
                    "rank_position": product.get("rank_position"),
                    "is_ad": 1 if product.get("is_ad") else 0,
                    "ad_type": product.get("ad_type", ""),
                    "review_count": product.get("review_count"),
                    "rating": product.get("rating"),
                    "snapshot_time": snapshot_time,
                    "raw_json": self._safe_json_dumps(product),
                })

            self.on_search_complete(keyword, len(products))
            elapsed = time.time() - keyword_start
            logger.info(
                f"[搜索完成] 关键词 '{keyword}': 采集 {len(products)} 条, "
                f"耗时 {elapsed:.2f}s",
                self.task_uuid
            )

        except Exception as e:
            error_msg = f"关键词 '{keyword}' 采集失败: {e}"
            logger.error(error_msg, self.task_uuid, exc_info=True)
            self.errors.append({
                "task_uuid": self.task_uuid,
                "keyword": keyword,
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            self.on_error(keyword, e)

    def _safe_collect_detail_by_id(self, product_id: str):
        """
        通过商品ID直接采集详情（适用于按ASIN直接追踪的场景）

        参数:
            product_id: 平台商品ID（如 Amazon ASIN）
        """
        try:
            # 构建商品详情页URL（子类可覆写 _build_detail_url）
            detail_url = self._build_detail_url(product_id)
            if not detail_url:
                logger.warning(f"[详情] 无法构建 {product_id} 的详情页URL", self.task_uuid)
                return

            if not self._safe_goto(detail_url):
                return

            detail = self.get_product_detail(detail_url, self._page)
            if not detail:
                logger.warning(f"[详情] {product_id} 详情为空", self.task_uuid)
                return

            snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.results.append({
                "competitor_id": self.task.get("competitor_id"),
                "task_uuid": self.task_uuid,
                "platform": self.platform_name,
                "product_url": detail_url,
                "title": detail.get("title", ""),
                "current_price": detail.get("current_price"),
                "original_price": detail.get("original_price"),
                "currency": self.currency,
                "rank_position": None,
                "is_ad": 0,
                "ad_type": "",
                "review_count": detail.get("review_count"),
                "rating": detail.get("rating"),
                "snapshot_time": snapshot_time,
                "raw_json": self._safe_json_dumps(detail),
            })

            logger.info(f"[详情] {product_id}: {detail.get('title', 'N/A')[:60]}", self.task_uuid)

        except Exception as e:
            error_msg = f"商品详情采集失败 product_id={product_id}: {e}"
            logger.error(error_msg, self.task_uuid, exc_info=True)
            self.errors.append({
                "task_uuid": self.task_uuid,
                "product_id": product_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
            })

    # ============================================================
    # 钩子方法（子类可选覆写）
    # ============================================================

    def on_search_start(self, keyword: str):
        """搜索开始前钩子"""
        pass

    def on_search_complete(self, keyword: str, count: int):
        """搜索完成后钩子"""
        pass

    def on_error(self, keyword: str, error: Exception):
        """单关键词采集出错钩子（已被 _safe_search_and_collect 捕获）"""
        pass

    # ============================================================
    # 辅助方法
    # ============================================================

    def _get_keywords(self) -> list:
        """从任务参数中解析关键词列表"""
        keywords_raw = self.task.get("keywords", "")
        if isinstance(keywords_raw, list):
            return keywords_raw
        if isinstance(keywords_raw, str):
            import json
            try:
                return json.loads(keywords_raw)
            except json.JSONDecodeError:
                # 纯字符串，按逗号分割
                return [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
        return []

    def _get_asin_list(self) -> list:
        """从任务参数中解析 ASIN/商品ID 列表"""
        asin_raw = self.task.get("asin_list", "")
        if isinstance(asin_raw, list):
            return asin_raw
        if isinstance(asin_raw, str):
            import json
            try:
                return json.loads(asin_raw)
            except json.JSONDecodeError:
                return [a.strip() for a in asin_raw.split(",") if a.strip()]
        return []

    def _build_detail_url(self, product_id: str) -> str:
        """
        根据商品ID构建详情页URL（子类应覆写）

        参数:
            product_id: 平台商品ID

        返回:
            str: 商品详情页完整URL
        """
        return ""

    @staticmethod
    def _safe_json_dumps(obj) -> str:
        """安全的JSON序列化，防止 datetime/decimal 等类型报错"""
        import json
        import decimal

        def default_encoder(o):
            if isinstance(o, datetime):
                return o.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(o, decimal.Decimal):
                return float(o)
            return str(o)

        try:
            return json.dumps(obj, ensure_ascii=False, default=default_encoder)
        except Exception:
            return str(obj)

    @staticmethod
    def _safe_extract_float(value, default=None):
        """安全提取浮点数（处理货币符号、逗号等）"""
        if value is None:
            return default
        import re
        if isinstance(value, (int, float)):
            return float(value)
        # 去除货币符号和空格
        cleaned = re.sub(r'[^\d.,]', '', str(value))
        # 处理逗号分隔符（如 "1,299.99" → "1299.99"）
        if ',' in cleaned and '.' in cleaned:
            cleaned = cleaned.replace(',', '')
        cleaned = cleaned.replace(',', '.')
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return default

    # ============================================================
    # Status reporting & bot detection
    # ============================================================

    def _report_status(self, status: str, detail: str = ""):
        """Report collection status to Redis for frontend polling."""
        try:
            from mq.redis_queue import CompetitorRedisQueue
            from config.settings import get_config
            q = CompetitorRedisQueue(redis_url=get_config().redis.url)
            q.set_crawl_status(self.task_uuid, status, detail)
        except Exception:
            pass

    def _detect_bot_challenge(self, page) -> Optional[str]:
        """Detect bot/captcha/login challenge on page."""
        try:
            url = (page.url or "").lower()
            captcha_indicators = page.query_selector_all(
                '#nc_1_n1z, .nc_wrapper, .slider, iframe[src*="captcha"]'
            )
            if len(captcha_indicators) > 0:
                return "captcha"

            is_login_url = any(w in url for w in [
                "login.taobao", "login.jd", "login.", "passport.", "signin", "auth"
            ])
            if is_login_url:
                pwd_fields = page.query_selector_all(
                    'input[type="password"]:not([type="hidden"]), .login-form, #login-form'
                )
                if len(pwd_fields) > 0:
                    return "login"

            try:
                html = page.content().lower()
            except Exception:
                html = ""
            login_signals = 0
            if "password" in html: login_signals += 1
            visible_pwd = page.query_selector_all('input[type="password"]:not([type="hidden"])')
            if len(visible_pwd) > 0: login_signals += 2
            if login_signals >= 3:
                return "login"

            if any(w in url for w in ["verify", "challenge", "block"]):
                return "verify"
        except Exception:
            pass
        return None

    def _wait_for_login(self, page, timeout_sec: int = 30) -> bool:
        """Wait for user login + frontend confirmation."""
        logger.info(f"[Login Wait] Waiting {timeout_sec}s...", self.task_uuid)
        self._report_status("waiting_login", f"等待登录中，请在 {timeout_sec}s 内完成登录...")

        start = time.time()
        was_login = True

        while time.time() - start < timeout_sec:
            time.sleep(3)
            elapsed = int(time.time() - start)
            remaining = timeout_sec - elapsed

            try:
                challenge = self._detect_bot_challenge(page)
                if challenge != "login" and was_login:
                    logger.info(f"[Login Wait] Page stabilized, waiting for confirmation...", self.task_uuid)
                    self._report_status("login_done", "登录页面已稳定，等待用户在前端点击确认...")

                    confirmed = False
                    while time.time() - start < timeout_sec:
                        time.sleep(2)
                        try:
                            from mq.redis_queue import CompetitorRedisQueue
                            from config.settings import get_config
                            q = CompetitorRedisQueue(redis_url=get_config().redis.url)
                            st = q.get_crawl_status(self.task_uuid)
                            if st and st.get("status") == "login_confirmed":
                                confirmed = True
                                break
                        except Exception:
                            pass
                        if self._detect_bot_challenge(page) == "login":
                            was_login = True
                            break

                    if confirmed:
                        time.sleep(1)
                        if self._detect_bot_challenge(page) != "login":
                            logger.info(f"[Login Wait] Confirmed, proceeding", self.task_uuid)
                            return True
                    continue

                was_login = (challenge == "login")
                if elapsed % 10 < 3:
                    self._report_status("waiting_login", f"等待登录确认中...剩余 {remaining}s")

            except Exception as e:
                logger.debug(f"[Login Wait] Poll error: {e}", self.task_uuid)

        logger.warning(f"[Login Wait] Timeout", self.task_uuid)
        self._report_status("login_timeout", f"登录超时 ({timeout_sec}s)，采集已跳过")
        return False

