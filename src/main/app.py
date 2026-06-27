"""
EcomIQ-RPA — 电商 RPA 与智能工具集 统一平台
================================
整合五大模块:
  - 📡 RPADataHub      — 数据采集与运维
  - 📊 CompetitorWatch  — 竞品竞价分析
  - 🎯 LeadScraper      — 客户开发
  - 🎬 VideoIQ          — AI视频内容分析
  - 🤖 AI Assistant     — AI智能助手

启动: python -m src.main.app
访问: http://localhost:5000
默认账号: admin / RPA@admin2026
"""

import hashlib
import os
import sys
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from flask_sock import Sock

# ============================================================
# Flask 应用初始化
# ============================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
app.secret_key = os.environ.get("ECOMIQ_RPA_SECRET_KEY", os.urandom(24).hex())
app.config.update(
    PERMANENT_SESSION_LIFETIME=604800,    # 7 days
    SESSION_COOKIE_SECURE=False,          # 生产环境改为 True (HTTPS)
    SESSION_COOKIE_HTTPONLY=True,         # 防止 XSS 读取 cookie
    SESSION_COOKIE_SAMESITE='Lax',        # CSRF 防护
)

# WebSocket support
sock = Sock(app)

# ============================================================
# RPADataHub 数据库连接 (用于登录鉴权)
# ============================================================
import threading
import pymysql

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_db_module_dir = os.path.join(_src_dir, "rpa")
sys.path.insert(0, _db_module_dir)
sys.path.insert(0, _src_dir)
try:
    from config.settings import get_config
    _cfg = get_config()
    _db_config = _cfg.database.as_dict()
except Exception:
    # Fallback defaults
    _db_config = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "rpa_admin"),
    }

_conn_pool = threading.local()


def _get_db():
    if not hasattr(_conn_pool, 'conn') or _conn_pool.conn is None:
        _conn_pool.conn = pymysql.connect(**_db_config)
    try:
        _conn_pool.conn.ping(reconnect=True)
    except Exception:
        _conn_pool.conn = pymysql.connect(**_db_config)
    return _conn_pool.conn


def _safe_query(sql, params=None):
    """安全查询，数据库不可用时返回占位数据"""
    try:
        conn = _get_db()
        import pandas as pd
        df = pd.read_sql(sql, conn, params=params)
        return df
    except Exception as e:
        import traceback
        print(f"[DB ERROR] {e}", file=sys.stderr)
        traceback.print_exc()
        import pandas as pd
        return pd.DataFrame()


def _hash_password(password):
    """PBKDF2 安全密码哈希 (兼容旧版 SHA256)"""
    import hashlib as _hl
    salt = os.urandom(16)
    dk = _hl.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return (salt + dk).hex()

def _verify_password(password, stored):
    """验证密码：支持新版 PBKDF2 和旧版 SHA256"""
    import hashlib as _hl
    if len(stored) == 64 and all(c in '0123456789abcdef' for c in stored[:64]):
        # 旧版 SHA256 格式 (无盐) — 兼容存量用户
        if stored == _hl.sha256(password.encode()).hexdigest():
            return True, 'legacy'
        return False, None
    # 新版 PBKDF2 格式：salt(32hex) + dk(64hex)
    try:
        raw = bytes.fromhex(stored)
        salt = raw[:16]
        stored_dk = raw[16:]
        computed_dk = _hl.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        if stored_dk == computed_dk:
            return True, 'pbkdf2'
    except:
        pass
    return False, None


# ============================================================
# 登录鉴权
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_user_permissions():
    """获取当前用户权限列表"""
    if "user" not in session:
        return []
    role_id = session["user"].get("role_id", 2)
    try:
        df = _safe_query("SELECT permissions FROM user_roles WHERE id=%s", (role_id,))
        if not df.empty:
            import json
            return json.loads(df["permissions"].iloc[0])
    except Exception:
        pass
    return []


# ============================================================
# 模板全局注入 — sidebar 高亮用
# ============================================================

@app.context_processor
def inject_globals():
    perms = get_user_permissions() if "user" in session else []
    return {
        "user_permissions": perms,
        "now": datetime.now(),
    }


# ============================================================
# 登录 / 登出
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        try:
            # 先检查数据库连接
            conn = _get_db()
            import pandas as pd

            # 先查用户名，然后本地验证密码
            df = pd.read_sql(
                "SELECT u.id, u.username, u.role, u.password_hash, COALESCE(u.role_id,2) as role_id, "
                "COALESCE(r.name,'观察者') as role_name FROM admin_users u "
                "LEFT JOIN user_roles r ON u.role_id=r.id "
                "WHERE u.username=%s AND u.is_active=1",
                conn,
                params=(username,)
            )

            if not df.empty:
                row = df.iloc[0].to_dict()
                for k, v in list(row.items()):
                    if pd.isna(v): row[k] = ""
                stored_hash = row.pop('password_hash', '')
                valid, hash_type = _verify_password(password, stored_hash)
                if valid:
                    session["user"] = row
                    session.permanent = True
                    # 旧版密码自动升级
                    if hash_type == 'legacy':
                        try:
                            new_hash = _hash_password(password)
                            conn.cursor().execute(
                                "UPDATE admin_users SET password_hash=%s WHERE id=%s",
                                (new_hash, row['id'])
                            )
                            conn.commit()
                        except: pass
                    return redirect(url_for("home"))
                else:
                    error = "密码错误"

            # 检查用户名是否存在
            user_check = pd.read_sql(
                "SELECT username FROM admin_users WHERE username=%s", conn, params=(username,)
            )
            if user_check.empty:
                error = f"用户 '{username}' 不存在"
            else:
                error = "密码错误"

        except Exception as e:
            import traceback
            traceback.print_exc()
            error = f"数据库连接失败: {str(e)[:100]}"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/change_password", methods=["POST"])
@login_required
def change_password():
    data = request.json
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if not new_pw or len(new_pw) < 6:
        return jsonify({"error": "新密码至少6位"}), 400

    user = session["user"]
    try:
        conn = _get_db()
        import pandas as pd
        df = pd.read_sql(
            "SELECT password_hash FROM admin_users WHERE username=%s",
            conn, params=(user["username"],)
        )
        if df.empty:
            return jsonify({"error": "用户不存在"}), 404

        stored_hash = str(df["password_hash"].iloc[0])
        valid, _ = _verify_password(old_pw, stored_hash)
        if not valid:
            return jsonify({"error": "原密码错误"}), 403

        new_hash = _hash_password(new_pw)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE admin_users SET password_hash=%s WHERE username=%s",
                (new_hash, user["username"])
            )
        conn.commit()
        return jsonify({"success": True, "message": "密码已修改"})
    except Exception as e:
        return jsonify({"error": f"修改失败: {str(e)[:100]}"}), 500


# ============================================================
# 首页仪表盘
# ============================================================

@app.route("/")
@login_required
def home():
    return render_template("home.html", user=session["user"])


# ============================================================
# 仪表盘 API — 今日概览
# ============================================================

@app.route("/api/dashboard/summary")
@login_required
def dashboard_summary():
    """首页底部栏数据：采集任务、竞品快照、异常统计"""
    summary = {
        "collect_tasks": 0,
        "competitor_snapshots": 0,
        "abnormal_count": 0,
        "recent_actions": [],
    }

    try:
        # RPADataHub: 今日采集任务
        df = _safe_query(
            "SELECT COUNT(*) as cnt FROM task_queue WHERE DATE(create_time)=CURDATE()"
        )
        if not df.empty:
            summary["collect_tasks"] = int(df["cnt"].iloc[0])

        # RPADataHub: 今日异常
        df = _safe_query(
            "SELECT COUNT(*) as cnt FROM rpa_exception_log WHERE DATE(create_time)=CURDATE()"
        )
        if not df.empty:
            summary["abnormal_count"] = int(df["cnt"].iloc[0])

        # CompetitorWatch: 今日竞品快照
        df = _safe_query(
            "SELECT COUNT(*) as cnt FROM ods_price_snapshot "
            "WHERE DATE(created_at)=CURDATE()"
        )
        if not df.empty:
            summary["competitor_snapshots"] = int(df["cnt"].iloc[0])
    except Exception:
        # 返回默认值
        summary = {
            "collect_tasks": "--",
            "competitor_snapshots": "--",
            "abnormal_count": "--",
            "recent_actions": [],
        }

    return jsonify(summary)


# ============================================================
# 智能客服占位页面 (Customer Service)
# ============================================================

@app.route("/cs/inbox")
@login_required
def cs_inbox():
    return render_template("cs_inbox.html")

@app.route("/cs/templates")
@login_required
def cs_templates():
    return render_template("cs_templates.html")

@app.route("/cs/knowledge")
@login_required
def cs_knowledge():
    return render_template("cs_knowledge.html")

# ============================================================
# 智能客服 API (ServiceIQ)
# ============================================================

@app.route("/api/cs/messages")
@login_required
def api_cs_messages():
    """消息列表 API — 分页 + 多维筛选"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    platform = request.args.get("platform", "")
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    category = request.args.get("category", "")
    search = request.args.get("search", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    conditions = ["1=1"]
    params = []

    if platform:
        platforms = [p.strip() for p in platform.split(",") if p.strip()]
        if platforms:
            ph = ",".join(["%s"] * len(platforms))
            conditions.append(f"platform IN ({ph})")
            params.extend(platforms)

    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            ph = ",".join(["%s"] * len(statuses))
            conditions.append(f"status IN ({ph})")
            params.extend(statuses)

    if priority:
        priorities = [p.strip() for p in priority.split(",") if p.strip()]
        if priorities:
            ph = ",".join(["%s"] * len(priorities))
            conditions.append(f"priority IN ({ph})")
            params.extend(priorities)

    if category:
        categories = [c.strip() for c in category.split(",") if c.strip()]
        if categories:
            ph = ",".join(["%s"] * len(categories))
            conditions.append(f"category IN ({ph})")
            params.extend(categories)

    if search:
        conditions.append(
            "(customer_name LIKE %s OR order_id LIKE %s OR content LIKE %s OR subject LIKE %s)"
        )
        like_val = f"%{search}%"
        params.extend([like_val, like_val, like_val, like_val])

    if date_from:
        conditions.append("DATE(received_at) >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("DATE(received_at) <= %s")
        params.append(date_to)

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    try:
        import pandas as pd
        count_df = _safe_query(
            f"SELECT COUNT(*) as cnt FROM cs_messages WHERE {where}", params
        )
        total = int(count_df["cnt"].iloc[0]) if not count_df.empty else 0

        data_df = _safe_query(
            f"SELECT id, platform, customer_name, order_id, asin, subject, "
            f"content, priority, status, category, sentiment, ai_intent, "
            f"received_at, first_reply_at FROM cs_messages "
            f"WHERE {where} ORDER BY received_at DESC LIMIT %s OFFSET %s",
            params + [per_page, offset],
        )

        records = []
        if not data_df.empty:
            for _, row in data_df.iterrows():
                r = row.to_dict()
                for k, v in list(r.items()):
                    if hasattr(v, "strftime") and not pd.isna(v):
                        r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                    elif pd.isna(v):
                        r[k] = None
                if r.get("content"):
                    r["preview"] = r["content"][:100]
                records.append(r)

        return jsonify({
            "success": True,
            "data": {
                "records": records, "total": total, "page": page,
                "per_page": per_page,
                "total_pages": max(1, (total + per_page - 1) // per_page),
            },
            "error": "",
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "data": {}, "error": f"查询失败: {str(e)[:200]}"}), 500


@app.route("/api/cs/messages/<int:message_id>")
@login_required
def api_cs_message_detail(message_id):
    """消息详情 API — 含订单关联信息和对话历史"""
    try:
        import json as _json
        import pandas as pd

        msg_df = _safe_query("SELECT * FROM cs_messages WHERE id=%s", (message_id,))
        if msg_df.empty:
            return jsonify({"success": False, "data": {}, "error": "消息不存在"}), 404

        msg = msg_df.iloc[0].to_dict()
        for k, v in list(msg.items()):
            if hasattr(v, "strftime") and not pd.isna(v):
                msg[k] = v.strftime("%Y-%m-%d %H:%M:%S")
            elif pd.isna(v):
                msg[k] = None
        if msg.get("tags") and isinstance(msg["tags"], str):
            try:
                msg["tags"] = _json.loads(msg["tags"])
            except Exception:
                msg["tags"] = []

        # 关联订单
        order_info = {}
        if msg.get("order_id"):
            odf = _safe_query(
                "SELECT order_date, quantity, amount, order_status FROM ods_order_raw "
                "WHERE po_number=%s ORDER BY order_date DESC LIMIT 1",
                (msg["order_id"],),
            )
            if not odf.empty:
                o = odf.iloc[0].to_dict()
                order_info = {
                    "order_date": o["order_date"].strftime("%Y-%m-%d") if hasattr(o["order_date"], "strftime") else str(o.get("order_date", "")),
                    "amount": float(o["amount"]) if not pd.isna(o.get("amount")) else None,
                    "status": o.get("order_status", ""),
                }

        # 产品名
        product_name = None
        if msg.get("asin"):
            pdf = _safe_query("SELECT title FROM ods_agreement_raw WHERE asin=%s LIMIT 1", (msg["asin"],))
            if not pdf.empty:
                product_name = str(pdf["title"].iloc[0])

        # 对话历史
        cdf = _safe_query(
            "SELECT id, reply_content, reply_type, is_ai_assisted, created_at "
            "FROM cs_conversations WHERE message_id=%s ORDER BY created_at ASC",
            (message_id,),
        )
        conversations = []
        if not cdf.empty:
            for _, row in cdf.iterrows():
                c = row.to_dict()
                if hasattr(c.get("created_at"), "strftime"):
                    c["created_at"] = c["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                c["is_ai_assisted"] = bool(c.get("is_ai_assisted", 0))
                conversations.append(c)

        # 同订单历史消息数
        related_count = 0
        if msg.get("order_id"):
            rdf = _safe_query(
                "SELECT COUNT(*) as cnt FROM cs_messages WHERE order_id=%s AND id != %s",
                (msg["order_id"], message_id),
            )
            if not rdf.empty:
                related_count = int(rdf["cnt"].iloc[0])

        return jsonify({
            "success": True,
            "data": {
                "message": msg, "order_info": order_info,
                "product_name": product_name, "conversations": conversations,
                "related_count": related_count,
            },
            "error": "",
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "data": {}, "error": f"查询失败: {str(e)[:200]}"}), 500


@app.route("/api/cs/messages/<int:message_id>/reply", methods=["POST"])
@login_required
def api_cs_message_reply(message_id):
    """发送回复 API"""
    data = request.json
    reply_content = (data.get("content") or "").strip()
    if not reply_content:
        return jsonify({"success": False, "data": {}, "error": "回复内容不能为空"}), 400

    template_id = data.get("template_id")
    reply_type = data.get("reply_type", "manual")
    is_ai_assisted = 1 if data.get("is_ai_assisted") else 0

    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cs_conversations (message_id, reply_content, reply_type, "
                "template_id, agent_id, is_ai_assisted) VALUES (%s,%s,%s,%s,%s,%s)",
                (message_id, reply_content, reply_type, template_id,
                 session["user"].get("id"), is_ai_assisted),
            )
            cur.execute(
                "UPDATE cs_messages SET status='replied', "
                "first_reply_at=COALESCE(first_reply_at, NOW()) WHERE id=%s",
                (message_id,),
            )
            if template_id:
                try:
                    cur.execute("UPDATE cs_templates SET usage_count=usage_count+1 WHERE id=%s", (template_id,))
                except Exception:
                    pass
        conn.commit()
        return jsonify({"success": True, "data": {"message": "回复已发送"}, "error": ""})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "data": {}, "error": f"回复失败: {str(e)[:200]}"}), 500


@app.route("/api/cs/messages/<int:message_id>/close", methods=["POST"])
@login_required
def api_cs_message_close(message_id):
    """关闭会话"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute("UPDATE cs_messages SET status='closed', closed_at=NOW() WHERE id=%s", (message_id,))
        conn.commit()
        return jsonify({"success": True, "data": {"message": "会话已关闭"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/messages/<int:message_id>/spam", methods=["POST"])
@login_required
def api_cs_message_spam(message_id):
    """标记为垃圾消息"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute("UPDATE cs_messages SET status='spam' WHERE id=%s", (message_id,))
        conn.commit()
        return jsonify({"success": True, "data": {"message": "已标记为垃圾"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/messages/batch", methods=["POST"])
@login_required
def api_cs_messages_batch():
    """批量操作"""
    data = request.json
    ids = data.get("ids", [])
    action = data.get("action", "")
    if not ids or not action:
        return jsonify({"success": False, "data": {}, "error": "参数不完整"}), 400
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            if action == "close":
                cur.executemany(
                    "UPDATE cs_messages SET status='closed', closed_at=NOW() WHERE id=%s",
                    [(i,) for i in ids],
                )
            elif action == "spam":
                cur.executemany(
                    "UPDATE cs_messages SET status='spam' WHERE id=%s",
                    [(i,) for i in ids],
                )
            else:
                return jsonify({"success": False, "data": {}, "error": f"未知操作: {action}"}), 400
        conn.commit()
        return jsonify({"success": True, "data": {"affected": len(ids)}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/messages/<int:message_id>/ai-suggest")
@login_required
def api_cs_message_ai_suggest(message_id):
    """AI 回复建议 — DeepSeek API 分析消息，生成回复草稿"""
    import requests
    import json as _json

    # 获取消息内容
    msg_df = _safe_query(
        "SELECT id, customer_name, order_id, asin, subject, content, platform "
        "FROM cs_messages WHERE id=%s", (message_id,)
    )
    if msg_df.empty:
        return jsonify({"success": False, "data": {}, "error": "消息不存在"}), 404

    msg = msg_df.iloc[0].to_dict()
    customer_name = msg.get("customer_name", "")
    order_id = msg.get("order_id", "")
    platform = msg.get("platform", "")
    content = msg.get("content", "")

    # 获取产品名
    product_name = "Unknown Product"
    if msg.get("asin"):
        pdf = _safe_query("SELECT title FROM ods_agreement_raw WHERE asin=%s LIMIT 1", (msg["asin"],))
        if not pdf.empty:
            product_name = str(pdf["title"].iloc[0])

    # 先尝试关键词规则兜底
    content_lower = content.lower()
    rule_intent = "other"
    rule_suggested_category = "custom"
    keyword_map = [
        (["return", "refund", "damaged", "wrong item", "exchange", "broken", "defect"], "return",
         "退货退款"),
        (["tracking", "shipping", "delivery", "where is my", "package", "ship"], "logistics",
         "物流查询"),
        (["size", "color", "material", "compatible", "does it", "how to", "dimension"], "inquiry",
         "产品咨询"),
        (["complaint", "disappointed", "angry", "terrible", "bad service", "awful"], "complaint",
         "投诉处理"),
        (["love", "great", "amazing", "thank", "excellent", "wonderful"], "other", "好评"),
    ]
    for keywords, intent, cat in keyword_map:
        if any(kw in content_lower for kw in keywords):
            rule_intent = intent
            rule_suggested_category = cat
            break

    # 尝试 DeepSeek API
    try:
        cfg = get_config()
        api_key = cfg.alert.deepseek_api_key
        if not api_key or "your-" in api_key:
            raise ValueError("API Key 未配置")

        prompt = f"""你是一个跨境电商客服专家。请分析以下客户消息，返回 JSON：

客户名称：{customer_name}
订单号：{order_id}
产品：{product_name}
平台：{platform}
客户消息：
\"\"\"
{content}
\"\"\"

请返回以下 JSON 格式（仅返回 JSON，不要其他文字）：
{{
  "intent": "退货退款/物流查询/产品咨询/投诉/好评/其他",
  "sentiment": "positive/neutral/negative/angry",
  "extracted_info": {{
    "issue": "客户问题的简短中文描述（20字以内）",
    "key_details": ["关键细节"]
  }},
  "suggested_reply": "建议的完整回复内容",
  "suggested_template_category": "return/logistics/inquiry/complaint/custom"
}}

要求：
- 回复专业、耐心、有同理心
- 如果是投诉或退货，先道歉再给解决方案
- 如果是物流查询，说明物流查询流程
- 如果是产品咨询，提供准确信息
- 如果是好评，表示感谢
- 不要编造不存在的订单信息
- suggested_reply 根据平台语言：Amazon/Walmart 用英文，Shopee 视情况，1688 用中文"""

        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
                "temperature": 0.3,
            },
            timeout=15,
        )

        if resp.status_code == 200:
            ai_text = resp.json()["choices"][0]["message"]["content"]
            # 清理可能的 markdown 包裹
            ai_text = ai_text.strip()
            if ai_text.startswith("```"):
                ai_text = ai_text.split("\n", 1)[-1]
                if ai_text.endswith("```"):
                    ai_text = ai_text[: ai_text.rfind("```")]
            result = _json.loads(ai_text)
        else:
            raise Exception(f"API 返回 {resp.status_code}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 降级：关键词规则兜底
        sentiment_map = {
            "return": "negative",
            "complaint": "angry",
            "logistics": "neutral",
            "inquiry": "neutral",
            "other": "positive",
        }
        result = {
            "intent": rule_intent,
            "sentiment": sentiment_map.get(rule_intent, "neutral"),
            "extracted_info": {
                "issue": "关键词分析（AI 暂不可用）",
                "key_details": [],
            },
            "suggested_reply": f"Dear {customer_name},\n\nThank you for your message. We are reviewing your inquiry regarding order {order_id} and will get back to you shortly.\n\nBest regards,\nCustomer Service Team",
            "suggested_template_category": rule_suggested_category,
        }

    # 更新消息的 AI 分析字段
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cs_messages SET ai_intent=%s, sentiment=%s, ai_confidence=%s WHERE id=%s",
                (result.get("intent"), result.get("sentiment"), 85.0, message_id),
            )
        conn.commit()
    except Exception:
        pass

    return jsonify({
        "success": True,
        "data": {
            "intent": result.get("intent", ""),
            "sentiment": result.get("sentiment", ""),
            "issue": result.get("extracted_info", {}).get("issue", ""),
            "key_details": result.get("extracted_info", {}).get("key_details", []),
            "suggested_reply": result.get("suggested_reply", ""),
            "suggested_template_category": result.get("suggested_template_category", ""),
        },
        "error": "",
    })

@app.route("/api/cs/knowledge")
@login_required
def api_cs_knowledge_list():
    """知识库列表 API — 分页 + 搜索 + 分类筛选"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 15, type=int)
    search = request.args.get("search", "")
    category = request.args.get("category", "")

    try:
        import pandas as pd
        conditions = ["is_published=1"]
        params = []
        if category:
            conditions.append("category=%s")
            params.append(category)

        # 全文搜索：NATURAL LANGUAGE MODE 模式兼容 ngram 中文分词，降级 LIKE
        if search:
            try:
                conditions.append(
                    "MATCH(question, answer, keywords, content_text) AGAINST(%s IN NATURAL LANGUAGE MODE)"
                )
                params.append(search)
            except Exception:
                conditions.append(
                    "(question LIKE %s OR answer LIKE %s OR keywords LIKE %s OR content_text LIKE %s)"
                )
                like_val = f"%{search}%"
                params.extend([like_val, like_val, like_val, like_val])

        where = " AND ".join(conditions)
        offset = (page - 1) * per_page

        count_df = _safe_query(
            f"SELECT COUNT(*) as cnt FROM cs_knowledge WHERE {where}", params
        )
        total = int(count_df["cnt"].iloc[0]) if not count_df.empty else 0

        df = _safe_query(
            f"SELECT id, question, answer, category, keywords, language, document_name, "
            f"document_size, usage_count, is_published, created_at "
            f"FROM cs_knowledge WHERE {where} ORDER BY usage_count DESC LIMIT %s OFFSET %s",
            params + [per_page, offset],
        )

        records = []
        if not df.empty:
            for _, row in df.iterrows():
                r = row.to_dict()
                for k, v in list(r.items()):
                    if hasattr(v, "strftime") and not pd.isna(v):
                        r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                    elif pd.isna(v):
                        r[k] = None
                # 截断答案预览
                if r.get("answer"):
                    r["answer_preview"] = r["answer"][:120]
                records.append(r)

        return jsonify({
            "success": True,
            "data": {"records": records, "total": total, "page": page, "per_page": per_page},
            "error": "",
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/knowledge/create", methods=["POST"])
@login_required
def api_cs_knowledge_create():
    """创建 FAQ 条目"""
    data = request.json
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    if not question or not answer:
        return jsonify({"success": False, "data": {}, "error": "问题和答案不能为空"}), 400
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cs_knowledge (question, answer, category, keywords, language) "
                "VALUES (%s,%s,%s,%s,%s)",
                (question, answer, data.get("category", "product"),
                 data.get("keywords", ""), data.get("language", "zh")),
            )
        conn.commit()
        return jsonify({"success": True, "data": {"message": "FAQ已创建"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/knowledge/update/<int:faq_id>", methods=["POST"])
@login_required
def api_cs_knowledge_update(faq_id):
    """更新 FAQ"""
    data = request.json
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cs_knowledge SET question=%s, answer=%s, category=%s, keywords=%s, language=%s WHERE id=%s",
                (data.get("question", ""), data.get("answer", ""), data.get("category", "product"),
                 data.get("keywords", ""), data.get("language", "zh"), faq_id),
            )
        conn.commit()
        return jsonify({"success": True, "data": {"message": "FAQ已更新"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/knowledge/delete/<int:faq_id>", methods=["POST"])
@login_required
def api_cs_knowledge_delete(faq_id):
    """删除知识库条目"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cs_knowledge WHERE id=%s", (faq_id,))
        conn.commit()
        return jsonify({"success": True, "data": {"message": "已删除"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/knowledge/upload", methods=["POST"])
@login_required
def api_cs_knowledge_upload():
    """上传文档到知识库 — 解析文本内容并存入 content_text"""
    import os as _os
    if "file" not in request.files:
        return jsonify({"success": False, "data": {}, "error": "请选择文件"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"success": False, "data": {}, "error": "文件名为空"}), 400

    # 安全文件名
    safe_name = _os.path.basename(f.filename)
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in ("pdf", "txt", "md", "docx", "csv", "xlsx"):
        return jsonify({"success": False, "data": {}, "error": f"不支持的文件类型: .{ext}"}), 400

    # 保存文件
    upload_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "uploads", "knowledge")
    _os.makedirs(upload_dir, exist_ok=True)
    import time
    stored_name = f"{int(time.time())}_{safe_name}"
    filepath = _os.path.join(upload_dir, stored_name)
    f.save(filepath)

    # 解析文本内容
    content_text = ""
    if ext == "txt" or ext == "md":
        content_text = open(filepath, "r", encoding="utf-8", errors="ignore").read()
    elif ext == "csv":
        try:
            import pandas as pd
            df = pd.read_csv(filepath)
            content_text = df.to_string(index=False)
        except Exception:
            content_text = open(filepath, "r", encoding="utf-8", errors="ignore").read()
    elif ext == "xlsx":
        try:
            import pandas as pd
            df = pd.read_excel(filepath)
            content_text = df.to_string(index=False)
        except Exception:
            content_text = "[Excel 文件，无法解析]"
    elif ext == "pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(filepath)
            pages = [p.extract_text() or "" for p in reader.pages]
            content_text = "\n".join(pages)
        except ImportError:
            content_text = "[PDF文件，需安装 PyPDF2 解析]"
    elif ext == "docx":
        try:
            from docx import Document
            doc = Document(filepath)
            content_text = "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            content_text = "[DOCX文件，需安装 python-docx 解析]"

    # 存入数据库
    question = (request.form.get("title") or safe_name).strip()
    category = request.form.get("category", "product")
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cs_knowledge (question, answer, category, document_name, document_size, "
                "document_path, content_text, is_published) VALUES (%s,%s,%s,%s,%s,%s,%s,1)",
                (question, content_text[:500] + ("..." if len(content_text) > 500 else ""),
                 category, safe_name, _os.path.getsize(filepath), stored_name, content_text),
            )
        conn.commit()
        return jsonify({
            "success": True,
            "data": {
                "message": "文档已上传",
                "filename": safe_name,
                "chars_parsed": len(content_text),
            },
            "error": "",
        })
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/knowledge/download/<int:faq_id>")
@login_required
def api_cs_knowledge_download(faq_id):
    """下载知识库文档"""
    import os as _os
    df = _safe_query(
        "SELECT document_path, document_name FROM cs_knowledge WHERE id=%s", (faq_id,)
    )
    if df.empty or not df["document_path"].iloc[0]:
        return jsonify({"success": False, "data": {}, "error": "文档不存在"}), 404

    stored_name = str(df["document_path"].iloc[0])
    orig_name = str(df["document_name"].iloc[0] or stored_name.split("_", 1)[-1])
    upload_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "uploads", "knowledge")
    filepath = _os.path.join(upload_dir, stored_name)

    if not _os.path.isfile(filepath):
        return jsonify({"success": False, "data": {}, "error": "文件已丢失"}), 404

    from flask import send_file
    return send_file(filepath, as_attachment=True, download_name=orig_name)


@app.route("/api/cs/knowledge/semantic-search", methods=["POST"])
@login_required
def api_cs_knowledge_semantic_search():
    """RAG 语义检索 — 基于 DeepSeek 意图理解 + FULLTEXT 关键词搜索"""
    import requests as _requests
    import json as _json

    data = request.json
    query = (data.get("query") or "").strip()
    if not query or len(query) < 3:
        return jsonify({"success": False, "data": {}, "error": "搜索内容太短"}), 400

    # Step 1: AI 理解查询意图，提取英文关键词
    keywords = query
    try:
        cfg = get_config()
        api_key = cfg.alert.deepseek_api_key
        if api_key and "your-" not in api_key:
            resp = _requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{
                        "role": "user",
                        "content": f"将以下用户问题翻译提取为5个英文关键词，以空格分隔，只返回关键词不要其他内容:\n\n{query}",
                    }],
                    "max_tokens": 60,
                    "temperature": 0.1,
                },
                timeout=8,
            )
            if resp.status_code == 200:
                keywords = resp.json()["choices"][0]["message"]["content"].strip()
                if len(keywords) > 100 or "\n" in keywords:
                    keywords = query  # 降级
    except Exception:
        pass  # 降级到原始查询

    # Step 2: FULLTEXT 搜索 + 组合键词
    try:
        import pandas as pd
        # 用原始查询 + AI提取的关键词组合搜索
        search_terms = []
        # 用原始查询（NATURAL LANGUAGE MODE 兼容 ngram 中文分词）
        try:
            df1 = _safe_query(
                "SELECT id, question, answer, category, document_name, "
                "MATCH(question, answer, keywords, content_text) AGAINST(%s IN NATURAL LANGUAGE MODE) as relevance "
                "FROM cs_knowledge WHERE is_published=1 AND MATCH(question, answer, keywords, content_text) AGAINST(%s IN NATURAL LANGUAGE MODE) "
                "LIMIT 5",
                (query, query),
            )
            if not df1.empty:
                search_terms.extend(df1.to_dict("records"))
        except Exception:
            pass

        # 用 AI 关键词再搜（也包含 content_text）
        if keywords and keywords != query:
            try:
                df2 = _safe_query(
                    "SELECT id, question, answer, category, document_name, "
                    "MATCH(question, answer, keywords, content_text) AGAINST(%s IN NATURAL LANGUAGE MODE) as relevance "
                    "FROM cs_knowledge WHERE is_published=1 AND MATCH(question, answer, keywords, content_text) AGAINST(%s IN NATURAL LANGUAGE MODE) "
                    "LIMIT 5",
                    (keywords, keywords),
                )
                if not df2.empty:
                    search_terms.extend(df2.to_dict("records"))
            except Exception:
                pass

        # 去重
        seen_ids = set()
        unique_results = []
        for r in search_terms:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                if r.get("answer"):
                    r["answer_preview"] = r["answer"][:200]
                if pd.isna(r.get("document_name")):
                    r["document_name"] = None
                unique_results.append(r)

        # 如果 FULLTEXT 无结果，降级 LIKE
        if not unique_results:
            like_val = f"%{query}%"
            df3 = _safe_query(
                "SELECT id, question, answer, category, document_name FROM cs_knowledge "
                "WHERE is_published=1 AND (question LIKE %s OR answer LIKE %s OR keywords LIKE %s OR content_text LIKE %s) "
                "LIMIT 5",
                (like_val, like_val, like_val, like_val),
            )
            if not df3.empty:
                for _, row in df3.iterrows():
                    r = row.to_dict()
                    if r.get("answer"):
                        r["answer_preview"] = r["answer"][:200]
                    if pd.isna(r.get("document_name")):
                        r["document_name"] = None
                    unique_results.append(r)

        # usage_count +1
        if unique_results:
            try:
                conn = _get_db()
                with conn.cursor() as cur:
                    for r in unique_results[:3]:
                        cur.execute("UPDATE cs_knowledge SET usage_count=usage_count+1 WHERE id=%s", (r["id"],))
                conn.commit()
            except Exception:
                pass

        # Step 3: RAG — 基于检索到的知识库内容，调用 DeepSeek 生成回答
        ai_answer = ""
        context_sources = []
        if unique_results:
            try:
                cfg = get_config()
                api_key = cfg.alert.deepseek_api_key
                if api_key and "your-" not in api_key:
                    # 获取 Top 3 条目的完整内容构建上下文
                    top_ids = [r["id"] for r in unique_results[:3]]
                    for kid in top_ids:
                        content_df = _safe_query(
                            "SELECT question, answer, content_text, document_name FROM cs_knowledge WHERE id=%s",
                            (kid,),
                        )
                        if not content_df.empty:
                            row = content_df.iloc[0]
                            text = ""
                            if row.get("content_text") and not pd.isna(row["content_text"]):
                                text = str(row["content_text"])[:3000]
                            elif row.get("answer") and not pd.isna(row["answer"]):
                                text = str(row["answer"])
                            else:
                                text = str(row.get("question", ""))
                            context_sources.append({
                                "title": str(row.get("question") or row.get("document_name") or "知识库文档"),
                                "text": text,
                            })

                    # 拼接上下文
                    context_blocks = []
                    for s in context_sources:
                        context_blocks.append(f"【{s['title']}】\n{s['text']}")
                    context = "\n\n---\n\n".join(context_blocks)

                    rag_prompt = f"""你是 EcomIQ-RPA 电商 RPA 平台的技术专家助手。请根据以下知识库内容回答用户问题。如果知识库中有相关内容，请引用知识库中的具体信息来回答。如果知识库中没有相关信息，请如实告知，不要编造。

知识库内容:
{context}

用户问题: {query}

请用中文回答，格式清晰，可以分点说明。回答:"""

                    rag_resp = _requests.post(
                        "https://api.deepseek.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "deepseek-chat",
                            "messages": [{"role": "user", "content": rag_prompt}],
                            "max_tokens": 800,
                            "temperature": 0.3,
                        },
                        timeout=20,
                    )
                    if rag_resp.status_code == 200:
                        ai_answer = rag_resp.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                import traceback
                traceback.print_exc()
                ai_answer = ""

        return jsonify({
            "success": True,
            "data": {
                "results": unique_results,
                "ai_keywords": keywords,
                "total": len(unique_results),
                "ai_answer": ai_answer,
            },
            "error": "",
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/templates")
@login_required
def api_cs_templates_list():
    """获取模板列表（用于收件箱下拉选择和管理页面）"""
    try:
        import pandas as pd
        df = _safe_query(
            "SELECT id, name, category, language, platform, content, usage_count, is_active, created_at "
            "FROM cs_templates ORDER BY usage_count DESC"
        )
        records = []
        if not df.empty:
            for _, row in df.iterrows():
                r = row.to_dict()
                for k, v in list(r.items()):
                    if hasattr(v, "strftime") and not pd.isna(v):
                        r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                    elif pd.isna(v):
                        r[k] = None
                records.append(r)
        return jsonify({"success": True, "data": {"records": records}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/templates/create", methods=["POST"])
@login_required
def api_cs_templates_create():
    """创建模板"""
    data = request.json
    name = (data.get("name") or "").strip()
    content = (data.get("content") or "").strip()
    if not name or not content:
        return jsonify({"success": False, "data": {}, "error": "名称和内容不能为空"}), 400
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cs_templates (name, category, language, platform, content, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (name, data.get("category", "custom"), data.get("language", "en"),
                 data.get("platform", ""), content, session["user"]["username"])
            )
        conn.commit()
        return jsonify({"success": True, "data": {"message": "模板已创建"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/templates/update/<int:template_id>", methods=["POST"])
@login_required
def api_cs_templates_update(template_id):
    """更新模板"""
    data = request.json
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cs_templates SET name=%s, category=%s, language=%s, platform=%s, content=%s WHERE id=%s",
                (data.get("name", ""), data.get("category", "custom"), data.get("language", "en"),
                 data.get("platform", ""), data.get("content", ""), template_id)
            )
        conn.commit()
        return jsonify({"success": True, "data": {"message": "模板已更新"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/templates/delete/<int:template_id>", methods=["POST"])
@login_required
def api_cs_templates_delete(template_id):
    """删除模板"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cs_templates WHERE id=%s", (template_id,))
        conn.commit()
        return jsonify({"success": True, "data": {"message": "模板已删除"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


@app.route("/api/cs/templates/toggle/<int:template_id>", methods=["POST"])
@login_required
def api_cs_templates_toggle(template_id):
    """启用/停用模板"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute("UPDATE cs_templates SET is_active = NOT is_active WHERE id=%s", (template_id,))
        conn.commit()
        return jsonify({"success": True, "data": {"message": "状态已切换"}, "error": ""})
    except Exception as e:
        return jsonify({"success": False, "data": {}, "error": str(e)[:200]}), 500


# ============================================================
# 视频分析占位页面 (VideoIQ)
# ============================================================

@app.route("/video")
@login_required
def video_home():
    return render_template("video.html")


@app.route("/video/analyze")
@login_required
def video_analyze():
    return render_template("video_analyze.html")


@app.route("/video/scripts")
@login_required
def video_scripts():
    return render_template("video_scripts.html")


@app.route("/video/history")
@login_required
def video_history():
    return render_template("video_history.html")


# ============================================================
# AI 智能助手占位页面
# ============================================================

@app.route("/ai")
@login_required
def ai_assistant():
    return render_template("ai_assistant.html")


# ============================================================
# 系统设置占位页面
# ============================================================

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


# ============================================================
# LeadScraper API 兼容路由（必须在 RPADataHub /api 蓝图之前注册）
# LeadScraper 模板中用 fetch('/api/upload') 等，但 RPADataHub 占了 /api 前缀
# ============================================================

@app.route('/api/upload', methods=['POST'], endpoint='ls_compat_upload')
@app.route('/api/start', methods=['POST'], endpoint='ls_compat_start')
@app.route('/api/stop', methods=['POST'], endpoint='ls_compat_stop')
@app.route('/api/resume', methods=['POST'], endpoint='ls_compat_resume')
@app.route('/api/skip', methods=['POST'], endpoint='ls_compat_skip')
@app.route('/api/download', methods=['GET'], endpoint='ls_compat_download')
@app.route('/api/status', methods=['GET'], endpoint='ls_compat_status')
@app.route('/api/campaign/import', methods=['POST'], endpoint='ls_compat_campaign_import')
@app.route('/api/campaign/leads', methods=['GET'], endpoint='ls_compat_campaign_leads')
@app.route('/api/campaign/keywords', methods=['GET'], endpoint='ls_compat_campaign_keywords')
@app.route('/api/campaign/template', methods=['GET', 'POST'], endpoint='ls_compat_campaign_template')
@app.route('/api/campaign/send', methods=['POST'], endpoint='ls_compat_campaign_send')
@app.route('/api/campaign/send/progress', methods=['GET'], endpoint='ls_compat_campaign_send_progress')
@app.route('/api/campaign/send/stop', methods=['POST'], endpoint='ls_compat_campaign_send_stop')
@login_required
def _redirect_to_leads_api():
    qs = request.query_string.decode('utf-8')
    target = '/leads' + request.path
    if qs:
        target += '?' + qs
    return redirect(target, code=307)

# ============================================================
# 挂载子模块 Blueprints
# ============================================================

_module_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 确保模块父目录在 sys.path 中
if _module_base not in sys.path:
    sys.path.insert(0, _module_base)

_blueprint_msgs = []

# RPADataHub
try:
    from rpa.blueprint import create_rpa_data_hub_blueprint
    rpa_bp = create_rpa_data_hub_blueprint()
    app.register_blueprint(rpa_bp, url_prefix="/rpa")
    _blueprint_msgs.append("[EcomIQ-RPA] ✓ RPADataHub 蓝图已挂载 -> /rpa")
except Exception as e:
    _blueprint_msgs.append(f"[EcomIQ-RPA] ✗ RPADataHub 蓝图挂载失败: {e}")

# CompetitorWatch
try:
    from competitor.blueprint import create_competitor_watch_blueprint
    comp_bp = create_competitor_watch_blueprint()
    app.register_blueprint(comp_bp, url_prefix="/competitor")
    _blueprint_msgs.append("[EcomIQ-RPA] ✓ CompetitorWatch 蓝图已挂载 -> /competitor")
except Exception as e:
    _blueprint_msgs.append(f"[EcomIQ-RPA] ✗ CompetitorWatch 蓝图挂载失败: {e}")

# LeadScraper
try:
    from leads.blueprint import create_lead_scraper_blueprint
    lead_bp = create_lead_scraper_blueprint()
    app.register_blueprint(lead_bp, url_prefix="/leads")
    _blueprint_msgs.append("[EcomIQ-RPA] ✓ LeadScraper 蓝图已挂载 -> /leads")
except Exception as e:
    _blueprint_msgs.append(f"[EcomIQ-RPA] ✗ LeadScraper 蓝图挂载失败: {e}")


# ============================================================
# WebSocket — YAML 执行器实时日志
# ============================================================

@sock.route('/rpa/api/winauto/ws')
def winauto_ws(ws):
    """WebSocket endpoint for YAML executor live logging"""
    import json as _json
    while True:
        data = ws.receive()
        if data is None:
            break
        try:
            import yaml as _yaml
            message = _json.loads(data)
            prompt = message.get('yaml', '')
            flow_config = _yaml.safe_load(prompt)
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                from rpa.win_automation.flow_engine import FlowEngine
                engine = FlowEngine()
                engine.execute(flow_config)
                output = sys.stdout.getvalue()
                ws.send(_json.dumps({'level': 'success', 'message': '✅ 流程执行完成\n' + output}))
            except Exception as e:
                import traceback
                ws.send(_json.dumps({'level': 'error', 'message': traceback.format_exc()}))
            finally:
                sys.stdout = old_stdout
        except Exception as e:
            ws.send(_json.dumps({'level': 'error', 'message': str(e)}))

# ============================================================
# 健康检查
# ============================================================

@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "app": "EcomIQ-RPA",
        "timestamp": datetime.now().isoformat(),
    })


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    # 使用统一的启动辅助工具：
    #   - debug=True  时避免启动信息打印两遍（Werkzeug reloader 子进程问题）
    #   - debug=False 时自动切换为 waitress 生产服务器
    from shared.runner import run_flask_app, should_print_startup

    DEBUG_MODE = True  # 开发环境设为 True，生产部署改为 False

    if should_print_startup(DEBUG_MODE):
        for msg in _blueprint_msgs:
            print(msg)
        print("=" * 60)
        print("  EcomIQ-RPA — 电商 RPA 与智能工具集 v1.0")
        print("  统一平台入口")
        print("=" * 60)
        print(f"  访问地址: http://localhost:5000")
        print(f"  默认账号: admin / RPA@admin2026")
        print(f"  模块路由:")
        print(f"    📡 RPADataHub      -> /rpa")
        print(f"    📊 CompetitorWatch  -> /competitor")
        print(f"    🎯 LeadScraper      -> /leads")
        print(f"    🎬 VideoIQ          -> /video")
        print(f"    🤖 AI Assistant     -> /ai")
        print("=" * 60)

    run_flask_app(app, host="0.0.0.0", port=5000, debug=DEBUG_MODE)