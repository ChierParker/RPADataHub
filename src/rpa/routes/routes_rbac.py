"""
RBAC 路由：成员管理 + 权限审批
=============================
从 blueprint.py 拆分
"""

from flask import render_template, request, jsonify
import pandas as pd


def register(bp, query, execute, login_required, permission_required, get_user_permissions):
    """注册 RBAC 相关路由"""

    @bp.route("/members")
    @login_required
    def member_manage():
        users = query("""
            SELECT u.id, u.username, u.role, u.role_id, COALESCE(r.name,'观察者') role_name, u.is_active, u.create_time
            FROM admin_users u LEFT JOIN user_roles r ON u.role_id=r.id ORDER BY u.id
        """)
        roles = query("SELECT * FROM user_roles ORDER BY id")

        users_list = _df_clean(users)
        roles_list = _df_clean(roles)

        return render_template("members.html", users=users_list, roles=roles_list)

    @bp.route("/api/members/update_role", methods=["POST"])
    @login_required
    def update_user_role():
        data = request.get_json() or {}
        user_id = data.get("user_id")
        role_id = data.get("role_id")
        if not user_id or role_id is None:
            return jsonify({"success": False, "error": "参数缺失"})
        execute("UPDATE admin_users SET role_id=%s WHERE id=%s", (int(role_id), user_id))
        return jsonify({"success": True})

    @bp.route("/approvals")
    @login_required
    def approval_page():
        reqs = query("SELECT * FROM permission_requests ORDER BY create_time DESC")
        requests_list = []
        if not reqs.empty:
            for _, r in reqs.iterrows():
                d = r.to_dict()
                for k, v in d.items():
                    if hasattr(v, "strftime") and not pd.isna(v):
                        d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                    elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                        d[k] = None
                requests_list.append(d)
        return render_template("approvals.html", requests_list=requests_list)

    @bp.route("/api/approvals/review", methods=["POST"])
    @login_required
    def review_permission():
        data = request.get_json() or {}
        request_id = data.get("request_id")
        status = data.get("status")
        comment = data.get("comment", "")
        if not request_id or status not in ("approved", "rejected"):
            return jsonify({"success": False, "error": "参数错误"})

        if status == "approved":
            req = query("SELECT * FROM permission_requests WHERE id=%s", (request_id,))
            if not req.empty:
                r = req.iloc[0]
                perms = get_user_permissions()
                # 将申请的权限添加到用户角色
                requested = r.get("requested_permission", "")
                if requested and requested not in str(perms):
                    execute("""
                        UPDATE user_roles SET permissions = JSON_ARRAY_APPEND(permissions, '$', %s)
                        WHERE id = (SELECT role_id FROM admin_users WHERE id=%s)
                    """, (requested, int(r.get("user_id", 0))))

        execute("UPDATE permission_requests SET status=%s, review_comment=%s, review_time=NOW() WHERE id=%s",
                (status, comment, request_id))
        return jsonify({"success": True})


def _df_clean(df):
    """DataFrame clean helper"""
    recs = []
    if not df.empty:
        for _, r in df.iterrows():
            d = r.to_dict()
            for k, v in d.items():
                if hasattr(v, "strftime") and not pd.isna(v):
                    d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                    d[k] = None
            recs.append(d)
    return recs
