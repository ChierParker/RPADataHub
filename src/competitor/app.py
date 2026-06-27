"""
CompetitorWatch Admin 后台应用入口 (Flask)
- 竞品管理 CRUD API
- 竞价看板数据 API
- AI 报告生成与查看 API
- 采集任务下发（Redis MQ）
- 采集结果消费（Redis → MySQL）

启动: python app.py
生产: gunicorn -w 2 -b 0.0.0.0:5100 app:app
"""

import json
import os
import sys
import uuid
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify

from config.settings import get_config
from logger_config import setup_logger

logger = setup_logger("AdminServer")

# 初始化 Flask
app = Flask(__name__)
cfg = get_config()
app.secret_key = cfg.flask.secret_key

# 初始化 Redis 队列（延迟导入，避免循环依赖）
queue = None


def get_queue():
    """延迟初始化 Redis 队列"""
    global queue
    if queue is None:
        from mq.redis_queue import CompetitorRedisQueue
        queue = CompetitorRedisQueue(redis_url=cfg.redis.url)
    return queue


# ============================================================
# 页面路由
# ============================================================

@app.route("/competitor/manage")
def page_manage():
    """竞品管理页面"""
    return render_template("competitor/manage.html")


@app.route("/competitor/dashboard")
def page_dashboard():
    """竞价看板页面"""
    return render_template("competitor/dashboard.html")


@app.route("/competitor/reports")
def page_reports():
    """AI 报告页面"""
    return render_template("competitor/reports.html")


# ============================================================
# 辅助：统一 JSON 信封
# ============================================================

def ok(data=None, status_code=200):
    """成功响应"""
    return jsonify({"success": True, "data": data, "error": ""}), status_code


def fail(error="", status_code=400):
    """错误响应"""
    return jsonify({"success": False, "data": None, "error": error}), status_code


# ============================================================
# 竞品配置 CRUD API
# ============================================================

@app.route("/api/competitor/list")
def api_competitor_list():
    """获取竞品配置列表"""
    try:
        region = request.args.get("region")
        platform = request.args.get("platform")

        from core.db_operations import DatabaseManager
        db = DatabaseManager()
        items = db.get_competitor_list(region=region or None)

        # 按平台筛选（数据库层未做，应用层过滤）
        if platform:
            items = [it for it in items if it.get("platform") == platform]

        return ok(items)
    except Exception as e:
        logger.error(f"[API] 竞品列表查询失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/get")
def api_competitor_get():
    """获取单个竞品配置"""
    try:
        competitor_id = request.args.get("id")
        if not competitor_id:
            return fail("缺少参数: id")

        from core.db_operations import DatabaseManager
        db = DatabaseManager()
        item = db.get_competitor_by_id(int(competitor_id))
        if not item:
            return fail("竞品不存在", 404)

        # 转换 datetime 为字符串
        for key in ("created_at", "updated_at"):
            if item.get(key):
                item[key] = item[key].strftime("%Y-%m-%d %H:%M:%S")

        return ok(item)
    except Exception as e:
        logger.error(f"[API] 竞品查询失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/create", methods=["POST"])
def api_competitor_create():
    """新增竞品配置"""
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
        logger.error(f"[API] 竞品创建失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/update", methods=["POST"])
def api_competitor_update():
    """更新竞品配置"""
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
        logger.error(f"[API] 竞品更新失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/toggle", methods=["POST"])
def api_competitor_toggle():
    """切换竞品启用/停用状态"""
    try:
        competitor_id = request.args.get("id")
        if not competitor_id:
            return fail("缺少参数: id")

        from core.db_operations import DatabaseManager
        db = DatabaseManager()
        new_status = db.toggle_competitor(int(competitor_id))

        return ok({"new_status": new_status})
    except Exception as e:
        logger.error(f"[API] 竞品状态切换失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/delete", methods=["POST"])
def api_competitor_delete():
    """删除竞品配置（危险操作）"""
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
        logger.error(f"[API] 竞品删除失败: {e}", exc_info=True)
        return fail(str(e), 500)


# ============================================================
# 采集任务下发
# ============================================================

@app.route("/api/competitor/crawl", methods=["POST"])
def api_trigger_crawl():
    """
    下发采集任务到 Redis MQ

    流程:
        1. 从 DB 查询竞品配置
        2. 组装任务数据
        3. LPUSH 到 competitor:task:{region}
        4. Worker 的 BRPOP 会自动消费
    """
    try:
        competitor_id = request.args.get("id")
        if not competitor_id:
            return fail("缺少参数: id")

        from core.db_operations import DatabaseManager
        db = DatabaseManager()
        competitor = db.get_competitor_by_id(int(competitor_id))
        if not competitor:
            return fail("竞品不存在", 404)

        # 组装任务数据
        task_uuid = uuid.uuid4().hex[:16]
        task_data = {
            "task_uuid": task_uuid,
            "competitor_id": competitor["id"],
            "competitor_name": competitor["competitor_name"],
            "keywords": competitor["keywords"],        # JSON字符串
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
            "task_type": request.args.get("task_type", "crawl"),  # crawl / login_confirm
        }

        # 发布到 Redis 任务队列
        q = get_queue()
        published = q.publish_task(competitor["region"], task_data)

        logger.info(
            f"[Admin] 采集任务已下发: task_uuid={task_uuid}, "
            f"competitor={competitor['competitor_name']}, "
            f"region={competitor['region']}, mq={'OK' if published else 'DB降级'}"
        )

        return ok({
            "task_uuid": task_uuid,
            "message": "任务已下发",
            "via": "redis" if published else "db_fallback",
        })

    except Exception as e:
        logger.error(f"[API] 采集任务下发失败: {e}", exc_info=True)
        return fail(str(e), 500)


# ============================================================
# 看板数据 API
# ============================================================



@app.route("/api/competitor/login_confirm", methods=["POST"])
def api_login_confirm():
    """Frontend confirms login completion - signals backend to proceed."""
    try:
        task_uuid = request.args.get("task_uuid")
        if not task_uuid:
            return fail("missing task_uuid")
        q = get_queue()
        q.set_crawl_status(task_uuid, "login_confirmed", "用户已确认登录完成")
        return ok({"task_uuid": task_uuid, "confirmed": True})
    except Exception as e:
        return fail(str(e), 500)


@app.route("/api/competitor/crawl_status")
def api_crawl_status():
    """Get real-time crawl status for a task (frontend polling)."""
    try:
        task_uuid = request.args.get("task_uuid")
        if not task_uuid:
            return fail("missing task_uuid")
        q = get_queue()
        status = q.get_crawl_status(task_uuid)
        if status:
            return ok(status)
        return ok({"task_uuid": task_uuid, "status": "unknown", "detail": "no status record"})
    except Exception as e:
        return fail(str(e), 500)


@app.route("/api/competitor/trend")
def api_price_trend():
    """获取竞品价格趋势数据（图表用）"""
    try:
        competitor_id = request.args.get("id")
        days = int(request.args.get("days", 30))

        if not competitor_id:
            return fail("缺少参数: id")

        from core.db_operations import DatabaseManager
        db = DatabaseManager()
        trend = db.get_price_trend(int(competitor_id), days)

        # 转换 Decimal → float（JSON 序列化兼容）
        result = []
        for row in trend:
            r = dict(row)
            for k, v in r.items():
                if hasattr(v, 'isoformat'):  # date → str
                    r[k] = v.isoformat()
                elif hasattr(v, 'as_tuple'):  # Decimal → float
                    r[k] = float(v)
                elif isinstance(v, float):
                    r[k] = round(v, 4) if v is not None else None
            result.append(r)

        return ok(result)
    except Exception as e:
        logger.error(f"[API] 趋势查询失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/snapshots")
def api_snapshots():
    """获取最近价格快照明细"""
    try:
        competitor_id = request.args.get("id")
        limit = int(request.args.get("limit", 30))

        if not competitor_id:
            return fail("缺少参数: id")

        from core.db_operations import DatabaseManager
        db = DatabaseManager()
        snapshots = db.get_recent_snapshots(int(competitor_id), limit)

        # 转换类型
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
        logger.error(f"[API] 快照查询失败: {e}", exc_info=True)
        return fail(str(e), 500)


# ============================================================
# AI 报告 API
# ============================================================

@app.route("/api/competitor/reports")
def api_reports():
    """获取 AI 报告列表"""
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
        logger.error(f"[API] 报告列表查询失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/report_detail")
def api_report_detail():
    """获取单份报告完整内容"""
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
        logger.error(f"[API] 报告详情查询失败: {e}", exc_info=True)
        return fail(str(e), 500)


@app.route("/api/competitor/generate_report", methods=["POST"])
def api_generate_report():
    """
    生成 AI 分析报告

    流程:
        1. 从 DB 获取价格趋势和快照数据
        2. 调用 AIAnalyzer 生成报告
        3. 将报告保存到 competitor_report 表
        4. 如果告警级别为 critical，触发 Bark 推送（TODO）
    """
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

        # 获取竞品信息
        competitor = db.get_competitor_by_id(int(competitor_id))
        if not competitor:
            return fail("竞品不存在", 404)

        # 获取趋势数据
        trend_data = db.get_price_trend(int(competitor_id), days=14)

        # 获取最近快照
        snapshots = db.get_recent_snapshots(int(competitor_id), limit=20)

        # 调用 AI 分析
        from services.ai_analyzer import AIAnalyzer
        analyzer = AIAnalyzer()

        competitor_name = competitor["competitor_name"]
        platform = competitor.get("platform", "amazon")

        if report_type == "weekly":
            ai_result = analyzer.generate_weekly_report(
                competitor_name, platform, trend_data
            )
        else:
            ai_result = analyzer.generate_daily_report(
                competitor_name, platform, trend_data, snapshots
            )

        # 保存报告
        report_id = db.save_report(
            competitor_id=int(competitor_id),
            report_type=report_type,
            report_date=report_date,
            content=ai_result["content"],
            summary=ai_result["summary"],
            alert_level=ai_result.get("alert_level", "info"),
        )

        logger.info(
            f"[Admin] AI报告已生成: id={report_id}, "
            f"type={report_type}, competitor={competitor_name}, "
            f"alert={ai_result.get('alert_level', 'info')}"
        )

        # 如果是严重告警，触发推送（TODO: 集成 Bark）
        if ai_result.get("alert_level") == "critical":
            logger.warning(
                f"[Admin] 严重告警报告: {competitor_name} - {ai_result['summary']}"
            )
            # TODO: 调用 Bark 推送
            # from core.alert_manager import AlertManager
            # AlertManager().send_bark(ai_result["summary"])

        return ok({
            "report_id": report_id,
            "summary": ai_result["summary"],
            "alert_level": ai_result.get("alert_level", "info"),
        })

    except Exception as e:
        logger.error(f"[API] AI报告生成失败: {e}", exc_info=True)
        return fail(str(e), 500)


# ============================================================
# 结果消费后台线程（消费 Worker 回传的采集结果）
# ============================================================

def start_result_consumer():
    """
    启动后台线程消费 Worker 回传的采集结果

    流程:
        1. BRPOP competitor:result:{region}
        2. 解析结果数据
        3. 写入 ods_price_snapshot（Worker 已写入，此处做幂等兜底）
        4. 触发 ETL 日聚合（可选）
    """
    def consume_result(result_data: dict):
        """处理单条结果"""
        task_uuid = result_data.get("task_uuid", "-")
        status = result_data.get("status", "?")
        total = result_data.get("total_results", 0)

        logger.info(
            f"[Admin消费者] 收到结果: task_uuid={task_uuid}, "
            f"status={status}, results={total}"
        )

        # 如果 Worker 端未成功写入 DB，这里做兜底
        try:
            from core.db_operations import DatabaseManager
            db = DatabaseManager(task_uuid)

            # 检查是否已入库（幂等）
            snapshots = db.get_recent_snapshots(
                result_data.get("competitor_id", 0), limit=1
            )
            if not snapshots and result_data.get("results"):
                db.insert_snapshots_batch(result_data["results"])
                logger.info(f"[Admin消费者] DB兜底写入: {len(result_data['results'])} 条")

            # 触发日聚合
            if result_data.get("competitor_id"):
                pass  # DW aggregation handled by Worker; skip fallback
        except Exception as e:
            logger.error(f"[Admin消费者] 兜底处理失败: {e}", task_uuid)

    def run_consumer():
        """消费者线程主循环"""
        try:
            q = get_queue()
            q.consume_results("international", consume_result)
        except Exception as e:
            logger.error(f"[Admin消费者] international 消费异常: {e}")
        try:
            q = get_queue()
            q.consume_results("domestic", consume_result)
        except Exception as e:
            logger.error(f"[Admin消费者] domestic 消费异常: {e}")

    # 后台线程启动
    t1 = threading.Thread(target=run_consumer, daemon=True, name="ResultConsumer-intl")
    t1.start()
    logger.info("[Admin] 结果消费线程已启动 (international)")
    # domestic 由同一线程中的第二个 consume 处理（或独立线程）
    t2 = threading.Thread(
        target=lambda: get_queue().consume_results("domestic", consume_result),
        daemon=True, name="ResultConsumer-dom"
    )
    t2.start()
    logger.info("[Admin] 结果消费线程已启动 (domestic)")


# ============================================================
# 健康检查
# ============================================================

@app.route("/api/health")
def api_health():
    """健康检查接口"""
    q = get_queue()
    return ok({
        "status": "ok",
        "redis": "connected" if q.is_available else "unavailable",
        "timestamp": datetime.now().isoformat(),
    })


# ============================================================
# 应用入口
# ============================================================

if __name__ == "__main__":
    # 确保 src/ 在 sys.path 中，以便导入 shared.runner
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared.runner import run_flask_app, should_print_startup

    if should_print_startup(cfg.flask.debug):
        logger.info("=" * 60)
        logger.info("CompetitorWatch Admin v1.0 启动")
        logger.info(f"  Database: {cfg.database.host}:{cfg.database.port}/{cfg.database.database}")
        logger.info(f"  Redis: {cfg.redis.host}:{cfg.redis.port}/{cfg.redis.db}")
        logger.info(f"  Flask: {cfg.flask.host}:{cfg.flask.port}")
        logger.info(f"  AI Model: {cfg.ai.model}")
        logger.info("=" * 60)

    # 启动结果消费线程
    try:
        start_result_consumer()
    except Exception as e:
        logger.warning(f"结果消费线程启动失败（Redis不可用?）: {e}")

    # 启动 Flask
    run_flask_app(
        app,
        host=cfg.flask.host,
        port=cfg.flask.port,
        debug=cfg.flask.debug,
    )
