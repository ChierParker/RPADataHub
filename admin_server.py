"""
RPA Admin 管理平台
功能: ETL运行看板 / 运维SQL调度 / 路由配置管理
启动: python admin_server.py
访问: http://localhost:5000
默认账号: admin / YOUR_ADMIN_PASSWORD
"""

import hashlib
import io
import json
import os
import sys
from datetime import datetime
from functools import wraps

import pymysql
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.settings import get_config

app = Flask(__name__)
app.secret_key = b'your-flask-secret-key'
cfg = get_config()

# ============================================================
# 数据库工具（连接复用，减少开销）
# ============================================================
import threading
_conn_pool = threading.local()

def get_db():
    if not hasattr(_conn_pool, 'conn') or _conn_pool.conn is None:
        _conn_pool.conn = pymysql.connect(**cfg.database.as_dict())
    try:
        _conn_pool.conn.ping(reconnect=True)
    except:
        _conn_pool.conn = pymysql.connect(**cfg.database.as_dict())
    return _conn_pool.conn


def query(sql, params=None, as_dict=True):
    """执行查询，返回 DataFrame（复用连接）"""
    conn = get_db()
    df = pd.read_sql(sql, conn, params=params)
    return df


def execute(sql, params=None):
    """执行写操作"""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()


def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def clean_json_records(records):
    """清理 DataFrame records 中的 NaN/NaT, 确保可 JSON 序列化"""
    for r in records:
        for k in list(r.keys()):
            v = r[k]
            if hasattr(v, "strftime") and not pd.isna(v):
                r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
            elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                r[k] = None
    return records


# ============================================================
# 登录鉴权 + 权限控制
# ============================================================

PAGE_PERMISSION_MAP = {
    "dashboard": "ETL执行记录", "monitor": "SQL巡检", "monitor_dashboard": "采集图表",
    "health_dashboard": "健康总览", "tasks_page": "任务管理", "collection_monitor": "任务监控",
    "collection_records_page": "执行明细", "collection_health": "店铺健康",
    "bi_dashboard": "BI经营分析", "business_dashboard": "经营看板",
    "shops_page": "店铺管理", "routes_page": "路由配置",
    "ai_assistant_page": "AI助手", "ops_center": "AI运营中心",
}

def get_user_permissions():
    """获取当前用户权限列表"""
    if "user" not in session:
        return []
    role_id = session["user"].get("role_id", 2)
    try:
        df = query("SELECT permissions FROM user_roles WHERE id=%s", (role_id,))
        if not df.empty:
            return json.loads(df["permissions"].iloc[0])
    except: pass
    return []

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def permission_required(perm_key):
    """权限装饰器: 无权限时跳转提示页"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            perms = get_user_permissions()
            if "approval_manage" in perms or "member_manage" in perms or perm_key in perms:
                return f(*args, **kwargs)
            return render_template("permission_denied.html", page_name=PAGE_PERMISSION_MAP.get(perm_key, perm_key), perm_key=perm_key)
        return decorated
    return decorator

# 模板全局注入权限信息
@app.context_processor
def inject_permissions():
    perms = get_user_permissions() if "user" in session else []
    return {"user_permissions": perms, "page_map": PAGE_PERMISSION_MAP}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        df = query(
            "SELECT u.id, u.username, u.role, COALESCE(u.role_id,2) as role_id, COALESCE(r.name,'观察者') as role_name FROM admin_users u "
            "LEFT JOIN user_roles r ON u.role_id=r.id "
            "WHERE u.username=%s AND u.password_hash=%s AND u.is_active=1",
            params=(username, sha256(password))
        )
        if not df.empty:
            row = df.iloc[0].to_dict()
            # 清理 NaN
            for k,v in list(row.items()):
                if pd.isna(v): row[k] = ""
            session["user"] = row
            return redirect(url_for("home"))
        error = "账号或密码错误"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# 1. ETL执行记录仪表盘
# ============================================================

@app.route("/")
@login_required
def home():
    """默认首页"""
    return render_template("home.html")

@app.route("/dashboard")
@login_required
def dashboard():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    per_page = request.args.get("per_page", 15, type=int)
    offset = (page - 1) * per_page

    where = ""
    params = []
    if status_filter in ("SUCCESS", "FAILED"):
        where = "WHERE status = %s"
        params = [status_filter]

    # 总数
    total_df = query(f"SELECT COUNT(*) as cnt FROM etl_process_log {where}", params)
    total = int(total_df["cnt"].iloc[0]) if not total_df.empty else 0

    # 分页数据
    data_df = query(
        f"SELECT trace_id, file_name, ods_table, dw_table, status, row_count, "
        f"       dirty_count, error_msg, start_time, end_time "
        f"FROM etl_process_log {where} ORDER BY id DESC LIMIT %s OFFSET %s",
        params + [per_page, offset]
    )

    # 统计概览
    stats = {}
    stats_df = query(
        "SELECT status, COUNT(*) as cnt FROM etl_process_log "
        "WHERE start_time >= DATE_SUB(NOW(), INTERVAL 7 DAY) GROUP BY status"
    )
    for _, row in stats_df.iterrows():
        stats[row["status"]] = int(row["cnt"])

    records = data_df.to_dict("records") if not data_df.empty else []
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template("dashboard.html",
                           records=records, stats=stats,
                           page=page, total_pages=total_pages,
                           total=total, status_filter=status_filter)


@app.route("/api/etl_record/<trace_id>")
@login_required
def etl_record_detail(trace_id):
    """查看单条ETL记录详情"""
    # ETL记录
    etl = query(
        "SELECT * FROM etl_process_log WHERE trace_id=%s", (trace_id,)
    )
    # 校验记录
    validations = query(
        "SELECT * FROM data_validation_log WHERE trace_id=%s", (trace_id,)
    )
    # 告警记录
    alerts = query(
        "SELECT * FROM rpa_alert_log WHERE trace_id=%s", (trace_id,)
    )

    return jsonify({
        "etl": etl.to_dict("records")[0] if not etl.empty else None,
        "validations": validations.to_dict("records") if not validations.empty else [],
        "alerts": alerts.to_dict("records") if not alerts.empty else [],
    })


# ============================================================
# 2. 运维SQL监控
# ============================================================

@app.route("/monitor")
@login_required
def monitor():
    """运维监控页"""
    status_filter = request.args.get("alert_status", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    search_name = request.args.get("search_name", "")
    search_person = request.args.get("search_person", "")
    page = request.args.get("page", 1, type=int)
    per_page = 15

    templates = query(
        "SELECT * FROM monitor_sql_templates ORDER BY is_active DESC, id DESC"
    )
    # 筛选条件
    conditions = []
    params = []
    if status_filter in ("pending", "resolved", "ignored"):
        conditions.append("r.alert_status = %s"); params.append(status_filter)
    if date_from:
        conditions.append("DATE(r.executed_at) >= %s"); params.append(date_from)
    if date_to:
        conditions.append("DATE(r.executed_at) <= %s"); params.append(date_to)
    if search_name:
        conditions.append("t.name LIKE %s"); params.append(f"%{search_name}%")
    if search_person:
        conditions.append("t.responsible_person LIKE %s"); params.append(f"%{search_person}%")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    results = query(
        f"SELECT r.*, t.name as template_name, t.responsible_person "
        f"FROM monitor_sql_results r "
        f"JOIN monitor_sql_templates t ON r.template_id = t.id "
        f"{where} ORDER BY r.executed_at DESC LIMIT %s OFFSET %s",
        params + [per_page, (page - 1) * per_page]
    )
    total_df = query(
        f"SELECT COUNT(*) as cnt FROM monitor_sql_results r "
        f"JOIN monitor_sql_templates t ON r.template_id = t.id {where}", params
    )
    total = int(total_df["cnt"].iloc[0]) if not total_df.empty else 0
    return render_template("monitor.html",
                           templates=templates.to_dict("records") if not templates.empty else [],
                           results=results.to_dict("records") if not results.empty else [],
                           total=total, page=page,
                           total_pages=max(1, (total + per_page - 1) // per_page),
                           status_filter=status_filter, date_from=date_from, date_to=date_to,
                           search_name=search_name, search_person=search_person)


@app.route("/api/monitor/execute/<int:template_id>", methods=["POST"])
@login_required
def execute_monitor_sql(template_id):
    """执行一条监控SQL"""
    tmpl = query(
        "SELECT * FROM monitor_sql_templates WHERE id=%s", (template_id,)
    )
    if tmpl.empty:
        return jsonify({"error": "模板不存在"}), 404

    sql_text = tmpl["sql_text"].iloc[0]
    template_name = tmpl["name"].iloc[0]
    severity = tmpl["severity"].iloc[0]

    try:
        result_df = query(sql_text)
        total_rows = len(result_df)
        status = "WARN" if total_rows > 0 else "SUCCESS"

        # 结果预览（前20行JSON）
        preview = result_df.head(20).to_dict("records") if total_rows > 0 else []

        # 去重：先删除同一模板+当天的旧记录，再插入新记录
        execute(
            "DELETE FROM monitor_sql_results WHERE template_id=%s AND DATE(executed_at)=CURDATE()",
            (template_id,)
        )
        execute(
            "INSERT INTO monitor_sql_results (template_id, executed_by, exec_status, total_rows, result_preview) "
            "VALUES (%s, %s, %s, %s, %s)",
            (template_id, session["user"]["username"], status, total_rows, json.dumps(preview, default=str))
        )

        return jsonify({
            "success": True,
            "status": status,
            "total_rows": total_rows,
            "preview": preview,
            "message": f"正常" if status == "SUCCESS" else f"发现 {total_rows} 条异常"
        })
    except Exception as e:
        execute(
            "INSERT INTO monitor_sql_results (template_id, executed_by, exec_status, total_rows, error_msg) "
            "VALUES (%s, %s, 'FAILED', 0, %s)",
            (template_id, session["user"]["username"], str(e)[:500])
        )
        return jsonify({
            "success": False,
            "status": "FAILED",
            "message": str(e)[:300]
        }), 500


@app.route("/api/monitor/template", methods=["POST"])
@login_required
def save_monitor_template():
    """新增/编辑监控SQL模板"""
    data = request.json
    template_id = data.get("id")

    if template_id:
        execute(
            "UPDATE monitor_sql_templates SET name=%s, description=%s, sql_text=%s, "
            "target_table=%s, severity=%s, responsible_person=%s, schedule_cron=%s, is_active=%s WHERE id=%s",
            (data["name"], data.get("description", ""), data["sql_text"],
             data.get("target_table", ""), data.get("severity", "P1"),
             data.get("responsible_person", "admin"), data.get("schedule_cron", ""),
             data.get("is_active", 1), template_id)
        )
    else:
        execute(
            "INSERT INTO monitor_sql_templates (name, description, sql_text, target_table, "
            "severity, responsible_person, schedule_cron, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (data["name"], data.get("description", ""), data["sql_text"],
             data.get("target_table", ""), data.get("severity", "P1"),
             data.get("responsible_person", "admin"), data.get("schedule_cron", ""),
             session["user"]["username"])
        )
    return jsonify({"success": True})


@app.route("/api/monitor/template/<int:template_id>/data")
@login_required
def get_monitor_template(template_id):
    """获取单个监控模板数据（用于编辑弹窗）"""
    df = query("SELECT * FROM monitor_sql_templates WHERE id=%s", (template_id,))
    if df.empty:
        return jsonify({"error": "模板不存在"}), 404
    r = df.iloc[0].to_dict()
    for k, v in r.items():
        if hasattr(v, "strftime"):
            r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(r)


@app.route("/api/monitor/alert/<int:result_id>/data")
@login_required
def get_alert_detail(result_id):
    """获取单条告警详情（用于编辑弹窗）"""
    df = query("SELECT * FROM monitor_sql_results WHERE id=%s", (result_id,))
    if df.empty:
        return jsonify({"error": "告警不存在"}), 404
    r = df.iloc[0].to_dict()
    for k, v in r.items():
        if hasattr(v, "strftime"):
            r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(r)


@app.route("/api/monitor/alert/<int:result_id>", methods=["POST"])
@login_required
def update_alert_status(result_id):
    """更新告警处理状态"""
    data = request.json
    execute(
        "UPDATE monitor_sql_results SET alert_status=%s, alert_category=%s, "
        "error_reason=%s, solution=%s, resolved_by=%s, resolved_at=NOW() WHERE id=%s",
        (data.get("alert_status", "pending"),
         data.get("alert_category", ""),
         data.get("error_reason", ""),
         data.get("solution", ""),
         session["user"]["username"],
         result_id)
    )
    return jsonify({"success": True})


@app.route("/api/monitor/template/<int:template_id>", methods=["DELETE"])
@login_required
def delete_monitor_template(template_id):
    execute("DELETE FROM monitor_sql_templates WHERE id=%s", (template_id,))
    return jsonify({"success": True})


# ============================================================
# 3. 路由配置管理 (etl_path_route CRUD)
# ============================================================

@app.route("/routes")
@login_required
def routes_page():
    """路由配置页"""
    routes = query(
        "SELECT r.*, "
        "CASE WHEN r.dw_transform_sql IS NOT NULL AND r.dw_transform_sql != '' THEN 'Y' ELSE 'N' END AS has_dw_sql "
        "FROM etl_path_route r ORDER BY r.is_active DESC, r.id DESC"
    )
    return render_template("routes.html",
                           routes=routes.to_dict("records") if not routes.empty else [])


@app.route("/api/route/<int:route_id>/data")
@login_required
def get_route_data(route_id):
    df = query("SELECT * FROM etl_path_route WHERE id=%s",(route_id,))
    if df.empty: return jsonify({"error":"路由不存在"}),404
    r = df.iloc[0].to_dict()
    for k,v in r.items():
        if hasattr(v,"strftime") and not pd.isna(v): r[k]=v.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(r)

@app.route("/api/route", methods=["POST"])
@login_required
def save_route():
    """新增/编辑路由"""
    data = request.json
    route_id = data.get("id")

    if route_id:
        execute(
            "UPDATE etl_path_route SET path_pattern=%s, target_ods_table=%s, "
            "target_dw_table=%s, dw_transform_sql=%s, is_active=%s WHERE id=%s",
            (data["path_pattern"], data["target_ods_table"], data.get("target_dw_table", ""),
             data.get("dw_transform_sql", ""), data.get("is_active", 1), route_id)
        )
    else:
        execute(
            "INSERT INTO etl_path_route (path_pattern, target_ods_table, target_dw_table, "
            "dw_transform_sql, is_active) VALUES (%s,%s,%s,%s,%s)",
            (data["path_pattern"], data["target_ods_table"], data.get("target_dw_table", ""),
             data.get("dw_transform_sql", ""), data.get("is_active", 1))
        )
    return jsonify({"success": True})


@app.route("/api/change_password", methods=["POST"])
@login_required
def change_password():
    """修改当前用户密码"""
    data = request.json
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if not new_pw or len(new_pw) < 6:
        return jsonify({"error": "新密码至少6位"}), 400

    user = session["user"]
    df = query(
        "SELECT id FROM admin_users WHERE username=%s AND password_hash=%s",
        (user["username"], sha256(old_pw))
    )
    if df.empty:
        return jsonify({"error": "原密码错误"}), 403

    execute(
        "UPDATE admin_users SET password_hash=%s WHERE username=%s",
        (sha256(new_pw), user["username"])
    )
    return jsonify({"success": True, "message": "密码已修改"})


@app.route("/api/route/<int:route_id>", methods=["DELETE"])
@login_required
def delete_route(route_id):
    execute("DELETE FROM etl_path_route WHERE id=%s", (route_id,))
    return jsonify({"success": True})


# ============================================================
# 3b. 采集监控看板 (Grafana风格图表)
# ============================================================

@app.route("/monitor/dashboard")
@login_required
def monitor_dashboard():
    """采集监控看板"""
    # 获取所有ODS表名（用于筛选下拉）
    tables = query(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME LIKE %s ORDER BY TABLE_NAME",
        (cfg.database.database, "ods_%")
    )
    table_list = tables["TABLE_NAME"].tolist() if not tables.empty else []
    return render_template("monitor_dashboard.html", tables=table_list)


@app.route("/api/monitor/chart_data")
@login_required
def monitor_chart_data():
    """获取图表数据"""
    table = request.args.get("table", "ods_amazon_order_raw")
    days = request.args.get("days", 30, type=int)

    # 采集量趋势 — 根据表名匹配业务日期字段
    date_field_map = {
        "ods_order_raw": "order_date", "ods_sales_raw": "sale_date",
        "ods_advertising_raw": "ad_date", "ods_agreement_raw": "crawl_time",
        "ods_fee_raw": "fee_date", "ods_promotion_raw": "start_date",
        "ods_sina_news_raw": "crawl_time",
    }
    date_field = date_field_map.get(table, "create_time")

    collect_sql = f"""
        SELECT DATE({date_field}) AS dt, COUNT(*) AS cnt
        FROM {table}
        WHERE {date_field} >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY DATE({date_field}) ORDER BY dt
    """
    collect_df = query(collect_sql, (days,))
    collect_data = []
    if not collect_df.empty:
        for _, row in collect_df.iterrows():
            collect_data.append({
                "dt": row["dt"].strftime("%m-%d") if hasattr(row["dt"], "strftime") else str(row["dt"]),
                "cnt": int(row["cnt"])
            })

    # 拦截量趋势
    dirty_sql = f"""
        SELECT DATE(detect_time) AS dt, COUNT(*) AS cnt
        FROM rpa_dirty_data_log
        WHERE detect_time >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY DATE(detect_time) ORDER BY dt
    """
    dirty_df = query(dirty_sql, (days,))
    dirty_data = []
    if not dirty_df.empty:
        for _, row in dirty_df.iterrows():
            dirty_data.append({
                "dt": row["dt"].strftime("%m-%d") if hasattr(row["dt"], "strftime") else str(row["dt"]),
                "cnt": int(row["cnt"])
            })

    # 今日统计
    today_collect = query(
        f"SELECT COUNT(*) as cnt FROM {table} WHERE DATE({date_field}) = CURDATE()"
    )
    today_dirty = query(
        "SELECT COUNT(*) as cnt FROM rpa_dirty_data_log WHERE DATE(detect_time) = CURDATE()"
    )
    # 总拦截
    total_dirty = query("SELECT COUNT(*) as cnt FROM rpa_dirty_data_log")
    # 成功率
    success_rate = query(
        "SELECT "
        "  ROUND(SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS rate "
        "FROM etl_process_log WHERE start_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
    )

    return jsonify({
        "collect": collect_data,
        "dirty": dirty_data,
        "stats": {
            "today_collect": int(today_collect["cnt"].iloc[0]) if not today_collect.empty else 0,
            "today_dirty": int(today_dirty["cnt"].iloc[0]) if not today_dirty.empty else 0,
            "total_dirty": int(total_dirty["cnt"].iloc[0]) if not total_dirty.empty else 0,
            "success_rate": float(success_rate["rate"].iloc[0]) if not success_rate.empty else 0,
        }
    })


# ============================================================
# 4. 店铺管理
# ============================================================

@app.route("/shops")
@login_required
def shops_page():
    """店铺维表管理页"""
    return render_template("shops.html")


@app.route("/api/shops/data")
@login_required
def shops_data():
    """获取店铺列表（分页+筛选）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 15, type=int)
    offset = (page - 1) * per_page

    search = request.args.get("search", "")
    platform = request.args.get("platform", "")
    status = request.args.get("status", "")

    conditions = ["1=1"]
    params = []
    if search:
        conditions.append("(shop_name LIKE %s OR shop_id LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if platform:
        conditions.append("platform = %s")
        params.append(platform)
    if status != "":
        conditions.append("status = %s")
        params.append(int(status))

    where = " AND ".join(conditions)

    count_df = query(f"SELECT COUNT(*) as cnt FROM dim_shop_info WHERE {where}", params)
    total = int(count_df["cnt"].iloc[0]) if not count_df.empty else 0

    # 动态排序
    sort = request.args.get("sort", "")
    order = request.args.get("order", "desc")
    valid_shop_cols = ["shop_id", "shop_name", "platform", "bu", "email", "status", "create_time"]
    if sort in valid_shop_cols:
        order_dir = "ASC" if order.lower() == "asc" else "DESC"
        order_clause = f"ORDER BY {sort} {order_dir}"
    else:
        order_clause = "ORDER BY status DESC, shop_name"

    data_df = query(
        f"SELECT shop_id, shop_name, platform, bu, email, status, create_time "
        f"FROM dim_shop_info WHERE {where} {order_clause} "
        f"LIMIT %s OFFSET %s",
        params + [per_page, offset]
    )
    records = data_df.to_dict("records") if not data_df.empty else []
    for r in records:
        for k, v in r.items():
            if hasattr(v, "strftime"):
                r[k] = v.strftime("%Y-%m-%d %H:%M:%S")

    # 平台列表（筛选下拉）
    platforms = query("SELECT DISTINCT platform FROM dim_shop_info WHERE platform != '' ORDER BY platform")

    return jsonify({
        "records": records,
        "total": total,
        "platforms": platforms["platform"].tolist() if not platforms.empty else [],
    })


@app.route("/api/shops/save", methods=["POST"])
@login_required
def shops_save():
    """新增/编辑店铺"""
    data = request.json
    shop_id = data.get("shop_id", "").strip()
    if not shop_id:
        return jsonify({"error": "店铺ID不能为空"}), 400

    existing = query("SELECT shop_id FROM dim_shop_info WHERE shop_id=%s", (shop_id,))
    if existing.empty:
        execute(
            "INSERT INTO dim_shop_info (shop_id, shop_name, platform, bu, email, status) VALUES (%s,%s,%s,%s,%s,%s)",
            (shop_id, data.get("shop_name", ""), data.get("platform", ""),
             data.get("bu", ""), data.get("email", ""), data.get("status", 1))
        )
    else:
        execute(
            "UPDATE dim_shop_info SET shop_name=%s, platform=%s, bu=%s, email=%s, status=%s WHERE shop_id=%s",
            (data.get("shop_name", ""), data.get("platform", ""), data.get("bu", ""),
             data.get("email", ""), data.get("status", 1), shop_id)
        )
    return jsonify({"success": True})


@app.route("/api/shops/export")
@login_required
def shops_export():
    """导出店铺列表"""
    search = request.args.get("search", "")
    platform = request.args.get("platform", "")
    status = request.args.get("status", "")

    conditions = ["1=1"]
    params = []
    if search:
        conditions.append("(shop_name LIKE %s OR shop_id LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if platform:
        conditions.append("platform = %s"); params.append(platform)
    if status != "":
        conditions.append("status = %s"); params.append(int(status))

    where = " AND ".join(conditions)
    df = query(f"SELECT shop_id, shop_name, platform, bu, email, status, create_time FROM dim_shop_info WHERE {where} ORDER BY shop_name", params)
    df = df.rename(columns={"shop_id": "店铺ID", "shop_name": "店铺名称", "platform": "平台", "bu": "BU", "email": "邮箱", "status": "状态", "create_time": "创建时间"})

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="店铺管理", index=False)
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=f"shops_{datetime.now().strftime('%Y%m%d')}.xlsx")


# ============================================================
# 5. 经营看板 (DM层)
# ============================================================

# 看板配置注册表 — 新增看板只需在此注册
DASHBOARD_CONFIGS = {
    "agreement": {
        "title": "协议数据看板",
        "icon": "bi-file-earmark-text",
        # ODS表存明细，DW表存聚合 → 看板查ODS，统计可查DW
        "ods_table": "ods_agreement_raw",
        "dw_table": "dw_agreement_daily",
        "primary_key": "agreement_id",
        "display_columns": {
            "account": "店铺", "agreement_id": "协议ID", "marketplace": "站点",
            "asin": "ASIN", "title": "标题", "crawl_time": "采集时间",
            "method": "采集方式", "last_up_datetime": "最后更新", "delete_flag": "删除标记"
        },
        "filters": {
            "date_field": "crawl_time",
            "account_field": "account",
            "search_fields": ["asin", "title"],
            "enum_fields": {"marketplace": "站点", "delete_flag": "删除标记"},
        },
        # 统计查DW聚合表（速度快），明细查ODS表
        "stats_sql": """
            SELECT COUNT(*) as total, COUNT(DISTINCT asin) as asin_count,
                   COUNT(DISTINCT account) as shop_count,
                   SUM(CASE WHEN delete_flag=1 THEN 1 ELSE 0 END) as deleted
            FROM {table} WHERE {where}
        """,
        "data_sql": """
            SELECT account, agreement_id, marketplace, asin, title,
                   crawl_time, method, last_up_datetime, delete_flag
            FROM {table} WHERE 1=1 {filters}
            ORDER BY crawl_time DESC LIMIT %s OFFSET %s
        """,
        "count_sql": "SELECT COUNT(*) as cnt FROM {table} WHERE 1=1 {filters}",
    },
    "order": {
        "title": "订单数据看板", "icon": "bi-cart",
        "ods_table": "ods_order_raw", "dw_table": "dw_order_daily_summary",
        "primary_key": "po_number",
        "display_columns": {
            "shop_name": "店铺", "po_number": "PO号", "asin": "ASIN", "sku": "SKU",
            "order_date": "订单日期", "quantity": "数量", "amount": "金额", "order_status": "状态"
        },
        "filters": {
            "date_field": "order_date", "account_field": "shop_name",
            "search_fields": ["asin", "sku"],
            "enum_fields": {"order_status": "订单状态"},
        },
        "stats_sql": "SELECT COUNT(*) as total, SUM(quantity) as total_qty, SUM(amount) as total_amount, COUNT(DISTINCT asin) as asin_count, COUNT(DISTINCT shop_name) as shop_count FROM {table} WHERE {where}",
        "data_sql": "SELECT shop_name, po_number, asin, sku, order_date, quantity, amount, order_status FROM {table} WHERE 1=1 {filters} ORDER BY order_date DESC LIMIT %s OFFSET %s",
        "count_sql": "SELECT COUNT(*) as cnt FROM {table} WHERE 1=1 {filters}",
    },
    "advertising": {
        "title": "广告数据看板", "icon": "bi-megaphone",
        "ods_table": "ods_advertising_raw", "dw_table": "dw_advertising_daily_summary",
        "primary_key": "campaign_name",
        "display_columns": {
            "shop_name": "店铺", "campaign_name": "广告活动", "ad_type": "类型",
            "asin": "ASIN", "ad_date": "日期", "impressions": "曝光", "clicks": "点击",
            "spend": "花费", "sales": "广告销售额", "acos": "ACOS%"
        },
        "filters": {
            "date_field": "ad_date", "account_field": "shop_name",
            "search_fields": ["campaign_name", "asin"],
            "enum_fields": {"ad_type": "广告类型"},
        },
        "stats_sql": "SELECT COUNT(*) as total, SUM(impressions) as impr, SUM(clicks) as clicks, SUM(spend) as spend, SUM(sales) as sales, ROUND(SUM(spend)/NULLIF(SUM(sales),0)*100,1) as acos FROM {table} WHERE {where}",
        "data_sql": "SELECT shop_name, campaign_name, ad_type, asin, ad_date, impressions, clicks, spend, sales, acos FROM {table} WHERE 1=1 {filters} ORDER BY ad_date DESC LIMIT %s OFFSET %s",
        "count_sql": "SELECT COUNT(*) as cnt FROM {table} WHERE 1=1 {filters}",
    },
    "sales": {
        "title": "销量数据看板", "icon": "bi-graph-up-arrow",
        "ods_table": "ods_sales_raw", "dw_table": "dw_sales_daily_summary",
        "primary_key": "sale_date",
        "display_columns": {
            "shop_name": "店铺", "asin": "ASIN", "sale_date": "日期",
            "units_sold": "销量", "revenue": "销售额", "avg_price": "均价",
            "refund_qty": "退款量", "refund_amount": "退款金额"
        },
        "filters": {
            "date_field": "sale_date", "account_field": "shop_name",
            "search_fields": ["asin"],
            "enum_fields": {},
        },
        "stats_sql": "SELECT COUNT(*) as total, SUM(units_sold) as units, SUM(revenue) as revenue, SUM(refund_qty) as refunds, SUM(refund_amount) as refund_amt FROM {table} WHERE {where}",
        "data_sql": "SELECT shop_name, asin, sale_date, units_sold, revenue, avg_price, refund_qty, refund_amount FROM {table} WHERE 1=1 {filters} ORDER BY sale_date DESC LIMIT %s OFFSET %s",
        "count_sql": "SELECT COUNT(*) as cnt FROM {table} WHERE 1=1 {filters}",
    },
    "promotion": {
        "title": "折扣促销看板", "icon": "bi-tag",
        "ods_table": "ods_promotion_raw", "dw_table": "dw_promotion_daily_summary",
        "primary_key": "promo_name",
        "display_columns": {
            "shop_name": "店铺", "asin": "ASIN", "promo_name": "活动名称",
            "promo_type": "类型", "start_date": "开始", "end_date": "结束",
            "discount_pct": "折扣%", "promo_budget": "预算", "promo_sales": "活动销售额", "units_promo": "活动销量"
        },
        "filters": {
            "date_field": "start_date", "account_field": "shop_name",
            "search_fields": ["promo_name", "asin"],
            "enum_fields": {"promo_type": "活动类型"},
        },
        "stats_sql": "SELECT COUNT(*) as total, SUM(promo_budget) as budget, SUM(promo_sales) as sales, SUM(units_promo) as units FROM {table} WHERE {where}",
        "data_sql": "SELECT shop_name, asin, promo_name, promo_type, start_date, end_date, discount_pct, promo_budget, promo_sales, units_promo FROM {table} WHERE 1=1 {filters} ORDER BY start_date DESC LIMIT %s OFFSET %s",
        "count_sql": "SELECT COUNT(*) as cnt FROM {table} WHERE 1=1 {filters}",
    },
    "fee": {
        "title": "费用数据看板", "icon": "bi-cash-coin",
        "ods_table": "ods_fee_raw", "dw_table": "dw_fee_daily_summary",
        "primary_key": "invoice_id",
        "display_columns": {
            "shop_name": "店铺", "fee_type": "费用类型", "fee_date": "日期",
            "asin": "ASIN", "amount": "金额", "currency": "币种",
            "invoice_id": "发票号", "is_disputed": "争议"
        },
        "filters": {
            "date_field": "fee_date", "account_field": "shop_name",
            "search_fields": ["invoice_id", "asin"],
            "enum_fields": {"fee_type": "费用类型", "is_disputed": "争议状态"},
        },
        "stats_sql": "SELECT COUNT(*) as total, SUM(amount) as total_amount, COUNT(DISTINCT shop_name) as shops, SUM(CASE WHEN is_disputed=1 THEN 1 ELSE 0 END) as disputed FROM {table} WHERE {where}",
        "data_sql": "SELECT shop_name, fee_type, fee_date, asin, amount, currency, invoice_id, is_disputed FROM {table} WHERE 1=1 {filters} ORDER BY fee_date DESC LIMIT %s OFFSET %s",
        "count_sql": "SELECT COUNT(*) as cnt FROM {table} WHERE 1=1 {filters}",
    },
}


def _build_filter_clause(config, request_args):
    """根据看板配置和请求参数构建SQL WHERE条件"""
    conditions = []
    params = []

    # 日期范围
    date_field = config["filters"].get("date_field", "crawl_time")
    date_from = request_args.get("date_from", "")
    date_to = request_args.get("date_to", "")
    if date_from:
        conditions.append(f"DATE({date_field}) >= %s")
        params.append(date_from)
    if date_to:
        conditions.append(f"DATE({date_field}) <= %s")
        params.append(date_to)
    if not date_from and not date_to:
        # 默认最近7天
        conditions.append(f"DATE({date_field}) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)")

    # 店铺筛选
    account_field = config["filters"].get("account_field", "account")
    account = request_args.get("account", "")
    if account:
        accounts = [a.strip() for a in account.split(",") if a.strip()]
        if accounts:
            placeholders = ",".join(["%s"] * len(accounts))
            conditions.append(f"{account_field} IN ({placeholders})")
            params.extend(accounts)

    # 枚举字段筛选
    for field, label in config["filters"].get("enum_fields", {}).items():
        val = request_args.get(field, "")
        if val != "" and val is not None:
            conditions.append(f"{field} = %s")
            params.append(val)

    # 模糊搜索
    search = request_args.get("search", "")
    if search and config["filters"].get("search_fields"):
        search_clauses = []
        for f in config["filters"]["search_fields"]:
            search_clauses.append(f"{f} LIKE %s")
            params.append(f"%{search}%")
        conditions.append(f"({ ' OR '.join(search_clauses) })")

    where = " AND ".join(conditions) if conditions else "1=1"
    return where, params


@app.route("/dashboard/<name>")
@login_required
def business_dashboard(name):
    """经营看板页面"""
    config = DASHBOARD_CONFIGS.get(name)
    if not config:
        return "看板不存在", 404

    # 获取店铺列表（用于筛选下拉）
    account_field = config["filters"].get("account_field", "account")
    shops_df = query(
        "SELECT DISTINCT shop_name FROM dim_shop_info WHERE status=1 ORDER BY shop_name"
    )
    shops = shops_df["shop_name"].tolist() if not shops_df.empty else []

    # 枚举值（从ODS明细表查，DW聚合表没有明细列）
    enum_values = {}
    for field, label in config["filters"].get("enum_fields", {}).items():
        ods_table = config["ods_table"]
        vals = query(f"SELECT DISTINCT {field} FROM {ods_table} WHERE {field} IS NOT NULL ORDER BY {field}")
        enum_values[field] = vals[field].tolist() if not vals.empty else []

    return render_template("dashboard_data.html",
                           config=config, name=name,
                           shops=shops, enum_values=enum_values)


@app.route("/api/dashboard/<name>/data")
@login_required
def dashboard_data(name):
    """获取看板数据（分页 + 筛选）"""
    config = DASHBOARD_CONFIGS.get(name)
    if not config:
        return jsonify({"error": "看板不存在"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 15, type=int)
    offset = (page - 1) * per_page
    sort = request.args.get("sort", "")
    order = request.args.get("order", "desc")

    # 明细数据和统计都查ODS（DW聚合表没有asin/marketplace等明细列）
    ods_table = config["ods_table"]

    where, params = _build_filter_clause(config, request.args)
    count_params = list(params)

    # 统计
    stats_sql = config["stats_sql"].replace("{table}", ods_table).replace("{where}", where)
    stats_df = query(stats_sql, count_params)
    stats = stats_df.iloc[0].to_dict() if not stats_df.empty else {}

    # 动态排序：验证排序列名，防止SQL注入
    valid_cols = list(config["display_columns"].keys())
    if sort in valid_cols:
        order_dir = "ASC" if order.lower() == "asc" else "DESC"
        order_clause = f"ORDER BY {sort} {order_dir}"
    else:
        # 默认按日期降序
        date_field = config["filters"].get("date_field", "id")
        order_clause = f"ORDER BY {date_field} DESC"

    # 明细数据（查ODS）
    base_sql = config["data_sql"]
    # 替换模板中的硬编码ORDER BY为动态排序
    import re
    base_sql = re.sub(r'ORDER BY \S+ (?:DESC|ASC)', order_clause, base_sql, flags=re.IGNORECASE)
    data_sql = base_sql.replace("{table}", ods_table).replace("{filters}", f"AND {where}" if where != "1=1" else "")
    data_params = list(params) + [per_page, offset]
    data_df = query(data_sql, data_params)
    records = data_df.to_dict("records") if not data_df.empty else []

    # 总数
    count_sql = config["count_sql"].replace("{table}", ods_table).replace("{filters}", f"AND {where}" if where != "1=1" else "")
    total_df = query(count_sql, count_params)
    total = int(total_df["cnt"].iloc[0]) if not total_df.empty else 0

    # 转换 datetime → 字符串（JSON序列化）
    for r in records:
        for k, v in r.items():
            if hasattr(v, "strftime"):
                r[k] = v.strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({
        "records": records,
        "stats": {k: (int(v) if isinstance(v, (int, float)) else v) for k, v in stats.items()},
        "total": total,
        "page": page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    })


@app.route("/api/dashboard/<name>/export")
@login_required
def dashboard_export(name):
    """导出看板数据为Excel"""
    config = DASHBOARD_CONFIGS.get(name)
    if not config:
        return "看板不存在", 404

    # 导出明细数据（从ODS查）
    ods_table = config["ods_table"]
    where, params = _build_filter_clause(config, request.args)

    export_sql = f"""
        SELECT {', '.join(config['display_columns'].keys())}
        FROM {ods_table} WHERE 1=1 {"AND " + where if where != "1=1" else ""}
        ORDER BY {config['filters']['date_field']} DESC
        LIMIT 50000
    """
    df = query(export_sql, params)

    # 重命名列为中文
    df = df.rename(columns=config["display_columns"])

    # 写入Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=config["title"], index=False)
    output.seek(0)

    filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=filename)


# ============================================================
# 6. BI经营分析 (跨模块聚合 + 下钻)
# ============================================================

@app.route("/bi")
@login_required
def bi_dashboard():
    """BI经营分析看板"""
    shops_df = query("SELECT shop_name, platform FROM dim_shop_info WHERE status=1 ORDER BY platform, shop_name")
    shops = shops_df.to_dict("records") if not shops_df.empty else []
    platforms = sorted(set(s["platform"] for s in shops))
    return render_template("bi_dashboard.html", shops=shops, platforms=platforms)


@app.route("/api/bi/overview")
@login_required
def bi_overview():
    """BI概览数据"""
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    platform = request.args.get("platform", "")

    # 日期条件
    if date_from and date_to:
        date_clause = "BETWEEN %s AND %s"; date_vals = [date_from, date_to]
    elif date_from:
        date_clause = ">= %s"; date_vals = [date_from]
    elif date_to:
        date_clause = "<= %s"; date_vals = [date_to]
    else:
        date_clause = ">= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"; date_vals = []

    # 平台JOIN
    if platform:
        plat_join = " JOIN dim_shop_info ds ON t.shop_name = ds.shop_name AND ds.platform = %s"
        plat_val = [platform]
    else:
        plat_join = ""; plat_val = []

    try:
        # KPI
        gmv_df = query(f"SELECT COALESCE(SUM(t.revenue),0) v FROM ods_sales_raw t{plat_join} WHERE t.sale_date {date_clause}", plat_val + date_vals)
        total_gmv = float(gmv_df["v"].iloc[0])

        ad_df = query(f"SELECT COALESCE(SUM(t.spend),0) sp, COALESCE(SUM(t.sales),0) sa FROM ods_advertising_raw t{plat_join} WHERE t.ad_date {date_clause}", plat_val + date_vals)
        ad_spend = float(ad_df["sp"].iloc[0]); ad_sales = float(ad_df["sa"].iloc[0])
        acos = round(ad_spend / ad_sales * 100, 1) if ad_sales > 0 else 0

        ord_df = query(f"SELECT COUNT(*) c FROM ods_order_raw t{plat_join} WHERE t.order_date {date_clause}", plat_val + date_vals)
        order_cnt = int(ord_df["c"].iloc[0])

        ref_df = query(f"SELECT COALESCE(SUM(t.units_sold),0) s, COALESCE(SUM(t.refund_qty),0) r FROM ods_sales_raw t{plat_join} WHERE t.sale_date {date_clause}", plat_val + date_vals)
        refund_rate = round(float(ref_df["r"].iloc[0]) / float(ref_df["s"].iloc[0]) * 100, 1) if float(ref_df["s"].iloc[0]) > 0 else 0

        fee_df = query(f"SELECT COALESCE(SUM(t.amount),0) v FROM ods_fee_raw t{plat_join} WHERE t.fee_date {date_clause}", plat_val + date_vals)
        total_fees = float(fee_df["v"].iloc[0])

        # 日度趋势
        rev_t = query(f"SELECT t.sale_date d, SUM(t.revenue) v FROM ods_sales_raw t{plat_join} WHERE t.sale_date {date_clause} GROUP BY t.sale_date ORDER BY d", plat_val + date_vals)
        ad_t = query(f"SELECT t.ad_date d, SUM(t.spend) v FROM ods_advertising_raw t{plat_join} WHERE t.ad_date {date_clause} GROUP BY t.ad_date ORDER BY d", plat_val + date_vals)
        ord_t = query(f"SELECT t.order_date d, COUNT(*) v FROM ods_order_raw t{plat_join} WHERE t.order_date {date_clause} GROUP BY t.order_date ORDER BY d", plat_val + date_vals)

        from collections import OrderedDict
        trend_map = OrderedDict()
        for _, r in rev_t.iterrows():
            k = r["d"].strftime("%m-%d") if hasattr(r["d"],"strftime") else str(r["d"])
            trend_map[k] = {"revenue":float(r["v"]),"ad_spend":0,"orders":0}
        for _, r in ad_t.iterrows():
            k = r["d"].strftime("%m-%d") if hasattr(r["d"],"strftime") else str(r["d"])
            if k not in trend_map: trend_map[k] = {"revenue":0,"ad_spend":0,"orders":0}
            trend_map[k]["ad_spend"] = float(r["v"])
        for _, r in ord_t.iterrows():
            k = r["d"].strftime("%m-%d") if hasattr(r["d"],"strftime") else str(r["d"])
            if k not in trend_map: trend_map[k] = {"revenue":0,"ad_spend":0,"orders":0}
            trend_map[k]["orders"] = int(r["v"])
        trend_data = [{"date":k,**v} for k,v in trend_map.items()]

        # 平台分布（不受平台筛选影响，始终展示全部）
        plat_df = query(f"SELECT ds.platform, COALESCE(SUM(t.revenue),0) revenue FROM ods_sales_raw t JOIN dim_shop_info ds ON t.shop_name=ds.shop_name WHERE t.sale_date {date_clause} GROUP BY ds.platform ORDER BY revenue DESC", date_vals)

        # 费用构成
        fee_brk = query(f"SELECT t.fee_type, SUM(t.amount) total FROM ods_fee_raw t{plat_join} WHERE t.fee_date {date_clause} GROUP BY t.fee_type ORDER BY total DESC", plat_val + date_vals)

        # 热销TOP10
        top_df = query(f"SELECT t.asin, SUM(t.units_sold) units, SUM(t.revenue) revenue FROM ods_sales_raw t{plat_join} WHERE t.sale_date {date_clause} GROUP BY t.asin ORDER BY revenue DESC LIMIT 10", plat_val + date_vals)
        products = []
        if not top_df.empty:
            titles = {}
            try:
                tdf = query("SELECT DISTINCT asin, title FROM ods_agreement_raw")
                for _, r in tdf.iterrows(): titles[r["asin"]] = r["title"]
            except: pass
            for _, r in top_df.iterrows():
                products.append({"asin":r["asin"],"title":titles.get(r["asin"],r["asin"]),"units":int(r["units"]),"revenue":float(r["revenue"])})

        return jsonify({
            "kpi":{"gmv":round(total_gmv,2),"orders":order_cnt,"ad_spend":round(ad_spend,2),
                   "acos":acos,"refund_rate":refund_rate,"fees":round(total_fees,2)},
            "trend":trend_data,
            "platform_dist":plat_df.to_dict("records") if not plat_df.empty else [],
            "fee_breakdown":fee_brk.to_dict("records") if not fee_brk.empty else [],
            "top_products":products,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================================
# 启动
# ============================================================



# ============================================================
import hashlib as _hashlib


@app.route("/api/monitor/ai_analyze", methods=["POST"])
@login_required
def ai_analyze_alert():
    """AI分析告警"""
    data = request.json
    alert_id = data.get("alert_id", "")
    exception_type = data.get("exception_type", "")
    error_message = data.get("error_message", "")

    # 获取告警详情
    try:
        alert_df = query("SELECT * FROM monitor_sql_results WHERE id=%s", (alert_id,))
        if not alert_df.empty:
            r = alert_df.iloc[0]
            exception_type = exception_type or "数据异常"
            error_message = error_message or r.get("error_reason") or r.get("error_msg") or str(r.get("result_preview",""))
    except: pass

    try:
        from core.ai_agent import AIOpsAgent
        agent = AIOpsAgent(api_key=cfg.alert.deepseek_api_key)
        analysis = agent.analyze_exception(None, f"ai-{alert_id}", exception_type, error_message)

        if analysis:
            try:
                execute(
                    "UPDATE monitor_sql_results SET error_reason=%s, solution=%s WHERE id=%s",
                    (str(analysis.get("root_cause",""))[:500], str(analysis.get("suggestion",""))[:500], alert_id)
                )
            except: pass
            return jsonify({"success":True,
                "root_cause":analysis.get("root_cause",""),
                "suggestion":analysis.get("suggestion",""),
                "business_impact":analysis.get("business_impact",""),
                "notification":analysis.get("notification","")})
        return jsonify({"success":False,"error":"AI未返回有效结果"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success":False,"error":f"AI分析失败: {str(e)[:200]}"}), 500

    return jsonify({"success":False,"error":"AI分析未返回结果"}), 500


# 7. 任务管理
@app.route("/tasks")
@login_required
def tasks_page():
    configs = query("SELECT * FROM task_config ORDER BY id DESC")
    return render_template("tasks.html",
        configs=configs.to_dict("records") if not configs.empty else [])

@app.route("/api/tasks/config", methods=["POST"])
@login_required
def task_config_save():
    data = request.json
    cfg_id = data.get("id")
    if cfg_id:
        execute(
            "UPDATE task_config SET task_name=%s,script_name=%s,platform=%s,country=%s,"
            "shop_name=%s,collect_type=%s,business_date=%s,executor_ip=%s,"
            "schedule_type=%s,cron_expression=%s,timeout_sec=%s,priority=%s,status=%s WHERE id=%s",
            (data["task_name"],data["script_name"],data.get("platform"),data.get("country"),
             data.get("shop_name"),data.get("collect_type"),data.get("business_date"),
             data.get("executor_ip"),data.get("schedule_type","now"),data.get("cron_expression"),
             data.get("timeout_sec",3600),data.get("priority",1),data.get("status",1),cfg_id))
    else:
        execute(
            "INSERT INTO task_config (task_name,script_name,platform,country,shop_name,"
            "collect_type,business_date,executor_ip,schedule_type,cron_expression,timeout_sec,priority) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (data["task_name"],data["script_name"],data.get("platform"),data.get("country"),
             data.get("shop_name"),data.get("collect_type"),data.get("business_date"),
             data.get("executor_ip"),data.get("schedule_type","now"),data.get("cron_expression"),
             data.get("timeout_sec",3600),data.get("priority",1)))
    return jsonify({"success":True})

@app.route("/api/tasks/config/<int:cfg_id>", methods=["DELETE"])
@login_required
def task_config_delete(cfg_id):
    execute("DELETE FROM task_config WHERE id=%s",(cfg_id,))
    return jsonify({"success":True})

@app.route("/api/tasks/run/<int:cfg_id>", methods=["POST"])
@login_required
def task_run_now(cfg_id):
    cfg = query("SELECT * FROM task_config WHERE id=%s",(cfg_id,))
    if cfg.empty: return jsonify({"error":"任务不存在"}),404
    c = cfg.iloc[0]
    import hashlib
    task_uuid = hashlib.md5(f"{cfg_id}{datetime.now()}".encode()).hexdigest()[:16]
    task_msg = {"task_uuid":task_uuid,"script_name":str(c["script_name"]),"config_id":int(cfg_id),
                "platform":str(c["platform"] or ""),"shop_name":str(c["shop_name"] or ""),
                "business_date":str(c["business_date"] or ""),"collect_type":str(c["collect_type"] or ""),
                "executor_ip":str(c["executor_ip"] or ""),"timeout_sec":int(c["timeout_sec"] or 3600),
                "priority":int(c["priority"] or 1),"timestamp":datetime.now().isoformat()}
    try:
        from mq.redis_broker import RedisBroker
        broker = RedisBroker()
        broker.publish(task_msg)
        mq = "Redis Streams" if broker._redis_available else "DB (Redis不可用)"
    except ImportError:
        execute("INSERT INTO task_queue (config_id,task_uuid,script_name,task_params,executor_ip) VALUES (%s,%s,%s,%s,%s)",
                (cfg_id,task_uuid,c["script_name"],json.dumps(task_msg,ensure_ascii=False),c["executor_ip"]))
        mq = "DB"
    return jsonify({"success":True,"task_uuid":task_uuid,"mq":mq})

@app.route("/api/tasks/queue")
@login_required
def task_queue_data():
    status = request.args.get("status","")
    page = request.args.get("page",1,type=int)
    per_page = request.args.get("per_page", 15, type=int)
    where = ""; params = []
    if status: where = "WHERE q.task_status=%s"; params = [status]
    total_df = query(f"SELECT COUNT(*) c FROM task_queue q {where}",params)
    total = int(total_df["c"].iloc[0])
    df = query(f"SELECT q.id,q.config_id,q.task_uuid,q.script_name,q.task_params,q.task_status,q.executor_ip,q.start_time,q.end_time,q.duration_sec,q.error_message,q.total_shops,q.success_shops,q.failed_shops,q.no_data_shops,q.create_time,c.task_name FROM task_queue q LEFT JOIN task_config c ON q.config_id=c.id {where} ORDER BY q.id DESC LIMIT %s OFFSET %s", params+[per_page,(page-1)*per_page])
    records = df.to_dict("records") if not df.empty else []
    clean_json_records(records)
    return jsonify({"records":records,"total":total})

# 8. 采集监控
@app.route("/api/collection/summary")
@login_required
def collection_summary_data():
    date = request.args.get("date",datetime.now().strftime("%Y-%m-%d"))
    page = request.args.get("page",1,type=int)
    per_page = request.args.get("per_page",15,type=int)
    try:
        total_df = query("SELECT COUNT(*) c FROM task_queue q WHERE DATE(q.create_time)>=DATE_SUB(CURDATE(),INTERVAL 7 DAY)")
        total = int(total_df["c"].iloc[0])
        df = query(f"SELECT q.task_uuid,q.script_name,q.task_status,q.start_time,q.end_time,q.duration_sec,q.total_shops,q.success_shops,q.failed_shops,q.no_data_shops,q.error_message,s.success_rate FROM task_queue q LEFT JOIN task_summary s ON q.task_uuid=s.task_uuid WHERE DATE(q.create_time)>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) ORDER BY q.id DESC LIMIT %s OFFSET %s", [per_page,(page-1)*per_page])
        records = df.to_dict("records") if not df.empty else []
        clean_json_records(records)
        return jsonify({"records":records,"total":total})
    except Exception as e:
        return jsonify({"records":[],"total":0,"error":str(e)})

@app.route("/collection/monitor")
@app.route("/collection/monitor")
@login_required
def collection_monitor():
    today = datetime.now().strftime("%Y-%m-%d")
    stats = query(f"SELECT COUNT(*) total, SUM(CASE WHEN task_status='SUCCESS' THEN 1 ELSE 0 END) success, SUM(CASE WHEN task_status='FAILED' THEN 1 ELSE 0 END) failed, SUM(CASE WHEN task_status='RUNNING' THEN 1 ELSE 0 END) running FROM task_queue WHERE DATE(create_time)='{today}'")
    st = {"total":0,"success":0,"failed":0,"running":0}
    try:
        if not stats.empty: st = {k:int(stats[k].iloc[0] or 0) for k in st}
    except: pass
    return render_template("collection_monitor.html",stats=st)

@app.route("/api/collection/records")
@login_required
def collection_records_data():
    task_uuid = request.args.get("task_uuid","")
    shop = request.args.get("shop","")
    date = request.args.get("date","")
    page = request.args.get("page",1,type=int)
    per_page = request.args.get("per_page", 10, type=int)
    conds = []; ps = []
    if task_uuid: conds.append("task_uuid=%s"); ps.append(task_uuid)
    if shop: conds.append("shop_name LIKE %s"); ps.append(f"%{shop}%")
    if date: conds.append("create_time >= %s AND create_time < DATE_ADD(%s, INTERVAL 1 DAY)"); ps.append(date); ps.append(date)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total_df = query(f"SELECT COUNT(*) c FROM task_record {where}",ps)
    total = int(total_df["c"].iloc[0])
    cols = "id,task_uuid,shop_name,platform,script_name,ods_table,collect_start,collect_end,collect_result,row_count,duration_sec,create_time"
    df = query(f"SELECT {cols} FROM task_record {where} ORDER BY id DESC LIMIT %s OFFSET %s", ps+[per_page,(page-1)*per_page])
    records = df.to_dict("records") if not df.empty else []
    for r in records:
        for k,v in r.items():
            if hasattr(v,"strftime") and not pd.isna(v): r[k]=v.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"records":records,"total":total})

@app.route("/collection/records")
@login_required
def collection_records_page():
    shops = query("SELECT DISTINCT shop_name FROM task_record ORDER BY shop_name")
    return render_template("collection_records.html", shops=shops["shop_name"].tolist() if not shops.empty else [])

@app.route("/collection/health")
@login_required
def collection_health():
    shops_df = query("SELECT DISTINCT shop_name FROM dim_shop_info WHERE status=1 ORDER BY shop_name")
    shops = shops_df["shop_name"].tolist() if not shops_df.empty else []
    return render_template("collection_health.html",shops=shops)

@app.route("/api/collection/health")
@login_required
def collection_health_data():
    shop = request.args.get("shop","")
    cond = ""; ps = []
    if shop: cond = "AND shop_name=%s"; ps = [shop]
    df = query(f"SELECT shop_name, DATE(create_time) dt, collect_result, COUNT(*) cnt FROM task_record WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) {cond} GROUP BY shop_name, DATE(create_time), collect_result ORDER BY shop_name, dt", ps)
    records = df.to_dict("records") if not df.empty else []
    for r in records:
        if hasattr(r["dt"],"strftime"): r["dt"]=r["dt"].strftime("%Y-%m-%d")
    return jsonify({"records":records})

@app.route("/dashboard/health")
@login_required
def health_dashboard():
    today = datetime.now().strftime("%Y-%m-%d")
    task_stats = query(f"SELECT COUNT(*) t, SUM(CASE WHEN task_status='SUCCESS' THEN 1 ELSE 0 END) s, SUM(CASE WHEN task_status='FAILED' THEN 1 ELSE 0 END) f FROM task_queue WHERE DATE(create_time)='{today}'")
    collect = query("SELECT (SELECT COUNT(*) FROM ods_order_raw WHERE DATE(create_time)=CURDATE()) + (SELECT COUNT(*) FROM ods_sales_raw WHERE DATE(create_time)=CURDATE()) + (SELECT COUNT(*) FROM ods_agreement_raw WHERE DATE(crawl_time)=CURDATE()) as total")
    dirty = query("SELECT COUNT(*) c FROM rpa_dirty_data_log WHERE DATE(detect_time)=CURDATE()")
    exceptions = query(f"SELECT COUNT(*) c FROM rpa_exception_log WHERE DATE(create_time)='{today}'")
    etl = query("SELECT ROUND(SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END)/COUNT(*)*100,1) r FROM etl_process_log WHERE start_time >= DATE_SUB(CURDATE(),INTERVAL 7 DAY)")
    return render_template("health_dashboard.html",
        task_success=int(task_stats["s"].iloc[0]or 0), task_failed=int(task_stats["f"].iloc[0]or 0),
        today_collect=int(collect["total"].iloc[0]or 0), today_dirty=int(dirty["c"].iloc[0]or 0),
        today_exceptions=int(exceptions["c"].iloc[0]or 0), etl_rate=float(etl["r"].iloc[0]or 0))


# ============================================================
# 9. AI 运营助手 (Function Calling)
# ============================================================

@app.route("/ai")
@login_required
def ai_assistant_page():
    return render_template("ai_assistant.html")

import pandas as pd

def _ai_query(sql):
    """AI助手的SQL查询（只读白名单）"""
    allowed = ['ods_order_raw','ods_sales_raw','ods_advertising_raw','ods_fee_raw','ods_agreement_raw',
               'ods_sina_news_raw','dim_shop_info','task_queue','task_record','task_summary',
               'rpa_exception_log','rpa_dirty_data_log','etl_process_log']
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith('SELECT'): return '仅支持SELECT查询'
    if not any(t in sql.lower() for t in allowed): return '查询的表中包含非白名单表'
    try:
        df = query(sql)
        if df.empty: return '查询结果为空'
        return df.head(20).to_markdown(index=False)
    except Exception as e:
        return f'SQL执行失败: {str(e)[:200]}'

def _ai_today_summary():
    """今日概览"""
    parts = []
    for table, date_col in [('ods_order_raw','order_date'),('ods_sales_raw','sale_date'),
                              ('ods_advertising_raw','ad_date'),('ods_agreement_raw','crawl_time'),
                              ('ods_sina_news_raw','crawl_time')]:
        try:
            df = query(f"SELECT COUNT(*) c FROM {table} WHERE DATE({date_col})=CURDATE()")
            parts.append(f"{table}: {int(df['c'].iloc[0])} 条")
        except: pass
    try:
        df = query("SELECT COUNT(*) c FROM rpa_exception_log WHERE DATE(create_time)=CURDATE()")
        parts.append(f"今日异常: {int(df['c'].iloc[0])} 次")
        df = query("SELECT task_status, COUNT(*) c FROM task_queue WHERE DATE(create_time)=CURDATE() GROUP BY task_status")
        for _,r in df.iterrows(): parts.append(f"任务{r['task_status']}: {int(r['c'])}")
    except: pass
    return '\n'.join(parts) or '暂无今日数据'

def _ai_exception_detail(etype):
    """异常详情"""
    try:
        df = query("SELECT shop_name, error_message, create_time FROM rpa_exception_log WHERE exception_type=%s AND create_time>=DATE_SUB(NOW(),INTERVAL 7 DAY) ORDER BY create_time DESC LIMIT 20", (etype,))
        if df.empty: return f'最近7天无「{etype}」异常'
        shops = df['shop_name'].value_counts().head(5).to_dict()
        lines = [f'最近7天「{etype}」共 {len(df)} 次，TOP5店铺:']
        for s,c in shops.items(): lines.append(f'  {s}: {c}次')
        return '\n'.join(lines)
    except Exception as e: return f'查询失败: {e}'

def _ai_analyze(question, raw_data):
    """将原始数据 + 用户问题发给 DeepSeek 生成洞察"""
    if not raw_data or len(raw_data) < 10:
        return raw_data
    try:
        import requests
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + cfg.alert.deepseek_api_key + "", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是电商数据平台的AI运营分析师。根据用户问题和数据，用中文给出简洁专业的分析洞察（100字内），指出关键数字、趋势、异常和建议。不要重复原始数据。"},
                    {"role": "user", "content": f"用户问题：{question}\n\n查询结果数据：\n{raw_data}"}
                ],
                "temperature": 0.5, "max_tokens": 300
            },
            timeout=10
        )
        if resp.status_code == 200:
            ai_reply = resp.json()["choices"][0]["message"]["content"]
            return ai_reply + "\n\n---\n" + raw_data
    except:
        pass
    return raw_data

@app.route("/api/ai/chat", methods=["POST"])
@login_required
def ai_chat():
    """AI 运营助手对话"""
    data = request.json
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "请输入问题"}), 400

    try:
        # 直接匹配常见问题，绕过 Function Calling 延迟
        msg_lower = message.lower()
        # 匹配关键词 → 查数据 → AI 分析
        raw = None
        if any(w in msg_lower for w in ['今天','今日','概览']):
            raw = _ai_today_summary()
        elif '异常' in msg_lower:
            raw = _ai_exception_detail('登录失败') + '\n' + _ai_exception_detail('网络超时')
        elif any(w in msg_lower for w in ['采集','数据量','趋势']):
            raw = _ai_query("SELECT DATE(create_time) dt, COUNT(*) cnt FROM task_record WHERE create_time>=DATE_SUB(NOW(),INTERVAL 14 DAY) GROUP BY DATE(create_time) ORDER BY dt DESC LIMIT 14")
        elif 'gmv' in msg_lower or '平台' in msg_lower:
            raw = _ai_query("SELECT ds.platform, SUM(s.revenue) revenue FROM ods_sales_raw s JOIN dim_shop_info ds ON s.shop_name=ds.shop_name WHERE s.sale_date>=DATE_SUB(CURDATE(),INTERVAL 30 DAY) GROUP BY ds.platform ORDER BY revenue DESC")
        elif '店铺' in msg_lower and '退款' in msg_lower:
            raw = _ai_query("SELECT shop_name, SUM(refund_amount) refund FROM ods_sales_raw WHERE sale_date>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) GROUP BY shop_name ORDER BY refund DESC LIMIT 5")
        elif '广告' in msg_lower:
            raw = _ai_query("SELECT shop_name, SUM(spend) spend FROM ods_advertising_raw WHERE ad_date>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) GROUP BY shop_name ORDER BY spend DESC LIMIT 5")
        elif '新闻' in msg_lower or '新浪' in msg_lower:
            raw = _ai_query("SELECT COUNT(*) total, DATE(crawl_time) dt FROM ods_sina_news_raw WHERE crawl_time>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) GROUP BY DATE(crawl_time) ORDER BY dt DESC")
        elif '成功' in msg_lower or '任务' in msg_lower:
            raw = _ai_query("SELECT task_status, COUNT(*) cnt FROM task_queue WHERE create_time>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) GROUP BY task_status")
        else:
            raw = _ai_today_summary()

        # AI 分析原始数据生成洞察
        reply = _ai_analyze(message, raw) if raw else "暂无数据"
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"AI助手异常: {str(e)[:200]}"}), 500



# ============================================================
# 10. 成员管理 + 权限审批 + 注册
# ============================================================

@app.route("/register", methods=["GET","POST"])
def register_page():
    """用户注册"""
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        phone = request.form.get("phone","").strip()
        wechat = request.form.get("wechat","").strip()
        email = request.form.get("email","").strip()
        if not username or not password:
            return render_template("register.html", error="用户名和密码不能为空")
        if len(password) < 6:
            return render_template("register.html", error="密码至少6位")
        # 检查用户名唯一性
        exist = query("SELECT id FROM admin_users WHERE username=%s",(username,))
        if not exist.empty:
            return render_template("register.html", error="用户名已存在")
        execute(
            "INSERT INTO admin_users (username,password_hash,phone,wechat,role_id) VALUES (%s,%s,%s,%s,2)",
            (username,sha256(password),phone,wechat))
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/request-permission", methods=["GET","POST"])
@login_required
def request_permission():
    """申请权限页面"""
    if request.method == "POST":
        data = request.json
        execute(
            "INSERT INTO permission_requests (user_id,username,requested_permissions,reason) VALUES (%s,%s,%s,%s)",
            (session["user"]["id"], session["user"]["username"],
             json.dumps(data.get("permissions",[])), data.get("reason","")))
        return jsonify({"success":True})
    # 可申请的权限列表
    all_perms = list(PAGE_PERMISSION_MAP.keys())
    current = get_user_permissions()
    available = [{"key":k,"name":v} for k,v in PAGE_PERMISSION_MAP.items() if k not in current]
    return render_template("request_permission.html", available=available, current=current)

@app.route("/members")
@login_required
def member_manage():
    """成员管理（仅超级管理员）"""
    perms = get_user_permissions()
    if "member_manage" not in perms and "approval_manage" not in perms:
        return render_template("permission_denied.html", page_name="成员管理", perm_key="member_manage")
    users = query("SELECT u.*, r.name as role_name FROM admin_users u LEFT JOIN user_roles r ON u.role_id=r.id ORDER BY u.id")
    roles = query("SELECT * FROM user_roles")
    return render_template("members.html",
        users=users.to_dict("records") if not users.empty else [],
        roles=roles.to_dict("records") if not roles.empty else [])

@app.route("/api/members/update_role", methods=["POST"])
@login_required
def update_user_role():
    data = request.json
    execute("UPDATE admin_users SET role_id=%s WHERE id=%s",(data["role_id"],data["user_id"]))
    return jsonify({"success":True})

@app.route("/approvals")
@login_required
def approval_page():
    """权限审批页"""
    perms = get_user_permissions()
    if "approval_manage" not in perms and "member_manage" not in perms:
        return render_template("permission_denied.html", page_name="权限审批", perm_key="approval_manage")
    requests_list = query("SELECT * FROM permission_requests ORDER BY FIELD(status,'pending','approved','rejected'), id DESC")
    records = requests_list.to_dict("records") if not requests_list.empty else []
    # 预处理权限列表为可读标签
    for r in records:
        try:
            perms = json.loads(r["requested_permissions"])
            r["perm_labels"] = [PAGE_PERMISSION_MAP.get(p, p) for p in perms]
        except:
            r["perm_labels"] = [str(r.get("requested_permissions",""))]
    return render_template("approvals.html", requests_list=records)

@app.route("/api/approvals/review", methods=["POST"])
@login_required
def review_permission():
    data = request.json
    execute("UPDATE permission_requests SET status=%s,reviewed_by=%s,review_comment=%s,review_time=NOW() WHERE id=%s",
        (data["status"],session["user"]["username"],data.get("comment",""),data["request_id"]))
    if data["status"] == "approved":
        # 将申请的权限合并到用户角色
        req_df = query("SELECT user_id, requested_permissions FROM permission_requests WHERE id=%s",(data["request_id"],))
        if not req_df.empty:
            new_perms = json.loads(req_df["requested_permissions"].iloc[0])
            user_id = int(req_df["user_id"].iloc[0])
            user_df = query("SELECT role_id FROM admin_users WHERE id=%s",(user_id,))
            if not user_df.empty:
                role_id = int(user_df["role_id"].iloc[0])
                role_df = query("SELECT permissions FROM user_roles WHERE id=%s",(role_id,))
                if not role_df.empty:
                    existing = json.loads(role_df["permissions"].iloc[0])
                    merged = list(set(existing + new_perms))
                    execute("UPDATE user_roles SET permissions=%s WHERE id=%s",(json.dumps(merged),role_id))
    return jsonify({"success":True})



# ============================================================
# 11. 智能运维中心 (3 Skills + 1 Agent)
# ============================================================

@app.route("/ops")
@login_required
def ops_center():
    return render_template("ops_center.html")

# --- Skill 1: rpa-health-scanner ---

@app.route("/api/ops/agent/chat", methods=["POST"])
@login_required
def ops_agent_chat():
    """RPAOps-Agent 对话接口"""
    msg = request.json.get("message","")
    try:
        from Skill.rpa_ops_agent.main import create_agent
        agent = create_agent(query, api_key=cfg.alert.deepseek_api_key)
        result = agent.run(msg)
        return jsonify(result)
    except Exception as e:
        return jsonify({"intent":None,"data":{},"reply":f"Agent异常: {str(e)[:100]}"})

@app.route("/api/ops/health_scan")
@login_required
def ops_health_scan():
    """流程健康度巡检: 一键扫描生成红黄绿灯评分"""
    from Skill.rpa_health_scanner.main import scan
    return jsonify(scan(query))

# --- Skill 2: rpa-task-summary ---
@app.route("/api/ops/task_summary")
@login_required
def ops_task_summary():
    """任务执行日报"""
    raw = []
    try:
        df = query("SELECT task_status, COUNT(*) c FROM task_queue WHERE DATE(create_time)=CURDATE() GROUP BY task_status")
        for _,r in df.iterrows(): raw.append(f"{r['task_status']}: {r['c']}个")
        df2 = query("SELECT COUNT(*) c FROM task_record WHERE DATE(create_time)=CURDATE()")
        raw.append(f"店铺采集记录: {int(df2['c'].iloc[0])}条")
        df3 = query("SELECT COUNT(DISTINCT shop_name) c FROM task_record WHERE DATE(create_time)=CURDATE() AND collect_result='SUCCESS'")
        raw.append(f"成功采集店铺: {int(df3['c'].iloc[0])}个")
        raw_text = '; '.join(raw)
        # AI润色
        try:
            import requests
            resp = requests.post("https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization":"Bearer " + cfg.alert.deepseek_api_key + "","Content-Type":"application/json"},
                json={"model":"deepseek-chat","messages":[{"role":"user","content":f"根据以下数据生成一段50字内的RPA任务执行日报: {raw_text}"}],"max_tokens":200},timeout=8)
            if resp.status_code==200: raw_text = resp.json()["choices"][0]["message"]["content"]
        except: pass
        return jsonify({"summary":raw_text,"details":raw})
    except Exception as e:
        return jsonify({"summary":f"生成失败:{e}","details":[]})

# --- Skill 3: rpa-diagnose ---
@app.route("/api/ops/diagnose", methods=["POST"])
@login_required
def ops_diagnose():
    """智能诊断"""
    data = request.json; issue = data.get("issue",""); etype = data.get("type","")
    result = {"root_cause":"","suggestion":"","impact":"","confidence":0}
    try:
        # 聚合上下文
        ctx_parts = []
        if etype:
            df = query("SELECT COUNT(*) c FROM rpa_exception_log WHERE exception_type=%s AND create_time>=DATE_SUB(NOW(),INTERVAL 7 DAY)",(etype,))
            ctx_parts.append(f"近7天同类异常: {int(df['c'].iloc[0])}次")
        df2 = query("SELECT task_status, COUNT(*) c FROM task_queue WHERE DATE(create_time)=CURDATE() GROUP BY task_status")
        ctx_parts.append("今日任务: " + ", ".join([f"{r['task_status']}{int(r['c'])}" for _,r in df2.iterrows()]))
        ctx = '; '.join(ctx_parts)
        # AI诊断
        import requests
        resp = requests.post("https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization":"Bearer " + cfg.alert.deepseek_api_key + "","Content-Type":"application/json"},
            json={"model":"deepseek-chat","messages":[{"role":"user","content":"你是RPA运维专家。问题:"+issue+"。上下文:"+ctx+"。请用JSON返回: {root_cause,suggestion,impact,confidence}"}],"max_tokens":400},timeout=10)
        if resp.status_code==200:
            content = resp.json()["choices"][0]["message"]["content"].replace("","").strip()
            result.update(json.loads(content))
    except Exception as e:
        result["root_cause"]=f"诊断异常: {e}"
    return jsonify(result)


if __name__ == "__main__":
    print("=" * 50)
    print("  RPA Admin 管理平台")
    print(f"  访问: http://localhost:5000")
    print(f"  账号: admin / YOUR_ADMIN_PASSWORD")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
