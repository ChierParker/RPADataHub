# EcomIQ-RPA — 电商智能工具集 统一平台

<div align="center">

**五大模块统一入口 · 零冗余架构 · 即开即用**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple.svg)](https://getbootstrap.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)](https://www.mysql.com/)
[![Redis](https://img.shields.io/badge/Redis-7.0+-red.svg)](https://redis.io/)
[![License](https://img.shields.io/badge/License-Internal-red.svg)]()

</div>

---

## 📋 目录

- [项目简介](#-项目简介)
- [技术架构](#-技术架构)
- [集成模块](#-集成模块)
- [快速开始](#-快速开始)
- [路由映射](#-路由映射)
- [安全机制](#-安全机制)
- [项目结构](#-项目结构)
- [部署指南](#-部署指南)
- [更新日志](#-更新日志)

---

## 📖 项目简介

EcomIQ 是面向跨境电商的**统一运营管理平台**，整合了数据采集、竞品分析、客户开发、视频分析和 AI 助手五大核心模块，提供统一认证、全局导航和一站式数据看板。

### 核心特性

- ✅ **统一登录鉴权** — PBKDF2 密码哈希 + Session 持久化（7天）
- ✅ **模块蓝图集成** — 四大子模块以 Flask Blueprint 挂载，独立可运行
- ✅ **WebSocket 支持** — 原生 WS 协议，用于 YAML 执行器实时日志
- ✅ **跨模块 API 兼容** — 四套独立 API 路径自动映射，零修改搭载
- ✅ **安全加固** — SQL 参数化查询 · Session 安全 Cookie · 密码自动升级
- ✅ **响应式布局** — Bootstrap 5 + 自定义暗色侧边栏 + 可折叠导航
- ✅ **Windows 桌面自动化** — YAML 流程编排 + pywinauto/UIA/OCR/图像识别

---

## 🏗️ 技术架构

```
┌──────────────────────────────────────────────────────────┐
│                     EcomIQ-RPA (Flask)                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐  │
│  │RPA Data │  │Competit. │  │ Lead    │  │VideoIQ +  │  │
│  │  Hub    │  │ Watch   │  │Scraper  │  │AI Assist. │  │
│  └─────────┘  └─────────┘  └─────────┘  └───────────┘  │
│        │            │            │             │         │
│        └────────────┴────────────┴─────────────┘         │
│                         │                                │
│              ┌──────────┴──────────┐                     │
│              │  MySQL (data 库)    │                     │
│              └─────────────────────┘                     │
└──────────────────────────────────────────────────────────┘
```

| 层级 | 技术 | 说明 |
|:---|:---|:---|
| **后端框架** | Python 3.10+ / Flask 3.0+ | Web 服务 + Blueprint 模块化管理 |
| **前端** | Bootstrap 5.3 + Bootstrap Icons | 响应式布局 + 图标库 |
| **YAML 编辑器** | Monaco Editor (CDN) | YAML 语法高亮、自动补全 |
| **WebSocket** | Flask-Sock + simple-websocket | 实时日志推送 |
| **数据库** | MySQL 8.0 + PyMySQL | 共享 data 库，统一数据源 |
| **密码安全** | PBKDF2-HMAC-SHA256 + 随机盐 | 10 万次迭代，兼容旧版 SHA256 |
| **MQ** | Redis Streams / DB 降级 | 消息队列推送 |

---

## 📦 集成模块

| 模块 | 路由 | 说明 | 状态 |
|:---|:---|:---|:---|
| 📡 RPADataHub | `/rpa/*` | 数据采集与运维 · ETL · SQL巡检 · BI看板 | 完整 |
| 📊 CompetitorWatch | `/competitor/*` | 竞品管理 · 竞价看板 · AI 报告 | 完整 |
| 🎯 LeadScraper | `/leads/*` | 客户开发 · 关键词采集 · 开发信 | 完整 |
| 🎬 VideoIQ | `/video/*` | AI 视频内容分析 | 占位 |
| 🤖 AI Assistant | `/ai` | 智能对话助手 · DeepSeek · 数据查询分析 | 完整 |
| 🤖 YAML 执行器 | `/rpa/winauto` | 可视化 Windows 桌面自动化 | 新增 |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+ (localhost:3306)
- Redis 7.0+ (可选，不配则降级数据库轮询)
- Windows 10/11 (for WinAuto 桌面自动化)

### 1. 安装依赖

```bash
cd EcomIQ-RPA
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

核心依赖：`flask flask-sock pymysql pandas python-dotenv playwright simple-websocket pyyaml`

### 2. 配置数据库

```bash
# 确保 MySQL 运行中，src/rpa/.env 配置正确
# 示例：
RPA_DB_HOST=localhost
RPA_DB_PORT=3306
RPA_DB_USER=root
RPA_DB_PASSWORD=yourpassword
RPA_DB_DATABASE=data
```

### 3. 初始化 CompetitorWatch 数据表

```bash
python src/competitor/sql/setup_db.py
```

### 4. 启动

**纯 Web 模式：**

```bash
python src/main/app.py
# 访问 http://localhost:5000
# 账号: admin / RPA@admin2026
```

**全栈模式（含 Worker + Redis + FileWatcher）：**

```bash
start_services.bat  (root directory)
```

---

## 🗺️ 路由映射

### 主应用路由

| 路径 | 功能 |
|:---|:---|
| `/` | 首页仪表盘 (5个功能卡片) |
| `/login` | 统一登录 |
| `/logout` | 登出 |
| `/video/*` | VideoIQ (占位) |
| `/ai` | AI 智能助手 · DeepSeek 对话 · 数据查询分析 |
| `/settings` | 系统设置 |
| `/api/change_password` | 修改密码 |
| `/api/dashboard/summary` | 底部状态栏数据 |
| `/api/health` | 健康检查 |

### 子模块路由 (详见各模块 README)

- RPADataHub: `/rpa/tasks` `/rpa/bi` `/rpa/monitor` `/rpa/winauto` 等
- CompetitorWatch: `/competitor/manage` `/competitor/dashboard` `/competitor/reports`
- LeadScraper: `/leads/` `/leads/export`

---

## 🛡️ 安全机制

| 措施 | 实现 | 版本 |
|:---|:---|:---|
| **密码哈希** | PBKDF2-HMAC-SHA256 + 16字节盐 + 10万迭代 | v1.1 |
| **旧密码升级** | 旧版 SHA256 登录时自动升级为 PBKDF2 | v1.1 |
| **SQL 注入防护** | 参数化查询 + 白名单排序 + 表名校验 | v1.1 |
| **Session 安全** | HTTPOnly + SameSite=Lax + 7天持久化 | v1.1 |
| **路径遍历** | `..` 检测 + 文件名清洗 | v1.1 |
| **文件上传** | 扩展名校验 + 文件大小限制 | v1.1 |
| **XSS 防护** | Jinja2 自动转义 + 客户端 `escapeHtml()` | v1.0 |
| **API 限流** | 登录失败提示 + AI 生成限频 | 待实现 |

---

## 📁 项目结构

```
src/main/                         # 🏠 EcomIQ-RPA Hub（本文档）
├── app.py                    # 主应用入口 (Flask + WebSocket)
├── generate_mock_data.py     # 模拟数据生成器
├── README.md                 # 本文档
├── templates/
│   ├── base.html             # 统一布局 (侧边栏+顶栏+底栏)
│   ├── home.html             # 首页仪表盘
│   ├── login.html            # 登录页
│   ├── ai_assistant.html     # AI 助手 (DeepSeek 对话 + 数据查询)
│   ├── settings.html         # 系统设置
│   └── video*.html           # VideoIQ (占位)
├── static/                   # 静态资源
└── sql/                       # SQL 脚本
```

四大子模块 (`src/rpa/`, `src/competitor/`, `src/leads/`) 保持独立目录结构，各自有 `blueprint.py` 封装和独立 `README.md`。

---

## 🚢 部署指南

### 生产环境

```bash
# 1. 关闭 debug 模式
# 编辑 src/main/app.py: app.run(debug=False)

# 2. 使用 gunicorn / waitress
pip install waitress
waitress-serve --port=5000 src.main.app:app

# 3. 生产环境安全配置
# 修改 src/main/app.py:
SESSION_COOKIE_SECURE = True    # HTTPS
ECOMIQ_RPA_SECRET_KEY = 随机字符串    # 环境变量

# 4. 启动后台服务
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
        proxy_set_header Connection "upgrade";  # WebSocket
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 📝 更新日志

| 版本 | 日期 | 变更 |
|:---|:---|:---|
| v1.1 | 2026-06-25 | PBKDF2 密码升级、SQL 参数化、Session 安全加固、折叠侧边栏 |
| v1.0 | 2026-06-24 | 三大模块蓝图集成、统一登录、首页仪表盘、YAML 智能执行器 |

---

## 📄 License

Internal use only. All rights reserved.
