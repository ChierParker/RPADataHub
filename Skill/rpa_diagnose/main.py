"""
rpa-diagnose — 智能诊断
输入异常问题，聚合上下文，AI分析根因、方案、影响、置信度。
"""


def diagnose(db_query, issue, exception_type="", ai_call=None):
    """
    诊断异常
    db_query: 数据库查询函数
    issue: 问题描述
    exception_type: 异常类型(可选)
    ai_call: AI调用函数 ai_call(prompt) -> str
    """
    result = {"root_cause": "", "suggestion": "", "impact": "", "confidence": 0}

    try:
        # 聚合上下文
        ctx_parts = []
        if exception_type:
            df = db_query(
                "SELECT COUNT(*) c FROM rpa_exception_log "
                "WHERE exception_type=%s AND create_time>=DATE_SUB(NOW(),INTERVAL 7 DAY)",
                (exception_type,)
            )
            ctx_parts.append(f"近7天同类异常: {int(df['c'].iloc[0])}次")

        df2 = db_query(
            "SELECT task_status, COUNT(*) c FROM task_queue "
            "WHERE DATE(create_time)=CURDATE() GROUP BY task_status"
        )
        parts = [f"{row['task_status']}{int(row['c'])}" for _, row in df2.iterrows()]
        ctx_parts.append("今日任务: " + ", ".join(parts))
        ctx = "; ".join(ctx_parts)

        # AI诊断
        if ai_call:
            prompt = (
                f"你是RPA运维专家。问题: {issue}。上下文: {ctx}。"
                f"请用JSON返回诊断结果，格式: "
                f'{{"root_cause":"根因","suggestion":"方案","impact":"影响","confidence":80}}'
            )
            try:
                raw = ai_call(prompt)
                import json
                # 清理 markdown 代码块
                raw = raw.replace("```json", "").replace("```", "").strip()
                result.update(json.loads(raw))
            except Exception:
                result["root_cause"] = "AI分析超时，请手动排查"
                result["suggestion"] = "查看SQL巡检和ETL执行记录"
        else:
            result["root_cause"] = "需配置DeepSeek API Key进行智能诊断"
            result["suggestion"] = "参考: 检查同类历史异常、查看今日任务成功率、对比近7天趋势"

    except Exception as e:
        result["root_cause"] = f"诊断异常: {e}"

    return result
