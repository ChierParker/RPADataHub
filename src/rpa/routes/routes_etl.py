"""
ETL执行记录 + 健康检查路由
==========================
从 blueprint.py 拆分 (原行号 ~140-350)
"""

import json
from datetime import datetime, timedelta
from flask import render_template, request, jsonify
import pandas as pd


def register(bp, query, execute, login_required, permission_required, get_user_permissions):
    """注册 ETL 相关路由"""

    # ============================================================
    # 1. ETL 执行记录仪表盘
    # ============================================================

    @bp.route("/dashboard")
    @login_required
    def dashboard():
        # 统计
        stats = query("""
            SELECT status, COUNT(*) cnt
            FROM etl_process_log
            WHERE start_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY status
        """)
        stats_dict = {"SUCCESS": 0, "FAILED": 0}
        if not stats.empty:
            for _, r in stats.iterrows():
                stats_dict[r["status"]] = int(r["cnt"])

        total = query("SELECT COUNT(*) c FROM etl_process_log")
        total = int(total["c"].iloc[0]) if not total.empty else 0

        # 列表（分页）
        page = request.args.get("page", 1, type=int)
        status_filter = request.args.get("status", "")
        status_cond = f"AND status='{status_filter}'" if status_filter else ""
        per_page = 20
        offset = (page - 1) * per_page

        records = query(f"""
            SELECT trace_id, file_name, ods_table, dw_table, status,
                   row_count, dirty_count, error_msg, start_time, end_time
            FROM etl_process_log
            WHERE 1=1 {status_cond}
            ORDER BY start_time DESC
            LIMIT {per_page} OFFSET {offset}
        """)
        records_list = []
        if not records.empty:
            for _, r in records.iterrows():
                d = r.to_dict()
                for k, v in d.items():
                    if pd.isna(v):
                        d[k] = None
                    elif hasattr(v, "strftime"):
                        d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                records_list.append(d)

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return render_template(
            "dashboard.html",
            stats=stats_dict,
            total=total,
            records=records_list,
            page=page,
            total_pages=total_pages,
            status_filter=status_filter,
        )

    @bp.route("/api/etl_record/<trace_id>")
    @login_required
    def etl_record_detail(trace_id):
        etl = query(
            "SELECT * FROM etl_process_log WHERE trace_id=%s", (trace_id,)
        )
        validations = query(
            "SELECT * FROM rpa_alert_log WHERE trace_id=%s ORDER BY create_time DESC",
            (trace_id,)
        )

        etl_data = None
        if not etl.empty:
            r = etl.iloc[0].to_dict()
            for k, v in r.items():
                if pd.isna(v):
                    r[k] = None
                elif hasattr(v, "strftime"):
                    r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
            etl_data = r

        val_list = []
        if not validations.empty:
            for _, v in validations.iterrows():
                d = v.to_dict()
                for k, val in d.items():
                    if pd.isna(val):
                        d[k] = None
                    elif hasattr(val, "strftime"):
                        d[k] = val.strftime("%Y-%m-%d %H:%M:%S")
                val_list.append(d)

        return jsonify({"etl": etl_data, "validations": val_list})

    @bp.route("/health")
    @login_required
    def health_page():
        today = datetime.now().strftime("%Y-%m-%d")
        task_stats = query(f"""
            SELECT COUNT(*) t,
                   SUM(CASE WHEN task_status='SUCCESS' THEN 1 ELSE 0 END) s,
                   SUM(CASE WHEN task_status='FAILED' THEN 1 ELSE 0 END) f
            FROM task_queue
            WHERE DATE(create_time)='{today}'
        """)
        collect = query("""
            SELECT
                (SELECT COUNT(*) FROM ods_order_raw WHERE DATE(create_time)=CURDATE()) +
                (SELECT COUNT(*) FROM ods_sales_raw WHERE DATE(create_time)=CURDATE()) +
                (SELECT COUNT(*) FROM ods_agreement_raw WHERE DATE(crawl_time)=CURDATE()) as total
        """)
        dirty = query("SELECT COUNT(*) c FROM rpa_dirty_data_log WHERE DATE(detect_time)=CURDATE()")
        exceptions = query(f"SELECT COUNT(*) c FROM rpa_exception_log WHERE DATE(create_time)='{today}'")
        etl = query("""
            SELECT ROUND(SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END)/COUNT(*)*100,1) r
            FROM etl_process_log
            WHERE start_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        """)

        return render_template(
            "health_dashboard.html",
            task_success=int(task_stats["s"].iloc[0]) if not task_stats.empty else 0,
            task_failed=int(task_stats["f"].iloc[0]) if not task_stats.empty else 0,
            today_collect=int(collect["total"].iloc[0]) if not collect.empty else 0,
            today_dirty=int(dirty["c"].iloc[0]) if not dirty.empty else 0,
            today_exceptions=int(exceptions["c"].iloc[0]) if not exceptions.empty else 0,
            etl_rate=round(float(etl["r"].iloc[0]), 1) if not etl.empty and not pd.isna(etl["r"].iloc[0]) else 0,
        )
