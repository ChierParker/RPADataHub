"""
RPADataHub 共享工具模块
======================
提供 admin_server.py 和 blueprint.py 共用的：
- 数据库连接池（DBUtils PooledDB）
- SQL 查询/执行工具
- 权限管理（RBAC）
- API 响应信封
- 通用工具函数

消除代码重复，统一入口。
"""

import hashlib
import json
import os
import threading
from datetime import datetime
from functools import wraps
from typing import Optional, Any

import pandas as pd
import pymysql
from flask import session, redirect, url_for, render_template, jsonify, request

# ============================================================
# 数据库连接池（替代 threading.local()）
# ============================================================

class DatabasePool:
    """基于 DBUtils 的数据库连接池

    如果 DBUtils 不可用，降级为 threading.local() 单连接复用。
    """

    def __init__(self, db_config: dict):
        self._config = db_config
        self._use_pool = False
        self._pool = None

        try:
            from dbutils.pooled_db import PooledDB
            self._pool = PooledDB(
                creator=pymysql,
                maxconnections=10,
                mincached=2,
                maxcached=5,
                blocking=True,
                ping=1,
                **db_config,
            )
            self._use_pool = True
        except ImportError:
            self._local = threading.local()

    def get_conn(self) -> pymysql.Connection:
        """获取数据库连接"""
        if self._use_pool:
            return self._pool.connection()
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = pymysql.connect(**self._config)
        try:
            self._local.conn.ping(reconnect=True)
        except Exception:
            self._local.conn = pymysql.connect(**self._config)
        return self._local.conn

    def query(self, sql: str, params=None) -> pd.DataFrame:
        """执行 SELECT 查询，返回 DataFrame"""
        conn = self.get_conn()
        return pd.read_sql(sql, conn, params=params)

    def execute(self, sql: str, params=None):
        """执行 INSERT/UPDATE/DELETE"""
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()



# ============================================================
# 通用工具函数
# ============================================================

def sha256(s: str) -> str:
    """SHA256 哈希（用于旧版密码兼容）"""
    return hashlib.sha256(s.encode()).hexdigest()


def clean_json_records(records: list) -> list:
    """清理 DataFrame records 中的 NaN/NaT，确保可 JSON 序列化"""
    for r in records:
        for k in list(r.keys()):
            v = r[k]
            if hasattr(v, "strftime") and not pd.isna(v):
                r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
            elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                r[k] = None
    return records


def parse_int_arg(key: str, default: int = 0, min_val: int = 0, max_val: int = 999999) -> int:
    """安全解析整数参数"""
    try:
        val = int(request.args.get(key, default))
        return max(min_val, min(max_val, val))
    except (ValueError, TypeError):
        return default


# ============================================================
# API 响应信封（统一格式）
# ============================================================

def api_ok(data: Any = None, message: str = "", status_code: int = 200):
    """统一成功响应: {success:true, data, error:"", message}"""
    return jsonify({
        "success": True,
        "data": data,
        "error": "",
        "message": message,
    }), status_code


def api_fail(error: str = "", data: Any = None, status_code: int = 400):
    """统一失败响应: {success:false, data, error, message:""}"""
    return jsonify({
        "success": False,
        "data": data,
        "error": error,
        "message": "",
    }), status_code


# ============================================================
# 权限管理（RBAC）
# ============================================================

PAGE_PERMISSION_MAP = {
    "dashboard": "ETL执行记录",
    "monitor": "SQL巡检",
    "monitor_dashboard": "采集图表",
    "health_dashboard": "健康总览",
    "tasks_page": "任务管理",
    "collection_monitor": "任务监控",
    "collection_records_page": "执行明细",
    "collection_health": "店铺健康",
    "bi_dashboard": "BI经营分析",
    "business_dashboard": "经营看板",
    "shops_page": "店铺管理",
    "routes_page": "路由配置",
    "ai_assistant_page": "AI助手",
    "ops_center": "AI运营中心",
    "approval_page": "权限审批",
    "member_manage": "成员管理",
}


class PermissionManager:
    """RBAC 权限管理器"""

    def __init__(self, db: DatabasePool):
        self.db = db

    def get_user_permissions(self) -> list:
        """获取当前用户权限列表"""
        if "user" not in session:
            return []
        role_id = session["user"].get("role_id", 2)
        try:
            df = self.db.query(
                "SELECT permissions FROM user_roles WHERE id=%s",
                (role_id,)
            )
            if not df.empty:
                return json.loads(df["permissions"].iloc[0])
        except Exception:
            pass
        return []

    def login_required(self, f):
        """登录鉴权装饰器"""
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated

    def permission_required(self, perm_key: str):
        """权限装饰器：无权限时跳转提示页"""
        def decorator(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                if "user" not in session:
                    return redirect(url_for("login"))
                perms = self.get_user_permissions()
                if "approval_manage" in perms or "member_manage" in perms or perm_key in perms:
                    return f(*args, **kwargs)
                return render_template(
                    "permission_denied.html",
                    page_name=PAGE_PERMISSION_MAP.get(perm_key, perm_key),
                    perm_key=perm_key,
                )
            return decorated
        return decorator

    def inject_permissions(self):
        """模板上下文注入（用于 sidebar 权限控制）"""
        perms = self.get_user_permissions() if "user" in session else []
        return {"user_permissions": perms, "page_map": PAGE_PERMISSION_MAP}


# ============================================================
# 便捷工厂函数
# ============================================================

def create_shared_components(db_config: dict = None):
    """创建共享组件实例

    Returns:
        (DatabasePool, PermissionManager)
    """
    if db_config is None:
        from config.settings import get_config
        db_config = get_config().database.as_dict()

    db = DatabasePool(db_config)
    perm = PermissionManager(db)
    return db, perm
