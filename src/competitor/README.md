# CompetitorWatch - 电商竞品竞价采集与智能分析系统

自动化竞品情报平台，覆盖京东/淘宝/Amazon/Walmart 等主流电商平台。
通过 Playwright 浏览器自动化采集价格、排名、广告位数据，结合 DeepSeek AI 生成智能分析报告。

## 技术栈

| 层级 | 技术 |
|---|---|
| 后端框架 | Python 3.10+ / Flask |
| 前端 | Bootstrap 5 + Chart.js + Vanilla JS |
| 浏览器自动化 | Playwright (sync_api) |
| 消息队列 | Redis List (BRPOP/LPUSH) |
| 数据库 | MySQL 8.0 (ODS → DW 分层) |
| AI 分析 | DeepSeek Chat API |
| 日志 | TraceLogger (Trace ID 全链路追踪) |

## 快速启动

### 前置条件

1. **MySQL 8.0** 已启动在 localhost:3306
2. **Redis** 已启动在 localhost:6379
3. **Python 3.10+** 已安装
4. **Playwright Chromium** 浏览器已安装

### 一键启动 (Windows)

`atch

# 1. 配置环境变量

copy .env.docker .env

# 编辑 .env，填入你的数据库密码、DeepSeek API Key

# 2. 安装依赖 + 初始化数据库

start.bat → 选择 [5] 安装依赖
start.bat → 选择 [4] 初始化数据库

# 3. 一键启动

start.bat → 选择 [1] 一键启动全部服务
`

### 手动启动

`ash

# 1. 安装依赖

pip install -r requirements.txt
playwright install chromium

# 2. 配置环境

copy .env.docker .env

# 编辑 .env 填入真实值

# 3. 初始化数据库

python -c "exec(open('sql/init_tables.sql','r',encoding='utf-8').read())"

# 4. 启动 Admin (终端1)

python app.py

# 5. 启动 Worker (终端2)

python worker.py --region both
`

### 访问地址

- 竞品管理: <http://localhost:5100/competitor/manage>
- 竞价看板: <http://localhost:5100/competitor/dashboard>
- AI 报告: <http://localhost:5100/competitor/reports>

## 测试步骤

### 1. 基础功能测试

`ash

# 运行全部单元测试

python -m pytest tests/ -v

# 运行特定模块测试

python -m pytest tests/test_settings.py -v
python -m pytest tests/test_db_operations.py -v
python -m pytest tests/test_collectors.py -v
python -m pytest tests/test_ai_analyzer.py -v
`

### 2. 国内平台采集测试 (京东/淘宝)

`ash

# 步骤 1: 启动 Admin

start.bat → 选择 [2] 仅启动 Admin

# 步骤 2: 启动 Worker  

start.bat → 选择 [3] 仅启动 Worker → 选择 domestic

# 步骤 3: 打开管理页面

浏览器访问 <http://localhost:5100/competitor/manage>

# 步骤 4: 创建竞品配置

- 点击"新增竞品"
- 板块选择"国内"
- 平台选择"京东"或"淘宝"
- 输入竞品名称和关键词
- 采集条数: 建议先填 10-20 条测试

# 步骤 5: 触发采集

- 关闭"无头模式"开关（有头模式可看到浏览器操作）
- 点击竞品行的"采集"按钮
- 浏览器会自动打开，导航到搜索页面
- 如需登录：扫码/输入账号密码 → 点击"确认登录完成"按钮
- 等待采集完成，查看结果

# 步骤 6: 查看结果

- 切换到"竞价看板"页面
- 选择刚才采集的竞品
- 查看价格趋势图和数据明细
`

### 3. 国际平台采集测试 (Amazon)

`ash

# 步骤同上，竞品配置时

# - 板块选择"国际"

# - 平台选择"Amazon"

# - 需要配置代理 (可选，在 .env 中设置 HTTP_PROXY)

`

### 4. 常见问题排查

| 问题 | 检查项 |
|---|---|
| 采集数据为0条 | 检查 Worker 日志，确认页面是否正确加载 |
| Redis 超时报错 | 确认 Redis 服务已启动，密码配置正确 |
| 登录后立即跳过 | 登录完成后需点击"确认登录完成"按钮 |
| 页面检测到验证码 | 切换"有头模式"，手动完成验证后重试 |
| MySQL 连接失败 | 检查 .env 中数据库密码是否正确 |

## 项目结构

`
CompetitorWatch/
├── app.py                    # Flask Admin 应用入口
├── worker.py                 # Worker 采集入口 (多进程)
├── logger_config.py          # 结构化日志模块
├── requirements.txt          # Python 依赖
├── start.bat                 # Windows 一键启动脚本
├── Dockerfile                # Docker 镜像定义
├── docker-compose.yml        # Docker Compose 编排
├── .env                      # 环境配置 (不提交)
├── .env.docker               # Docker 环境模板
├── .gitignore                # Git 忽略规则
├── config/
│   └── settings.py           # 统一配置中心 (环境变量驱动)
├── core/
│   └── db_operations.py      # 数据库操作层 (参数化查询)
├── mq/
│   └── redis_queue.py        # Redis 消息队列管理
├── collectors/
│   ├── base_collector.py     # 采集器抽象基类
│   ├── amazon_collector.py   # Amazon 平台采集器
│   ├── jd_collector.py       # 京东平台采集器
│   └── taobao_collector.py   # 淘宝平台采集器
├── services/
│   └── ai_analyzer.py        # AI 分析服务 (DeepSeek API)
├── templates/
│   ├── manage.html           # 竞品管理页面
│   ├── dashboard.html        # 竞价看板页面
│   └── reports.html          # AI 报告页面
├── tests/
│   ├── test_settings.py      # 配置模块测试
│   ├── test_db_operations.py # 数据库层测试
│   ├── test_collectors.py    # 采集器测试
│   └── test_ai_analyzer.py   # AI 分析测试
└── sql/
    └── init_tables.sql       # 数据库初始化 SQL
`

## API 文档

所有 API 返回统一 JSON 信封格式:
`json
{"success": true, "data": {}, "error": ""}
`

### 竞品管理 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/competitor/list?region=&platform= | 竞品配置列表 |
| GET | /api/competitor/get?id= | 单个竞品详情 |
| POST | /api/competitor/create | 新增竞品 |
| POST | /api/competitor/update?id= | 更新竞品 |
| POST | /api/competitor/toggle?id= | 启用/停用 |
| POST | /api/competitor/delete?id= | 删除竞品 |
| POST | /api/competitor/crawl?id=&headless=&max_results= | 触发采集 |
| GET | /api/competitor/crawl_status?task_uuid= | 采集状态轮询 |
| POST | /api/competitor/login_confirm?task_uuid= | 确认登录完成 |

### 看板数据 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/competitor/trend?id=&days=30 | 价格趋势数据 |
| GET | /api/competitor/snapshots?id=&limit=30 | 最新快照明细 |

### AI 报告 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/competitor/reports?competitor_id=&type= | 报告列表 |
| GET | /api/competitor/report_detail?id= | 报告详情 |
| POST | /api/competitor/generate_report | 生成 AI 报告 |

## Worker 启动参数

`ash
python worker.py                              # 监听全部区域
python worker.py --region international       # 仅国际板块
python worker.py --region domestic            # 仅国内板块
python worker.py --once --region domestic     # 单次测试执行
python worker.py --db                         # 强制 DB 降级模式
python worker.py --workers 4                  # 4 个 Worker 进程
`

## 平台覆盖

| 平台 | 板块 | 状态 |
|---|---|---|
| Amazon | 国际 | ✅ 已实现 |
| Amazon | 国内 | ✅ 已实现 |
| Walmart | 国际 | ⚠️ 降级为 Amazon 模式 |
| 京东 (JD) | 国内 | ✅ 已实现 |
| 淘宝 (Taobao) | 国内 | ✅ 已实现 |
| 拼多多 (PDD) | 国内 | ❌ 计划中 |
| Shopee | 国际 | ❌ 计划中 |

## 架构原则

本项目遵循 UNIVERSAL_DEV_STANDARDS.md:

- 禁止硬编码密钥 (全部从环境变量读取)
- 参数化 SQL 查询 (防 SQL 注入)
- 运行时产物通过 .gitignore 排除
- 结构化日志 + trace_id 全链路追踪
- 优雅错误隔离 (单条失败不影响整体)

## License

仅供学习和内部运营使用。所有采集目标均为公开平台页面。
请遵守目标平台的 robots.txt 和服务条款。

<br>

## 🔗 EcomIQ 统一框架集成

CompetitorWatch 已作为 **Flask Blueprint** 集成到 [EcomIQ-RPA](../../README.md) 统一平台中。

### 在 EcomIQ 中的访问方式

| 功能 | EcomIQ-RPA 路由 | 说明 |
|:---|:---|:---|
| 竞品管理 | `/competitor/manage` | 竞品CRUD + 采集任务下发 |
| 竞价看板 | `/competitor/dashboard` | 价格趋势 + 排名 + 广告位 |
| AI 报告 | `/competitor/reports` | AI 日报/周报生成 |

### 在大框架中启动

```bash
python -m src.main.app        # 纯 Web 模式
start_services.bat   # 全栈模式
```

启动后访问 `http://localhost:5000`，通过左侧导航栏 → **竞品分析** 进入。

### 数据库初始化（首次使用）

```bash
python src/competitor/sql/setup_db.py
```

将在共享的 `data` 数据库中创建 4 张表：`competitor_config`, `ods_price_snapshot`, `dw_competitor_daily`, `competitor_report`。

> **注意**：在大框架模式下，`app.py` 不再需要单独运行（原端口 5100）。所有功能通过 Blueprint 挂载在 `/competitor` 下。

### 更新日志

| 版本 | 日期 | 变更 |
|:---|:---|:---|
| v1.1 | 2026-06-25 | EcomIQ-RPA 统一集成、Blueprint 封装、API 路径适配 |
| v1.0 | 2026-06-14 | 原始独立版本 |
