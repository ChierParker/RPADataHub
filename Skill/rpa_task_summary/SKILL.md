# rpa-task-summary — 任务执行日报

## 定位
查询数据库，聚合今日任务执行统计，通过 AI 生成自然语言日报。

## 触发方式
- Admin → 智能运维 → 点击"生成日报"
- Agent 对话: "今天任务情况"

## 数据来源
- `task_queue` — 今日任务状态分布
- `task_record` — 店铺采集记录数
- `task_summary` — 任务成功率

## 输出
```json
{
  "summary": "今日RPA执行任务共19个，成功10个，失败9个，需排查失败原因。",
  "details": ["SUCCESS: 10个", "FAILED: 9个", "店铺采集记录: 64条", "成功采集店铺: 11个"]
}
```
