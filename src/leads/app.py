"""
LeadScraper Flask Web 服务
=========================
提供文件上传、采集控制、状态查询、结果下载等 HTTP API。
采集任务在后台线程中运行，状态通过 ScraperState 共享。
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
)

from config import (
    INPUT_DIR, OUTPUT_DIR, LOG_DIR, TEMPLATES_DIR, STATIC_DIR,
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG, MAX_UPLOAD_SIZE_MB,
    DEFAULT_MAX_PAGES, DEFAULT_CONCURRENCY,
    CONCURRENCY_MIN, CONCURRENCY_MAX,
    MAX_PAGES_MIN, MAX_PAGES_MAX,
    ensure_dirs,
)
from logger_config import TraceLogger
from scraper import (
    ScraperState,
    ScraperConfig,
    TargetInfo,
    load_targets,
    run_scraper,
)
from campaign import (
    load_latest_results,
    load_templates,
    save_template,
    get_template_for_keyword,
    start_mock_send,
    get_send_progress,
    stop_send,
    EmailTemplate,
    LeadInfo,
)
from config import DEFAULT_EMAIL_TEMPLATES

# ============================================================
# 应用初始化
# ============================================================

# 确保必要目录存在
ensure_dirs()

# 创建 Flask 实例
app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_MB * 1024 * 1024
app.config["JSON_AS_ASCII"] = False  # 支持中文 JSON

# 全局状态和线程
state = ScraperState()
scraper_thread: threading.Thread | None = None
logger = TraceLogger("LeadScraper", str(LOG_DIR))


# ============================================================
# 页面路由
# ============================================================

@app.route("/")
def index():
    """主页面"""
    return render_template("index.html")


# ============================================================
# API — 上传 Excel
# ============================================================

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    上传关键词 Excel 文件。

    Request: multipart/form-data，字段名 "file"
    Response:
        {
            "success": true,
            "filename": "xxx.xlsx",
            "targets": [{"name": "...", "keyword": "..."}, ...]
        }
    """
    if state.is_running():
        return jsonify({"success": False, "error": "采集正在运行中，请先停止后再上传"}), 409

    if "file" not in request.files:
        return jsonify({"success": False, "error": "未选择文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "文件名为空"}), 400

    # 检查文件扩展名
    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        return jsonify({"success": False, "error": f"不支持的文件格式 {ext}，请上传 .xlsx 或 .xls 文件"}), 400

    try:
        # 保存到 input 目录
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        filepath = INPUT_DIR / filename
        file.save(str(filepath))

        # 解析关键词
        targets_raw = load_targets(str(filepath))

        if not targets_raw:
            return jsonify({"success": False, "error": "未从文件中解析到任何关键词"}), 400

        # 构建 TargetInfo 列表并更新共享状态
        target_infos = [
            TargetInfo(name=t["name"], keyword=t["keyword"], selected=True)
            for t in targets_raw
        ]

        with state.lock:
            state.targets = target_infos
            state.leads_found = 0
            state.set_error("")

        logger.info(f"文件上传成功: {file.filename}, 解析出 {len(targets_raw)} 个目标")

        return jsonify({
            "success": True,
            "filename": file.filename,
            "targets": [
                {"name": t.name, "keyword": t.keyword}
                for t in target_infos
            ],
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"上传处理异常: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"文件处理失败: {str(e)}"}), 500


# ============================================================
# API — 开始采集
# ============================================================

@app.route("/api/start", methods=["POST"])
def api_start():
    """
    启动采集任务（后台线程）。

    Request JSON:
        {
            "selected_indices": [0, 2, 5],
            "max_pages": 3,
            "concurrency": 5,
            "headless": true,
            "country_code": "+44",
            "phone_filter": true,
            "proxy": ""
        }

    Response:
        {"success": true}
    """
    global scraper_thread

    if state.is_running():
        return jsonify({"success": False, "error": "采集已在运行中"}), 409

    try:
        data = request.get_json(silent=True) or {}

        selected_indices = data.get("selected_indices", [])
        if not selected_indices:
            # 默认全部选中
            selected_indices = list(range(len(state.targets)))

        # 验证并解析参数
        max_pages = int(data.get("max_pages", DEFAULT_MAX_PAGES))
        max_pages = max(MAX_PAGES_MIN, min(MAX_PAGES_MAX, max_pages))

        concurrency = int(data.get("concurrency", DEFAULT_CONCURRENCY))
        concurrency = max(CONCURRENCY_MIN, min(CONCURRENCY_MAX, concurrency))

        headless = bool(data.get("headless", True))
        country_code = str(data.get("country_code", "")).strip()
        phone_filter = bool(data.get("phone_filter", False))
        proxy = str(data.get("proxy", "")).strip()

        output_dir = str(data.get("output_dir", "")).strip()
        if output_dir:
            output_path = Path(output_dir)
        else:
            output_path = OUTPUT_DIR

        # 构建目标列表（标记选中状态）
        targets = []
        with state.lock:
            for i, t in enumerate(state.targets):
                t.selected = (i in selected_indices)
                t.status = "pending"
                t.leads_count = 0
                t.error = ""
                targets.append(t)

        selected_targets = [t for t in targets if t.selected]
        if not selected_targets:
            return jsonify({"success": False, "error": "没有选中的目标"}), 400

        # 构建配置
        config = ScraperConfig(
            max_pages=max_pages,
            concurrency=concurrency,
            output_dir=output_path,
            headless=headless,
            country_code=country_code,
            phone_filter_enabled=phone_filter and bool(country_code),
            proxy=proxy,
        )

        # 重置状态
        state.set_running(False)
        state.stop_flag = False
        state.set_error("")
        state.leads_found = 0
        state.captcha_detected = False
        state.captcha_skip_target = False
        state.captcha_resolved.clear()

        # 启动后台线程（传全量 targets，保证 index 与 state.targets 一致；
        # run_scraper 内部通过 target.selected 跳过未选中项）
        scraper_thread = threading.Thread(
            target=run_scraper,
            args=(state, targets, config),
            daemon=True,
            name="scraper-thread",
        )
        scraper_thread.start()

        logger.info(
            f"采集任务已启动：{len(selected_targets)} 个目标, "
            f"max_pages={max_pages}, concurrency={concurrency}, headless={headless}"
        )

        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"启动采集失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# API — 查询状态
# ============================================================

@app.route("/api/status", methods=["GET"])
def api_status():
    """
    返回当前采集状态。

    Response:
        {
            "running": true,
            "current_target": "Acme-UK",
            "current_page": 2,
            "total_pages": 3,
            "leads_found": 45,
            "captcha_detected": false,
            "captcha_page_url": "",
            "captcha_target_name": "",
            "error": "",
            "output_filepath": "",
            "elapsed_seconds": 120.5,
            "targets": [...]
        }
    """
    status_dict = state.to_dict()
    # 计算耗时
    if state.start_time > 0 and state.is_running():
        status_dict["elapsed_seconds"] = round(time.time() - state.start_time, 1)
    else:
        status_dict["elapsed_seconds"] = 0
    return jsonify(status_dict)


# ============================================================
# API — 停止采集
# ============================================================

@app.route("/api/stop", methods=["POST"])
def api_stop():
    """
    设置停止标志，后台线程将在当前页处理完毕后退出。
    已采集的数据会保留。
    """
    state.stop_flag = True
    logger.info("收到停止信号")
    return jsonify({"success": True})


# ============================================================
# API — CAPTCHA 恢复
# ============================================================

@app.route("/api/resume", methods=["POST"])
def api_resume():
    """
    用户完成 CAPTCHA 手动解决后点击"继续采集"。
    解除 scraper 线程的阻塞等待。
    """
    state.captcha_skip_target = False
    state.captcha_resolved.set()
    logger.info("用户请求继续采集（CAPTCHA 已解决）")
    return jsonify({"success": True})


# ============================================================
# API — CAPTCHA 跳过
# ============================================================

@app.route("/api/skip", methods=["POST"])
def api_skip():
    """
    用户点击"跳过当前目标"。
    解除 scraper 线程阻塞并标记跳过当前目标。
    """
    state.captcha_skip_target = True
    state.captcha_resolved.set()
    logger.info("用户选择跳过当前目标")
    return jsonify({"success": True})


# ============================================================
# API — 下载结果
# ============================================================

@app.route("/api/download", methods=["GET"])
def api_download():
    """
    下载最新采集结果 Excel 文件。

    优先返回 state 中记录的路径，否则查找 output/ 下最新 .xlsx。
    """
    filepath = state.output_filepath

    if not filepath or not Path(filepath).exists():
        # 查找 output 目录中最新的 xlsx 文件
        xlsx_files = sorted(
            OUTPUT_DIR.glob("*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if xlsx_files:
            filepath = str(xlsx_files[0])
        else:
            return jsonify({"success": False, "error": "没有可下载的结果文件"}), 404

    logger.info(f"下载结果: {filepath}")
    return send_file(
        filepath,
        as_attachment=True,
        download_name=Path(filepath).name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ============================================================
# API — 健康检查
# ============================================================

@app.route("/api/health", methods=["GET"])
def api_health():
    """服务健康检查"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "running": state.is_running(),
    })


# ============================================================
# Campaign 开发信页面与 API
# ============================================================

@app.route("/campaign")
def campaign_page():
    """开发信下钻页面"""
    return render_template("campaign.html")


@app.route("/api/campaign/import", methods=["POST"])
def api_campaign_import():
    """
    直接导入 Excel/CSV 数据进入开发信模块。
    支持：采集结果 Excel、手动准备的客户名单等。
    自动识别邮箱列和公司名列。
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未选择文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "文件名为空"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        return jsonify({"success": False, "error": f"不支持的文件格式 {ext}"}), 400

    try:
        from campaign import import_leads_from_file
        filename = f"campaign_import_{uuid.uuid4().hex[:8]}_{file.filename}"
        filepath = INPUT_DIR / filename
        file.save(str(filepath))

        leads = import_leads_from_file(str(filepath))
        return jsonify({
            "success": True,
            "total": len(leads),
            "filename": file.filename,
            "leads": [
                {
                    "id": l.id,
                    "sheet_name": l.sheet_name,
                    "company": l.company,
                    "contact": l.contact,
                    "email": l.email,
                    "phone": l.phone,
                    "whatsapp": l.whatsapp,
                    "website": l.website,
                    "source_url": l.source_url,
                    "collected_at": l.collected_at,
                }
                for l in leads
            ],
        })
    except Exception as e:
        logger.error(f"导入失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/campaign/leads", methods=["GET"])
def api_campaign_leads():
    """
    获取最新采集结果中有邮箱的线索列表。
    ?force=1  强制从磁盘重新加载（忽略导入缓存）
    """
    try:
        force = request.args.get("force", "0") == "1"
        leads = load_latest_results(force_reload=force)
        return jsonify({
            "success": True,
            "total": len(leads),
            "leads": [
                {
                    "id": l.id,
                    "sheet_name": l.sheet_name,
                    "company": l.company,
                    "contact": l.contact,
                    "email": l.email,
                    "phone": l.phone,
                    "whatsapp": l.whatsapp,
                    "website": l.website,
                    "source_url": l.source_url,
                    "collected_at": l.collected_at,
                }
                for l in leads
            ],
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/campaign/keywords", methods=["GET"])
def api_campaign_keywords():
    """获取所有可用的关键词列表（用于模板匹配）"""
    leads = load_latest_results()
    keywords = list(set(l.sheet_name for l in leads))
    return jsonify({"success": True, "keywords": keywords})


@app.route("/api/campaign/templates", methods=["GET"])
def api_campaign_templates():
    """获取所有邮件模板"""
    templates = load_templates()
    return jsonify({
        "success": True,
        "templates": {
            kw: {
                "keyword": t.keyword,
                "subject": t.subject,
                "body": t.body,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for kw, t in templates.items()
        },
    })


@app.route("/api/campaign/template", methods=["GET"])
def api_campaign_get_template():
    """
    获取指定关键词的邮件模板。
    ?keyword=xxx       返回已保存模板（如无则返回默认）
    ?keyword=xxx&default=1  强制返回系统默认模板（忽略已保存）
    """
    keyword = request.args.get("keyword", "")
    if not keyword:
        return jsonify({"success": False, "error": "缺少 keyword 参数"}), 400

    use_default = request.args.get("default", "0") == "1"

    if use_default:
        template = EmailTemplate(
            keyword=keyword,
            subject=DEFAULT_EMAIL_TEMPLATES["subject"],
            body=DEFAULT_EMAIL_TEMPLATES["body"],
        )
    else:
        template = get_template_for_keyword(keyword)

    return jsonify({
        "success": True,
        "template": {
            "keyword": template.keyword,
            "subject": template.subject,
            "body": template.body,
            "created_at": getattr(template, "created_at", ""),
            "updated_at": getattr(template, "updated_at", ""),
        },
    })


@app.route("/api/campaign/template", methods=["POST"])
def api_campaign_save_template():
    """保存邮件模板"""
    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "").strip()
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()

    if not keyword:
        return jsonify({"success": False, "error": "缺少关键词"}), 400
    if not subject:
        return jsonify({"success": False, "error": "缺少邮件主题"}), 400
    if not body:
        return jsonify({"success": False, "error": "缺少邮件正文"}), 400

    try:
        template = save_template(keyword, subject, body)
        return jsonify({
            "success": True,
            "template": {
                "keyword": template.keyword,
                "subject": template.subject,
                "body": template.body,
                "updated_at": template.updated_at,
            },
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/campaign/send", methods=["POST"])
def api_campaign_send():
    """启动模拟邮件发送"""
    data = request.get_json(silent=True) or {}
    lead_ids = data.get("lead_ids", [])
    keyword = data.get("keyword", "").strip()

    if not lead_ids:
        return jsonify({"success": False, "error": "未选择任何线索"}), 400
    if not keyword:
        return jsonify({"success": False, "error": "缺少模板关键词"}), 400

    # 加载最新结果并匹配
    all_leads = load_latest_results()
    selected = [l for l in all_leads if l.id in lead_ids]

    if not selected:
        return jsonify({"success": False, "error": "未匹配到选中线索"}), 400

    start_mock_send(selected, keyword)
    return jsonify({"success": True, "total": len(selected)})


@app.route("/api/campaign/send/progress", methods=["GET"])
def api_campaign_send_progress():
    """获取发送进度"""
    return jsonify({"success": True, "progress": get_send_progress()})


@app.route("/api/campaign/send/stop", methods=["POST"])
def api_campaign_send_stop():
    """停止发送"""
    stop_send()
    return jsonify({"success": True})


# ============================================================
# 启动入口
# ============================================================

def main():
    """应用启动入口"""
    # 确保 src/ 在 sys.path 中，以便导入 shared.runner
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared.runner import run_flask_app, should_print_startup

    if should_print_startup(FLASK_DEBUG):
        logger.info("=" * 50)
        logger.info("LeadScraper 启动中...")
        logger.info(f"访问地址: http://{FLASK_HOST}:{FLASK_PORT}")
        logger.info(f"输入目录: {INPUT_DIR}")
        logger.info(f"输出目录: {OUTPUT_DIR}")
        logger.info(f"日志目录: {LOG_DIR}")
        logger.info("=" * 50)

    # 自动打开浏览器
    if should_print_startup(FLASK_DEBUG):
        try:
            import webbrowser
            import threading as _threading

            def _open_browser():
                time.sleep(1.5)
                webbrowser.open(f"http://{FLASK_HOST}:{FLASK_PORT}")

            _threading.Thread(target=_open_browser, daemon=True).start()
        except Exception:
            pass

    run_flask_app(app, host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, threaded=True)


if __name__ == "__main__":
    main()
