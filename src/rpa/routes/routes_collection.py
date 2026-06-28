"""
采集监控 / 执行明细 / 店铺健康路由
=================================
从 blueprint.py 拆分
"""

from flask import render_template, request, jsonify
import pandas as pd


def register(bp, query, execute, login_required, permission_required, get_user_permissions):
    """注册采集相关路由"""

    @bp.route("/collection/monitor")
    @login_required
    def collection_monitor():
        today_stats = query("""
            SELECT
                COUNT(*) total,
                SUM(CASE WHEN task_status='SUCCESS' THEN 1 ELSE 0 END) success,
                SUM(CASE WHEN task_status='FAILED' THEN 1 ELSE 0 END) failed,
                SUM(CASE WHEN task_status='RUNNING' THEN 1 ELSE 0 END) running
            FROM task_queue
            WHERE DATE(create_time)=CURDATE()
        """)
        stats = {"total": 0, "success": 0, "failed": 0, "running": 0}
        if not today_stats.empty:
            r = today_stats.iloc[0]
            stats = {k: int(r[k]) if not pd.isna(r[k]) else 0
                     for k in ["total", "success", "failed", "running"]}

        return render_template("collection_monitor.html", stats=stats)

    @bp.route("/api/collection/summary")
    @login_required
    def collection_summary():
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 15, type=int)
        per_page = min(per_page, 100)
        offset = (page - 1) * per_page

        count = query("SELECT COUNT(*) c FROM task_queue")
        total = int(count["c"].iloc[0]) if not count.empty else 0

        recs = query(f"""
            SELECT task_uuid, script_name, task_status, start_time,
                   duration_sec, error_message
            FROM task_queue
            ORDER BY create_time DESC
            LIMIT {per_page} OFFSET {offset}
        """)

        records = []
        if not recs.empty:
            for _, r in recs.iterrows():
                d = r.to_dict()
                for k, v in d.items():
                    if hasattr(v, "strftime") and not pd.isna(v):
                        d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                    elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                        d[k] = None
                d["success_shops"] = 0
                d["failed_shops"] = 0
                d["success_rate"] = 0
                records.append(d)

        return jsonify({"records": records, "total": total, "page": page, "per_page": per_page})

    @bp.route("/collection/records")
    @login_required
    def collection_records_page():
        return render_template("collection_records.html")

    @bp.route("/api/collection/records")
    @login_required
    def collection_records():
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        per_page = min(per_page, 100)
        offset = (page - 1) * per_page

        task_uuid = request.args.get("task_uuid", "")
        shop = request.args.get("shop", "")
        date = request.args.get("date", "")

        conds = []
        params = []
        if task_uuid:
            conds.append("task_uuid=%s")
            params.append(task_uuid)
        if shop:
            conds.append("shop_name LIKE %s")
            params.append(f"%{shop}%")
        if date:
            conds.append("DATE(create_time)=%s")
            params.append(date)

        where = ("WHERE " + " AND ".join(conds)) if conds else ""

        count = query(f"SELECT COUNT(*) c FROM task_record {where}", tuple(params))
        total = int(count["c"].iloc[0]) if not count.empty else 0

        recs = query(f"""
            SELECT * FROM task_record {where}
            ORDER BY create_time DESC
            LIMIT {per_page} OFFSET {offset}
        """, tuple(params))

        records = []
        if not recs.empty:
            for _, r in recs.iterrows():
                d = r.to_dict()
                for k, v in d.items():
                    if hasattr(v, "strftime") and not pd.isna(v):
                        d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                    elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                        d[k] = None
                records.append(d)

        return jsonify({"records": records, "total": total, "page": page, "per_page": per_page})

    @bp.route("/collection/health")
    @login_required
    def collection_health():
        shops_df = query("SELECT DISTINCT shop_name FROM dim_shop_info WHERE status=1 ORDER BY shop_name")
        shops = shops_df["shop_name"].tolist() if not shops_df.empty else []
        return render_template("collection_health.html", shops=shops)

    @bp.route("/api/collection/health")
    @login_required
    def collection_health_data():
        shop = request.args.get("shop", "")
        cond = ""
        ps = []
        if shop:
            cond = "AND shop_name=%s"
            ps = [shop]
        df = query(f"""
            SELECT shop_name, DATE(create_time) dt, collect_result, COUNT(*) cnt
            FROM task_record
            WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) {cond}
            GROUP BY shop_name, DATE(create_time), collect_result
            ORDER BY shop_name, dt
        """, ps)
        records = df.to_dict("records") if not df.empty else []
        for r in records:
            if hasattr(r["dt"], "strftime"):
                r["dt"] = r["dt"].strftime("%Y-%m-%d")
        return jsonify({"records": records})

