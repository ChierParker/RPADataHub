"""
AI 运营助手 — 自然语言查询数据库 + 智能诊断 + 趋势分析
整合 DeepSeek API 实现 Function Calling 模式
"""

import json, re
from datetime import datetime
import requests


class AIOpsAssistant:
    """AI 运营助手（Function Calling 模式）"""

    SYSTEM_PROMPT = """你是 RPADataHub 的 AI 运营助手，服务于跨境电商数据采集平台。
你可以通过 Function Calling 查询以下数据库表：

数据表：
- ods_order_raw: 订单数据 (shop_name, po_number, asin, order_date, quantity, amount, order_status)
- ods_sales_raw: 销量数据 (shop_name, asin, sale_date, units_sold, revenue, refund_qty)
- ods_advertising_raw: 广告数据 (shop_name, campaign_name, ad_type, asin, ad_date, spend, sales, acos)
- ods_fee_raw: 费用数据 (shop_name, fee_type, fee_date, amount, invoice_id, is_disputed)
- ods_agreement_raw: 协议数据 (account, agreement_id, marketplace, asin, title, crawl_time, delete_flag)
- ods_sina_news_raw: 新浪新闻数据 (title, url, source, pub_time, crawl_time, category)
- dim_shop_info: 店铺维表 (shop_id, shop_name, platform, bu, status)
- task_queue: 任务队列 (task_uuid, script_name, task_status, start_time, end_time)
- task_record: 采集记录 (shop_name, collect_result, row_count, create_time)
- rpa_exception_log: 异常日志 (exception_type, error_message, shop_name, create_time)
- rpa_dirty_data_log: 脏数据日志 (shop_name, reason, detect_time)
- etl_process_log: ETL处理记录 (file_name, status, row_count, dirty_count, start_time)

可用函数：
1. execute_sql(sql) — 执行只读SQL查询并返回结果
2. get_today_summary() — 获取今日运营概览
3. get_exception_detail(exception_type) — 获取指定类型异常的详细分析

回答要求：
- 用中文回复，简洁专业
- 涉及数据时用数字说话
- 如果用户问的问题超出数据范围，诚实告知
- 可以建议用户去看具体的 Admin 页面
"""

    # 可用的 SQL 表白名单（只读安全）
    ALLOWED_TABLES = [
        'ods_order_raw', 'ods_sales_raw', 'ods_advertising_raw', 'ods_fee_raw',
        'ods_agreement_raw', 'ods_sina_news_raw', 'dim_shop_info',
        'task_queue', 'task_record', 'task_summary',
        'rpa_exception_log', 'rpa_dirty_data_log', 'etl_process_log',
    ]

    def __init__(self, api_key, db_manager=None):
        self.api_key = api_key
        self.db = db_manager
        self.conversation = []

    def chat(self, user_message):
        """自然语言对话入口"""
        self.conversation.append({"role": "user", "content": user_message})

        # 构建 Function Calling 请求
        response = self._call_deepseek_with_functions()

        if response:
            self.conversation.append({"role": "assistant", "content": response})
        return response

    def _call_deepseek_with_functions(self):
        """带 Function Calling 的 DeepSeek 调用"""
        if not self.api_key or len(self.api_key) < 10:
            return self._local_fallback()

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "execute_sql",
                    "description": "执行只读SQL查询数据库。仅支持SELECT语句，表名必须在白名单中。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string", "description": "只读SELECT语句"}
                        },
                        "required": ["sql"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_today_summary",
                    "description": "获取今日数据采集和运营的概览统计",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_exception_detail",
                    "description": "获取指定异常类型的详细分析报告",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "exception_type": {"type": "string", "description": "异常类型，如：登录失败/网络超时/数据为空"}
                        },
                        "required": ["exception_type"]
                    }
                }
            }
        ]

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
        ] + self.conversation[-5:]  # 最近5轮对话

        try:
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.3,
                    "max_tokens": 1500
                },
                timeout=30
            )

            if resp.status_code != 200:
                return self._local_fallback()

            result = resp.json()
            msg = result["choices"][0]["message"]

            # 检查是否需要调用函数
            if "tool_calls" in msg and msg["tool_calls"]:
                tool_results = []
                for tc in msg["tool_calls"]:
                    func_name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])

                    if func_name == "execute_sql":
                        result_text = self._safe_execute_sql(args.get("sql", ""))
                    elif func_name == "get_today_summary":
                        result_text = self._get_today_summary()
                    elif func_name == "get_exception_detail":
                        result_text = self._get_exception_detail(args.get("exception_type", ""))
                    else:
                        result_text = "未知函数"

                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_text
                    })

                # 二次调用：用函数结果生成最终回复
                resp2 = requests.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "deepseek-chat",
                        "messages": messages + [msg] + tool_results,
                        "temperature": 0.3,
                        "max_tokens": 1000
                    },
                    timeout=30
                )
                if resp2.status_code == 200:
                    return resp2.json()["choices"][0]["message"]["content"]

            return msg.get("content", "")

        except Exception as e:
            return f"[AI助手] 请求异常: {e}\n\n建议: 检查 DeepSeek API 连接或联系管理员。"

    def _safe_execute_sql(self, sql):
        """安全执行只读SQL"""
        if not self.db:
            return "数据库连接不可用"

        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            return "仅支持SELECT查询"
        for keyword in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"]:
            if keyword in sql_upper.split():
                return f"禁止{keyword}操作"

        # 检查表名白名单
        for table in self.ALLOWED_TABLES:
            if table in sql.lower():
                break
        else:
            return "查询的表不在白名单中"

        try:
            conn = self.db.get_connection() if hasattr(self.db, 'get_connection') else None
            if not conn:
                return "数据库连接不可用"

            import pandas as pd
            df = pd.read_sql(sql, conn)
            conn.close()

            if df.empty:
                return "查询结果为空"
            if len(df) > 50:
                return f"查询返回 {len(df)} 行（仅显示前20行）:\n" + df.head(20).to_markdown(index=False)
            return df.to_markdown(index=False)
        except Exception as e:
            return f"SQL执行失败: {str(e)[:200]}"

    def _get_today_summary(self):
        """今日运营概览"""
        if not self.db:
            return "数据库不可用"

        try:
            conn = self.db.get_connection() if hasattr(self.db, 'get_connection') else None
            if not conn: return "数据库不可用"

            summary = []
            tables = {
                'ods_order_raw': ('order_date', '今日订单'),
                'ods_sales_raw': ('sale_date', '今日销量记录'),
                'ods_advertising_raw': ('ad_date', '今日广告记录'),
                'ods_agreement_raw': ('crawl_time', '今日协议记录'),
                'ods_sina_news_raw': ('crawl_time', '今日新闻采集'),
            }
            for table, (date_col, label) in tables.items():
                try:
                    import pandas as pd
                    df = pd.read_sql(
                        f"SELECT COUNT(*) as cnt FROM {table} WHERE DATE({date_col}) = CURDATE()",
                        conn
                    )
                    cnt = df['cnt'].iloc[0]
                    summary.append(f"{label}: {cnt} 条")
                except:
                    pass

            # 异常
            try:
                df = pd.read_sql("SELECT COUNT(*) as cnt FROM rpa_exception_log WHERE DATE(create_time)=CURDATE()", conn)
                summary.append(f"今日异常: {df['cnt'].iloc[0]} 次")
            except: pass

            # 任务
            try:
                df = pd.read_sql("SELECT task_status, COUNT(*) as cnt FROM task_queue WHERE DATE(create_time)=CURDATE() GROUP BY task_status", conn)
                for _, r in df.iterrows():
                    summary.append(f"今日任务{r['task_status']}: {r['cnt']} 个")
            except: pass

            conn.close()
            return "\n".join(summary) if summary else "暂无今日数据"
        except Exception as e:
            return f"查询失败: {e}"

    def _get_exception_detail(self, exception_type):
        """异常详细分析"""
        if not self.db: return "数据库不可用"
        try:
            conn = self.db.get_connection() if hasattr(self.db, 'get_connection') else None
            if not conn: return "数据库不可用"

            import pandas as pd
            # 最近7天该类型异常
            df = pd.read_sql(
                "SELECT shop_name, error_message, create_time FROM rpa_exception_log "
                "WHERE exception_type=%s AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY) "
                "ORDER BY create_time DESC LIMIT 20",
                conn, params=(exception_type,)
            )
            conn.close()

            if df.empty:
                return f"最近7天无「{exception_type}」异常"

            shops = df['shop_name'].value_counts().head(5).to_dict()
            lines = [f"最近7天「{exception_type}」共 {len(df)} 次"]
            lines.append("受影响店铺TOP5:")
            for shop, cnt in shops.items():
                lines.append(f"  - {shop}: {cnt}次")
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"

    def _local_fallback(self):
        """无API时的本地兜底回复"""
        msg = self.conversation[-1]["content"].lower() if self.conversation else ""
        if "今天" in msg or "今日" in msg or "概览" in msg:
            return self._get_today_summary()
        if "异常" in msg or "错误" in msg or "报错" in msg:
            return "建议前往 Admin → SQL巡检 或 ETL执行记录 查看异常详情。需要我分析具体哪种异常吗？（登录失败/网络超时/数据为空/元素定位失败）"
        return "我是 AI 运营助手，可以帮你：\n1. 查询今日数据概览\n2. 分析异常趋势\n3. 执行数据查询\n请告诉我你需要什么？"
