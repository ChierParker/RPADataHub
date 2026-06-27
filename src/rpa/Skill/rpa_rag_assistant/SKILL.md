# rpa-rag-assistant — 私有 RAG 知识库问答

## 定位
基于项目架构文档 + Skill 文档 + 运维手册 + SQL 校验规则的私有 RAG 知识库，
用户用自然语言提问，系统检索相关文档片段，结合 DeepSeek 生成专业回答。

## 技术架构
```
文档(.md/.txt) → 分块(chunk 500字) → SQLite FTS5 全文索引
                                            ↓
用户提问 → 关键词检索(top 5 chunks) → 拼接 Prompt → DeepSeek 生成回答
```

## 知识库来源
- 架构文档：四层解耦/双轨采集/三层校验/技术演进
- Skill 文档：health-scanner / task-summary / diagnose / Agent
- 运维手册：常见异常处理 SOP / 故障排查 / 恢复流程
- SQL 校验规则：数据质量监控规则模板

## 使用方式
- Admin → AI 运营中心 → 自然语言提问
- "RPA 采集超时怎么排查？"
- "如何新增一个采集平台？"
- "数据质量校验规则有哪些？"
