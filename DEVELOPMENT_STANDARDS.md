# EcomIQ-RPA 开发规范与架构约束

> 适用范围：EcomIQ-RPA 平台全部模块（main / rpa / competitor / leads）
>
> 使用方式：在给 AI 或协作者的任务说明中加入：
>
> **请遵守项目根目录下的 `DEVELOPMENT_STANDARDS.md` 进行开发、重构和代码审查。**

---

## 0. 约束等级

本文使用三个等级：

- **MUST**：必须遵守。违反后可能造成安全、数据、部署或维护风险。
- **SHOULD**：默认应遵守。若场景不适合，可说明原因后暂缓。
- **MAY**：可选优化。适合长期维护或产品化阶段。

优先级：安全与数据完整性 > 用户可用性 > 可维护性 > 代码风格。

---

## 1. 项目结构与职责分离

### MUST

每个模块（`.py` 文件）必须有单一、明确的职责：

| 模块 | 允许的职责 | 禁止的职责 |
|------|-----------|-----------|
| `app.py` / `admin_server.py` | Flask 路由定义、请求解析、HTTP 响应 | 业务逻辑、数据库操作、文件解析 |
| `scraper.py` / `worker.py` | 浏览器控制、采集编排、搜索流程 | Excel 读写、邮件发送 |
| `config.py` | 全局常量、路径声明、配置加载 | 任何运行时逻辑 |
| `*_processing.py` | 纯数据处理（正则、去重、清洗） | 浏览器操作、HTTP 请求 |
| `*_exporter.py` | 文件导出/格式化 | 数据采集、网络请求 |
| `logger_config.py` | 日志器初始化、格式化、轮转 | 业务逻辑 |
| `blueprint.py` | Flask Blueprint 注册 | 业务逻辑 |

### SHOULD

- 单文件不超过 800 行，单函数不超过 60 行
- 超过上限应拆分为子模块或私有函数
- 不要把框架入口 + 业务编排 + 数据访问混在同一个文件

### 目录结构约定

```
EcomIQ-RPA/
├── src/
│   ├── main/        # 统一入口（Hub）
│   ├── rpa/         # 数据采集与运维
│   ├── competitor/  # 竞品分析
│   └── leads/       # 客户开发
├── docs/            # 设计文档
├── README.md
├── requirements.txt
├── .gitignore
└── .env
```

每个子模块内部结构：
```
module/
├── app.py / admin_server.py  # 入口
├── blueprint.py              # EcomIQ-RPA 蓝图封装
├── config.py / settings.py   # 配置
├── *_processing.py           # 数据处理
├── *_exporter.py             # 文件导出
├── logger_config.py          # 日志
├── templates/ / static/      # 前端
├── tests/                    # 测试
├── input/ output/ logs/      # 运行时数据（gitignore）
└── README.md
```

---

## 2. 编码规范

### MUST

- 所有源码、配置、文档使用 **UTF-8 without BOM** 编码
- `open()` 调用必须显式指定 `encoding="utf-8"`
- 每个 `.py` 文件以 docstring 开头，说明模块职责

### SHOULD

- 公开函数包含完整的参数和返回值注解
- 中文注释和文档正常使用

### 命名约定

| 类型 | 规则 | 示例 |
|------|------|------|
| 模块文件 | `snake_case.py` | `lead_processing.py` |
| 公开函数 | `snake_case()` | `load_targets()` |
| 私有函数 | `_snake_case()` | `_launch_browser()` |
| 类名 | `PascalCase` | `ScraperState` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_UPLOAD_SIZE_MB` |
| 全局变量 | 禁止新增；已有使用 `_prefix` | `_send_progress` |

---

## 3. 状态管理

### MUST

- 可变共享状态必须明确归属，不能散落为无保护的模块级变量
- 多线程共享状态必须有锁保护（`Lock` / `RLock`）或队列/数据库持久化
- 如果服务重启后状态丢失会造成数据丢失，状态必须持久化

### SHOULD

演进路径：
```
Prototype: 单任务状态对象
Tool: TaskManager + lock + 明确生命周期
Product: task_id + 持久化 + 可恢复
Service: 队列 + Redis/DB + worker
```

---

## 4. 配置与安全

### MUST

- 密钥、密码、API Key 不得硬编码在源码中
- 所有敏感配置从 `.env` 或 `settings.json` 读取
- `.env` 和 `settings.local.json` 必须加入 `.gitignore`
- 文件上传必须校验扩展名白名单和文件大小
- 用户传入的路径参数必须做路径遍历检查（禁止 `..`）
- SQL 查询必须使用参数化查询，禁止字符串拼接

### SHOULD

- 浏览器 Profile 包含 Cookie，禁止分享和入库
- 每个配置节包含注释说明字段
- 敏感配置赋值后重启生效

---

## 5. 测试规范

### SHOULD

| 模块类型 | 最低覆盖 | 必须覆盖的场景 |
|----------|---------|--------------|
| 纯数据处理 | 80% | 正常输入、边界值、空输入、异常输入 |
| 文件导出 | 60% | 空数据、单条、多条、重复名 |
| 采集引擎 | 40% | 核心流程、异常处理 |
| Web 路由 | 40% | 正常请求、缺参数、无效类型 |

### 测试原则

- 测试文件放在 `tests/` 目录，文件名 `test_<模块名>.py`
- 使用 `unittest` 或 `pytest` 框架
- 优先测试纯函数（输入决定输出）
- 曾经出 bug 的逻辑必须有回归测试

---

## 6. 日志规范

### MUST

- 生产代码不得依赖 `print()` 作为主要日志
- 日志必须区分级别：`DEBUG`、`INFO`、`WARNING`、`ERROR`
- 日志不得记录密码、token、cookie
- 日志文件必须轮转（单文件 ≤ 50MB，保留 30 个）

### 日志级别约定

| 级别 | 使用场景 |
|------|---------|
| `DEBUG` | 调试细节 |
| `INFO` | 正常流程节点（任务开始/完成） |
| `WARNING` | 可恢复异常（重试、跳过、超时） |
| `ERROR` | 不可恢复错误，必须传 `exc_info=True` |

---

## 7. API 规范

### SHOULD

统一 JSON 信封格式：
```json
{
  "success": true,
  "data": {},
  "error": ""
}
```

常用 HTTP 状态码：
| 场景 | 状态码 |
|------|--------|
| 成功 | 200 |
| 参数错误 | 400 |
| 未认证 | 401 |
| 无权限 | 403 |
| 冲突 | 409 |
| 服务端错误 | 500 |

---

## 8. 前端规范

### MUST

- 异步 UI 必须覆盖：初始态、加载态、成功态、空态、错误态
- 表单字段有明确校验和错误提示
- 危险操作有确认机制
- 按钮提交期间禁用，避免重复提交

### 技术选型

- Bootstrap 5（本地副本，离线可用）
- 原生 JavaScript（不引入 jQuery / React / Vue）
- 静态资源优先本地化

---

## 9. 依赖管理

### MUST

- 所有依赖写入 `requirements.txt`，固定主版本号
- 不要引入未使用的大型依赖
- 新增依赖前说明用途

---

## 10. AI 协作规则

给 AI 分派任务时，默认要求：

- 先阅读项目结构和相关文件，再修改
- 不重构无关代码
- 不删除用户数据或未确认的文件
- 修改前说明将改哪些区域
- 修改后运行可用的检查：编译、测试、lint
- 架构优化优先做小步、可验证的改动

### AI 代码审查清单

**P0: 必须修复**
- [ ] 真实密钥、cookie、token 入库
- [ ] 用户输入可导致路径遍历、SQL 注入
- [ ] 并发共享状态无保护
- [ ] 运行产物污染源码目录
- [ ] 编码损坏

**P1: 本轮应修复**
- [ ] 单文件承担多个核心职责
- [ ] 关键逻辑无法独立测试
- [ ] 文件上传缺少校验
- [ ] 错误处理只吞异常无反馈
- [ ] 魔法数字/字符串未命名

**P2: 后续优化**
- [ ] 函数过长建议拆分
- [ ] API 响应不统一
- [ ] 缺少 README 说明
- [ ] 缺少基础测试

---

## 11. EcomIQ-RPA 项目特定约定

### 模块蓝图注册

所有子模块通过 `blueprint.py` 封装 Flask Blueprint，挂载到主应用：

```python
# 主应用注册示例
from rpa.blueprint import rpa_bp
from competitor.blueprint import competitor_bp
from leads.blueprint import leads_bp

app.register_blueprint(rpa_bp, url_prefix='/rpa')
app.register_blueprint(competitor_bp, url_prefix='/competitor')
app.register_blueprint(leads_bp, url_prefix='/leads')
```

### API 路径兼容层

子模块原有 API 路径（如 `/api/upload`）通过蓝图自动映射为 `/leads/api/upload`，无需修改子模块代码。

### 数据库

- 共享 `data` 库，通过 `pymysql` 连接
- 连接池使用 `threading.local()` 线程隔离
- 不使用 ORM，统一使用参数化 SQL

---

> 最后更新：2026-06-27
>
> 核心原则：先保证安全和可恢复，再保证清晰和可测试。
