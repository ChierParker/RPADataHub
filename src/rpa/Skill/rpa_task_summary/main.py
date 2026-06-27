"""
rpa-task-summary — 任务执行日报
查询数据库，聚合任务统计，AI生成自然语言日报。
"""


def generate(db_query, ai_call=None):
    """
    生成任务日报
    db_query: 数据库查询函数
    ai_call: AI调用函数 ai_call(prompt) -> str，为None时返回原始数据
    """
    raw = []
    try:
        # 今日任务状态
        df = db_query(
            "SELECT task_status, COUNT(*) c FROM task_queue "
            "WHERE DATE(create_time)=CURDATE() GROUP BY task_status"
        )
        for _, r in df.iterrows():
            raw.append(f"{r['task_status']}: {int(r['c'])}个")

        # 今日采集记录
        df2 = db_query(
            "SELECT COUNT(*) c FROM task_record WHERE DATE(create_time)=CURDATE()"
        )
        raw.append(f"店铺采集记录: {int(df2['c'].iloc[0])}条")

        # 成功店铺数
        df3 = db_query(
            "SELECT COUNT(DISTINCT shop_name) c FROM task_record "
            "WHERE DATE(create_time)=CURDATE() AND collect_result='SUCCESS'"
        )
        raw.append(f"成功采集店铺: {int(df3['c'].iloc[0])}个")

        raw_text = "; ".join(raw)

        # AI润色
        if ai_call:
            try:
                prompt = f"根据以下数据生成一段50字内的RPA任务执行日报，简洁专业: {raw_text}"
                raw_text = ai_call(prompt)
            except Exception:
                pass

        return {"summary": raw_text, "details": raw}

    except Exception as e:
        return {"summary": f"生成失败: {e}", "details": []}
