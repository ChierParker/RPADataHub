"""
RPAOps-Agent — RPA 智能运维数字员工
自然语言 → 意图识别 → 技能路由 → 格式化返回
"""

import re
from Skill.rpa_health_scanner.main import scan
from Skill.rpa_task_summary.main import generate
from Skill.rpa_diagnose.main import diagnose


# 意图路由表
INTENT_TABLE = {
    "health": {
        "keywords": ["扫描", "健康", "巡检", "体检", "状态", "概况"],
        "handler": "scan",
        "description": "系统健康度巡检"
    },
    "summary": {
        "keywords": ["日报", "今天", "总结", "报告", "情况", "简报", "汇总", "今日"],
        "handler": "summary",
        "description": "任务执行日报"
    },
    "diagnose": {
        "keywords": ["诊断", "异常", "问题", "失败", "超时", "报错", "错误",
                      "登录", "网络", "数据为空", "定位", "DB", "数据库"],
        "handler": "diagnose",
        "description": "异常智能诊断"
    },
    "biz_query": {
        "keywords": ["gmv", "平台", "排名", "广告", "退款", "花费", "排行",
                      "新闻", "新浪", "数据量", "采集", "趋势", "订单", "销量",
                      "费用", "折扣", "促销", "店铺", "成功率", "任务"],
        "handler": "biz_query",
        "description": "业务数据查询"
    },
}


class RPAOpsAgent:
    """RPA 智能运维 Agent"""

    def __init__(self, db_query, ai_call=None):
        self.db_query = db_query
        self.ai_call = ai_call
        self._register_skills()

    def _register_skills(self):
        """注册技能处理器"""
        self._handlers = {
            "scan": lambda: scan(self.db_query),
            "summary": lambda: generate(self.db_query, self.ai_call),
            "diagnose": lambda msg, etype="": diagnose(self.db_query, msg, etype, self.ai_call),
            "biz_query": lambda msg: self._handle_biz(msg),
        }

    # ============================================================
    # 意图解析
    # ============================================================

    def parse_intent(self, message):
        """
        从自然语言中解析运维意图
        返回: (intent, confidence)
        """
        msg_lower = message.lower()
        for intent, config in INTENT_TABLE.items():
            for kw in config["keywords"]:
                if kw in msg_lower:
                    return intent, 0.9
        return None, 0.0

    def extract_type(self, message):
        """从消息中提取异常类型"""
        type_map = {
            "登录": "登录失败", "网络": "网络超时", "超时": "网络超时",
            "数据为空": "数据为空", "没有数据": "数据为空",
            "定位": "元素定位失败", "元素": "元素定位失败",
            "DB": "DB异常", "数据库": "DB异常",
        }
        for kw, etype in type_map.items():
            if kw in message:
                return etype
        return ""

    # ============================================================
    # 路由执行
    # ============================================================

    def run(self, message):
        """
        执行 Agent 对话
        返回: {"intent": str, "data": dict, "reply": str}
        """
        intent, conf = self.parse_intent(message)
        data = {}
        reply = ""

        if intent == "health":
            data = self._handlers["scan"]()
            reply = self._format_health(data)

        elif intent == "summary":
            data = self._handlers["summary"]()
            reply = data.get("summary", "暂无数据")

        elif intent == "diagnose":
            etype = self.extract_type(message)
            data = self._handlers["diagnose"](message, etype)
            reply = self._format_diagnose(data)

        elif intent == "biz_query":
            reply = self._handlers["biz_query"](message)

        else:
            reply = (
                "我是 RPAOps-Agent，可以帮你：\n"
                "• 扫描系统健康状态\n"
                "• 生成今日任务日报\n"
                "• 诊断异常根因\n"
                "请直接告诉我你想做什么？"
            )

        return {"intent": intent, "data": data, "reply": reply}

    # ============================================================
    # 格式化回复
    # ============================================================

    def _format_health(self, data):
        lines = [f"📊 系统健康评分: {data['overall_score']} ({data['overall_grade']})"]
        emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
        for m in data.get("modules", []):
            lines.append(f"  {emoji.get(m['grade'], '⚪')} {m['name']}: {m['value']}")
        for s in data.get("suggestions", []):
            lines.append(f"  ⚠ {s}")
        return "\n".join(lines)

    def _format_diagnose(self, data):
        parts = []
        if data.get("root_cause"):
            parts.append(f"🔍 根因: {data['root_cause']}")
        if data.get("suggestion"):
            parts.append(f"💡 方案: {data['suggestion']}")
        if data.get("impact"):
            parts.append(f"📊 影响: {data['impact']}")
        if data.get("confidence"):
            parts.append(f"置信度: {data['confidence']}%")
        return "\n".join(parts) if parts else "诊断未返回结果"


# ============================================================
# 便捷函数
# ============================================================

    def _handle_biz(self, message):
        """处理业务查询: 关键词匹配 → SQL → 返回表格"""
        import pandas as pd
        m = message.lower()
        sql = None
        if any(w in m for w in ['gmv','平台','排名']):
            sql = "SELECT ds.platform, SUM(s.revenue) revenue FROM ods_sales_raw s JOIN dim_shop_info ds ON s.shop_name=ds.shop_name WHERE s.sale_date>=DATE_SUB(CURDATE(),INTERVAL 30 DAY) GROUP BY ds.platform ORDER BY revenue DESC"
        elif '广告' in m and ('花费' in m or '排行' in m):
            sql = "SELECT shop_name, SUM(spend) spend FROM ods_advertising_raw WHERE ad_date>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) GROUP BY shop_name ORDER BY spend DESC LIMIT 5"
        elif '退款' in m:
            sql = "SELECT shop_name, SUM(refund_amount) refund FROM ods_sales_raw WHERE sale_date>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) GROUP BY shop_name ORDER BY refund DESC LIMIT 5"
        elif '新闻' in m or '新浪' in m:
            sql = "SELECT DATE(crawl_time) dt, COUNT(*) cnt FROM ods_sina_news_raw WHERE crawl_time>=DATE_SUB(CURDATE(),INTERVAL 14 DAY) GROUP BY DATE(crawl_time) ORDER BY dt DESC"
        elif any(w in m for w in ['今天','今日','概览','采集','数据量']):
            parts = []
            for table, dc in [('ods_order_raw','order_date'),('ods_sales_raw','sale_date'),('ods_advertising_raw','ad_date'),('ods_sina_news_raw','crawl_time')]:
                try:
                    df = self.db_query(f"SELECT COUNT(*) c FROM {table} WHERE DATE({dc})=CURDATE()")
                    parts.append(f"{table}: {int(df['c'].iloc[0])}条")
                except: pass
            return "\n".join(parts) if parts else "暂无数据"
        elif '任务' in m and '成功' in m:
            sql = "SELECT task_status, COUNT(*) cnt FROM task_queue WHERE create_time>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) GROUP BY task_status"

        if sql:
            try:
                df = self.db_query(sql)
                if df.empty: return "查询结果为空"
                return df.head(15).to_markdown(index=False)
            except Exception as e:
                return f"查询失败: {e}"
        return "请具体描述想查询的数据，如: 各平台GMV排名、广告花费排行、今日概览"

def create_agent(db_query, api_key=None):
    """创建 Agent 实例"""
    ai_call = None
    if api_key:
        import requests
        def _ai(prompt):
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 400, "temperature": 0.3},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            return ""
        ai_call = _ai
    return RPAOpsAgent(db_query, ai_call)
