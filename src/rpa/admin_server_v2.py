"""
RPA Admin 独立服务器 v2.0
==========================
路由逻辑已拆分至 routes/ 包，本文件仅负责 Flask 启动 + 登录鉴权。
启动: python admin_server_v2.py  访问: http://localhost:5000
"""
import os, sys, json
from datetime import datetime
from functools import wraps

import pymysql, pandas as pd
from flask import Flask, Blueprint, render_template, request, redirect, url_for, session, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.settings import get_config

app = Flask(__name__)
app.secret_key = os.environ.get("RPA_FLASK_SECRET_KEY", os.urandom(24).hex()).encode()
cfg = get_config()

# ============================================================
# 共享组件 — 全部来自 core/shared.py + routes/
# ============================================================
from core.shared import (
    DatabasePool, PermissionManager, clean_json_records, sha256,
    api_ok, api_fail, PAGE_PERMISSION_MAP, parse_int_arg
)

db = DatabasePool(cfg.database.as_dict())
perm = PermissionManager(db)

query, execute = db.query, db.execute
login_required = perm.login_required
permission_required = perm.permission_required
get_user_permissions = perm.get_user_permissions

# ============================================================
# 路由注册 — 全部来自 routes/ 包
# ============================================================
admin_bp = Blueprint("admin", __name__, template_folder="templates", static_folder="static")

from routes import register_all
register_all(admin_bp, query, execute, login_required, permission_required, get_user_permissions)

app.register_blueprint(admin_bp)

# ============================================================
# 独立模式专属：登录 / 登出（main/app.py 已处理登录时不需要）
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        df = query(
            "SELECT u.id, u.username, u.role, COALESCE(u.role_id,2) as role_id, "
            "COALESCE(r.name,'观察者') as role_name FROM admin_users u "
            "LEFT JOIN user_roles r ON u.role_id=r.id "
            "WHERE u.username=%s AND u.password_hash=%s AND u.is_active=1",
            params=(username, sha256(password))
        )
        if not df.empty:
            row = df.iloc[0].to_dict()
            for k, v in list(row.items()):
                if pd.isna(v): row[k] = ""
            session["user"] = row
            session.permanent = True
            return redirect(url_for("admin.home"))
        error = "账号或密码错误"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.context_processor
def inject_permissions():
    perms = get_user_permissions() if "user" in session else []
    return {"user_permissions": perms, "page_map": PAGE_PERMISSION_MAP}

# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    print(f"RPA Admin v2.0 启动 → http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
