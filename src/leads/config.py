"""
LeadScraper 全局配置常量
======================
所有全局路径、列定义、正则模式、超时参数、CAPTCHA检测信号均定义于此。
导入顺序：本模块零依赖，可被所有其他模块安全导入。

支持两种运行模式：
  - 开发模式：python app.py，BASE_DIR = 本文件所在目录
  - 打包模式：PyInstaller --onedir，BASE_DIR = exe 所在目录
外部 settings.json 可覆盖大部分用户可配置参数。
"""

import json
import os
import sys
from pathlib import Path

# ============================================================
# 运行环境检测与基础路径
# ============================================================
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后：以 exe 所在目录为基准（便携式）
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    # 开发模式：以当前文件所在目录为基准
    BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "input"           # 上传的 Excel 关键词文件
OUTPUT_DIR = BASE_DIR / "output"         # 采集结果输出目录
PROFILES_DIR = BASE_DIR / "profiles"     # Playwright 用户数据目录（按 target 隔离）
BROWSER_DIR = BASE_DIR / "browser"       # Chromium 便携版存放目录
LOG_DIR = BASE_DIR / "logs"              # 应用日志目录
TEMPLATES_DIR = BASE_DIR / "templates"   # Flask 模板目录
STATIC_DIR = BASE_DIR / "static"         # 静态资源目录

# ============================================================
# 运行时参数
# ============================================================
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = False
MAX_UPLOAD_SIZE_MB = 50                  # 上传文件大小上限

# ============================================================
# 采集参数
# ============================================================
DEFAULT_CONCURRENCY = 5    # 默认并行访问页面数
CONCURRENCY_MIN = 3        # 最小并行数
CONCURRENCY_MAX = 8        # 最大并行数
DEFAULT_MAX_PAGES = 3      # 默认 Google 搜索翻页数
MAX_PAGES_MIN = 1
MAX_PAGES_MAX = 10
RETRY_TIMES = 2            # 网络超时重试次数
RETRY_DELAY_SECS = 3       # 重试间隔秒数
CAPTCHA_TIMEOUT_SECS = 600 # CAPTCHA 手动解决超时（10分钟）
PAGE_LOAD_TIMEOUT_MS = 30000   # 页面加载超时 ms
SEARCH_TIMEOUT_MS = 60000      # 搜索等待超时 ms
POLL_INTERVAL_SECS = 1.5       # 前端状态轮询间隔

# 代理和电话过滤（可被 settings.json 覆盖）
DEFAULT_PROXY = ""
DEFAULT_COUNTRY_CODE = ""

# ============================================================
# Excel 输入列定义
# ============================================================
# 业务员上传的 Excel 必须包含 "关键词" 列
INPUT_COLUMN_KEYWORD = "关键词"

# ============================================================
# Excel 输出列定义（按文档规范）
# ============================================================
OUTPUT_COLUMNS = [
    "序号",
    "公司名",
    "联系人",
    "邮箱",
    "电话",
    "WhatsApp链接",
    "网站",
    "来源链接",
    "采集时间",
]

# Excel Sheet 名称最大长度
EXCEL_SHEET_MAXLEN = 31

# ============================================================
# 正则表达式 — 联系方式提取
# ============================================================

# 邮箱（标准格式）
EMAIL_REGEX = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"

# 电话（通用国际格式，含分机号）
PHONE_REGEX = r"(?:\+?\d{1,4}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{2,4}[\s.\-]?\d{2,4}(?:[\s.\-]?\d{2,4})?"

# WhatsApp 链接匹配
WHATSAPP_PATTERNS = [
    r"https?://wa\.me/\+\d+",
    r"https?://wa\.me/\d+",
    r"https?://api\.whatsapp\.com/send\?phone=\d+",
]

# ============================================================
# 邮件发送配置（开发信功能）
# 业务员如需修改账密，直接修改此处即可
# ============================================================
SMTP_CONFIG = {
    "host": "smtp.gmail.com",           # SMTP 服务器
    "port": 587,                         # 端口 (587=TLS, 465=SSL)
    "username": "your-email@gmail.com",  # 发件邮箱
    "password": "your-app-password",     # 邮箱密码或应用专用密码
    "use_tls": True,
    "from_name": "LeadScraper",          # 发件人显示名称
    "send_interval_secs": 3,             # 每封邮件间隔秒数（防限流）
}

# 开发信默认模板（{keyword} {company} {email} 等会在发送时替换）
# 每个关键词在 Campaign 页面可独立编辑和保存
DEFAULT_EMAIL_TEMPLATES = {
    "subject": "Inquiry Regarding {keyword} — Partnership Opportunity",

    "body": """Dear {company} Team,

My name is [Your Name], and I represent a leading international trading company specializing in global sourcing and supply chain solutions.

I came across {company} while conducting market research on "{keyword}", and I was impressed by your company's presence in this sector. We are currently expanding our supplier network and believe there is strong potential for a mutually beneficial partnership.

About Our Company:
We have extensive experience in international procurement, with established distribution channels across multiple markets. Our clients consistently seek high-quality products in the {keyword} category, and we are actively looking for reliable partners to meet this growing demand.

We Would Like To:
1. Learn more about {company}'s product range and specifications
2. Receive your latest catalog and pricing information
3. Explore opportunities for long-term collaboration
4. Discuss potential OEM/ODM arrangements if applicable

Should you be interested, we would be delighted to schedule a call or video conference at your convenience to discuss how we can work together. Please feel free to reach out via email or WhatsApp.

Thank you for your time and consideration. We look forward to the possibility of building a successful partnership with {company}.

Warm regards,
[Your Name]
International Sourcing Department
Email: [your-email]
WhatsApp: [your-whatsapp]
---
This is a business development inquiry. If you are not the right contact person, we would appreciate it if you could forward this message to the appropriate department.""",
}

# ============================================================
# CAPTCHA 检测信号
# ============================================================

# 关键词检测（页面文本 / title 中出现以下任一视为 CAPTCHA）
CAPTCHA_KEYWORDS = [
    "captcha",
    "unusual traffic",
    "not a robot",
    "verify you are human",
    "are you a robot",
    "请输入验证码",
    "验证码",
    "人机验证",
    "recaptcha",
    "cf-challenge",
    "cf_captcha",
    "hcaptcha",
    "verify that you are not a robot",
    "请证明你不是机器人",
]

# CSS 选择器检测（页面中存在以下任一元素视为 CAPTCHA）
CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='cf-challenge']",
    "#captcha",
    "#captcha-form",
    ".g-recaptcha",
    "#px-captcha",
    "#challenge-stage",
    "#challenge-form",
    "div[aria-label*='captcha' i]",
    "div[aria-label*='验证码' i]",
]

# ============================================================
# Google 搜索相关
# ============================================================
GOOGLE_HOME = "https://www.google.com"
GOOGLE_SEARCH_SELECTOR = "textarea[name='q'], input[name='q']"

# 有机搜索结果选择器（排除广告、购物、视频等）
SERP_RESULT_SELECTORS = [
    "div.g a[href^='http']",
    "div[data-sokoban-container] a[href^='http']",
]

# "下一页" 按钮选择器
NEXT_PAGE_SELECTORS = [
    "a#pnnext",
    "a[aria-label='Next page']",
    "a[aria-label*='next' i]",
    "a[aria-label*='下一页' i]",
    "#pnnext",
    "a[jsname='Mratb']",
]

# ============================================================
# 网站提取相关
# ============================================================
CANONICAL_SELECTOR = "link[rel='canonical']"

# ============================================================
# User-Agent（模拟真实 Chrome）
# ============================================================
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ============================================================
# 目录自动创建
# ============================================================
def ensure_dirs():
    """确保所有必要目录存在"""
    for d in [INPUT_DIR, OUTPUT_DIR, PROFILES_DIR, LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ============================================================
# 外部 settings.json 加载（覆盖默认常量）
# ============================================================
_SETTINGS_FILE = BASE_DIR / "settings.json"


def _load_settings():
    """加载 settings.json 并覆盖对应的模块级常量.

    该函数在模块导入时自动执行。settings.json 不存在或格式错误时静默跳过，
    使用 config.py 中的默认值。
    """
    if not _SETTINGS_FILE.exists():
        return

    try:
        with open(str(_SETTINGS_FILE), "r", encoding="utf-8") as f:
            s = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    g = globals()

    # --- SMTP 配置 ---
    smtp = s.get("smtp", {})
    if smtp:
        g["SMTP_CONFIG"]["host"] = smtp.get("host", SMTP_CONFIG["host"])
        g["SMTP_CONFIG"]["port"] = smtp.get("port", SMTP_CONFIG["port"])
        g["SMTP_CONFIG"]["username"] = smtp.get("username", SMTP_CONFIG["username"])
        g["SMTP_CONFIG"]["password"] = smtp.get("password", SMTP_CONFIG["password"])
        g["SMTP_CONFIG"]["use_tls"] = smtp.get("use_tls", SMTP_CONFIG["use_tls"])
        g["SMTP_CONFIG"]["from_name"] = smtp.get("from_name", SMTP_CONFIG["from_name"])
        g["SMTP_CONFIG"]["send_interval_secs"] = smtp.get(
            "send_interval_secs", SMTP_CONFIG["send_interval_secs"]
        )

    # --- Flask 配置 ---
    flask_cfg = s.get("flask", {})
    if flask_cfg:
        g["FLASK_HOST"] = flask_cfg.get("host", FLASK_HOST)
        g["FLASK_PORT"] = flask_cfg.get("port", FLASK_PORT)
        g["FLASK_DEBUG"] = flask_cfg.get("debug", FLASK_DEBUG)

    # --- 采集参数 ---
    scraper_cfg = s.get("scraper", {})
    if scraper_cfg:
        g["DEFAULT_CONCURRENCY"] = scraper_cfg.get(
            "default_concurrency", DEFAULT_CONCURRENCY
        )
        g["CONCURRENCY_MIN"] = scraper_cfg.get("min_concurrency", CONCURRENCY_MIN)
        g["CONCURRENCY_MAX"] = scraper_cfg.get("max_concurrency", CONCURRENCY_MAX)
        g["DEFAULT_MAX_PAGES"] = scraper_cfg.get(
            "default_max_pages", DEFAULT_MAX_PAGES
        )
        g["MAX_PAGES_MIN"] = scraper_cfg.get("max_pages_min", MAX_PAGES_MIN)
        g["MAX_PAGES_MAX"] = scraper_cfg.get("max_pages_max", MAX_PAGES_MAX)
        g["RETRY_TIMES"] = scraper_cfg.get("retry_times", RETRY_TIMES)
        g["RETRY_DELAY_SECS"] = scraper_cfg.get(
            "retry_delay_secs", RETRY_DELAY_SECS
        )
        g["CAPTCHA_TIMEOUT_SECS"] = scraper_cfg.get(
            "captcha_timeout_secs", CAPTCHA_TIMEOUT_SECS
        )
        g["PAGE_LOAD_TIMEOUT_MS"] = scraper_cfg.get(
            "page_load_timeout_ms", PAGE_LOAD_TIMEOUT_MS
        )
        g["SEARCH_TIMEOUT_MS"] = scraper_cfg.get(
            "search_timeout_ms", SEARCH_TIMEOUT_MS
        )

    # --- 上传限制 ---
    upload_cfg = s.get("upload", {})
    if upload_cfg:
        g["MAX_UPLOAD_SIZE_MB"] = upload_cfg.get("max_size_mb", MAX_UPLOAD_SIZE_MB)

    # --- 代理 ---
    proxy_cfg = s.get("proxy", {})
    if proxy_cfg:
        g["DEFAULT_PROXY"] = proxy_cfg.get("address", DEFAULT_PROXY)

    # --- 国家代码 ---
    country_cfg = s.get("country_code", {})
    if country_cfg:
        g["DEFAULT_COUNTRY_CODE"] = country_cfg.get("code", DEFAULT_COUNTRY_CODE)

    # --- User-Agent ---
    ua_cfg = s.get("user_agent", {})
    if ua_cfg:
        g["DEFAULT_USER_AGENT"] = ua_cfg.get("value", DEFAULT_USER_AGENT)


# 模块导入时自动执行
_load_settings()
