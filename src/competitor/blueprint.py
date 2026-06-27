"""
CompetitorWatch Flask Blueprint
===============================
可被 EcomIQ-RPA-RPA 主应用挂载，也可独立运行。

挂载方式:
    from CompetitorWatch.blueprint import create_competitor_watch_blueprint
    app.register_blueprint(create_competitor_watch_blueprint(), url_prefix='/competitor')
"""

import json
import os
import sys
import uuid
import threading
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify


def create_competitor_watch_blueprint() -> Blueprint:
    """创建 CompetitorWatch 蓝图，使用延迟导入避免循环依赖"""
    _comp_dir = os.path.dirname(os.path.abspath(__file__))
    if _comp_dir not in sys.path:
        sys.path.insert(0, _comp_dir)

    bp = Blueprint(
        "competitor_watch",
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ============================================================
    # 页面路由
    # ============================================================

    @bp.route("/manage")
    def page_manage():
        return render_template("competitor/manage.html")

    @bp.route("/dashboard")
    def page_dashboard():
        return render_template("competitor/dashboard.html")

    @bp.route("/reports")
    def page_reports():
        return render_template("competitor/reports.html")

    # ============================================================
    # 辅助：统一 JSON 信封
    # ============================================================

    def ok(data=None, status_code=200):
        return jsonify({"success": True, "data": data, "error": ""}), status_code

    def fail(error="", status_code=400):
        return jsonify({"success": False, "data": None, "error": error}), status_code

    # ============================================================
    # 竞品配置 CRUD API
    # ============================================================

    @bp.route("/api/competitor/list")
    def api_competitor_list():
        try:
            region = request.args.get("region")
            platform = request.args.get("platform")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            items = db.get_competitor_list(region=region or None)
            if platform:
                items = [it for it in items if it.get("platform") == platform]
            return ok(items)
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/get")
    def api_competitor_get():
        try:
            competitor_id = request.args.get("id")
            if not competitor_id:
                return fail("缺少参数: id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            item = db.get_competitor_by_id(int(competitor_id))
            if not item:
                return fail("竞品不存在", 404)
            for key in ("created_at", "updated_at"):
                if item.get(key):
                    item[key] = item[key].strftime("%Y-%m-%d %H:%M:%S")
            return ok(item)
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/create", methods=["POST"])
    def api_competitor_create():
        try:
            body = request.get_json(force=True)
            if not body:
                return fail("请求体为空")
            if not body.get("competitor_name"):
                return fail("竞品名称为必填项")
            if not body.get("keywords"):
                return fail("关键词为必填项")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            new_id = db.insert_competitor(body)
            return ok({"id": new_id, "message": "创建成功"}, 201)
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/update", methods=["POST"])
    def api_competitor_update():
        try:
            competitor_id = request.args.get("id")
            if not competitor_id:
                return fail("缺少参数: id")
            body = request.get_json(force=True)
            if not body:
                return fail("请求体为空")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            db.update_competitor(int(competitor_id), body)
            return ok({"message": "更新成功"})
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/toggle", methods=["POST"])
    def api_competitor_toggle():
        try:
            competitor_id = request.args.get("id")
            if not competitor_id:
                return fail("缺少参数: id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            new_status = db.toggle_competitor(int(competitor_id))
            return ok({"new_status": new_status})
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/delete", methods=["POST"])
    def api_competitor_delete():
        try:
            competitor_id = request.args.get("id")
            if not competitor_id:
                return fail("缺少参数: id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            deleted = db.delete_competitor(int(competitor_id))
            if deleted:
                return ok({"message": "删除成功"})
            else:
                return fail("竞品不存在", 404)
        except Exception as e:
            return fail(str(e), 500)

    # ============================================================
    # 采集任务下发
    # ============================================================

    @bp.route("/api/competitor/crawl", methods=["POST"])
    def api_trigger_crawl():
        try:
            competitor_id = request.args.get("id")
            if not competitor_id:
                return fail("缺少参数: id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            competitor = db.get_competitor_by_id(int(competitor_id))
            if not competitor:
                return fail("竞品不存在", 404)
            task_uuid = uuid.uuid4().hex[:16]
            task_data = {
                "task_uuid": task_uuid,
                "competitor_id": competitor["id"],
                "competitor_name": competitor["competitor_name"],
                "keywords": competitor["keywords"],
                "asin_list": competitor.get("asin_list", "[]"),
                "platform": competitor.get("platform", "amazon"),
                "region": competitor.get("region", "domestic"),
                "marketplace": competitor.get("marketplace", "amazon.com"),
                "monitor_price": bool(competitor.get("monitor_price", True)),
                "monitor_ad": bool(competitor.get("monitor_ad", True)),
                "monitor_ranking": bool(competitor.get("monitor_ranking", True)),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "headless": request.args.get("headless", "true").lower() != "false",
                "max_results": int(request.args.get("max_results", "50")),
                "task_type": request.args.get("task_type", "crawl"),
            }
            from mq.redis_queue import CompetitorRedisQueue
            from config.settings import get_config
            cfg = get_config()
            q = CompetitorRedisQueue(redis_url=cfg.redis.url)
            published = q.publish_task(competitor["region"], task_data)
            return ok({
                "task_uuid": task_uuid,
                "message": "任务已下发",
                "via": "redis" if published else "db_fallback",
            })
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/login_confirm", methods=["POST"])
    def api_login_confirm():
        try:
            task_uuid = request.args.get("task_uuid")
            if not task_uuid:
                return fail("missing task_uuid")
            from mq.redis_queue import CompetitorRedisQueue
            from config.settings import get_config
            q = CompetitorRedisQueue(redis_url=get_config().redis.url)
            q.set_crawl_status(task_uuid, "login_confirmed", "用户已确认登录完成")
            return ok({"task_uuid": task_uuid, "confirmed": True})
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/crawl_status")
    def api_crawl_status():
        try:
            task_uuid = request.args.get("task_uuid")
            if not task_uuid:
                return fail("missing task_uuid")
            from mq.redis_queue import CompetitorRedisQueue
            from config.settings import get_config
            q = CompetitorRedisQueue(redis_url=get_config().redis.url)
            status = q.get_crawl_status(task_uuid)
            if status:
                return ok(status)
            return ok({"task_uuid": task_uuid, "status": "unknown", "detail": "no status record"})
        except Exception as e:
            return fail(str(e), 500)

    # ============================================================
    # 看板数据 API
    # ============================================================

    @bp.route("/api/competitor/trend")
    def api_price_trend():
        try:
            competitor_id = request.args.get("id")
            days = int(request.args.get("days", 30))
            if not competitor_id:
                return fail("缺少参数: id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            trend = db.get_price_trend(int(competitor_id), days)
            result = []
            for row in trend:
                r = dict(row)
                for k, v in r.items():
                    if hasattr(v, 'isoformat'):
                        r[k] = v.isoformat()
                    elif hasattr(v, 'as_tuple'):
                        r[k] = float(v)
                    elif isinstance(v, float):
                        r[k] = round(v, 4) if v is not None else None
                result.append(r)
            return ok(result)
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/snapshots")
    def api_snapshots():
        try:
            competitor_id = request.args.get("id")
            limit = int(request.args.get("limit", 30))
            if not competitor_id:
                return fail("缺少参数: id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            snapshots = db.get_recent_snapshots(int(competitor_id), limit)
            result = []
            for row in snapshots:
                r = dict(row)
                for k, v in r.items():
                    if hasattr(v, 'isoformat'):
                        r[k] = v.isoformat()
                    elif hasattr(v, 'as_tuple'):
                        r[k] = float(v)
                result.append(r)
            return ok(result)
        except Exception as e:
            return fail(str(e), 500)

    # ============================================================
    # AI 报告 API
    # ============================================================

    @bp.route("/api/competitor/reports")
    def api_reports():
        try:
            competitor_id = request.args.get("competitor_id")
            report_type = request.args.get("type")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            reports = db.get_reports(
                competitor_id=int(competitor_id) if competitor_id else None,
                report_type=report_type or None,
            )
            result = []
            for row in reports:
                r = dict(row)
                for k, v in r.items():
                    if hasattr(v, 'isoformat'):
                        r[k] = v.isoformat()
                result.append(r)
            return ok(result)
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/report_detail")
    def api_report_detail():
        try:
            report_id = request.args.get("id")
            if not report_id:
                return fail("缺少参数: id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            report = db.get_report_content(int(report_id))
            if not report:
                return fail("报告不存在", 404)
            result = dict(report)
            for k, v in result.items():
                if hasattr(v, 'isoformat'):
                    result[k] = v.isoformat()
            return ok(result)
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/competitor/generate_report", methods=["POST"])
    def api_generate_report():
        try:
            body = request.get_json(force=True)
            if not body:
                return fail("请求体为空")
            competitor_id = body.get("competitor_id")
            report_type = body.get("report_type", "daily")
            report_date = body.get("report_date", datetime.now().strftime("%Y-%m-%d"))
            if not competitor_id:
                return fail("缺少参数: competitor_id")
            from core.db_operations import DatabaseManager
            db = DatabaseManager()
            competitor = db.get_competitor_by_id(int(competitor_id))
            if not competitor:
                return fail("竞品不存在", 404)
            trend_data = db.get_price_trend(int(competitor_id), days=14)
            snapshots = db.get_recent_snapshots(int(competitor_id), limit=20)
            from services.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer()
            competitor_name = competitor["competitor_name"]
            platform = competitor.get("platform", "amazon")
            if report_type == "weekly":
                ai_result = analyzer.generate_weekly_report(competitor_name, platform, trend_data)
            else:
                ai_result = analyzer.generate_daily_report(competitor_name, platform, trend_data, snapshots)
            report_id = db.save_report(
                competitor_id=int(competitor_id),
                report_type=report_type,
                report_date=report_date,
                content=ai_result["content"],
                summary=ai_result["summary"],
                alert_level=ai_result.get("alert_level", "info"),
            )
            return ok({
                "report_id": report_id,
                "summary": ai_result["summary"],
                "alert_level": ai_result.get("alert_level", "info"),
            })
        except Exception as e:
            return fail(str(e), 500)

    @bp.route("/api/health")
    def api_health():
        from mq.redis_queue import CompetitorRedisQueue
        from config.settings import get_config
        q = CompetitorRedisQueue(redis_url=get_config().redis.url)
        return ok({
            "status": "ok",
            "redis": "connected" if q.is_available else "unavailable",
            "timestamp": datetime.now().isoformat(),
        })

    return bp