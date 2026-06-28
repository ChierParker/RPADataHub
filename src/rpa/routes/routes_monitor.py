"""
SQL巡检 + 采集图表路由
======================
从 blueprint.py 拆分
"""

from flask import render_template, request, jsonify


def register(bp, query, execute, login_required, permission_required, get_user_permissions):
    """注册监控相关路由"""

    @bp.route("/monitor")
    @login_required
    def monitor():
        table_list = query("""
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA='data'
              AND (TABLE_NAME LIKE 'ods_%' OR TABLE_NAME LIKE 'dw_%')
            ORDER BY TABLE_NAME
        """)
        tables = table_list["TABLE_NAME"].tolist() if not table_list.empty else []
        return render_template("monitor.html", tables=tables)

    @bp.route("/monitor/dashboard")
    @login_required
    def monitor_dashboard():
        table_list = query("""
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA='data'
              AND (TABLE_NAME LIKE 'ods_%' OR TABLE_NAME LIKE 'dw_%')
            ORDER BY TABLE_NAME
        """)
        tables = table_list["TABLE_NAME"].tolist() if not table_list.empty else []
        return render_template("monitor_dashboard.html", tables=tables)

    @bp.route("/api/monitor/chart_data")
    @login_required
    def monitor_chart_data():
        table = request.args.get("table", "")
        days = request.args.get("days", "7", type=int)

        # 表名白名单校验
        allowed = query("""
            SELECT TABLE_NAME FROM information_schema.TABLES
            WHERE TABLE_SCHEMA='data'
        """)
        allowed_set = set(allowed["TABLE_NAME"].tolist()) if not allowed.empty else set()
        if table not in allowed_set:
            return jsonify({"error": "非法表名"}), 400

        data = query(f"""
            SELECT DATE(create_time) dt, COUNT(*) cnt
            FROM `{table}`
            WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)
            GROUP BY DATE(create_time)
            ORDER BY dt
        """)

        labels, values = [], []
        if not data.empty:
            for _, r in data.iterrows():
                dt = r["dt"]
                labels.append(dt.strftime("%m-%d") if hasattr(dt, "strftime") else str(dt))
                values.append(int(r["cnt"]))

        return jsonify({"labels": labels, "values": values})
