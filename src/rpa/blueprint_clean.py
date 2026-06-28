"""
RPADataHub Flask Blueprint (Clean v1.3)
========================================
修复 BuildError: 语法错误导致路由未注册。
"""

import hashlib, io, json, os, sys, threading
from datetime import datetime
from functools import wraps

import pandas as pd
import pymysql
from flask import Blueprint, render_template, request, session, jsonify, send_file, redirect, url_for


def create_rpa_data_hub_blueprint() -> Blueprint:
    bp = Blueprint("rpa_data_hub", __name__, template_folder="templates", static_folder="static")

    _module_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _module_dir)
    from config.settings import get_config
    cfg = get_config()

    # ============================================================
    # 数据库工具
    # ============================================================
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
        return pd.read_sql(sql, get_db(), params=params)

    def execute(sql, params=None):
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()

    def sha256(s):
        return hashlib.sha256(s.encode()).hexdigest()

    def clean_json_records(records):
        for r in records:
            for k in list(r.keys()):
                v = r[k]
                if hasattr(v, "strftime") and not pd.isna(v):
                    r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                    r[k] = None
        return records

    # ============================================================
    # 权限映射
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
        if "user" not in session: return []
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
                return redirect("/login")
            return f(*args, **kwargs)
        return decorated

    def permission_required(perm_key):
        def decorator(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                if "user" not in session: return redirect("/login")
                perms = get_user_permissions()
                if "approval_manage" in perms or "member_manage" in perms or perm_key in perms:
                    return f(*args, **kwargs)
                return render_template("permission_denied.html",
                    page_name=PAGE_PERMISSION_MAP.get(perm_key, perm_key), perm_key=perm_key)
            return decorated
        return decorator

    @bp.context_processor
    def inject_permissions():
        perms = get_user_permissions() if "user" in session else []
        return {"user_permissions": perms, "page_map": PAGE_PERMISSION_MAP}

    # ============================================================
    # 路由（可切换到 routes/ 包：from routes import register_all）
    # ============================================================
