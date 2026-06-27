# LeadScraper 开发规范

> 本文档面向 AI 辅助开发和人工代码审查，定义了本项目在结构、编码、状态管理、测试、安全等方面的硬性规范。
> 新功能开发和重构必须遵守本文档；违反规范的 PR 应被退回修改。

---

## 一、项目结构规范

### 1.1 模块职责分离（强制）

每个 Python 模块必须有单一、明确的职责。禁止出现"万能文件"。

| 模块 | 允许的职责 | 禁止的职责 |
|------|-----------|-----------|
| `app.py` | Flask 路由定义、请求参数解析、HTTP 响应 | 业务逻辑、数据库操作、文件解析、状态管理 |
| `scraper.py` | 浏览器控制、搜索编排、CAPTCHA 处理、采集流程 | Excel 读写、正则提取、去重逻辑、邮件发送 |
| `config.py` | 全局常量定义、路径声明、settings.json 加载 | 任何运行时逻辑 |
| `lead_processing.py` | 邮箱/电话正则提取、去重、Sheet 名清理 | 浏览器操作、HTTP 请求、Excel 读写 |
| `excel_exporter.py` | Excel 写入、Sheet 格式化（表头/列宽/冻结） | 数据采集、网络请求 |
| `campaign.py` | 线索加载、模板管理、发送编排 | 浏览器操作、采集逻辑 |
| `logger_config.py` | 日志器初始化、格式化、文件轮转 | 业务逻辑 |

### 1.2 文件行数上限（建议）

- 单文件 **不超过 800 行**（不含空行和纯注释行）
- 单函数 **不超过 60 行**
- 超过上限应拆分为子模块或私有函数

### 1.3 目录结构约定

```
project/
├── app.py                  # 入口（Flask/CLI）
├── config.py               # 全局配置常量
├── *_processing.py         # 纯数据处理（无副作用）
├── *_exporter.py           # 文件导出/格式化
├── logger_config.py        # 日志基础设施
├── settings.json           # 外部可编辑配置
├── templates/              # 前端模板
├── static/                 # 静态资源
├── tests/                  # 单元测试（与源码同结构）
├── input/                  # 用户上传（gitignore）
├── output/                 # 生成结果（gitignore）
├── logs/                   # 运行日志（gitignore）
├── profiles/               # 浏览器持久化数据（gitignore）
└── browser/                # 便携浏览器（gitignore）
```

---

## 二、编码规范

### 2.1 UTF-8 编码（强制）

所有源码文件、配置文件、文档必须使用 **UTF-8 without BOM** 编码。

- Python 文件首行声明 `# -*- coding: utf-8 -*-`（Python 3 默认 UTF-8，可省略）
- JSON 文件保存时选 UTF-8
- 所有中文字符串、注释、docstring 必须正常显示，严禁乱码
- `open()` 调用必须显式指定 `encoding="utf-8"`

```python
# 正确
with open(filepath, "r", encoding="utf-8") as f:
    data = json.load(f)

# 错误
with open(filepath, "r") as f:  # 可能使用系统默认编码
    data = json.load(f)
```

### 2.2 模块文档字符串（强制）

每个 `.py` 文件必须以 docstring 开头，说明模块职责：

```python
"""
模块名称
========
简要描述模块功能（1-2 句话）。
列出主要公开接口。
"""
```

### 2.3 函数注解与 docstring（建议）

公开函数应包含完整的参数和返回值说明：

```python
def load_targets(filepath: str) -> list[dict]:
    """
    从上传的 Excel 文件解析关键词列表。

    Args:
        filepath: Excel 文件路径

    Returns:
        [{"name": "Acme-UK", "keyword": "auto parts WhatsApp +44"}, ...]

    Raises:
        ValueError: 缺少必需的列
    """
```

### 2.4 命名约定（强制）

| 类型 | 规则 | 示例 |
|------|------|------|
| 模块文件 | `snake_case.py` | `lead_processing.py` |
| 公开函数 | `snake_case()` | `load_targets()` |
| 私有函数 | `_snake_case()` | `_launch_browser()` |
| 类名 | `PascalCase` | `ScraperState` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_UPLOAD_SIZE_MB` |
| 全局变量 | 禁止新增；已有使用 `_prefix` | `_send_progress` |

### 2.5 代码分区注释（建议）

长文件内部使用显式的分隔线组织段落：

```python
# ============================================================
# 浏览器控制
# ============================================================
```

---

## 三、全局状态管理规范

### 3.1 全局状态限制（强制）

- **禁止新增模块级可变全局变量**。已有的（`state`、`_send_progress` 等）在未迁移到持久化方案前维持现状。
- 需要跨函数共享状态时，优先使用：
  1. 函数参数传递（纯函数）
  2. 类实例属性（有状态对象）
  3. 线程安全容器（`threading.Lock` / `threading.RLock` 保护）
- 如果必须使用全局变量，必须：
  - 以 `_` 前缀命名，表明模块私有
  - 在同一模块内配套提供读写锁
  - 在模块 docstring 中明确列出

### 3.2 线程安全（强制）

任何被多线程读写的共享变量必须受锁保护：

```python
# 正确
_lock = threading.Lock()
_shared_data = {}

def update_data(key, value):
    with _lock:
        _shared_data[key] = value

# 错误
_shared_data = {}

def update_data(key, value):
    _shared_data[key] = value  # 多线程同时写入会出问题
```

### 3.3 任务模型（演进方向）

- 当前：全局 `ScraperState` + 单一后台线程
- 目标：引入 `task_id` 模型，每个采集任务独立状态
- 目标：状态持久化到 SQLite，支持进程重启恢复
- **新功能开发时预留 task_id 参数位置，即使当前不持久化**

---

## 四、配置管理规范

### 4.1 配置优先级（强制）

```
CLI 显式传入 > settings.json > config.py 默认值
```

### 4.2 config.py 职责（强制）

- 所有常量定义在 `config.py` 中
- 不得在其他模块中硬编码路径、超时、正则等魔术数字
- 支持 PyInstaller 打包模式（`sys.frozen` 检测）

### 4.3 settings.json 规范（强制）

- 每个配置节包含 `_说明` 注释字段
- 赋值后**重启程序生效**，需在文档中明确说明
- 敏感信息（邮箱密码）通过 settings.json 注入，不入库

---

## 五、安全规范

### 5.1 .gitignore（强制）

以下目录和文件必须加入 `.gitignore`，**禁止任何运行产物入库**：

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/

# Runtime data
debug/
input/
logs/
output/
profiles/
browser/

# Local config (contains secrets)
settings.local.json

# Build
build/
dist/
*.spec
*.exe
```

### 5.2 敏感数据保护（强制）

- **浏览器 Profile（`profiles/`）包含 Cookie 和登录态，禁止分享和入库**
- SMTP 密码、API Key 等通过 `settings.json` 注入，不硬编码
- `settings.json` 即使入库也不应包含真实密码（模板值为 `your-password`）

### 5.3 输入验证（强制）

- 文件上传必须校验扩展名白名单
- 文件大小必须限制（`MAX_UPLOAD_SIZE_MB`）
- 用户传入的路径参数必须做路径遍历检查

---

## 六、测试规范

### 6.1 测试覆盖要求（建议）

| 模块类型 | 最低覆盖 | 必须覆盖的场景 |
|----------|---------|--------------|
| 纯数据处理（`*_processing.py`） | 80% | 正常输入、边界值、空输入、异常输入 |
| 文件导出（`*_exporter.py`） | 60% | 空数据、单条、多条、重复 Sheet 名 |
| 采集引擎（`scraper.py`） | 40% | CAPTCHA 检测、搜索结果解析 |
| Web 路由（`app.py`） | 40% | 正常请求、缺少参数、无效文件类型 |

### 6.2 测试文件位置（强制）

- 测试文件放在 `tests/` 目录下
- 文件名 `test_<模块名>.py`
- 使用 `unittest` 或 `pytest` 框架

### 6.3 可测试性设计（强制）

业务逻辑函数应该是**纯函数**，不依赖全局状态或外部服务：

```python
# 正确：纯函数，输入决定输出，易于测试
def extract_emails(text: str) -> list[str]:
    ...

# 错误：依赖全局 page 对象，无法独立测试
def extract_emails_from_page():
    global page
    text = page.inner_text("body")
    ...
```

---

## 七、日志规范

### 7.1 日志器使用（强制）

- 使用项目统一的 `TraceLogger`，不使用 `print()` 或裸 `logging`
- 每个模块实例化自己的 logger：`_logger = TraceLogger("ModuleName", str(LOG_DIR))`
- 采集全链路使用 `trace_id` 贯穿

### 7.2 日志级别约定

| 级别 | 使用场景 |
|------|---------|
| `DEBUG` | 调试细节（选择器匹配、中间变量） |
| `INFO` | 正常流程节点（任务开始/完成、文件保存） |
| `WARNING` | 可恢复的异常（网络超时重试、CAPTCHA 检测） |
| `ERROR` | 不可恢复的错误（采集崩溃、文件损坏），必须传 `exc_info=True` |

### 7.3 日志轮转

- 单文件上限 50MB
- 保留最近 30 个轮转文件
- 每次启动生成独立日志文件（按时间戳命名）

---

## 八、前端规范

### 8.1 技术选型（强制）

- Bootstrap 5（本地副本，离线可用，不移除）
- 原生 JavaScript（不引入 jQuery / React / Vue）
- 所有静态资源放在 `static/` 目录

### 8.2 前后端交互

- API 统一返回 JSON 格式：`{"success": true/false, ...}`
- 前端通过 `fetch()` 轮询 `/api/status` 获取实时状态
- 轮询间隔由 `POLL_INTERVAL_SECS` 控制
- 所有 API 必须有错误响应（HTTP 4xx/5xx + error 字段）

### 8.3 UI 状态覆盖（强制）

前端必须覆盖以下全部状态，不能有空窗或卡死：
- 空闲（无任务）
- 运行中（进度条 + 当前目标）
- CAPTCHA 等待（醒目提示 + 操作按钮）
- 已完成（摘要 + 下载按钮）
- 失败（错误信息 + 重试引导）

---

## 九、依赖管理

### 9.1 依赖声明

- 所有 Python 依赖写入 `requirements.txt`
- 固定主版本号，避免自动升级导致兼容性问题
- Playwright 浏览器通过 `playwright install chromium` 安装，不入库

### 9.2 当前核心依赖

```
flask>=3.0
playwright>=1.40
pandas>=2.0
openpyxl>=3.1
```

---

## 十、AI 辅助开发约定

在与 AI（Claude、GPT 等）协作时，将本文档作为上下文传入：

> "请遵守 DEVELOPING_STANDARDS.md 中的规范进行开发/审查。"

AI 审查代码时应按照以下优先级检查：

1. **P0（阻断）**：违反模块职责分离、缺少 .gitignore、编码损坏、敏感数据泄露
2. **P1（重要）**：全局状态使用不当、缺少线程安全保护、硬编码魔术数字
3. **P2（建议）**：函数过长、缺少 docstring、测试覆盖不足

---

> 最后更新：2026-06-14
> 本文档随项目迭代持续更新，任何架构决策变更后应在 24 小时内同步本文档。
