"""
LeadScraper 开发信 Campaign 模块
===============================
提供采集结果加载、邮件模板管理、模拟发送等后端逻辑。
与采集模块（scraper.py）独立，通过 app.py 路由调用。
"""

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config import BASE_DIR, OUTPUT_DIR, LOG_DIR, SMTP_CONFIG, DEFAULT_EMAIL_TEMPLATES
from logger_config import TraceLogger

_logger = TraceLogger("LeadScraper.Campaign", str(LOG_DIR))

# 模板存储文件（基于项目根目录，开发/打包模式均适用）
TEMPLATES_FILE = BASE_DIR / "email_templates.json"


# ============================================================
# 数据结构
# ============================================================

@dataclass
class LeadInfo:
    """单条线索的完整信息"""
    id: str                    # 唯一标识
    sheet_name: str            # 来源目标（Sheet名）
    company: str               # 公司名
    contact: str               # 联系人
    email: str                 # 邮箱
    phone: str                 # 电话
    whatsapp: str              # WhatsApp 链接
    website: str               # 网站
    source_url: str            # 来源链接
    collected_at: str          # 采集时间
    selected: bool = False     # 是否被勾选


@dataclass
class EmailTemplate:
    """邮件模板"""
    keyword: str               # 关联的关键词
    subject: str               # 邮件主题
    body: str                  # 邮件正文
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SendProgress:
    """模拟发送进度"""
    total: int = 0
    sent: int = 0
    failed: int = 0
    current_recipient: str = ""
    status: str = "idle"       # idle / sending / completed / error
    logs: list = field(default_factory=list)


# 全局发送进度（线程安全）
_send_lock = threading.Lock()
_send_progress = SendProgress()

# 导入数据缓存：导入后暂存于此，避免被磁盘旧数据覆盖
_cached_leads: list[LeadInfo] = []
_cache_time: float = 0.0        # 缓存创建时间戳
_cache_lock = threading.Lock()


# ============================================================
# 结果加载
# ============================================================

def load_latest_results(force_reload: bool = False) -> list[LeadInfo]:
    """
    加载最新的采集结果 Excel 文件，解析为 LeadInfo 列表。
    优先返回上次导入的缓存数据（避免被磁盘旧数据覆盖）。
    只返回有邮箱的线索。

    Args:
        force_reload: 为 True 时强制从磁盘重新加载

    Returns:
        [LeadInfo, ...]
    """
    global _cached_leads, _cache_time

    # 优先返回缓存（最近一次导入的数据）
    # 但如果磁盘上有更新的采集结果，自动失效缓存
    with _cache_lock:
        if _cached_leads and not force_reload:
            # 检查磁盘上是否有更新的采集结果
            disk_files = sorted(
                OUTPUT_DIR.glob("采集结果_*.xlsx"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            if disk_files and disk_files[0].stat().st_mtime > _cache_time:
                # 磁盘文件更新 → 失效缓存，走磁盘加载
                _cached_leads = []
            else:
                return list(_cached_leads)

    xlsx_files = sorted(
        OUTPUT_DIR.glob("采集结果_*.xlsx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not xlsx_files:
        # 无磁盘文件但有缓存 → 仍返回缓存
        with _cache_lock:
            if _cached_leads:
                return list(_cached_leads)
        return []

    filepath = xlsx_files[0]
    _logger.info(f"加载结果文件: {filepath.name}")

    try:
        xl = pd.ExcelFile(filepath)
        leads = []

        for sheet_name in xl.sheet_names:
            df = pd.read_excel(filepath, sheet_name=sheet_name)
            # 标准化列名
            col_map = _normalize_columns(df.columns)
            df.rename(columns=col_map, inplace=True)

            required_cols = ["邮箱", "公司名"]
            if not all(c in df.columns for c in required_cols):
                continue

            for _, row in df.iterrows():
                email = str(row.get("邮箱", "")).strip()
                if not email or email.lower() in ("nan", ""):
                    continue

                lead = LeadInfo(
                    id=_make_lead_id(sheet_name, row),
                    sheet_name=sheet_name,
                    company=str(row.get("公司名", "")).strip(),
                    contact=str(row.get("联系人", "")).strip(),
                    email=email,
                    phone=str(row.get("电话", "")).strip(),
                    whatsapp=str(row.get("WhatsApp链接", "")).strip(),
                    website=str(row.get("网站", "")).strip(),
                    source_url=str(row.get("来源链接", "")).strip(),
                    collected_at=str(row.get("采集时间", "")).strip(),
                )
                leads.append(lead)

        _logger.info(f"加载 {len(leads)} 条有邮箱的线索")
        return leads

    except Exception as e:
        _logger.error(f"加载结果失败: {e}", exc_info=True)
        return []


def import_leads_from_file(filepath: str) -> list[LeadInfo]:
    """
    从任意 Excel/CSV 文件导入线索数据。
    自动识别邮箱列、公司名列等关键字段。

    Args:
        filepath: Excel 或 CSV 文件路径

    Returns:
        [LeadInfo, ...] 只返回有邮箱的线索
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    all_leads = []

    if ext == ".csv":
        df = pd.read_csv(filepath)
        _auto_map_columns(df)
        leads = _parse_dataframe_leads(df, filepath.stem[:31])
        all_leads.extend(leads)
    else:
        # 多 Sheet Excel：逐个 Sheet 解析，用实际 Sheet 名作为来源
        xl = pd.ExcelFile(filepath)
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(filepath, sheet_name=sheet_name)
            if df.empty:
                continue
            _auto_map_columns(df)
            sheet_leads = _parse_dataframe_leads(df, sheet_name)
            all_leads.extend(sheet_leads)

    sheet_count = 1 if ext == ".csv" else len(xl.sheet_names)
    _logger.info(f"导入 {len(all_leads)} 条有邮箱的线索 (from {filepath.name}, {sheet_count} sheets)")

    # 写入缓存（含时间戳），后续 load_latest_results 会优先返回
    global _cached_leads, _cache_time
    with _cache_lock:
        _cached_leads = all_leads
        _cache_time = time.time()

    return all_leads


def _parse_dataframe_leads(df: pd.DataFrame, source_name: str) -> list[LeadInfo]:
    """
    从单个 DataFrame 解析线索列表。

    Args:
        df: 数据表
        source_name: 来源标识（Excel Sheet 名 或 CSV 文件名）

    Returns:
        [LeadInfo, ...]
    """
    # 标准化列名
    col_map = _normalize_columns(df.columns)
    df.rename(columns=col_map, inplace=True)

    # 如果没有"邮箱"列，尝试自动发现
    if "邮箱" not in df.columns:
        for col in df.columns:
            col_lower = str(col).lower()
            if any(kw in col_lower for kw in ["email", "e-mail", "mail", "邮箱", "邮件"]):
                col_map[col] = "邮箱"
                break
        df.rename(columns=col_map, inplace=True)

    safe_name = source_name[:31]
    leads = []

    for idx, row in df.iterrows():
        email = str(row.get("邮箱", "")).strip()
        if not email or email.lower() in ("nan", "", "none"):
            continue

        # 可能一行有多个邮箱（分号分隔）
        emails = [e.strip() for e in email.split(";") if "@" in e]
        if not emails:
            continue

        lead = LeadInfo(
            id=f"imp_{hashlib.md5(f'{safe_name}{idx}'.encode()).hexdigest()[:12]}",
            sheet_name=safe_name,
            company=str(row.get("公司名", row.get("公司", safe_name))).strip(),
            contact=str(row.get("联系人", row.get("姓名", ""))).strip(),
            email="; ".join(emails),
            phone=str(row.get("电话", "")).strip(),
            whatsapp=str(row.get("WhatsApp链接", "")).strip(),
            website=str(row.get("网站", "")).strip(),
            source_url=str(row.get("来源链接", "")).strip(),
            collected_at=str(row.get("采集时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))).strip(),
        )
        leads.append(lead)

    return leads


def _auto_map_columns(df: pd.DataFrame):
    """自动映射常见列名到标准字段"""
    patterns = {
        "公司名": ["company", "corp", "business", "客户", "客户名称", "厂家", "供应商"],
        "联系人": ["contact", "name", "姓名", "负责人", "联络人"],
        "电话": ["phone", "tel", "mobile", "手机", "座机", "电话", "联系电话"],
        "网站": ["website", "url", "site", "网址", "主页"],
        "WhatsApp链接": ["whatsapp", "wa.me"],
    }
    for std_col, keywords in patterns.items():
        if std_col in df.columns:
            continue
        for col in df.columns:
            col_lower = str(col).lower()
            if any(kw in col_lower for kw in keywords):
                df.rename(columns={col: std_col}, inplace=True)
                break


def _normalize_columns(columns) -> dict:
    """将 Excel 列名映射到标准字段名"""
    mapping = {}
    for col in columns:
        col_str = str(col).strip()
        for std in ["序号", "公司名", "联系人", "邮箱", "电话",
                     "WhatsApp链接", "网站", "来源链接", "采集时间"]:
            if std in col_str:
                mapping[col] = std
                break
    return mapping


def _make_lead_id(sheet_name: str, row) -> str:
    """生成线索唯一ID"""
    import hashlib
    raw = f"{sheet_name}|{row.get('邮箱', '')}|{row.get('网站', '')}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ============================================================
# 邮件模板管理
# ============================================================

def load_templates() -> dict:
    """
    加载所有邮件模板。
    Returns: {keyword: EmailTemplate}
    """
    if not TEMPLATES_FILE.exists():
        return {}

    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        templates = {}
        for kw, t in data.items():
            templates[kw] = EmailTemplate(
                keyword=kw,
                subject=t.get("subject", ""),
                body=t.get("body", ""),
                created_at=t.get("created_at", ""),
                updated_at=t.get("updated_at", ""),
            )
        return templates
    except Exception as e:
        _logger.warning(f"加载模板失败: {e}")
        return {}


def save_template(keyword: str, subject: str, body: str) -> EmailTemplate:
    """
    保存或更新一个关键词的邮件模板。
    """
    templates = load_templates()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if keyword in templates:
        t = templates[keyword]
        t.subject = subject
        t.body = body
        t.updated_at = now
    else:
        templates[keyword] = EmailTemplate(
            keyword=keyword,
            subject=subject,
            body=body,
            created_at=now,
            updated_at=now,
        )

    # 持久化
    data = {}
    for kw, t in templates.items():
        data[kw] = {
            "keyword": kw,
            "subject": t.subject,
            "body": t.body,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }

    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    _logger.info(f"模板已保存: {keyword}")
    return templates[keyword]


def get_template_for_keyword(keyword: str) -> EmailTemplate:
    """
    获取某关键词的邮件模板，如无则返回默认模板。
    """
    templates = load_templates()
    if keyword in templates:
        return templates[keyword]

    # 返回默认模板
    return EmailTemplate(
        keyword=keyword,
        subject=DEFAULT_EMAIL_TEMPLATES["subject"],
        body=DEFAULT_EMAIL_TEMPLATES["body"],
    )


# ============================================================
# 模板变量替换
# ============================================================

def render_email(template: EmailTemplate, lead: LeadInfo) -> dict:
    """
    将模板中的变量替换为实际值。
    支持的变量：{keyword} {company} {contact} {email} {phone} {website}
    """
    vars_map = {
        "keyword": template.keyword,
        "company": lead.company or lead.sheet_name,
        "contact": lead.contact or "Sir/Madam",
        "email": lead.email,
        "phone": lead.phone or "N/A",
        "website": lead.website or "N/A",
        "whatsapp": lead.whatsapp or "N/A",
    }

    subject = template.subject
    body = template.body
    for key, val in vars_map.items():
        placeholder = "{" + key + "}"
        subject = subject.replace(placeholder, str(val))
        body = body.replace(placeholder, str(val))

    return {"subject": subject, "body": body, "to": lead.email}


# ============================================================
# 模拟发送
# ============================================================

def get_send_progress() -> dict:
    """获取当前发送进度"""
    with _send_lock:
        return {
            "total": _send_progress.total,
            "sent": _send_progress.sent,
            "failed": _send_progress.failed,
            "current_recipient": _send_progress.current_recipient,
            "status": _send_progress.status,
            "logs": _send_progress.logs[-20:],  # 最近20条
        }


def start_mock_send(leads: list[LeadInfo], template_keyword: str) -> None:
    """
    启动模拟邮件发送（后台线程）。

    Args:
        leads: 选中的线索列表
        template_keyword: 使用的模板关键词
    """
    global _send_progress

    with _send_lock:
        if _send_progress.status == "sending":
            return  # 已在发送中
        _send_progress = SendProgress(
            total=len(leads),
            status="sending",
        )

    template = get_template_for_keyword(template_keyword)

    def _send_worker():
        global _send_progress
        success = 0
        failed = 0

        for i, lead in enumerate(leads):
            with _send_lock:
                if _send_progress.status != "sending":
                    break
                _send_progress.current_recipient = lead.email

            try:
                rendered = render_email(template, lead)

                # ---- 模拟发送：随机延迟 0.5~2 秒 ----
                import random
                delay = random.uniform(0.5, 2.0)
                time.sleep(delay)

                # 模拟 90% 成功率
                is_success = random.random() < 0.9

                log_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "email": lead.email,
                    "company": lead.company[:30],
                    "subject": rendered["subject"][:60],
                    "success": is_success,
                    "message": "发送成功 ✓" if is_success else "模拟失败: 邮箱不存在",
                }

                with _send_lock:
                    if is_success:
                        success += 1
                        _send_progress.sent = success
                    else:
                        failed += 1
                        _send_progress.failed = failed
                    _send_progress.logs.append(log_entry)
                    _send_progress.current_recipient = ""

            except Exception as e:
                with _send_lock:
                    failed += 1
                    _send_progress.failed = failed
                    _send_progress.logs.append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "email": lead.email,
                        "company": lead.company[:30],
                        "subject": "",
                        "success": False,
                        "message": f"异常: {str(e)[:80]}",
                    })
                    _send_progress.current_recipient = ""

        with _send_lock:
            _send_progress.status = "completed"
            _send_progress.current_recipient = ""

        _logger.info(f"模拟发送完成: {success} 成功 / {failed} 失败")

    thread = threading.Thread(target=_send_worker, daemon=True, name="email-sender")
    thread.start()
    _logger.info(f"模拟发送已启动: {len(leads)} 封邮件")


def stop_send() -> None:
    """停止发送"""
    with _send_lock:
        _send_progress.status = "completed"
        _send_progress.logs.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "email": "-",
            "company": "-",
            "subject": "-",
            "success": False,
            "message": "用户手动停止发送",
        })
