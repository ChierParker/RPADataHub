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
| **消费层** | Python Watchdog | 文件夹监听，自动触发 ETL |
| **处理层** | Pandas + PyMySQL | 数据清洗、维表校验、幂等入库 |
| **存储层** | MySQL 8.0 | ODS → DW → DM 三级分层 |
| **调度层** | 自研 Worker + task_queue | DB 表模拟 MQ，轮询执行 |
| **监控层** | Flask Admin + Chart.js | 可视化运维看板 |
| **AI 层** | DeepSeek API | 异常根因分析 + 知识库检索 |

---

## 项目结构

```
RPADataHub/
│
├── admin_server.py              # Flask Admin 管理平台 (15+ 页面)
├── file_watcher.py              # 文件监听 + ETL 消费服务
├── worker.py                    # 任务执行器 Agent (轮询 task_queue)
│
├── config/
│   └── settings.py              # 全局配置中心 (支持环境变量)
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
├── demo_test.py                 # 端到端测试脚本 (SQLite模拟)
├── generate_mock_data.py        # 电商模拟数据生成器
├── logger_config.py             # 结构化日志 (TraceLogger + trace_id)
└── requirements.txt
```

---

## 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+
- Windows 10/11 (文件监听) 或 Linux (Worker 模式)

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置数据库

编辑 `config/settings.py` 或设置环境变量：

```bash
# Windows PowerShell
$env:RPA_DB_HOST = "localhost"
$env:RPA_DB_PORT = "3306"
$env:RPA_DB_USER = "root"
$env:RPA_DB_PASSWORD = "your_password"
$env:RPA_DB_DATABASE = "data"
$env:RPA_WATCH_FOLDER = "D:/rpa_output"
$env:RPA_ARCHIVE_FOLDER = "D:/rpa_archive"
```

### 3. 初始化数据库

```bash
mysql -u root -p data < sql/init_tables.sql
mysql -u root -p data < sql/init_admin_tables.sql
mysql -u root -p data < sql/init_task_tables.sql
```

### 4. 生成演示数据

```bash
python generate_mock_data.py
```

### 5. 启动服务

```bash
# 终端1: Admin 管理平台
python admin_server.py
# 访问 http://localhost:5000
# 默认账号: admin / YOUR_ADMIN_PASSWORD

# 终端2: 文件监听 + ETL 消费
python file_watcher.py

# 终端3: 任务执行 Worker (可选)
python worker.py
```

---

## 功能模块

### Admin 管理平台 (15 个页面)

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
| **基础管理** | 店铺管理 | 店铺维表 CRUD + 筛选导出 |
| | 路由配置 | 文件夹→ODS表 映射管理 |

### 采集调度系统

```
任务配置 (task_config)
    ↓ Admin 点击"启动"
任务队列 (task_queue)  ← PENDING
    ↓ Worker 轮询领取
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

## 作者

**YourName** — 架构设计、核心开发、全链路实现

---

## License

本项目仅供内部使用。核心技术方案参见《基于 RPA+工程化架构的规模化数据采集与运维实践白皮书》。

---

<div align="center">
  <sub>自动化的终点不是「替代人」，而是「让人回归创造」</sub>
</div>
