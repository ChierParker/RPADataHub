"""
LeadScraper 核心采集引擎
=======================
包含共享状态管理、Playwright 浏览器控制、Google 搜索、联系方式提取、
去重、CAPTCHA 检测与处理、Excel 输出等全部采集逻辑。

本模块独立于 Flask，可单独测试。
"""

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeoutError, Error as PwError

from config import (
    OUTPUT_DIR, PROFILES_DIR, BROWSER_DIR, LOG_DIR,
    DEFAULT_MAX_PAGES, DEFAULT_CONCURRENCY, RETRY_TIMES, RETRY_DELAY_SECS,
    CAPTCHA_TIMEOUT_SECS, PAGE_LOAD_TIMEOUT_MS, SEARCH_TIMEOUT_MS,
    INPUT_COLUMN_KEYWORD,
    CAPTCHA_KEYWORDS, CAPTCHA_SELECTORS,
    GOOGLE_HOME, GOOGLE_SEARCH_SELECTOR,
    NEXT_PAGE_SELECTORS, CANONICAL_SELECTOR,
    DEFAULT_USER_AGENT,
)
from excel_exporter import save_target_sheet as _save_target_sheet
from lead_processing import (
    deduplicate_leads as _deduplicate_leads,
    extract_emails as _extract_emails,
    extract_phones as _extract_phones,
    sanitize_sheet_name as _sanitize_sheet_name,
)
from logger_config import TraceLogger

# ============================================================
# 模块级日志器
# ============================================================
_logger = TraceLogger("LeadScraper", str(LOG_DIR))


# ============================================================
# 数据类
# ============================================================

@dataclass
class TargetInfo:
    """单个采信目标的元数据"""
    name: str           # Sheet 名称（截断至 31 字符）
    keyword: str        # Google 搜索关键词
    selected: bool = True
    status: str = "pending"   # pending / running / done / need-manual / failed
    leads_count: int = 0
    error: str = ""


@dataclass
class ScraperConfig:
    """采集任务配置"""
    max_pages: int = DEFAULT_MAX_PAGES
    concurrency: int = DEFAULT_CONCURRENCY
    output_dir: Path = OUTPUT_DIR
    headless: bool = True
    country_code: str = ""
    phone_filter_enabled: bool = False
    proxy: str = ""
    captcha_timeout: int = CAPTCHA_TIMEOUT_SECS


# ============================================================
# 共享状态（线程安全）
# ============================================================

class ScraperState:
    """
    线程安全的采集状态容器。
    由 Flask 主线程写入（用户操作）和 scraper 后台线程写入（进度更新），
    Flask 路由线程读取（返回 JSON 给前端）。

    线程安全策略：
    - 简单值通过 `self.lock` 保护（RLock 支持同一线程重入）
    - CAPTCHA 同步通过 `threading.Event` 实现
    - `stop_flag` 为原子布尔量，无需锁
    """

    def __init__(self):
        self.lock = threading.RLock()  # 可重入锁，避免嵌套调用死锁
        self.running = False
        self.stop_flag = False
        self.targets: list[TargetInfo] = []
        self.current_target_index = -1
        self.current_page = 0
        self.total_pages = 0
        self.leads_found = 0
        self.captcha_detected = False
        self.captcha_page_url = ""
        self.captcha_skip_target = False
        self.captcha_resolved = threading.Event()
        self.captcha_target_name = ""
        self.error_message = ""
        self.start_time: float = 0.0
        self.output_filepath: str = ""

    # ---- 线程安全的读写 ----

    def set_running(self, val: bool):
        with self.lock:
            self.running = val

    def is_running(self) -> bool:
        with self.lock:
            return self.running

    def set_current(self, index: int, page: int, total: int):
        with self.lock:
            self.current_target_index = index
            self.current_page = page
            self.total_pages = total

    def add_leads(self, count: int):
        with self.lock:
            self.leads_found += count

    def set_captcha(self, detected: bool, url: str = "", target_name: str = ""):
        with self.lock:
            self.captcha_detected = detected
            self.captcha_page_url = url
            self.captcha_target_name = target_name

    def set_error(self, msg: str):
        with self.lock:
            self.error_message = msg

    def update_target(self, index: int, **kwargs):
        with self.lock:
            if 0 <= index < len(self.targets):
                t = self.targets[index]
                for k, v in kwargs.items():
                    setattr(t, k, v)

    def to_dict(self) -> dict:
        """生成前端轮询所需的完整状态快照"""
        with self.lock:
            current_target = ""
            if 0 <= self.current_target_index < len(self.targets):
                current_target = self.targets[self.current_target_index].name

            return {
                "running": self.running,
                "current_target": current_target,
                "current_target_index": self.current_target_index,
                "current_page": self.current_page,
                "total_pages": self.total_pages,
                "leads_found": self.leads_found,
                "captcha_detected": self.captcha_detected,
                "captcha_page_url": self.captcha_page_url,
                "captcha_target_name": self.captcha_target_name,
                "error": self.error_message,
                "output_filepath": self.output_filepath,
                "targets": [
                    {
                        "name": t.name,
                        "keyword": t.keyword,
                        "selected": t.selected,
                        "status": t.status,
                        "leads": t.leads_count,
                        "error": t.error,
                    }
                    for t in self.targets
                ],
            }


# ============================================================
# 公开函数
# ============================================================

def load_targets(filepath) -> list[dict]:
    """
    从上传的 Excel 文件解析关键词列表。

    要求 Excel 至少包含 "关键词" 列。
    返回 list[dict]，每个 dict 包含 name 和 keyword。

    Args:
        filepath: Excel 文件路径（str 或 Path）

    Returns:
        [{"name": "Acme-UK", "keyword": "auto parts WhatsApp +44"}, ...]
    """
    filepath = Path(filepath)
    df = pd.read_excel(filepath)

    # 标准化列名：查找含"关键词"的列
    keyword_col = None
    for col in df.columns:
        if INPUT_COLUMN_KEYWORD in str(col):
            keyword_col = col
            break

    if keyword_col is None:
        raise ValueError(
            f"Excel file missing '{INPUT_COLUMN_KEYWORD}' column. "
            f"Available columns: {list(df.columns)}"
        )

    targets = []
    for idx, row in df.iterrows():
        keyword = str(row[keyword_col]).strip()
        if not keyword or keyword.lower() == "nan":
            continue

        # Sheet 名称：取关键词前 N 个字符，替换非法字符
        if "目标名称" in df.columns:
            name = str(row.get("目标名称", keyword)).strip()
        else:
            name = keyword

        name = _sanitize_sheet_name(name)
        targets.append({"name": name, "keyword": keyword})

    _logger.info(f"从 {filepath.name} 解析出 {len(targets)} 个目标")
    return targets


def run_scraper(state: ScraperState, targets: list[TargetInfo], config: ScraperConfig) -> None:
    """
    采集主入口，在后台线程中运行。

    Args:
        state: 共享状态对象（线程安全）
        targets: 待采集目标列表
        config: 采集配置
    """
    trace_id = _logger.new_trace_id()
    _logger.info(f"[{trace_id}] 采集任务启动，共 {len(targets)} 个目标", trace_id)

    # 生成输出文件路径
    config.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_excel = config.output_dir / f"采集结果_{timestamp}.xlsx"
    state.output_filepath = str(output_excel)

    state.set_running(True)
    state.stop_flag = False
    state.leads_found = 0
    state.start_time = time.time()
    state.set_error("")

    playwright_instance = None

    try:
        for idx, target in enumerate(targets):
            if not target.selected:
                continue
            if state.stop_flag:
                _logger.info(f"[{trace_id}] 收到停止信号，退出采集", trace_id)
                break

            _logger.info(f"[{trace_id}] 开始处理目标 [{idx+1}/{len(targets)}]: {target.name}", trace_id)
            state.set_current(idx, 0, config.max_pages)
            state.update_target(idx, status="running", error="")
            state.set_captcha(False)

            # 所有目标共用一个浏览器 Profile（保持 Cookie/Session 连续性）
            profile_dir = PROFILES_DIR / "default"
            profile_dir.mkdir(parents=True, exist_ok=True)

            pw = None
            context = None
            page = None
            headed_mode = config.headless  # 默认 headless
            skip_target = False
            target_leads: list[dict] = []

            try:
                # 启动浏览器
                pw, context, page = _launch_browser(
                    str(profile_dir), headed_mode, config.proxy
                )

                # 访问 Google 首页（使用 domcontentloaded 策略加速）
                _logger.info(f"[{trace_id}] 正在访问 Google...", trace_id)
                try:
                    page.goto(GOOGLE_HOME, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)  # 等待异步JS加载完成
                except Exception as goto_err:
                    _logger.warning(f"[{trace_id}] Google 访问异常（可能网络问题）: {goto_err}", trace_id)
                    # 不直接放弃，尝试继续

                _dismiss_cookie_banners(page)
                _logger.info(f"[{trace_id}] Google 页面已加载，当前URL: {page.url}", trace_id)

                # 首页 CAPTCHA 检测
                if _detect_captcha(page):
                    _logger.warning(f"[{trace_id}] Google 首页检测到 CAPTCHA", trace_id)
                    pw, context, page, headed_mode, resolved = _handle_captcha(
                        state, pw, context, page, str(profile_dir), config
                    )
                    if not resolved:
                        state.update_target(idx, status="need-manual")
                        continue

                # 执行搜索
                _logger.info(f"[{trace_id}] 搜索关键词: {target.keyword}", trace_id)
                _do_search(page, target.keyword)

                # 翻页采集
                for pg in range(1, config.max_pages + 1):
                    if state.stop_flag:
                        break

                    state.set_current(idx, pg, config.max_pages)

                    # SERP CAPTCHA 检测
                    if _detect_captcha(page):
                        _logger.warning(f"[{trace_id}] 第 {pg} 页检测到 CAPTCHA", trace_id)
                        pw, context, page, headed_mode, resolved = _handle_captcha(
                            state, pw, context, page, str(profile_dir), config
                        )
                        if not resolved:
                            skip_target = True
                            break

                    # 提取当前页搜索结果
                    results = _extract_search_results(page)
                    if not results:
                        _logger.info(f"[{trace_id}] 第 {pg} 页无搜索结果，停止翻页", trace_id)
                        break

                    _logger.info(f"[{trace_id}] 第 {pg} 页获取到 {len(results)} 条结果", trace_id)

                    # 并发访问结果页面
                    page_leads = _visit_results_concurrent(
                        context, results, config, state, trace_id
                    )
                    target_leads.extend(page_leads)
                    target_leads = _deduplicate_leads(target_leads)

                    state.add_leads(len(page_leads))

                    # 翻页
                    if not _go_next_page(page):
                        _logger.info(f"[{trace_id}] 无下一页，停止翻页", trace_id)
                        break

                if skip_target or state.captcha_skip_target:
                    state.update_target(idx, status="need-manual")
                    state.captcha_skip_target = False
                    state.set_captcha(False)
                    continue

                # 写入当前目标的结果
                if target_leads:
                    _save_target_sheet(target.name, target_leads, output_excel)
                    state.update_target(idx, status="done", leads_count=len(target_leads))
                    _logger.info(
                        f"[{trace_id}] 目标 {target.name} 完成，获取 {len(target_leads)} 条",
                        trace_id,
                    )
                else:
                    state.update_target(idx, status="done", leads_count=0)
                    _logger.info(f"[{trace_id}] 目标 {target.name} 完成，无结果", trace_id)

            except Exception as exc:
                _logger.error(
                    f"[{trace_id}] 目标 {target.name} 异常: {exc}", trace_id, exc_info=True
                )
                state.update_target(idx, status="failed", error=str(exc)[:200])

            finally:
                # 清理浏览器资源
                try:
                    if context:
                        context.close()
                    if pw:
                        pw.stop()
                except Exception:
                    pass

        # 所有目标处理完毕
        _logger.info(
            f"[{trace_id}] 采集完成。总计获取 {state.leads_found} 条线索，"
            f"输出文件: {output_excel}",
            trace_id,
        )

    except Exception as exc:
        _logger.error(f"[{trace_id}] 采集引擎崩溃: {exc}", trace_id, exc_info=True)
        state.set_error(str(exc))

    finally:
        state.set_running(False)


# ============================================================
# 浏览器控制
# ============================================================

def _launch_browser(user_data_dir: str, headless: bool = True, proxy: str = ""):
    """
    启动 Playwright Chromium 浏览器，使用持久化上下文以保留 Cookie。

    Args:
        user_data_dir: 用户数据目录路径
        headless: 是否无头模式
        proxy: 代理服务器地址（如 "http://127.0.0.1:7890"）

    Returns:
        (playwright_instance, browser_context, page)
    """
    # 基础启动参数
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-infobars",
    ]

    if headless:
        # 无头模式专用参数
        args.append("--disable-gpu")
        args.append("--window-size=1920,1080")
        _logger.info(f"启动无头浏览器 (headless) profile={user_data_dir}")
    else:
        # 有头模式：确保窗口可见、最大化
        args.append("--start-maximized")
        args.append("--window-size=1920,1080")
        _logger.info(f"启动有头浏览器 (headed) — 浏览器窗口即将弹出 profile={user_data_dir}")

    pw = sync_playwright().start()

    launch_options = {
        "headless": headless,
        "args": args,
    }

    # 如果有便携版 Chromium，使用指定路径
    chrome_exe = BROWSER_DIR / "chrome-win" / "chrome.exe"
    if chrome_exe.exists():
        launch_options["executable_path"] = str(chrome_exe)
        _logger.debug(f"使用便携版 Chromium: {chrome_exe}")

    if proxy:
        launch_options["proxy"] = {"server": proxy}

    context = pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        **launch_options,
    )

    # 设置 User-Agent
    context.set_extra_http_headers({"User-Agent": DEFAULT_USER_AGENT})

    page = context.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})

    return pw, context, page


def _dismiss_cookie_banners(page):
    """尝试关闭 Google Cookie 同意弹窗"""
    try:
        # Google 的 cookie 同意按钮
        page.click("button:has-text('Accept all')", timeout=3000)
        _logger.debug("已关闭 Cookie 弹窗")
    except Exception:
        pass
    try:
        page.click("button:has-text('Reject all')", timeout=2000)
    except Exception:
        pass


# ============================================================
# Google 搜索
# ============================================================

def _do_search(page, keyword: str):
    """
    在 Google 搜索框中输入关键词并提交搜索。

    Args:
        page: Playwright Page 对象
        keyword: 搜索关键词
    """
    _logger.info(f"正在Google搜索: {keyword}")
    # 等待搜索框出现
    page.wait_for_selector(GOOGLE_SEARCH_SELECTOR, timeout=PAGE_LOAD_TIMEOUT_MS)

    search_box = page.locator(GOOGLE_SEARCH_SELECTOR).first
    search_box.click()
    search_box.fill(keyword)
    search_box.press("Enter")

    # 等待搜索结果加载（使用 domcontentloaded 加速）
    try:
        page.wait_for_load_state("domcontentloaded", timeout=SEARCH_TIMEOUT_MS)
    except Exception:
        pass
    page.wait_for_timeout(2000)  # 额外等待异步渲染
    _logger.info(f"搜索结果页已加载: {page.url}")


def _extract_search_results(page) -> list[dict]:
    """
    从当前 Google SERP 提取有机搜索结果。

    适配新版 Google SERP DOM 结构：
      div.MjjYud → div.tF2Cxc → a[jsname='UWckNb'] (h3 + cite)
                              → span/VwiC3b (snippet)

    Returns:
        [{"title": "...", "url": "https://...", "snippet": "..."}, ...]
    """
    results = []
    try:
        # 等待搜索结果容器出现（新版 Google SERP）
        page.wait_for_selector("#rso, #search", timeout=10000)
        page.wait_for_timeout(500)

        # 使用 JS 在浏览器内直接提取，避免多次 IPC 往返
        results = page.evaluate("""
            () => {
                const results = [];
                // 找到所有有机结果链接 (jsname='UWckNb')
                const links = document.querySelectorAll('a[jsname="UWckNb"]');

                for (const link of links) {
                    try {
                        const href = link.getAttribute('href');
                        if (!href) continue;

                        // 排除 Google 自身链接
                        if (href.includes('google.com/shopping') ||
                            href.includes('google.com/search') ||
                            href.includes('googleadservices') ||
                            href.includes('webcache.google')) continue;

                        // 获取标题 (h3)
                        const h3 = link.querySelector('h3');
                        const title = h3 ? h3.textContent.trim() : '';
                        if (!title) continue;

                        // 获取摘要：向上找到 MjjYud 容器，提取其中描述文本
                        let snippet = '';
                        const container = link.closest('.MjjYud');
                        if (container) {
                            // 尝试多种摘要选择器
                            const snippetEls = container.querySelectorAll(
                                'div[data-sncf], span.aCOpRe, div.VwiC3b, div.lEBKkf, span.zz3gNc'
                            );
                            for (const el of snippetEls) {
                                const text = el.textContent.trim();
                                if (text && text.length > 20) {
                                    snippet = text;
                                    break;
                                }
                            }
                            // 如果摘要选择器没找到，尝试获取容器的整体文本
                            if (!snippet) {
                                const allText = container.innerText;
                                // 取标题后面的内容作为摘要（粗略提取）
                                const titleIdx = allText.indexOf(title);
                                if (titleIdx >= 0) {
                                    const afterTitle = allText.substring(titleIdx + title.length).trim();
                                    // 去掉URL行，取剩余文本的前200字符
                                    const lines = afterTitle.split('\\n').filter(l =>
                                        !l.startsWith('http') && l.length > 10
                                    );
                                    snippet = lines.slice(0, 3).join(' ').substring(0, 300);
                                }
                            }
                        }

                        results.push({
                            title: title,
                            url: href,
                            snippet: snippet
                        });
                    } catch(e) {}
                }
                return results;
            }
        """)

        _logger.info(f"提取到 {len(results) if results else 0} 条搜索结果")
    except Exception as e:
        _logger.warning(f"提取搜索结果失败: {e}")
        results = []

    return results


def _go_next_page(page) -> bool:
    """点击 Google 搜索结果下一页，返回是否成功"""
    for selector in NEXT_PAGE_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue
    return False


# ============================================================
# 结果页面访问与信息提取
# ============================================================

def _visit_results_concurrent(context, results: list[dict], config: ScraperConfig,
                               state: ScraperState, trace_id: str) -> list[dict]:
    """
    使用线程池并发访问搜索结果页面，提取联系方式。

    注意：Playwright 不是线程安全的，因此使用同步方式串行访问，
    但用 async_playwright 或每个线程创建独立 page 可实现真正并发。
    这里采用保守策略：单线程顺序访问以避免线程问题。
    """
    all_leads = []
    for result in results:
        if state.stop_flag:
            break
        try:
            leads = _visit_result_page(context, result, config)
            if leads:
                all_leads.extend(leads)
        except Exception as exc:
            _logger.warning(f"访问 {result.get('url', '?')[:60]} 失败: {exc}", trace_id)

    return all_leads


def _visit_result_page(context, result: dict, config: ScraperConfig) -> list[dict]:
    """
    访问单个搜索结果页面，提取联系方式。

    Args:
        context: Playwright BrowserContext
        result: {"title": ..., "url": ..., "snippet": ...}
        config: 采集配置

    Returns:
        [{"公司名": ..., "邮箱": ..., "电话": ..., ...}, ...]
    """
    url = result.get("url", "")
    if not url:
        return []

    page = None
    leads = []

    for attempt in range(1 + RETRY_TIMES):
        try:
            page = context.new_page()
            page.set_viewport_size({"width": 1920, "height": 1080})
            page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # 获取页面文本
            page_text = page.inner_text("body").lower()

            # ---- 提取各维度信息 ----
            emails = _extract_emails(page_text)
            phones = _extract_phones(
                page_text, config.country_code, config.phone_filter_enabled
            )
            whatsapp_urls = _extract_whatsapp_links(page)
            website = _extract_website(page, url)

            if emails or phones or whatsapp_urls:
                # 组合：每个联系方式组合创建一条记录
                lead = {
                    "公司名": result.get("title", ""),
                    "联系人": "",
                    "邮箱": "; ".join(emails) if emails else "",
                    "电话": "; ".join(phones) if phones else "",
                    "WhatsApp链接": "; ".join(whatsapp_urls) if whatsapp_urls else "",
                    "网站": website,
                    "来源链接": url,
                    "采集时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                leads.append(lead)

            break  # 成功则退出重试循环

        except (PwTimeoutError, PwError) as e:
            if attempt < RETRY_TIMES:
                _logger.debug(f"访问 {url[:60]} 超时，第 {attempt+1} 次重试...")
                time.sleep(RETRY_DELAY_SECS)
            else:
                _logger.warning(f"访问 {url[:60]} 失败（已达最大重试次数）: {e}")
        except Exception as e:
            _logger.warning(f"访问 {url[:60]} 异常: {e}")
            break
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    return leads


def _extract_whatsapp_links(page) -> list[str]:
    """从页面中提取 WhatsApp 链接"""
    urls = set()
    try:
        links = page.query_selector_all("a[href*='wa.me'], a[href*='api.whatsapp.com']")
        for link in links:
            href = link.get_attribute("href")
            if href:
                urls.add(href)
    except Exception:
        pass
    return list(urls)[:10]


def _extract_website(page, fallback_url: str) -> str:
    """
    提取网站主域名。
    优先取 <link rel="canonical">，其次为当前页面 hostname。
    """
    try:
        canonical = page.query_selector(CANONICAL_SELECTOR)
        if canonical:
            href = canonical.get_attribute("href")
            if href:
                return href
    except Exception:
        pass

    # Fallback：使用当前页面 URL 的 origin
    try:
        current_url = page.url
        from urllib.parse import urlparse
        parsed = urlparse(current_url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return fallback_url


# ============================================================
# CAPTCHA 检测与处理
# ============================================================

def _detect_captcha(page) -> bool:
    """
    检测当前页面是否存在 CAPTCHA。

    检测策略：
    1. 页面 title / 文本中是否包含 CAPTCHA 关键词
    2. DOM 中是否存在 CAPTCHA 相关 CSS 选择器
    """
    try:
        title = page.title().lower()
        for kw in CAPTCHA_KEYWORDS:
            if kw in title:
                _logger.info(f"CAPTCHA 检测（title）: {kw}")
                return True

        body_text = page.inner_text("body").lower()
        for kw in CAPTCHA_KEYWORDS:
            if kw in body_text:
                _logger.info(f"CAPTCHA 检测（body）: {kw}")
                return True

        for selector in CAPTCHA_SELECTORS:
            try:
                el = page.query_selector(selector)
                if el:
                    _logger.info(f"CAPTCHA 检测（selector）: {selector}")
                    return True
            except Exception:
                continue

    except Exception as e:
        _logger.warning(f"CAPTCHA 检测异常: {e}")

    return False


def _handle_captcha(state: ScraperState, pw, context, page,
                     profile_dir: str, config: ScraperConfig):
    """
    CAPTCHA 处理流程：
    1. 保存当前页面 URL
    2. 关闭 headless 浏览器
    3. 启动 headed 浏览器（同一 profile）
    4. 设置 state.captcha_detected = True
    5. 阻塞等待用户解决或超时
    6. 返回新浏览器实例和是否已解决

    Returns:
        (new_pw, new_context, new_page, headed_mode, resolved)
    """
    captcha_url = page.url
    _logger.info(f"CAPTCHA 处理开始，URL: {captcha_url}")

    # 通知前端
    state.set_captcha(True, captcha_url)
    state.captcha_skip_target = False
    state.captcha_resolved.clear()

    # 关闭旧浏览器
    try:
        context.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass

    # 启动 headed 浏览器
    _logger.info("启动 headed 浏览器供用户解决 CAPTCHA...")
    headed_pw, headed_context, headed_page = _launch_browser(
        profile_dir, headless=False, proxy=config.proxy
    )

    try:
        headed_page.goto(captcha_url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded")
    except Exception:
        pass

    # 等待用户解决或超时
    _logger.info(f"等待用户解决 CAPTCHA（超时 {config.captcha_timeout}s）...")
    resolved = state.captcha_resolved.wait(timeout=config.captcha_timeout)

    if not resolved:
        _logger.warning("CAPTCHA 超时，标记当前目标为需要手动处理")
        state.captcha_skip_target = True
        state.set_captcha(False)
        return headed_pw, headed_context, headed_page, False, False

    if state.captcha_skip_target:
        _logger.info("用户选择跳过当前目标")
        state.set_captcha(False)
        return headed_pw, headed_context, headed_page, False, False

    _logger.info("CAPTCHA 已解决，继续采集（保持 headed 模式）")
    state.set_captcha(False)
    return headed_pw, headed_context, headed_page, False, True
