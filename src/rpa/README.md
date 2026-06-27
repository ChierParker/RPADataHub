# RPADataHub

<div align="center">

**基于 RPA + 工程化架构的规模化数据采集与运维平台**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)](https://www.mysql.com/)
[![Playwright](https://img.shields.io/badge/Playwright-latest-purple.svg)](https://playwright.dev/)
[![License](https://img.shields.io/badge/License-Internal-red.svg)]()

</div>

---

## 📋 目录

- [项目简介](#项目简介)
- [核心架构](#核心架构)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [功能模块](#功能模块)
- [Admin 管理平台](#admin-管理平台)
- [采集调度系统](#采集调度系统)
- [数据治理](#数据治理)
- [AI 智能运维](#ai-智能运维)
- [部署指南](#部署指南)

---

## 项目简介

RPADataHub 是一套面向跨境电商的**全链路数据采集与运维管理平台**，覆盖从数据采集、ETL 清洗、质量校验、DW 聚合到 BI 可视化的完整数据链路。

**核心指标：**

| 指标 | 数值 |
|------|------|
| 覆盖平台 | 10+ (Amazon/Walmart/Shopee/TEMU/Sina...) |
| 管理店铺 | 8+ |
| 日均数据量 | 10,000+ 条 |
| 采集成功率 | 99.5% |
| 异常拦截率 | 90%+ |

---

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                       Admin 管理平台 (Flask)                      │
│  ETL记录 │ SQL巡检 │ BI分析 │ 经营看板 │ 任务管理 │ 采集监控    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP
┌──────────────────────────────┼──────────────────────────────────┐
│                    数据消费层 (Watchdog + ETL)                    │
│  文件监听 → 路由匹配 → 维表校验 → ODS写入 → DW聚合 → 归档      │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│                     采集执行层 (Playwright)                       │
│  Collector Registry → Task Runner → BaseCollector → 具体采集器  │
│  MQ Consumer ← task_queue ← Admin 任务下发                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────────┐
│                   数据存储层 (MySQL)                               │
│  ODS层(贴源) → DW层(加工) → 监控表(运维) → 任务表(调度)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **采集层** | Playwright + 影刀 RPA | 双轨采集，覆盖页面+接口 |
| **Win 自动化** | pywinauto + uiautomation + OpenCV + PaddleOCR | Windows 桌面应用自动化（Win32/UIA/OCR/图像） |
| **消费层** | Python Watchdog | 文件夹监听，自动触发 ETL |
| **处理层** | Pandas + PyMySQL | 数据清洗、维表校验、幂等入库 |
| **存储层** | MySQL 8.0 | ODS → DW → DM 三级分层 |
| **调度层** | Worker + Redis List MQ | LPUSH/BRPOP 实时推送，DB 审计降级 |
| **监控层** | Flask Admin + Chart.js | 可视化运维看板 |
| **AI 层** | DeepSeek API + SQLite FTS5 | Function Calling + 3 Skills + RAG 知识库 |

---

## 项目结构

```
RPADataHub/
│
├── admin_server.py              # Flask Admin 管理平台 (15+ 页面)
├── file_watcher.py              # 文件监听 + ETL 消费服务
├── worker.py                    # 任务执行器 Agent (Redis MQ 消费)
│
├── config/
│   └── settings.py              # 全局配置中心 (支持环境变量)
│
├── Skill/                        # AI 技能插件
│   ├── rpa_ops_agent/            #   Agent 智能体
│   ├── rpa_health_scanner/       #   健康巡检
│   ├── rpa_task_summary/         #   任务日报
│   ├── rpa_diagnose/             #   智能诊断
│   └── rpa_rag_assistant/        #   RAG 知识库问答
│       └── knowledge_base/       #   架构文档/运维手册/SQL规则
│
├── core/
│   ├── db_operations.py         # 数据库操作层 (ODS/DW/连接池)
│   ├── data_validator.py        # 数据校验引擎 (维表白名单/空文件/骤降)
│   ├── alert_manager.py         # 分级告警 (P0/P1/P2 + 低频降频)
│   ├── retry_manager.py         # 自愈重试 (指数退避 + 降级兜底)
│   ├── checkpoint.py            # 断点续传 (PROCESSING → SUCCESS/FAILED)
│   ├── error_classifier.py      # MySQL 错误 → 中文运维消息
│   └── ai_agent.py              # DeepSeek AI 智能分析 Agent
│
├── routers/
│   └── route_matcher.py         # 文件夹路由匹配 (Tier1: 路径, Tier2: 文件名)
│
├── templates/                   # Admin 前端模板 (Jinja2 + Bootstrap 5)
│   ├── base.html                #    布局框架 + 侧边栏
│   ├── login.html               #    登录页 (CareerCompass风格动画)
│   ├── dashboard.html           #    ETL执行记录
│   ├── monitor.html             #    SQL巡检 + AI分析
│   ├── bi_dashboard.html        #    BI经营分析 (KPI+趋势+分布)
│   ├── dashboard_data.html      #    经营看板 (6个模块)
│   ├── tasks.html               #    任务管理 (CRUD + 启动)
│   ├── collection_*.html        #    采集监控/执行明细/店铺健康
│   ├── health_dashboard.html    #    健康总览
│   ├── shops.html               #    店铺管理
│   └── routes.html              #    路由配置
│
├── sql/
│   ├── init_tables.sql          # 运维监控表 DDL
│   ├── init_admin_tables.sql    # Admin 用户/监控/知识库表
│   └── init_task_tables.sql     # 任务调度表
│
├── static/                      # 本地静态资源 (无CDN依赖)
│   ├── bootstrap.min.css
│   ├── bootstrap-icons.css
│   └── chart.umd.js
│
├── playwright_collection_script/ # 采集脚本工程
│   ├── main.py                  #   统一任务入口
│   ├── collector_registry.py    #   采集器注册中心
│   ├── worker.py                #   本机执行代理
│   ├── task_runner.py           #   任务编排层
│   ├── schemas/                 #   数据模型 (TaskConfig/Result/Log)
│   ├── collectors/              #   采集器集合
│   │   ├── base.py              #     BaseCollector 基类
│   │   ├── sina_finance.py      #     新浪财经要闻采集
│   │   ├── amazon_login_collector.py
│   │   ├── aba_keyword_collector.py
│   │   └── amazon_po_collector.py
│   ├── runtime/                 #   运行时 (Context/Logger/Reporter)
│   ├── mq/                      #   消息队列 (Consumer/Producer)
│   ├── library/                 #   工具库
│   └── amazon_login/            #   Amazon 登录模块 (现有)
│
├── tests/                        # 单元测试
│   ├── test_error_classifier.py  #   MySQL错误分类器测试 (11项)
│   └── test_data_validator.py    #   数据校验引擎测试 (17项)
├── logger_config.py             # 结构化日志 (TraceLogger + trace_id)
├── mq/
│   └── redis_broker.py          # Redis MQ 代理 (生产/消费 + DB降级)
├── .env.example                 # 环境变量模板
└── UNIVERSAL_DEV_STANDARDS.md   # 通用开发约束与架构准则
```

---

## 快速开始

### 环境要求

- Python 3.10+ / MySQL 8.0+ / Redis (可选)

### 1. 环境配置（推荐方式）

复制 `.env.example` 为 `.env`，填入真实值即可（`python-dotenv` 自动加载）：

```bash
copy .env.example .env
# 编辑 .env 填入你的真实密钥
```

| 配置项 | 环境变量 | 说明 |
|--------|---------|------|
| MySQL 密码 | `RPA_DB_PASSWORD` | 数据库密码 |
| MySQL 连接 | `RPA_DB_HOST` / `RPA_DB_PORT` / `RPA_DB_USER` / `RPA_DB_DATABASE` | 数据库连接信息 |
| DeepSeek Key | `RPA_DEEPSEEK_API_KEY` | AI 功能必需 |
| Redis 连接 | `RPA_REDIS_URL` | 格式 `redis://:password@host:6379`，不配则自动降级 DB 轮询 |
| Bark 推送 | `RPA_BARK_URL` | 告警推送（可选） |
| Flask 密钥 | `RPA_FLASK_SECRET_KEY` | 用于 Session 签名，生产环境务必修改 |
| 文件路径 | `RPA_WATCH_FOLDER` / `RPA_ARCHIVE_FOLDER` / `RPA_LOG_DIR` | 数据目录 |

> 启动时如果看到 `[Config] 警告` 说明 `.env` 未配置或配置不完整。完整清单见 `.env.example`。

### 2. 初始化数据库

```bash
mysql -u root -p < sql/init_tables.sql
mysql -u root -p < sql/init_admin_tables.sql
mysql -u root -p < sql/init_task_tables.sql
```

### 3. 启动服务

```bash
python admin_server.py           # Admin -> http://localhost:5000
python file_watcher.py           # 文件监听 + ETL
python worker.py                 # 任务执行 Worker
```

默认管理员: `admin`，密码在 `sql/init_admin_tables.sql` 中配置。

## 功能模块

### Admin 管理平台 (18 个页面)

| 模块 | 页面 | 功能 |
|------|------|------|
| **运维监控** | ETL执行记录 | 文件处理成功/失败日志 + 详情下钻 |
| | SQL巡检 | 监控SQL模板管理 + 定时执行 + 告警处理 + **AI分析** |
| | 采集图表 | 采集量/拦截量趋势图 (Grafana风格) |
| | 健康总览 | 6 KPI + 链路状态 + 平台覆盖 |
| **任务调度** | 任务管理 | 任务配置CRUD + 一键启动 + 执行历史 |
| | 任务监控 | 任务状态看板 + 点击下钻店铺明细 |
| | 执行明细 | 按UUID/店铺/日期筛选 + 异常高亮 |
| | 店铺健康 | 7天色块矩阵 (绿/红/灰) + 异常标记 |
| **数据分析** | BI经营分析 | GMV/订单/广告/退款 KPI + 趋势图 + 平台饼图 + 下钻 |
| | 经营看板 ×6 | 订单/广告/销量/折扣/费用/协议 数据明细 + 筛选导出 |
| **AI 智能运维** | AI 运营中心 | Agent对话 + 4个Skill(巡检/日报/诊断/RAG) + 历史记录 |
| **基础管理** | 店铺管理 | 店铺维表 CRUD + 筛选导出 |
| | 路由配置 | 文件夹→ODS表 映射管理 |
| | 成员管理 | 用户列表 + 角色权限分配 |
| | 权限审批 | 权限申请审批 + 通过/拒绝 |

### 采集调度系统

```
任务配置 (task_config)
    ↓ Admin 点击"启动"
任务队列 (task_queue)  ← PENDING
    ↓ Worker BRPOP 实时消费
任务执行 (BaseCollector.run)
    ↓ 逐店铺采集
采集记录 (task_record)  ← 单店铺明细
    ↓ 汇总
任务汇总 (task_summary)  ← 成功率统计
```

### 数据治理流水线

```
Excel文件 → 文件夹路由 → L0空文件检查 → 维表白名单校验
    → 通用ODS写入(MySQL Schema兜底) → DW加工SQL(配置驱动)
    → 异常分类 → 分级告警(P0/P1/P2) → 断点续传 → 文件归档
```

---

## AI 智能运维

### Skill 插件架构 (4 Skills + 1 Agent)

| Skill | 功能 | 触发方式 |
|-------|------|---------|
| `rpa-health-scanner` | 流程健康度巡检，红黄绿灯评分 | "扫描系统健康" |
| `rpa-task-summary` | 任务执行日报，AI 自然语言总结 | "今天任务情况" |
| `rpa-diagnose` | 智能根因诊断，输出方案+影响+置信度 | "诊断登录失败" |
| `rpa-rag-assistant` | 私有 RAG 知识库，架构文档+运维手册+SQL规则问答 | "RPA超时怎么排查" |
| `RPAOps-Agent` | 自然语言意图识别，自动路由到对应 Skill | 任意对话 |

### RAG 知识库

```
文档(.md) → 分块(500字) → SQLite FTS5 全文索引
    → 用户提问 → 关键词检索(top 5 chunks)
    → 拼接 Prompt → DeepSeek 生成回答
```

知识库来源：架构文档 + 运维手册(5类异常SOP) + SQL校验规则(10+条) + Skill技术文档

### 异常分析流程

```
异常触发 → 上下文聚合(历史+店铺+数据量)
         → 知识库检索(精确+模糊匹配)
         → DeepSeek API 分析(根因+方案+影响+通报)
         → 结果落库 → 业务方推送
```

### 使用方式

1. Admin → SQL巡检 → 编辑告警 → 填写错误原因
2. 点击 `🤖 AI分析` → 3-5秒返回分析结果
3. 根因自动填入"错误原因"，方案填入"解决方案"
4. 点击"标记已处理"保存

### 预置知识库

| 异常类型 | 典型模式 | 解决方案 |
|---------|---------|---------|
| 登录失败 | cookie expired | 重新登录刷新Cookie |
| 元素定位失败 | selector not found | 更新选择器配置 |
| 数据为空 | 0 rows returned | 标记为无数据 |
| 网络超时 | connection timeout | 切换代理重试 |
| DB异常 | connection refused | 检查MySQL服务 |

---

## 部署指南

### Windows 开机自启

```bash
# Win+R → shell:startup
# 将 start_admin_silent.vbs 快捷方式放入该文件夹
```

### 生产环境建议

1. **Web Server**: 使用 `waitress` 或 `gunicorn` 替代 Flask 开发服务器
2. **数据库**: 配置连接池，建议 `pool_size=20`
3. **日志**: 配置 RotatingFileHandler，单文件 50MB
4. **监控**: 接入 Grafana，SQL 看板已预置
5. **安全**: 修改默认密码，关闭 Debug 模式

```bash
# 生产启动示例
waitress-serve --host=0.0.0.0 --port=5000 admin_server:app
```

---

## 开发规范

本项目遵循 `UNIVERSAL_DEV_STANDARDS.md` 中的架构准则（MUST/SHOULD/MAY 三级约束）。

### 运行测试

```bash
python -m unittest discover tests -v     # 运行所有测试
```

### 新增采集器

1. 在 `collectors/` 下创建 `xxx_collector.py`，继承 `BaseCollector`
2. 实现 `run(config: TaskConfig) -> TaskSummary` 方法
3. 在 `collector_registry.py` 中注册
4. Admin → 任务管理 → 新增任务 → 配置采集器名

### 新增经营看板

1. 在 `admin_server.py` 的 `DASHBOARD_CONFIGS` 中添加配置
2. 侧边栏自动展开，模板复用 `dashboard_data.html`

### 新增监控 SQL

1. Admin → SQL巡检 → 新增监控SQL
2. 填写名称、SQL、负责人、Cron 表达式

---

## 🖥️ Windows 桌面自动化 (NEW)

### 概述

`win_automation/` 模块为 RPADataHub 提供了完整的 Windows 桌面应用自动化能力，补齐了原本仅支持浏览器的短板。

### 技术矩阵

| 技术 | 用途 | 适用场景 |
|------|------|---------|
| **pywinauto** | 控件级操作 (Win32/UIA) | 原生Win应用，Office，企业ERP |
| **uiautomation** | 微软 UIA 底层封装 | WPF/WinForm/UWP/Electron |
| **pyautogui** | 鼠标键盘模拟 | 兜底方案，跨应用快捷键 |
| **OpenCV** | 模板匹配，图像识别 | Citrix/VMware/远程桌面/老ERP |
| **PaddleOCR** | 中文OCR识别 | 图片按钮，无控件场景文字定位 |
| **Tesseract** | 轻量OCR备选 | 纯英文场景 |

### 架构

```
win_automation/
├── base.py              # WinCollector 基类（生命周期/OCR/图像/DB）
├── flow_engine.py       # 统一流程引擎 (YAML/JSON驱动)
├── ocr_engine.py        # OCR 引擎 (PaddleOCR + Tesseract)
├── image_engine.py      # 图像识别引擎 (OpenCV模板匹配)
├── uia_engine.py        # UIAutomation 引擎（底层控件树操作）
├── requirements.txt     # Win自动化依赖
└── collectors/          # 示例采集器
    ├── notepad_collector.py    # 记事本
    ├── calculator_collector.py # 计算器
    └── excel_collector.py      # Excel
```

### 快速使用

#### 1. 安装依赖

```bash
pip install -r win_automation/requirements.txt
```

#### 2. 方式一：WinCollector 采集器（编程式）

```python
from win_automation.collectors.notepad_collector import NotepadCollector
from playwright_collection_script.schemas.task_schema import TaskConfig

config = TaskConfig(task_id="test-001", shops=["notepad"])
collector = NotepadCollector()
result = collector.execute(config)
print(f"成功: {result.success_shops}/{result.total_shops}")
```

#### 3. 方式二：Flow Engine（配置式）

```python
from win_automation.flow_engine import FlowEngine

engine = FlowEngine()
result = engine.execute("win_automation/flows/demo_notepad.yaml")
print(f"执行步骤: {result['steps_executed']}")
```

#### 4. 方式三：命令行

```bash
cd src/rpa
python -c "from win_automation.flow_engine import FlowEngine; FlowEngine().execute('win_automation/flows/demo_notepad.yaml')"
```

### 编写自定义采集器

```python
from win_automation.base import WinCollector

class MyERPCollector(WinCollector):
    collector_name = "erp_collector"
    target_exe = r"C:\ERP\erp_client.exe"
    backend = "uia"

    def run(self, config: TaskConfig) -> TaskSummary:
        # 登录
        self.input_text("admin", target="Edit")
        self.click_button("登录")

        # OCR 读取数据（无控件场景兜底）
        text = self.read_text_from_region((100, 200, 600, 400))

        # 图像识别点击
        self.click_image("btn_export.png", confidence=0.8)

        self.add_record("ERP", "SUCCESS", row_count=10)
        return self.build_summary()
```

### 流程配置示例

```yaml
# 混合流程：浏览器 + OCR + 图像 + Excel导出
name: "电商数据采集"
steps:
  - browser_open: {url: "https://seller.example.com", wait_until: "networkidle"}
  - browser_input: {selector: "#username", value: "admin"}
  - browser_input: {selector: "#password", value: "{{password}}"}
  - browser_click: {selector: "#login"}
  - ocr_wait_text: {text: "登录成功", timeout: 10}
  - image_click: {template: "btn_download.png", confidence: 0.8}
  - export_excel: {path: "data/report.xlsx"}
```

### 控件树调试

```bash
# 打印当前活动窗口的控件树
python -c "
from win_automation.uia_engine import UIAEngine
engine = UIAEngine()
window = engine.get_active_window()
if window:
    engine.dump_control_tree(window)
"
```

---

## 作者

**Jackson** — 架构设计、核心开发、全链路实现

---

## License

本项目仅供内部使用。

---

<br>

## 🔗 EcomIQ 统一框架集成

RPADataHub 已作为 **Flask Blueprint** 集成到 [EcomIQ-RPA](../../README.md) 统一平台中。

### 在 EcomIQ 中的访问方式

| 功能 | EcomIQ-RPA 路由 | 原始路由 |
|:---|:---|:---|
| 任务管理 | `/rpa/tasks` | `/tasks` |
| BI 经营分析 | `/rpa/bi` | `/bi` |
| SQL 巡检 | `/rpa/monitor` | `/monitor` |
| YAML 智能执行器 | `/rpa/winauto` | 新增 |
| AI 运营中心 | `/rpa/ops` | `/ops` |
| 成员管理 | `/rpa/members` | `/members` |

### 在大框架中启动

**纯 Web 模式（仅管理界面）：**

```bash
python -m src.main.app
```

**全栈模式（含 Worker + Redis + FileWatcher + Web）：**

```bash
start_services.bat  (root directory)
```

启动后访问 `http://localhost:5000`，通过左侧导航栏 → **RPADataHub** 进入所有功能。


### 安全加固 (EcomIQ v1.1)

| 措施 | 说明 |
|:---|:---|
| 密码哈希 | PBKDF2-HMAC-SHA256 + 随机盐，登录时自动升级旧 SHA256 |
| SQL 注入防护 | 所有查询改为参数化，移除 f-string SQL 拼接 |
| Session 安全 | HTTPOnly Cookie + SameSite=Lax + 7天持久化 |

### 更新日志

| 版本 | 日期 | 变更 |
|:---|:---|:---|
| v2.1 | 2026-06-25 | EcomIQ 统一框架集成、Blueprint 封装、YAML 智能执行器、安全加固 |
| v2.0 | 2026-06-24 | 原始独立版本 |

---

<div align="center">
  <sub>自动化的终点不是「替代人」，而是「让人回归创造」</sub>
</div>
