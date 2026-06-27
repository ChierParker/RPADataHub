# EcomIQ-RPA — RPA & Web Scraping Platform for E-Commerce | 电商 RPA 智能工具集

<div align="center">

**RPA · Web Scraping · Playwright Automation · Desktop RPA (pywinauto+OCR)
· ETL Pipeline · AI Dashboard — All-in-one e-commerce operations platform**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![RPA](https://img.shields.io/badge/RPA-Playwright%20|%20pywinauto-blue)]()
[![Automation](https://img.shields.io/badge/Automation-Desktop%20|%20Web-green)]()
[![Scraping](https://img.shields.io/badge/Web%20Scraping-10+%20Platforms-orange)]()
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)](https://www.mysql.com/)
[![Redis](https://img.shields.io/badge/Redis-7.0+-red.svg)](https://redis.io/)
[![License](https://img.shields.io/badge/License-Internal-red.svg)]()

</div>

---

## 📋 目录

- [项目简介](#-项目简介)
- [模块总览](#-模块总览)
- [技术架构](#-技术架构)
- [快速开始](#-快速开始)
- [项目结构](#-项目结构)
- [路由映射](#-路由映射)
- [安全机制](#-安全机制)
- [开发规范](#-开发规范)
- [部署指南](#-部署指南)
- [更新日志](#-更新日志)

---

## 📖 项目简介

EcomIQ-RPA 是一套面向跨境电商的 **RPA 数据采集与自动化运维平台**，
整合了 **Playwright 浏览器自动化**、**Windows 桌面 RPA**（pywinauto + UIA + PaddleOCR）、
竞品监控（Competitor Monitoring）、客户开发（Lead Generation）、ETL 数据管道和 AI 智能分析五大核心模块，
提供统一认证、全局导航和一站式数据看板。

> **EcomIQ-RPA is a full-stack RPA & web scraping platform for e-commerce.
> Playwright browser automation · Desktop RPA (pywinauto+OCR) · Competitor monitoring
> · Lead generation · ETL pipeline · AI-powered dashboard. All-in-one.**

### 核心特性

- ✅ **统一登录鉴权** — PBKDF2 密码哈希 + Session 持久化（7天）
- ✅ **模块蓝图集成** — 四大子模块以 Flask Blueprint 挂载，独立可运行
- ✅ **WebSocket 支持** — 原生 WS 协议，用于 YAML 执行器实时日志
- ✅ **跨模块 API 兼容** — 三套独立 API 路径自动映射，零修改搭载
- ✅ **安全加固** — SQL 参数化查询 · Session 安全 Cookie · 密码自动升级
- ✅ **响应式布局** — Bootstrap 5 + 自定义暗色侧边栏 + 可折叠导航
- ✅ **Windows 桌面自动化** — YAML 流程编排 + pywinauto/UIA/OCR/图像识别

---

## 📦 模块总览

| 模块 | 路由前缀 | 独立端口 | 说明 | 状态 |
|:---|:---|:---|:---|:---|
| 🏠 **EcomIQ-RPA Hub** | `/` | `5000` | 统一入口、登录鉴权、首页仪表盘 | 完整 |
| 📡 **RPADataHub** | `/rpa/*` | `5100` | 数据采集与运维 · ETL · BI 看板 | 完整 |
| 📊 **CompetitorWatch** | `/competitor/*` | `5100` | 竞品管理 · 竞价看板 · AI 报告 | 完整 |
| 🎯 **LeadScraper** | `/leads/*` | `5000` | 客户开发 · 关键词采集 · 开发信 | 完整 |
| 🎬 **VideoIQ** | `/video/*` | — | AI 视频内容分析 | 占位 |
| 🤖 **AI Assistant** | `/ai` | — | 智能对话助手 · DeepSeek · 数据查询分析 | 完整 |

各模块独立 README：[src/rpa/](src/rpa/README.md) · [src/competitor/](src/competitor/README.md) · [src/leads/](src/leads/README.md) · [src/main/](src/main/README.md)

---

## 🏗️ 技术架构

```
┌──────────────────────────────────────────────────────────────────┐
│                  EcomIQ-RPA Hub (Flask :5000)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐  │
│  │ RPADataHub   │  │Competitor    │  │ Lead     │  │VideoIQ +│  │
│  │ (Blueprint)  │  │Watch (BP)    │  │Scraper(BP│  │AI Assist│  │
│  └──────┬───────┘  └──────┬───────┘  └────┬─────┘  └────┬────┘  │
│         │                 │               │             │        │
│         └─────────────────┴───────────────┴─────────────┘        │
│                                   │                               │
│                    ┌──────────────┴──────────────┐                │
│                    │  MySQL 8.0 (data 库)        │                │
│                    │  Redis 7.0 (MQ, 可选)       │                │
│                    └─────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────┘
```

| 层级 | 技术 | 说明 |
|:---|:---|:---|
| **后端框架** | Python 3.10+ / Flask 3.0+ | Web 服务 + Blueprint 模块化管理 |
| **前端** | Bootstrap 5.3 + Bootstrap Icons | 响应式布局 + 图标库 |
| **浏览器自动化** | Playwright | 数据采集 + 竞品监控 |
| **Win 自动化** | pywinauto + uiautomation + OpenCV + PaddleOCR | 桌面自动化 |
| **数据库** | MySQL 8.0 + PyMySQL | 共享 data 库，ODS → DW 分层 |
| **消息队列** | Redis Streams / DB 降级 | 任务调度 + 实时推送 |
| **密码安全** | PBKDF2-HMAC-SHA256 + 随机盐 | 10万次迭代 |
| **AI** | DeepSeek Chat API | 智能分析 + RAG 知识库 |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+ (localhost:3306)
- Redis 7.0+ (可选，不配则降级数据库轮询)
- Windows 10/11 (推荐)

### 1. 安装依赖

```bash
cd EcomIQ
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
playwright install chromium
```

### 2. 配置环境变量

编辑 `.env` 文件，填入数据库密码等配置。

### 3. 初始化数据库

```bash
python src/competitor/sql/setup_db.py
```

### 4. 启动

**纯 Web 模式：**

```bash
start.bat
# 访问 http://localhost:5000
# 账号: admin / RPA@admin2026
```

**全栈模式（含 Worker + Redis + FileWatcher）：**

```bash
start_services.bat
```


---

## 📁 项目结构

```
EcomIQ/
├── README.md                       # 项目总览（本文档）
├── DEVELOPMENT_STANDARDS.md        # 开发规范与约束
├── requirements.txt                # 统一 Python 依赖
├── .gitignore                      # Git 忽略规则
├── .env                            # 环境变量配置（不入库）
├── start.bat                       # Web 模式一键启动
├── start_services.bat              # 全栈模式一键启动
├── docs/                           # 设计文档
│   ├── 整套RPA解决方案.docx
│   ├── 架构整改方案.md
│   └── 智能客服模块_功能设计文档.md
│
└── src/
    ├── main/                       # 🏠 EcomIQ Hub（统一入口）
    │   ├── app.py                  # 主应用入口
    │   ├── README.md
    │   ├── templates/ / static/ / sql/
    │
    ├── rpa/                        # 📡 RPADataHub
    │   ├── blueprint.py            # 蓝图封装
    │   ├── admin_server.py         # 独立 Admin (5100)
    │   ├── worker.py               # Worker 执行器
    │   ├── file_watcher.py         # 文件监听
    │   ├── win_automation/         # Win 桌面自动化
    │   ├── templates/ / tests/
    │   └── README.md
    │
    ├── competitor/                 # 📊 CompetitorWatch
    │   ├── blueprint.py
    │   ├── app.py / worker.py
    │   ├── sql/ / templates/ / tests/
    │   └── README.md
    │
    └── leads/                      # 🎯 LeadScraper
        ├── blueprint.py            # 蓝图封装
        ├── app.py                  # 独立入口
        ├── scraper.py              # 采集引擎
        ├── campaign.py             # 开发信模块
        ├── templates/ / tests/
        └── README.md
```

---

## 🗺️ 路由映射

### 主应用路由

| 路径 | 功能 |
|:---|:---|
| `/` | 首页仪表盘 |
| `/login` / `/logout` | 统一登录 / 登出 |
| `/settings` | 系统设置 |
| `/video/*` | VideoIQ (占位) |
| `/ai` | AI 智能助手 · DeepSeek 对话 · 数据查询分析 |
| `/api/health` | 健康检查 |

### 子模块路由

| 模块 | 主要路由 |
|:---|:---|
| **RPADataHub** | `/rpa/tasks` `/rpa/bi` `/rpa/monitor` `/rpa/winauto` `/rpa/ops` |
| **CompetitorWatch** | `/competitor/manage` `/competitor/dashboard` `/competitor/reports` |
| **LeadScraper** | `/leads/` `/leads/export` `/leads/api/upload` `/leads/api/start` |

---

## 🛡️ 安全机制

| 措施 | 实现 |
|:---|:---|
| **密码哈希** | PBKDF2-HMAC-SHA256 + 16字节盐 + 10万迭代 |
| **旧密码升级** | 旧版 SHA256 登录时自动升级为 PBKDF2 |
| **SQL 注入防护** | 参数化查询 + 白名单排序 + 表名校验 |
| **Session 安全** | HTTPOnly + SameSite=Lax + 7天持久化 |
| **路径遍历防护** | `..` 检测 + 文件名清洗 |
| **文件上传校验** | 扩展名白名单 + 文件大小限制 |
| **XSS 防护** | Jinja2 自动转义 + 客户端 escapeHtml() |
| **敏感数据隔离** | `.env` + `settings.local.json` 不入库 |

---

## 📐 开发规范

本项目遵循 **[DEVELOPMENT_STANDARDS.md](DEVELOPMENT_STANDARDS.md)**，采用 MUST/SHOULD/MAY 三级约束体系。

### 核心原则

1. **安全优先**：密钥不入库、输入必校验、路径防遍历
2. **模块分离**：路由、业务逻辑、IO 操作严格分离
3. **可测试性**：纯函数优先，全局状态封装
4. **一致性**：API 统一返回 `{success, data, error}` 格式
5. **UTF-8**：所有源码、配置、文档统一 UTF-8 编码

### 运行测试

```bash
# RPADataHub
cd src/rpa && python -m pytest tests/ -v

# CompetitorWatch
cd src/competitor && python -m pytest tests/ -v

# LeadScraper
cd src/leads && python -m pytest tests/ -v
```

---

## 🚢 部署指南

### 生产环境

```bash
# 1. 关闭 debug 模式
# 2. 使用 waitress
pip install waitress
waitress-serve --port=5000 src.main.app:app

# 3. 安全配置 .env:
ECOMIQ_RPA_SECRET_KEY=<随机长字符串>
SESSION_COOKIE_SECURE=True

# 4. 后台服务
python src/rpa/worker.py &
python src/rpa/file_watcher.py &
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name ecomiq-rpa.example.com;
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 📝 更新日志

| 版本 | 日期 | 变更 |
|:---|:---|:---|
| v1.2 | 2026-06-27 | 根目录文档完善：README / .gitignore / requirements.txt / 开发规范 |
| v1.1 | 2026-06-25 | PBKDF2 密码升级、SQL 参数化、Session 安全加固、折叠侧边栏 |
| v1.0 | 2026-06-24 | 四大模块蓝图集成、统一登录、首页仪表盘、YAML 智能执行器 |

---

## 📄 License

Internal use only. All rights reserved.
