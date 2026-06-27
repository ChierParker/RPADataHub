# RPAOps-Agent — RPA 智能运维数字员工

## 定位
7×24 小时值班的 RPA 运维专家，接收自然语言指令，自动拆解意图、路由到对应 Skill、汇总生成报告。

## 核心能力
- **意图识别**: 从自然语言中提取运维意图 (健康扫描/日报生成/异常诊断)
- **技能路由**: 根据意图自动调用对应 Skill
- **上下文感知**: 聚合系统实时数据, 提供数据驱动的分析
- **可扩展**: 新增 Skill 只需注册, Agent 自动发现

## 触发方式
- Admin → 智能运维 → 对话输入
- API: POST /api/ops/agent/chat

## 意图路由表
| 关键词 | 意图 | 调用 Skill | 返回格式 |
|--------|------|-----------|---------|
| 扫描/健康/巡检/体检 | health | rpa-health-scanner | 评分+模块列表+建议 |
| 日报/今天/总结/报告/情况 | summary | rpa-task-summary | AI日报文本+明细 |
| 诊断/异常/问题/失败/超时/报错 | diagnose | rpa-diagnose | 根因+方案+影响+置信度 |

## 架构
```
用户输入 → Agent.intent_parse() → Agent.route() → Skill.main()
                                                    ↓
用户看到 ← Agent.format_response() ← Skill 返回数据
```
