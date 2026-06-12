from config.settings import get_config
"""
AI驱动的智能运维分析Agent
集成 DeepSeek API 实现: 异常根因分析 / 知识库检索 / 业务通报生成
触发时机: file_watcher.py 捕获异常后调用
"""

import json
import hashlib
import time
from datetime import datetime, timedelta
import requests


class AIOpsAgent:
    """
    智能运维Agent
    对应文档: 三、AI驱动的告警分析Agent
    """

    def __init__(self, api_key = get_config().alert.deepseek_api_key, api_url="https://api.deepseek.com/v1/chat/completions", db_manager=None):
        self.api_key = api_key
        self.api_url = api_url
        self.db = db_manager

    # ============================================================
    # 核心分析流程
    # ============================================================

    def analyze_exception(self, conn, trace_id, exception_type, error_message,
                          file_name="", shop_name="", task_uuid=""):
        """
        AI分析异常（文档四步流程）

        返回: dict with keys:
          root_cause, suggestion, business_impact, notification
        """
        # 第一步: 聚合上下文
        context = self._gather_context(conn, exception_type, error_message, file_name, shop_name)

        # 第二步: 知识库检索
        knowledge = self._search_knowledge(conn, exception_type, error_message)

        # 第三步: AI分析
        analysis = self._call_ai(exception_type, error_message, file_name, shop_name,
                                 context, knowledge)

        # 第四步: 结果落库
        if analysis and conn:
            self._save_analysis(conn, trace_id, exception_type, error_message,
                                analysis, task_uuid, shop_name)

        return analysis or self._fallback_analysis(exception_type)

    # ============================================================
    # 第一步: 上下文聚合
    # ============================================================

    def _gather_context(self, conn, exception_type, error_message, file_name, shop_name):
        """从相关表中收集异常上下文（简化版，避免复杂SQL）"""
        context = {"history_count": 0, "today_counts": {}, "affected_shops": [], "trend": []}

        if not conn:
            return context

        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS cnt FROM rpa_exception_log WHERE exception_type=%s", (exception_type,))
            row = cur.fetchone()
            context["history_count"] = row[0] if row else 0
        except:
            pass

        if shop_name:
            context["affected_shops"] = [shop_name]

        return context

    # ============================================================
    # 第二步: 知识库检索
    # ============================================================

    def _search_knowledge(self, conn, exception_type, error_message):
        """从知识库检索匹配的解决方案"""
        results = []
        if not conn:
            return results
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT exception_type, error_pattern, root_cause, solution, occur_count "
                "FROM alert_knowledge_base WHERE exception_type=%s ORDER BY occur_count DESC LIMIT 3",
                (exception_type,)
            )
            for row in cur.fetchall():
                results.append({
                    "exception_type": row[0], "error_pattern": row[1],
                    "root_cause": row[2], "solution": row[3], "occur_count": row[4]
                })
            if not results and error_message:
                for kw in error_message.split()[:3]:
                    if len(kw) > 3:
                        cur.execute(
                            "SELECT exception_type, error_pattern, root_cause, solution "
                            "FROM alert_knowledge_base WHERE error_pattern LIKE %s LIMIT 2",
                            (f"%{kw}%",)
                        )
                        for row in cur.fetchall():
                            results.append({
                                "exception_type": row[0], "error_pattern": row[1],
                                "root_cause": row[2], "solution": row[3]
                            })
        except Exception as e:
            print(f"[AI-Agent] Knowledge search failed: {e}")
        return results[:5]

    # ============================================================
    # 第三步: AI调用
    # ============================================================

    def _call_ai(self, exception_type, error_message, file_name, shop_name, context, knowledge):
        """调用DeepSeek API进行分析"""
        if not self.api_key or len(self.api_key) < 10:
            return None  # 未配置API Key，跳过AI分析

        prompt = f"""你是电商数据平台的智能运维助手。当前系统检测到以下异常：

异常类型：{exception_type}
错误详情：{error_message}
发生时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
涉及文件：{file_name or 'N/A'}
涉及店铺：{shop_name or 'N/A'}
近30天同类异常：{context.get('history_count', 0)}次
今日数据量：{json.dumps(context.get('today_counts', {}), ensure_ascii=False)}

历史解决方案参考：
{json.dumps(knowledge, ensure_ascii=False, indent=2)}

请完成以下分析并严格按JSON格式返回（不要markdown代码块）：
{{
    "root_cause": "推测最可能的原因(不超过3个，按可能性排序)",
    "suggestion": "推荐处理方案(分步骤)",
    "business_impact": "评估业务影响(高/中/低，附说明)",
    "notification": "生成一段可直接推送业务方的异常通报(100字内)"
}}"""

        try:
            resp = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1000
                },
                timeout=30
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                # 清理可能的markdown代码块
                content = content.replace("```json", "").replace("```", "").strip()
                return json.loads(content)
        except Exception:
            pass

        return None

    def _fallback_analysis(self, exception_type):
        """无API时的兜底分析"""
        fallback = {
            "登录失败": {"root_cause": "Cookie过期或账号异常", "suggestion": "重新登录并更新Cookie", "business_impact": "高"},
            "数据为空": {"root_cause": "该业务日期无数据产生", "suggestion": "标记为无数据,跳过重试", "business_impact": "低"},
            "元素定位失败": {"root_cause": "页面结构变更", "suggestion": "更新选择器配置", "business_impact": "中"},
            "网络超时": {"root_cause": "网络波动或代理异常", "suggestion": "切换代理重试", "business_impact": "中"},
            "DB异常": {"root_cause": "数据库服务异常", "suggestion": "检查MySQL服务状态", "business_impact": "高"},
        }
        fb = fallback.get(exception_type, {"root_cause": f"未知类型: {exception_type}", "suggestion": "人工排查", "business_impact": "待评估"})
        fb["notification"] = f"[RPA告警] {exception_type}: {fb['root_cause']}。建议: {fb['suggestion']}"
        return fb

    # ============================================================
    # 第四步: 结果落库
    # ============================================================

    def _save_analysis(self, conn, trace_id, exception_type, error_message, analysis, task_uuid, shop_name):
        """保存分析结果到异常日志表"""
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO rpa_exception_log
                   (trace_id, task_uuid, exception_type, error_message, shop_name,
                    ai_analysis, ai_root_cause, ai_suggestion, ai_business_impact, ai_notification)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (trace_id, task_uuid, exception_type, error_message, shop_name,
                 json.dumps(analysis, ensure_ascii=False),
                 analysis.get("root_cause", ""),
                 analysis.get("suggestion", ""),
                 analysis.get("business_impact", ""),
                 analysis.get("notification", ""))
            )
            conn.commit()
        except:
            pass
