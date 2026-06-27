"""
LeadScraper Flask Blueprint
===========================
可被 EcomIQ-RPA-RPA 主应用挂载，也可独立运行。

挂载方式:
    from LeadScraper.blueprint import create_lead_scraper_blueprint
    app.register_blueprint(create_lead_scraper_blueprint(), url_prefix='/leads')
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, render_template, request, jsonify, send_file


def create_lead_scraper_blueprint() -> Blueprint:
    """创建 LeadScraper 蓝图"""
    import sys
    _lead_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _lead_dir)

    bp = Blueprint(
        "lead_scraper",
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Step 1: 加载 LeadScraper/config.py 到单独的模块命名空间
    import importlib.util
    _spec = importlib.util.spec_from_file_location("leadscraper_config", os.path.join(_lead_dir, "config.py"))
    _lc = importlib.util.module_from_spec(_spec)
    _sys_modules_backup = sys.modules.get('config')
    sys.modules['config'] = _lc  # 临时注入，让 scraper/campaign 的 from config import ... 正确解析
    _spec.loader.exec_module(_lc)

    INPUT_DIR = _lc.INPUT_DIR
    OUTPUT_DIR = _lc.OUTPUT_DIR
    LOG_DIR = _lc.LOG_DIR
    TEMPLATES_DIR = _lc.TEMPLATES_DIR
    STATIC_DIR = _lc.STATIC_DIR
    FLASK_HOST = _lc.FLASK_HOST
    FLASK_PORT = _lc.FLASK_PORT
    FLASK_DEBUG = _lc.FLASK_DEBUG
    MAX_UPLOAD_SIZE_MB = _lc.MAX_UPLOAD_SIZE_MB
    DEFAULT_MAX_PAGES = _lc.DEFAULT_MAX_PAGES
    DEFAULT_CONCURRENCY = _lc.DEFAULT_CONCURRENCY
    CONCURRENCY_MIN = _lc.CONCURRENCY_MIN
    CONCURRENCY_MAX = _lc.CONCURRENCY_MAX
    MAX_PAGES_MIN = _lc.MAX_PAGES_MIN
    MAX_PAGES_MAX = _lc.MAX_PAGES_MAX
    ensure_dirs = _lc.ensure_dirs
    DEFAULT_EMAIL_TEMPLATES = _lc.DEFAULT_EMAIL_TEMPLATES

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
        import_leads_from_file,
    )

    # Step 3: 恢复 RPADataHub 的 config（如果存在）
    if _sys_modules_backup is not None:
        sys.modules['config'] = _sys_modules_backup
    else:
        sys.modules.pop('config', None)

    ensure_dirs()

    # 全局状态和线程
    state = ScraperState()
    scraper_thread: threading.Thread | None = None
    logger = TraceLogger("LeadScraper", str(LOG_DIR))

    # ============================================================
    # 页面路由
    # ============================================================

    @bp.route("/")
    def index():
        """主页面 — 关键词管理 + 采集执行"""
        return render_template("index.html")

    @bp.route("/export")
    def result_export():
        """结果导出页面"""
        return render_template("campaign.html")

    # ============================================================
    # API — 上传 Excel
    # ============================================================

    @bp.route("/api/upload", methods=["POST"])
    def api_upload():
        if state.is_running():
            return jsonify({"success": False, "error": "采集正在运行中，请先停止后再上传"}), 409

        if "file" not in request.files:
            return jsonify({"success": False, "error": "未选择文件"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "文件名为空"}), 400

        ext = Path(file.filename).suffix.lower()
        if ext not in (".xlsx", ".xls"):
            return jsonify({"success": False, "error": f"不支持的文件格式 {ext}，请上传 .xlsx 或 .xls 文件"}), 400

        try:
            filename = f"{uuid.uuid4().hex}_{file.filename}"
            filepath = INPUT_DIR / filename
            file.save(str(filepath))

            targets_raw = load_targets(str(filepath))
            if not targets_raw:
                return jsonify({"success": False, "error": "未从文件中解析到任何关键词"}), 400

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

    @bp.route("/api/start", methods=["POST"])
    def api_start():
        global scraper_thread

        if state.is_running():
            return jsonify({"success": False, "error": "采集已在运行中"}), 409

        try:
            data = request.get_json(silent=True) or {}

            selected_indices = data.get("selected_indices", [])
            if not selected_indices:
                selected_indices = list(range(len(state.targets)))

            max_pages = int(data.get("max_pages", DEFAULT_MAX_PAGES))
            max_pages = max(MAX_PAGES_MIN, min(MAX_PAGES_MAX, max_pages))

            concurrency = int(data.get("concurrency", DEFAULT_CONCURRENCY))
            concurrency = max(CONCURRENCY_MIN, min(CONCURRENCY_MAX, concurrency))

            headless = bool(data.get("headless", True))
            country_code = str(data.get("country_code", "")).strip()
            phone_filter = bool(data.get("phone_filter", False))
            proxy = str(data.get("proxy", "")).strip()

            output_dir = str(data.get("output_dir", "")).strip()
            output_path = Path(output_dir) if output_dir else OUTPUT_DIR

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

            config = ScraperConfig(
                max_pages=max_pages,
                concurrency=concurrency,
                output_dir=output_path,
                headless=headless,
                country_code=country_code,
                phone_filter_enabled=phone_filter and bool(country_code),
                proxy=proxy,
            )

            state.set_running(False)
            state.stop_flag = False
            state.set_error("")
            state.leads_found = 0
            state.captcha_detected = False
            state.captcha_skip_target = False
            state.captcha_resolved.clear()

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

    @bp.route("/api/status", methods=["GET"])
    def api_status():
        status_dict = state.to_dict()
        if state.start_time > 0 and state.is_running():
            status_dict["elapsed_seconds"] = round(time.time() - state.start_time, 1)
        else:
            status_dict["elapsed_seconds"] = 0
        return jsonify(status_dict)

    # ============================================================
    # API — 停止采集
    # ============================================================

    @bp.route("/api/stop", methods=["POST"])
    def api_stop():
        state.stop_flag = True
        logger.info("收到停止信号")
        return jsonify({"success": True})

    # ============================================================
    # API — CAPTCHA 恢复 / 跳过
    # ============================================================

    @bp.route("/api/resume", methods=["POST"])
    def api_resume():
        state.captcha_skip_target = False
        state.captcha_resolved.set()
        logger.info("用户请求继续采集（CAPTCHA 已解决）")
        return jsonify({"success": True})

    @bp.route("/api/skip", methods=["POST"])
    def api_skip():
        state.captcha_skip_target = True
        state.captcha_resolved.set()
        logger.info("用户选择跳过当前目标")
        return jsonify({"success": True})

    # ============================================================
    # API — 下载结果
    # ============================================================

    @bp.route("/api/download", methods=["GET"])
    def api_download():
        filepath = state.output_filepath

        if not filepath or not Path(filepath).exists():
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

    @bp.route("/api/health", methods=["GET"])
    def api_health():
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "running": state.is_running(),
        })

    # ============================================================
    # Campaign 开发信 API
    # ============================================================

    @bp.route("/api/campaign/import", methods=["POST"])
    def api_campaign_import():
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
                        "id": l.id, "sheet_name": l.sheet_name, "company": l.company,
                        "contact": l.contact, "email": l.email, "phone": l.phone,
                        "whatsapp": l.whatsapp, "website": l.website, "source_url": l.source_url,
                        "collected_at": l.collected_at,
                    }
                    for l in leads
                ],
            })
        except Exception as e:
            logger.error(f"导入失败: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/campaign/leads", methods=["GET"])
    def api_campaign_leads():
        try:
            force = request.args.get("force", "0") == "1"
            leads = load_latest_results(force_reload=force)
            return jsonify({
                "success": True,
                "total": len(leads),
                "leads": [
                    {
                        "id": l.id, "sheet_name": l.sheet_name, "company": l.company,
                        "contact": l.contact, "email": l.email, "phone": l.phone,
                        "whatsapp": l.whatsapp, "website": l.website, "source_url": l.source_url,
                        "collected_at": l.collected_at,
                    }
                    for l in leads
                ],
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/campaign/keywords", methods=["GET"])
    def api_campaign_keywords():
        leads = load_latest_results()
        keywords = list(set(l.sheet_name for l in leads))
        return jsonify({"success": True, "keywords": keywords})

    @bp.route("/api/campaign/templates", methods=["GET"])
    def api_campaign_templates():
        templates = load_templates()
        return jsonify({
            "success": True,
            "templates": {
                kw: {
                    "keyword": t.keyword, "subject": t.subject, "body": t.body,
                    "created_at": t.created_at, "updated_at": t.updated_at,
                }
                for kw, t in templates.items()
            },
        })

    @bp.route("/api/campaign/template", methods=["GET"])
    def api_campaign_get_template():
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
                "keyword": template.keyword, "subject": template.subject,
                "body": template.body,
                "created_at": getattr(template, "created_at", ""),
                "updated_at": getattr(template, "updated_at", ""),
            },
        })

    @bp.route("/api/campaign/template", methods=["POST"])
    def api_campaign_save_template():
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
                    "keyword": template.keyword, "subject": template.subject,
                    "body": template.body, "updated_at": template.updated_at,
                },
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/campaign/send", methods=["POST"])
    def api_campaign_send():
        data = request.get_json(silent=True) or {}
        lead_ids = data.get("lead_ids", [])
        keyword = data.get("keyword", "").strip()
        if not lead_ids:
            return jsonify({"success": False, "error": "未选择任何线索"}), 400
        if not keyword:
            return jsonify({"success": False, "error": "缺少模板关键词"}), 400
        all_leads = load_latest_results()
        selected = [l for l in all_leads if l.id in lead_ids]
        if not selected:
            return jsonify({"success": False, "error": "未匹配到选中线索"}), 400
        start_mock_send(selected, keyword)
        return jsonify({"success": True, "total": len(selected)})

    @bp.route("/api/campaign/send/progress", methods=["GET"])
    def api_campaign_send_progress():
        return jsonify({"success": True, "progress": get_send_progress()})

    @bp.route("/api/campaign/send/stop", methods=["POST"])
    def api_campaign_send_stop():
        stop_send()
        return jsonify({"success": True})

    return bp