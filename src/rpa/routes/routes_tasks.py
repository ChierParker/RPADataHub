"""
任务管理路由
============
从 blueprint.py 拆分
"""

import hashlib
from datetime import datetime
from flask import render_template, request, jsonify


def register(bp, query, execute, login_required, permission_required, get_user_permissions):
    """注册任务管理相关路由"""

    @bp.route("/tasks")
    @login_required
    def tasks_page():
        configs = query("SELECT * FROM task_config ORDER BY id DESC")
        config_list = []
        if not configs.empty:
            for _, r in configs.iterrows():
                d = r.to_dict()
                for k, v in d.items():
                    if hasattr(v, "strftime") and not pd.isna(v):
                        d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                    elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                        d[k] = None
                config_list.append(d)

        return render_template("tasks.html", configs=config_list)

    @bp.route("/api/tasks/queue")
    @login_required
    def tasks_queue():
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 15, type=int)
        per_page = min(per_page, 100)
        offset = (page - 1) * per_page

        count = query("SELECT COUNT(*) c FROM task_queue")
        total = int(count["c"].iloc[0]) if not count.empty else 0

        recs = query(f"""
            SELECT * FROM task_queue
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
                records.append(d)

        return jsonify({"records": records, "total": total, "page": page, "per_page": per_page})

    @bp.route("/api/tasks/config", methods=["GET", "POST"])
    @login_required
    def tasks_config():
        if request.method == "POST":
            data = request.get_json() or {}
            tid = data.get("id")
            if tid:
                execute("""
                    UPDATE task_config SET
                        task_name=%s, script_name=%s, platform=%s, shop_name=%s,
                        schedule_type=%s, cron_expression=%s, timeout_sec=%s,
                        priority=%s, country=%s, business_date=%s
                    WHERE id=%s
                """, (
                    data.get("task_name"), data.get("script_name"),
                    data.get("platform", ""), data.get("shop_name", ""),
                    data.get("schedule_type", "now"), data.get("cron_expression", ""),
                    data.get("timeout_sec", 3600), data.get("priority", 1),
                    data.get("country", ""), data.get("business_date", ""),
                    tid,
                ))
            else:
                execute("""
                    INSERT INTO task_config
                        (task_name, script_name, platform, shop_name,
                         schedule_type, cron_expression, timeout_sec, priority,
                         country, business_date, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
                """, (
                    data.get("task_name"), data.get("script_name"),
                    data.get("platform", ""), data.get("shop_name", ""),
                    data.get("schedule_type", "now"), data.get("cron_expression", ""),
                    data.get("timeout_sec", 3600), data.get("priority", 1),
                    data.get("country", ""), data.get("business_date", ""),
                ))
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "仅支持 POST"})

    @bp.route("/api/tasks/config/<int:cfg_id>", methods=["DELETE"])
    @login_required
    def tasks_config_delete(cfg_id):
        execute("DELETE FROM task_config WHERE id=%s", (cfg_id,))
        return jsonify({"success": True})

    @bp.route("/api/tasks/run/<int:cfg_id>", methods=["POST"])
    @login_required
    def tasks_run(cfg_id):
        cfg = query("SELECT * FROM task_config WHERE id=%s", (cfg_id,))
        if cfg.empty:
            return jsonify({"error": "任务不存在"}), 404
        c = cfg.iloc[0]

        task_uuid = hashlib.md5(f"{cfg_id}{datetime.now()}".encode()).hexdigest()[:16]
        execute("""
            INSERT INTO task_queue (task_uuid, script_name, config_id, task_status, create_time)
            VALUES (%s, %s, %s, 'PENDING', NOW())
        """, (task_uuid, str(c["script_name"]), cfg_id))

        return jsonify({"success": True, "task_uuid": task_uuid})


import pandas as pd
