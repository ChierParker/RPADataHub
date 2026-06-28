"""
BI经营分析 / 经营看板路由
=========================
从 blueprint.py 拆分
"""

import io
from collections import OrderedDict
from flask import render_template, request, jsonify, send_file
import pandas as pd


def register(bp, query, execute, login_required, permission_required, get_user_permissions):
    """注册 BI / 经营看板路由"""

    @bp.route("/bi")
    @login_required
    def bi_dashboard():
        return render_template("bi_dashboard.html")

    @bp.route("/api/bi/overview")
    @login_required
    def bi_overview():
        date_from, date_to, platform = _parse_args(request)
        dc, dv = _date_clause(date_from, date_to)
        pj, pv = _plat_join(platform)

        gmv_df = query(f"SELECT COALESCE(SUM(t.revenue),0) v FROM ods_sales_raw t{pj} WHERE t.sale_date {dc}", pv+dv)
        ad_df = query(f"SELECT COALESCE(SUM(t.spend),0) sp, COALESCE(SUM(t.sales),0) sa FROM ods_advertising_raw t{pj} WHERE t.ad_date {dc}", pv+dv)
        ord_df = query(f"SELECT COUNT(*) c FROM ods_order_raw t{pj} WHERE t.order_date {dc}", pv+dv)
        ref_df = query(f"SELECT COALESCE(SUM(t.units_sold),0) s, COALESCE(SUM(t.refund_qty),0) r FROM ods_sales_raw t{pj} WHERE t.sale_date {dc}", pv+dv)
        fee_df = query(f"SELECT COALESCE(SUM(t.amount),0) v FROM ods_fee_raw t{pj} WHERE t.fee_date {dc}", pv+dv)

        ad_sales = float(ad_df["sa"].iloc[0])
        return jsonify({"kpi": {
            "gmv": round(float(gmv_df["v"].iloc[0]), 2),
            "orders": int(ord_df["c"].iloc[0]),
            "ad_spend": round(float(ad_df["sp"].iloc[0]), 2),
            "acos": round(float(ad_df["sp"].iloc[0]) / ad_sales * 100, 1) if ad_sales > 0 else 0,
            "refund_rate": round(float(ref_df["r"].iloc[0]) / float(ref_df["s"].iloc[0]) * 100, 1) if float(ref_df["s"].iloc[0]) > 0 else 0,
            "fees": round(float(fee_df["v"].iloc[0]), 2),
        }})

    @bp.route("/api/bi/overview/data")
    @login_required
    def bi_overview_data():
        date_from, date_to, platform = _parse_args(request)
        dc, dv = _date_clause(date_from, date_to)
        pj, pv = _plat_join(platform)

        try:
            rev_t = query(f"SELECT t.sale_date d, SUM(t.revenue) v FROM ods_sales_raw t{pj} WHERE t.sale_date {dc} GROUP BY t.sale_date ORDER BY d", pv+dv)
            ad_t = query(f"SELECT t.ad_date d, SUM(t.spend) v FROM ods_advertising_raw t{pj} WHERE t.ad_date {dc} GROUP BY t.ad_date ORDER BY d", pv+dv)
            ord_t = query(f"SELECT t.order_date d, COUNT(*) v FROM ods_order_raw t{pj} WHERE t.order_date {dc} GROUP BY t.order_date ORDER BY d", pv+dv)

            trend_map = OrderedDict()
            for _, r in rev_t.iterrows():
                k = r["d"].strftime("%m-%d") if hasattr(r["d"],"strftime") else str(r["d"])
                trend_map[k] = {"revenue": float(r["v"]), "ad_spend": 0, "orders": 0}
            for _, r in ad_t.iterrows():
                k = r["d"].strftime("%m-%d") if hasattr(r["d"],"strftime") else str(r["d"])
                if k not in trend_map: trend_map[k] = {"revenue": 0, "ad_spend": 0, "orders": 0}
                trend_map[k]["ad_spend"] = float(r["v"])
            for _, r in ord_t.iterrows():
                k = r["d"].strftime("%m-%d") if hasattr(r["d"],"strftime") else str(r["d"])
                if k not in trend_map: trend_map[k] = {"revenue": 0, "ad_spend": 0, "orders": 0}
                trend_map[k]["orders"] = int(r["v"])
            trend = [{"date": k, **v} for k, v in trend_map.items()]

            plat_dist = query(f"SELECT ds.platform, SUM(t.revenue) revenue FROM ods_sales_raw t JOIN dim_shop_info ds ON t.shop_name=ds.shop_name WHERE t.sale_date {dc} GROUP BY ds.platform ORDER BY revenue DESC", dv)
            fee_break = query(f"SELECT t.fee_type, SUM(t.amount) total FROM ods_fee_raw t{pj} WHERE t.fee_date {dc} GROUP BY t.fee_type ORDER BY total DESC", pv+dv)
            top = query(f"SELECT t.asin, t.title, SUM(t.units_sold) units, SUM(t.revenue) revenue FROM ods_sales_raw t{pj} WHERE t.sale_date {dc} GROUP BY t.asin, t.title ORDER BY revenue DESC LIMIT 10", pv+dv)

            return jsonify({
                "trend": trend,
                "platform_dist": [{"platform": r["platform"] or "未知", "revenue": round(float(r["revenue"]),2)} for _,r in plat_dist.iterrows()] if not plat_dist.empty else [],
                "fee_breakdown": [{"fee_type": r["fee_type"] or "其他", "total": round(float(r["total"]),2)} for _,r in fee_break.iterrows()] if not fee_break.empty else [],
                "top_products": [{"title": r["title"] or r["asin"], "asin": r["asin"], "units": int(r["units"]), "revenue": round(float(r["revenue"]),2)} for _,r in top.iterrows()] if not top.empty else [],
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # ============================================================
    # 经营看板（orders/advertising/sales/fees/agreements/discounts）
    # ============================================================

    @bp.route("/dashboard/<name>")
    @login_required
    def business_dashboard(name):
        config = _get_config(name)
        shops = query("SELECT DISTINCT shop_name FROM dim_shop_info WHERE status=1 ORDER BY shop_name")
        shop_list = shops["shop_name"].tolist() if not shops.empty else []
        return render_template("dashboard_data.html", config=config, shops=shop_list, name=name)

    @bp.route("/api/dashboard/<name>/data")
    @login_required
    def business_dashboard_data(name):
        config = _get_config(name)
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(request.args.get("per_page", 15, type=int), 100)
        offset = (page - 1) * per_page
        sort = request.args.get("sort", "")
        order = request.args.get("order", "desc")
        if sort and sort not in config.get("display_columns", []):
            sort = ""
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")
        account = request.args.get("account", "")

        conds, params = [], []
        if date_from:
            conds.append(f"{config['date_column']} >= %s"); params.append(date_from)
        if date_to:
            conds.append(f"{config['date_column']} <= %s"); params.append(date_to)
        if account:
            conds.append("account = %s"); params.append(account)

        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        order_clause = f"ORDER BY {sort} {order}" if sort else ""
        cols = ", ".join(config["display_columns"])

        count = query(f"SELECT COUNT(*) c FROM {config['table']} {where}", tuple(params))
        total = int(count["c"].iloc[0]) if not count.empty else 0

        recs = query(f"SELECT {cols} FROM {config['table']} {where} {order_clause} LIMIT {per_page} OFFSET {offset}", tuple(params))
        records = _to_records(recs)
        stats = {
            "total": total,
            "asin_count": len(set(r.get("asin","") for r in records if r.get("asin"))),
            "shop_count": len(set(r.get("account","") for r in records if r.get("account"))),
            "deleted": sum(1 for r in records if str(r.get("delete_flag","0")) in ("1","true","True")),
        }
        return jsonify({"records": records, "total": total, "page": page, "per_page": per_page, "stats": stats})

    @bp.route("/api/dashboard/<name>/export")
    @login_required
    def business_dashboard_export(name):
        config = _get_config(name)
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")
        account = request.args.get("account", "")
        conds, params = [], []
        if date_from: conds.append(f"{config['date_column']} >= %s"); params.append(date_from)


# ============================================================
# Helpers & Config
# ============================================================

def _parse_args(req):
    return req.args.get("date_from",""), req.args.get("date_to",""), req.args.get("platform","")

def _date_clause(df, dt):
    if df and dt: return "BETWEEN %s AND %s", [df, dt]
    if df: return ">= %s", [df]
    if dt: return "<= %s", [dt]
    return ">= DATE_SUB(CURDATE(), INTERVAL 30 DAY)", []

def _plat_join(platform):
    if platform:
        return " JOIN dim_shop_info ds ON t.shop_name = ds.shop_name AND ds.platform = %s", [platform]
    return "", []

def _to_records(df):
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

def _get_config(name):
    configs = {
        "orders": {"title":"订单明细","icon":"bi-cart3","table":"ods_order_raw","date_column":"order_date","display_columns":["account","shop_name","po_number","asin","order_date","quantity","amount","order_status","create_time"],"filters":{"enum_fields":{"order_status":"订单状态"}}},
        "advertising": {"title":"广告明细","icon":"bi-megaphone","table":"ods_advertising_raw","date_column":"ad_date","display_columns":["account","shop_name","campaign_name","ad_type","asin","ad_date","spend","sales","acos","create_time"],"filters":{"enum_fields":{"ad_type":"广告类型"}}},
        "sales": {"title":"销售明细","icon":"bi-graph-up","table":"ods_sales_raw","date_column":"sale_date","display_columns":["account","shop_name","asin","sale_date","units_sold","revenue","refund_qty","create_time"],"filters":{"enum_fields":{}}},
        "fees": {"title":"费用明细","icon":"bi-cash-stack","table":"ods_fee_raw","date_column":"fee_date","display_columns":["account","shop_name","fee_type","fee_date","amount","invoice_id","is_disputed","create_time"],"filters":{"enum_fields":{"fee_type":"费用类型","is_disputed":"争议状态"}}},
        "agreements": {"title":"协议明细","icon":"bi-file-earmark-text","table":"ods_agreement_raw","date_column":"crawl_time","display_columns":["account","agreement_id","marketplace","asin","title","crawl_time","delete_flag"],"filters":{"enum_fields":{"marketplace":"商城","delete_flag":"删除标记"}}},
        "discounts": {"title":"折扣明细","icon":"bi-tags","table":"ods_agreement_raw","date_column":"crawl_time","display_columns":["account","agreement_id","asin","title","crawl_time","delete_flag"],"filters":{"enum_fields":{}}},
    }
    return configs.get(name, configs["orders"])

        if date_to: conds.append(f"{config['date_column']} <= %s"); params.append(date_to)
        if account: conds.append("account = %s"); params.append(account)

        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        cols = ", ".join(config["display_columns"])
        df = query(f"SELECT {cols} FROM {config['table']} {where}", tuple(params))

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=config["title"])
        output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        as_attachment=True, download_name=f"{name}.xlsx")
