"""
店铺管理 / 路由配置 / API采集路由
================================
从 blueprint.py 拆分
"""

import io
from flask import render_template, request, jsonify, send_file
import pandas as pd


def register(bp, query, execute, login_required, permission_required, get_user_permissions):
    """注册店铺/路由相关路由"""

    # ============================================================
    # 店铺管理
    # ============================================================

    @bp.route("/shops")
    @login_required
    def shops_page():
        return render_template("shops.html")

    @bp.route("/api/shops/data")
    @login_required
    def shops_data():
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 15, type=int)
        per_page = min(per_page, 100)
        offset = (page - 1) * per_page
        search = request.args.get("search", "")
        platform = request.args.get("platform", "")
        status = request.args.get("status", "")
        sort = request.args.get("sort", "shop_id")
        order = request.args.get("order", "asc")

        allowed_sorts = {"shop_id", "shop_name", "platform", "bu", "status", "create_time"}
        if sort not in allowed_sorts:
            sort = "shop_id"
        if order not in ("asc", "desc"):
            order = "asc"

        conds, params = [], []
        if search:
            conds.append("(shop_name LIKE %s OR shop_id LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        if platform:
            conds.append("platform=%s")
            params.append(platform)
        if status:
            conds.append("status=%s")
            params.append(int(status))

        where = ("WHERE " + " AND ".join(conds)) if conds else ""

        count = query(f"SELECT COUNT(*) c FROM dim_shop_info {where}", tuple(params))
        total = int(count["c"].iloc[0]) if not count.empty else 0

        recs = query(f"""
            SELECT * FROM dim_shop_info {where}
            ORDER BY {sort} {order}
            LIMIT {per_page} OFFSET {offset}
        """, tuple(params))

        records = _df_to_records(recs)

        plats = query("SELECT DISTINCT platform FROM dim_shop_info WHERE platform IS NOT NULL AND platform!='' ORDER BY platform")
        platforms = plats["platform"].tolist() if not plats.empty else []

        return jsonify({"records": records, "total": total, "page": page, "per_page": per_page, "platforms": platforms})

    @bp.route("/api/shops/save", methods=["POST"])
    @login_required
    def shops_save():
        data = request.get_json() or {}
        shop_id = data.get("shop_id", "")
        shop_name = data.get("shop_name", "")
        if not shop_id or not shop_name:
            return jsonify({"success": False, "error": "店铺ID和名称不能为空"})

        existing = query("SELECT 1 FROM dim_shop_info WHERE shop_id=%s", (shop_id,))
        if existing.empty:
            execute("""
                INSERT INTO dim_shop_info (shop_id, shop_name, platform, bu, email, status)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (shop_id, shop_name, data.get("platform",""), data.get("bu",""), data.get("email",""), data.get("status",1)))
        else:
            execute("""
                UPDATE dim_shop_info SET shop_name=%s, platform=%s, bu=%s, email=%s, status=%s WHERE shop_id=%s
            """, (shop_name, data.get("platform",""), data.get("bu",""), data.get("email",""), data.get("status",1), shop_id))
        return jsonify({"success": True})

    @bp.route("/api/shops/export")
    @login_required
    def shops_export():
        search = request.args.get("search", "")
        platform = request.args.get("platform", "")
        status = request.args.get("status", "")

        conds, params = [], []
        if search:
            conds.append("(shop_name LIKE %s OR shop_id LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        if platform:
            conds.append("platform=%s"); params.append(platform)
        if status:
            conds.append("status=%s"); params.append(int(status))

        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        df = query(f"SELECT * FROM dim_shop_info {where} ORDER BY shop_id", tuple(params))

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="店铺列表")
        output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        as_attachment=True, download_name="shops.xlsx")



    # ============================================================
    # 路由配置
    # ============================================================

    @bp.route("/routes")
    @login_required
    def routes_page():
        recs = query("SELECT * FROM file_route_config ORDER BY id")
        routes_list = []
        if not recs.empty:
            for _, r in recs.iterrows():
                d = r.to_dict()
                for k, v in d.items():
                    if pd.isna(v) if hasattr(pd, "isna") else (v != v):
                        d[k] = None
                routes_list.append(d)
        return render_template("routes.html", routes=routes_list)

    @bp.route("/api/route/<int:route_id>/data")
    @login_required
    def route_data(route_id):
        r = query("SELECT * FROM file_route_config WHERE id=%s", (route_id,))
        if r.empty:
            return jsonify({"error": "路由不存在"}), 404
        d = r.iloc[0].to_dict()
        for k, v in d.items():
            if pd.isna(v) if hasattr(pd, "isna") else (v != v):
                d[k] = None
        return jsonify(d)

    @bp.route("/api/route", methods=["POST"])
    @login_required
    def route_save():
        data = request.get_json() or {}
        path_pattern = data.get("path_pattern", "")
        ods_table = data.get("target_ods_table", "")
        if not path_pattern or not ods_table:
            return jsonify({"success": False, "error": "路径和ODS表名必填"})

        rid = data.get("id")
        if rid:
            execute("""
                UPDATE file_route_config SET path_pattern=%s, target_ods_table=%s,
                target_dw_table=%s, dw_transform_sql=%s, is_active=%s WHERE id=%s
            """, (path_pattern, ods_table, data.get("target_dw_table",""),
                  data.get("dw_transform_sql",""), data.get("is_active",1), rid))
        else:
            execute("""
                INSERT INTO file_route_config (path_pattern, target_ods_table,
                target_dw_table, dw_transform_sql, is_active) VALUES (%s,%s,%s,%s,%s)
            """, (path_pattern, ods_table, data.get("target_dw_table",""),
                  data.get("dw_transform_sql",""), data.get("is_active",1)))
        return jsonify({"success": True})

    @bp.route("/api/route/<int:route_id>", methods=["DELETE"])
    @login_required
    def route_delete(route_id):
        execute("DELETE FROM file_route_config WHERE id=%s", (route_id,))
        return jsonify({"success": True})


def _df_to_records(df):
    """DataFrame → JSON-serializable list of dicts"""
    records = []
    if not df.empty:
        for _, r in df.iterrows():
            d = r.to_dict()
            for k, v in d.items():
                if hasattr(v, "strftime") and not pd.isna(v):
                    d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                elif pd.isna(v) if hasattr(pd, "isna") else (v != v):
                    d[k] = None
            records.append(d)
    return records
