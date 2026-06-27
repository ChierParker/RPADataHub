# LeadScraper — 谷歌搜索获客采集器

批量通过谷歌搜索关键词，自动提取潜在客户的邮箱、电话、WhatsApp、网站等联系方式，导出为 Excel 文件。
内置开发信（Campaign）模块，支持邮件模板管理、线索导入和模拟批量发送。

## 功能概览

### 采集引擎

- **关键词搜索**：上传 Excel 关键词列表，逐条在 Google 搜索并翻页采集
- **联系方式提取**：自动识别页面中的邮箱、电话、WhatsApp 链接、网站域名
- **国家代码过滤**：可指定电话国家代码（如 +44），只采集目标地区号码
- **CAPTCHA 自动检测**：支持 Google reCAPTCHA、hCaptcha、Cloudflare Challenge 等识别
- **CAPTCHA 手动处理**：检测到验证码后自动弹出浏览器窗口，用户手动完成后续采
- **代理支持**：可配置 HTTP 代理，避免 IP 被限制
- **并发控制**：可配置翻页数和并发访问数
- **结果导出**：每个目标一个 Sheet，蓝色表头 + 冻结首行 + 自动列宽

### 开发信模块（Campaign）

- **线索导入**：自动加载采集结果，或手动导入 Excel/CSV 客户名单
- **智能列映射**：自动识别邮箱列、公司名列、电话列等常见字段名
- **邮件模板管理**：按关键词独立编辑和保存邮件模板，支持变量替换
- **变量替换**：`{keyword}` `{company}` `{contact}` `{email}` `{phone}` `{website}` `{whatsapp}`
- **模拟发送**：后台逐封"发送"（模拟模式），实时进度 + 发送日志
- **真实 SMTP**：预留 Gmail SMTP 配置（后续版本启用）

## 技术栈

- **后端**: Python 3.10+ / Flask
- **自动化**: Playwright (Chromium 持久化上下文)
- **数据处理**: pandas / openpyxl
- **前端**: Bootstrap 5 / 原生 JavaScript
- **日志**: 结构化 TraceLogger，支持 trace_id 全链路追踪，文件自动轮转（50MB/30个）

---

## 快速开始（开发模式）

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 启动服务

```bash
python app.py
```

服务启动后会自动打开浏览器访问界面。

### 3. 使用流程

#### 采集线索

1. 上传包含"关键词"列的 Excel 文件
2. 勾选需要采集的目标
3. 配置翻页数、并发数、国家代码、代理等参数
4. 点击"开始采集"，右侧实时显示进度和日志
5. 如遇到验证码，在弹出的浏览器窗口手动完成验证，点击"继续采集"
6. 采集完成后下载结果 Excel

#### 开发信

1. 点击导航栏"开发信"进入 Campaign 页面
2. 系统自动加载最新采集结果中有邮箱的线索
3. 也可手动导入外部 Excel/CSV 客户名单
4. 为每个关键词编辑邮件模板（主题 + 正文）
5. 勾选目标线索，选择模板关键词，点击"开始发送"
6. 右侧面板查看实时发送进度和日志

---

## 打包分发（给无需 Python 环境的用户）

### 构建

```bash
# 双击运行构建脚本
build.bat
```

构建完成后，`dist/LeadScraper/` 即为可分发的独立应用。

### 用户使用

1. 解压 `LeadScraper.zip`
2. 用记事本编辑 `settings.json`，配置 SMTP 邮箱、国家代码、代理等参数
3. 双击 `LeadScraper.exe` 启动
4. 浏览器访问 `http://127.0.0.1:5000`

**注意**：本程序自带 Chromium 浏览器（`browser/` 目录），无需额外安装。

---

## 配置说明 (settings.json)

### SMTP 邮件

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `smtp.host` | SMTP 服务器地址 | `smtp.gmail.com` |
| `smtp.port` | SMTP 端口（587=TLS, 465=SSL） | `587` |
| `smtp.username` | 开发信发件邮箱 | `your-email@gmail.com` |
| `smtp.password` | 邮箱应用专用密码 | `xxxx` |
| `smtp.use_tls` | 是否启用 TLS | `true` |
| `smtp.from_name` | 发件人显示名称 | `LeadScraper` |
| `smtp.send_interval_secs` | 每封邮件间隔（秒） | `3` |

### Flask 服务

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `flask.host` | Web 服务监听地址 | `127.0.0.1` |
| `flask.port` | Web 服务端口 | `5000` |
| `flask.debug` | 是否开启调试模式 | `false` |

### 采集参数

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `scraper.default_concurrency` | 默认并发访问数 | `5` |
| `scraper.min_concurrency` | 最小并发数 | `3` |
| `scraper.max_concurrency` | 最大并发数 | `8` |
| `scraper.default_max_pages` | 默认 Google 翻页数 | `3` |
| `scraper.max_pages_min` | 最小翻页数 | `1` |
| `scraper.max_pages_max` | 最大翻页数 | `10` |
| `scraper.retry_times` | 网络超时重试次数 | `2` |
| `scraper.retry_delay_secs` | 重试间隔秒数 | `3` |
| `scraper.captcha_timeout_secs` | CAPTCHA 手动解决超时（秒） | `600` |
| `scraper.page_load_timeout_ms` | 页面加载超时（毫秒） | `30000` |
| `scraper.search_timeout_ms` | 搜索等待超时（毫秒） | `60000` |

### 其他

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `proxy.address` | HTTP 代理地址（留空不用） | `http://127.0.0.1:7890` |
| `country_code.code` | 电话国家代码过滤（留空不过滤） | `+44` |
| `upload.max_size_mb` | 上传文件大小上限（MB） | `50` |
| `user_agent.value` | 浏览器 User-Agent | Chrome 125 |

---

## 项目结构

```
LeadScraper/
├── app.py                  # Flask 服务入口，路由定义
├── scraper.py              # 核心采集引擎（浏览器/搜索/CAPTCHA/编排）
├── config.py               # 全局配置常量（支持 settings.json 覆盖）
├── lead_processing.py      # 联系方式提取（邮箱/电话正则）+ 去重 + Sheet名清理
├── excel_exporter.py       # Excel 写入与格式化（蓝色表头/冻结首行/自动列宽）
├── campaign.py             # 开发信模块（线索加载/模板管理/模拟发送）
├── logger_config.py        # 结构化日志（TraceLogger + 文件轮转）
├── settings.json           # 外部配置文件（用户可编辑，覆盖默认值）
├── build.bat               # PyInstaller 一键打包脚本
├── requirements.txt        # Python 依赖清单
├── email_templates.json    # 邮件模板持久化文件（自动生成）
├── templates/
│   ├── index.html          # 采集 Web 界面
│   └── campaign.html       # 开发信 Web 界面
├── static/
│   ├── css/                # Bootstrap 5 本地副本（离线可用）
│   ├── js/                 # 前端交互逻辑
│   └── fonts/              # Bootstrap 图标字体
├── tests/
│   └── test_lead_processing.py  # 联系方式提取 + 去重单元测试
├── input/                  # 上传文件目录（.gitignore 排除）
├── output/                 # 采集结果输出目录（.gitignore 排除）
├── logs/                   # 日志目录（.gitignore 排除，自动轮转）
├── profiles/               # 浏览器用户数据（.gitignore 排除，含 Cookie）
├── browser/                # Chromium 便携版（构建时自动填充）
└── README.md
```

---

## 输入 Excel 格式

至少需要包含**"关键词"**列。可选列：`目标名称`

| 关键词 | 目标名称 |
|--------|----------|
| auto parts WhatsApp "+44" | AutoParts-UK |
| car dealers email Germany | CarDealers-DE |

---

## 输出 Excel 格式

每个目标一个独立的 Sheet，包含以下列：

| 序号 | 公司名 | 联系人 | 邮箱 | 电话 | WhatsApp链接 | 网站 | 来源链接 | 采集时间 |
|------|--------|--------|------|------|-------------|------|----------|----------|

格式特性：蓝色表头、冻结首行、自动列宽适配。

---

## CAPTCHA 处理流程

1. 系统在每次搜索前和翻页后自动检测 CAPTCHA（关键词 + CSS 选择器双重检测）
2. 支持的验证码类型：Google reCAPTCHA、hCaptcha、Cloudflare Challenge
3. 检测到后自动关闭 headless 浏览器，启动**有头浏览器**窗口
4. 前端显示"需要手动验证"状态和目标 URL
5. 用户在新窗口中完成验证 → 点击"继续采集"按钮恢复采集
6. 超时（默认 10 分钟）未完成则跳过当前目标

---

## 注意事项

- 仅供合法业务用途，请遵守 Google 服务条款和目标网站的使用协议
- 建议控制采集频率和并发数，避免触发反爬机制
- 采集过程中请勿关闭弹出的浏览器窗口
- `profiles/` 目录包含浏览器 Cookie 和登录态，请勿分享给他人
- 开发信模拟发送仅为功能演示，真实发送需在 `settings.json` 中配置正确的 SMTP 账密

<br>

## 🔗 EcomIQ 统一框架集成

LeadScraper 已作为 **Flask Blueprint** 集成到 [EcomIQ-RPA](../../README.md) 统一平台中。

### 在 EcomIQ 中的访问方式

| 功能 | EcomIQ-RPA 路由 | 说明 |
|:---|:---|:---|
| 关键词采集 | `/leads/` | 上传 Excel → 选择目标 → 配置参数 → 开始采集 |
| 结果导出/开发信 | `/leads/export` | 导入线索 → 模板管理 → 模拟发送 |

### 在大框架中启动

```bash
python -m src.main.app        # 纯 Web 模式
start_services.bat   # 全栈模式 (root)
```

启动后访问 `http://localhost:5000`，通过左侧导航栏 → **客户开发** 进入。

> **注意**：在大框架模式下，`app.py` 不再需要单独运行（原端口 5000 已由 EcomIQ-RPA 主应用占用）。原有 API 路径 `/api/upload`, `/api/start` 等通过兼容层自动映射到 `/leads/api/upload`, `/leads/api/start`。

### 更新日志

| 版本 | 日期 | 变更 |
|:---|:---|:---|
| v1.1 | 2026-06-25 | EcomIQ-RPA 统一集成、Blueprint 封装、API 路径兼容层 |
| v1.0 | 2026-06-12 | 原始独立版本 |
