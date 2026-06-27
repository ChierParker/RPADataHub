# rpa-health-scanner — 流程健康度巡检

## 定位
一键扫描任务成功率、店铺活跃度、异常频率、ETL 成功率，生成红黄绿灯评分与改进建议。

## 触发方式
- Admin → 智能运维 → 点击"一键扫描"
- Agent 对话: "扫描系统健康"

## 数据来源
- `task_queue` — 近 7 天任务状态分布
- `rpa_exception_log` — 近 7 天异常频率
- `task_record` — 活跃店铺数
- `etl_process_log` — ETL 成功率

## 输出
```json
{
  "overall_score": 71.6,
  "overall_grade": "RED",
  "modules": [
    {"name": "任务成功率", "value": "85.2%", "grade": "YELLOW"},
    {"name": "异常频率", "value": "29次/7天", "grade": "RED"},
    {"name": "活跃店铺", "value": "7个", "grade": "GREEN"},
    {"name": "ETL成功率", "value": "96.5%", "grade": "GREEN"}
  ],
  "suggestions": ["存在红色告警模块", "近7天异常29次"]
}
```

## 评分规则
- GREEN: 任务成功率 ≥95% / 异常 <5次 / 活跃店铺 ≥4 / ETL ≥95%
- YELLOW: 指标在 80%-95% 之间
- RED: 指标 <80%
- 综合评分: 四个模块加权平均
- 综合评级: 任一模块 RED → 综合 RED
