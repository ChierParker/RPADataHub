"""
rpa-health-scanner — 流程健康度巡检
一键扫描任务成功率、店铺活跃度、异常频率、ETL成功率，生成红黄绿灯评分。
"""


def scan(db_query):
    """
    执行健康扫描
    db_query: 数据库查询函数 query(sql, params=None) -> pd.DataFrame
    返回: dict
    """
    result = {"overall_score": 0, "overall_grade": "GREEN", "modules": [], "suggestions": []}

    try:
        # 1. 任务成功率(近7天)
        df = db_query(
            "SELECT task_status, COUNT(*) c FROM task_queue "
            "WHERE create_time>=DATE_SUB(NOW(),INTERVAL 7 DAY) GROUP BY task_status"
        )
        total = int(df["c"].sum())
        success_vals = df[df["task_status"] == "SUCCESS"]["c"]
        success = int(success_vals.sum()) if not success_vals.empty else 0
        task_rate = round(success / total * 100, 1) if total > 0 else 0
        task_grade = "GREEN" if task_rate >= 95 else "YELLOW" if task_rate >= 80 else "RED"
        result["modules"].append({
            "name": "任务成功率", "value": f"{task_rate}%", "grade": task_grade,
            "detail": f"{success}/{total}"
        })

        # 2. 异常频率(近7天)
        df2 = db_query(
            "SELECT COUNT(*) c FROM rpa_exception_log "
            "WHERE create_time>=DATE_SUB(NOW(),INTERVAL 7 DAY)"
        )
        exc_cnt = int(df2["c"].iloc[0])
        exc_grade = "GREEN" if exc_cnt < 5 else "YELLOW" if exc_cnt < 15 else "RED"
        result["modules"].append({
            "name": "异常频率", "value": f"{exc_cnt}次/7天", "grade": exc_grade
        })

        # 3. 店铺活跃度
        df3 = db_query(
            "SELECT COUNT(DISTINCT shop_name) c FROM task_record "
            "WHERE collect_result='SUCCESS' AND create_time>=DATE_SUB(NOW(),INTERVAL 7 DAY)"
        )
        active = int(df3["c"].iloc[0])
        active_grade = "GREEN" if active >= 4 else "YELLOW" if active >= 2 else "RED"
        result["modules"].append({
            "name": "活跃店铺", "value": f"{active}个", "grade": active_grade
        })

        # 4. ETL健康
        df4 = db_query(
            "SELECT status, COUNT(*) c FROM etl_process_log "
            "WHERE start_time>=DATE_SUB(NOW(),INTERVAL 7 DAY) GROUP BY status"
        )
        etl_total = int(df4["c"].sum())
        etl_success_vals = df4[df4["status"] == "SUCCESS"]["c"]
        etl_success = int(etl_success_vals.sum()) if not etl_success_vals.empty else 0
        etl_rate = round(etl_success / etl_total * 100, 1) if etl_total > 0 else 0
        etl_grade = "GREEN" if etl_rate >= 95 else "YELLOW" if etl_rate >= 80 else "RED"
        result["modules"].append({
            "name": "ETL成功率", "value": f"{etl_rate}%", "grade": etl_grade
        })

        # 综合评分
        grades = [m["grade"] for m in result["modules"]]
        score = round((task_rate + etl_rate
                       + min(100, max(0, 100 - exc_cnt * 5))
                       + min(100, active * 10)) / 4, 1)
        result["overall_score"] = score
        if "RED" in grades:
            result["overall_grade"] = "RED"
        elif "YELLOW" in grades:
            result["overall_grade"] = "YELLOW"

        # 建议
        if result["overall_grade"] == "RED":
            result["suggestions"].append("存在红色告警模块, 建议立即排查")
        if exc_cnt > 10:
            result["suggestions"].append(f"近7天异常{exc_cnt}次, 建议查看SQL巡检详情")
        if task_rate < 90:
            result["suggestions"].append(f"任务成功率仅{task_rate}%, 建议优化失败任务")
        if etl_rate < 95:
            result["suggestions"].append(f"ETL成功率{etl_rate}%, 建议检查文件消费管线")

    except Exception as e:
        result["error"] = str(e)

    return result
