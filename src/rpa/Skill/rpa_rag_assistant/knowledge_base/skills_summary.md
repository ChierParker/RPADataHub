# RPADataHub Skill 技能文档汇总

## Skill 1: rpa-health-scanner 流程健康度巡检
一键扫描任务成功率、店铺活跃度、异常频率、ETL成功率，生成红黄绿灯评分。
评分规则: GREEN(≥95%) / YELLOW(80-95%) / RED(<80%)
触发方式: Admin→AI运营中心→点击"一键扫描" 或 对话发送"扫描系统健康"

## Skill 2: rpa-task-summary 任务执行日报
查询今日任务状态分布、店铺采集记录数，通过DeepSeek生成自然语言日报。
数据来源: task_queue(今日任务状态) + task_record(采集记录) + task_summary(成功率)
触发方式: Admin→AI运营中心→点击"生成日报" 或 对话发送"今天任务情况"

## Skill 3: rpa-diagnose 智能诊断
输入异常问题或选择异常类型，自动聚合上下文(历史同类异常+今日任务状态)，
AI分析返回根因(不超过3个，按可能性排序)、推荐方案(分步骤)、业务影响(高/中/低)、置信度。
支持异常类型: 登录失败、网络超时、数据为空、元素定位失败、DB异常
触发方式: Admin→AI运营中心→选择异常类型+描述→点击"诊断"

## RPAOps-Agent 智能运维数字员工
统筹所有Skill，自然语言→意图识别→技能路由→格式化回复。
意图路由表:
- 扫描/健康/巡检 → health-scanner
- 日报/今天/总结 → task-summary
- 诊断/异常/问题 → diagnose
- GMV/广告/退款 → biz_query(业务数据查询)
