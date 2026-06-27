# RPADataHub API 采集模块 — 功能设计文档

> **文档版本**: v1.0  
> **创建日期**: 2026-06-27  
> **作者视角**: 10年架构师 + RPA资深实施工程师 + 技术经理  
> **模块状态**: 占位页面已就绪，功能待开发  
> **当前路由**: `/rpa/api_collect` · `/rpa/api_collect/logs`

---

## 目录

1. [业务背景与工程哲学](#1-业务背景与工程哲学)
2. [架构定位：API采集是数据采集体系的"第二轨"](#2-架构定位api采集是数据采集体系的第二轨)
3. [核心架构设计](#3-核心架构设计)
4. [功能清单与优先级](#4-功能清单与优先级)
5. [子模块一：API 凭证管理](#5-子模块一api-凭证管理)
6. [子模块二：API 任务配置](#6-子模块二api-任务配置)
7. [子模块三：API 执行记录与监控](#7-子模块三api-执行记录与监控)
8. [子模块四：API 适配器框架](#8-子模块四api-适配器框架)
9. [数据库设计](#9-数据库设计)
10. [API 接口设计](#10-api-接口设计)
11. [前端页面设计](#11-前端页面设计)
12. [与现有系统的集成方案](#12-与现有系统的集成方案)
13. [开发分期计划](#13-开发分期计划)
14. [技术选型与约束](#14-技术选型与约束)
15. [风险与缓解措施](#15-风险与缓解措施)

---

## 1. 业务背景与工程哲学

### 1.1 为什么需要 API 采集？

当前 RPADataHub 的数据采集体系主要依赖 **Playwright 浏览器自动化** 来抓取电商平台数据。这个方案在某电商后台等场景下已经验证有效，但存在三个结构性限制：

| 限制 | 场景 | 影响 |
|:---|:---|:---|
| **时效性** | Playwright 启动浏览器 → 登录 → 导航 → 提取数据，单店铺耗时 30-120 秒 | 200 个店铺需要数小时 |
| **稳定性** | 浏览器页面加载受网络波动、反爬策略、DOM 变更影响 | 失败率 5-15%，需重试 |
| **数据完整性** | 部分平台通过 API 提供的结构化数据（如广告报表、财务数据）在浏览器端无法获取 | 数据缺失 |

**API 采集的核心价值**：

> "API 是电商平台的'官方数据通道'。虽然接入门槛高（需要开发者账号、通过审核），但一旦接入，数据质量、时效性和稳定性都远超浏览器抓取。这是数据采集体系的'第二轨'——与 Playwright 采集互为补充、相互校验。"

### 1.2 工程决策：适配器模式 + 任务调度体系复用

作为架构师的核心决策：

1. **不重新发明轮子** — API 采集任务完全复用现有的 `task_queue` → `task_config` → Redis MQ → Worker 调度体系
2. **适配器隔离** — 每个电商平台的 API 差异巨大（认证方式、数据结构、限频策略），通过适配器模式统一规范
3. **凭证安全** — API Key / Secret 必须加密存储，与环境变量和数据库权限联动

---

## 2. 架构定位：API采集是数据采集体系的"第二轨"

### 2.1 双轨采集架构

```
                         ┌─────────────────────────────┐
                         │     RPADataHub 任务调度层     │
                         │  task_queue / Redis MQ       │
                         └─────────────┬───────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
    ┌─────────────────┐    ┌─────────────────────┐    ┌──────────────┐
    │ 🥇 浏览器采集轨   │    │ 🥈 API 采集轨 (新增) │    │ YAML 执行器   │
    │ (Playwright)     │    │ (REST/GraphQL)      │    │ (桌面自动化)   │
    │                  │    │                     │    │               │
    │ · 登录后台       │    │ · 直接API调用        │    │ · Windows应用 │
    │ · 页面抓取       │    │ · 结构化JSON响应     │    │               │
    │ · DOM解析        │    │ · 无需浏览器开销     │    │               │
    └────────┬────────┘    └──────────┬──────────┘    └───────────────┘
             │                        │
             └────────────┬───────────┘
                          │
                          ▼
              ┌─────────────────────────┐
              │   ETL 管道 (已有)        │
              │   ODS → DW → DM         │
              └─────────────────────────┘
```

### 2.2 API 采集的数据流

```
API 凭证 (加密存储)
    │
    ▼
用户配置任务 → task_config 表
(platform, endpoint, params, schedule)
    │
    ▼
调度引擎触发 (Redis MQ / Cron)
    │
    ▼
Worker 领取任务 → task_queue (PENDING → RUNNING)
    │
    ▼
API Adapter 调用 (OAuth / API Key / 签名认证)
    ├── Amazon SP-API Adapter
    ├── Walmart API Adapter
    ├── Shopee API Adapter
    └── 自定义 API Adapter
    │
    ▼
响应解析 → 标准化清洗 → ODS 表写入
    │
    ▼
task_record + task_summary 写入
    │
    ▼
ETL 管道 → DW → DM → BI 看板
```

### 2.3 与现有模块的关系

```
RPADataHub
├── task_config (任务配置表)    ←── API 采集任务也注册在这里
├── task_queue  (任务队列表)    ←── API 采集执行实例
├── task_record (采集明细表)    ←── API 采集结果记录
├── task_summary (任务汇总表)   ←── API 采集批次汇总
├── api_credentials (新增)      ←── API 凭证安全存储
├── api_call_logs (新增)         ←── API 调用明细日志
├── ETL 管道 (ODS/DW/DM)       ←── 数据落库 (复用)
└── BI 看板                    ←── 数据展示 (复用)
```

---

## 3. 核心架构设计

### 3.1 适配器模式

```
                    ┌──────────────────────────┐
                    │     APIAdapter (抽象基类)  │
                    │  + authenticate()         │
                    │  + call(endpoint, params) │
                    │  + parse_response(raw)    │
                    │  + rate_limit_check()     │
                    └───────────┬──────────────┘
                                │
        ┌───────────┬───────────┼───────────┬───────────┐
        │           │           │           │           │
        ▼           ▼           ▼           ▼           ▼
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│ Amazon    │ │ Walmart   │ │ Shopee    │ │ 1688     │ │ Custom    │
│ SP-API    │ │ API       │ │ API       │ │ API      │ │ HTTP API  │
│ Adapter   │ │ Adapter   │ │ Adapter   │ │ Adapter   │ │ Adapter   │
│           │ │           │ │           │ │           │ │           │
│ OAuth2    │ │ API Key   │ │ HMAC签名  │ │ AppKey   │ │ Bearer    │
│ LWAAuth   │ │ Signature │ │ + Token   │ │ + Secret │ │ Token     │
└───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘
```

### 3.2 调度体系集成方案

API 采集任务**完全复用**现有任务调度体系，零新增基础设施：

```
用户配置 API 任务 → task_config 表
                         │
              ┌──────────┴──────────┐
              │                     │
        schedule_type="now"   schedule_type="cron"
              │                     │
              ▼                     ▼
       立即执行 (REST)        定时执行 (Cron/Scheduler)
              │                     │
              └──────────┬──────────┘
                         ▼
              Redis MQ publish(task_msg)
                         │
                         ▼
              Worker 消费 → 执行 API Adapter
                         │
                         ▼
              结果写入 task_record + ODS 表
```

**关键决策**：API 采集任务的 `script_name` 字段填入 `"api_collect"`，Worker 根据这个字段路由到 API 适配器而非 Playwright 采集器。已有的 `task_runner.py` 和 `worker.py` 只需新增一个分支，不需要修改核心逻辑。

---

## 4. 功能清单与优先级

### 4.1 功能矩阵

| 序号 | 功能模块 | 路由 | 优先级 | 复杂度 | 预计工期 |
|:---|:---|:---|:---|:---|:---|
| 1 | API 凭证管理（加密存储） | `/rpa/api_collect` | P0 | 中 | 2天 |
| 2 | API 任务配置（CRUD + 平台选择） | `/rpa/api_collect` | P0 | 中 | 2天 |
| 3 | API 执行记录与日志 | `/rpa/api_collect/logs` | P0 | 低 | 1天 |
| 4 | 通用 HTTP API 适配器 | 后台服务 | P0 | 低 | 1天 |
| 5 | Amazon SP-API 适配器 | 后台服务 | P1 | 高 | 5天 |
| 6 | 调度集成（与 Redis MQ 对接） | 后台服务 | P1 | 中 | 2天 |
| 7 | API 调用限频与重试策略 | 后台服务 | P1 | 低 | 1天 |
| 8 | Walmart / Shopee 适配器 | 后台服务 | P2 | 高 | 5天 |
| 9 | API 数据校验（与 Playwright 双轨对比） | 后台服务 | P2 | 中 | 3天 |

### 4.2 MVP 范围（本次开发）

| 功能 | 说明 |
|:---|:---|
| API 凭证管理 | 加密存储平台 API 密钥，支持增删改查 |
| 通用 HTTP API 适配器 | 支持 GET/POST、Bearer Token、自定义 Header，覆盖 80% 场景 |
| API 任务配置 | 配置 API 端点、参数、调度频率 |
| 执行记录 | 查看每次调用的状态、耗时、返回数据量 |
| 调度集成 | 将 API 任务注册到 task_config，通过现有 MQ 调度 |

---

## 5. 子模块一：API 凭证管理

### 5.1 功能概述

> **安全第一原则**：API 密钥（Access Key、Secret Key、Refresh Token）必须加密存储，绝不能以明文形式存于数据库。采用 AES-256-GCM 加密，密钥从环境变量读取。

### 5.2 页面布局

```
┌──────────────────────────────────────────────────────────────────┐
│  🔌 API 凭证管理                                    [+ 添加凭证] │
├──────────────────────────────────────────────────────────────────┤
│  ┌─ 平台筛选 ─────────────────────────────────────────────────┐  │
│  │ [全部] [Amazon] [Walmart] [Shopee] [1688] [自定义]         │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ 🔑 Amazon SP-API                      ● 有效 · 2026-08-15    │  │
│  │    Client ID: amzn1.applica***        店铺: EcomIQ-US       │  │
│  │    [查看详情] [编辑] [删除]                                  │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │ 🔑 Walmart API                        ● 有效 · 无过期       │  │
│  │    Client ID: wmt-6f8a***            店铺: EcomIQ-Global    │  │
│  │    [查看详情] [编辑] [删除]                                  │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │ 🔑 自定义 API                         ○ 已过期 · 2026-01-01  │  │
│  │    端点: https://api.example.com      店铺: --              │  │
│  │    [查看详情] [编辑] [删除]                                  │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 凭证编辑器（模态框）

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| 平台 | 下拉 | Amazon / Walmart / Shopee / 1688 / 自定义 |
| 凭证名称 | 文本 | 便于识别的名称 |
| 关联店铺 | 下拉 | 从 `dim_shop_info` 选择 |
| 认证方式 | 下拉 | OAuth 2.0 / API Key / Bearer Token / HMAC 签名 |
| Client ID / App Key | 密码框 | 加密存储 |
| Client Secret / App Secret | 密码框 | 加密存储 |
| Access Token | 密码框 | 加密存储（OAuth 场景） |
| Refresh Token | 密码框 | 加密存储（OAuth 场景） |
| 过期时间 | 日期 | OAuth Token 过期时间 |
| 自定义 Header | JSON | 如 `{"X-Custom-Header": "value"}` |
| 状态 | 开关 | 有效 / 已过期 / 已撤销 |

### 5.4 加密方案

```python
# 加密: AES-256-GCM
# 密钥来源: 环境变量 RPA_API_ENCRYPTION_KEY
# 存储格式: IV(12bytes) + Ciphertext + Tag(16bytes)，Base64 编码

import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_KEY = os.environ.get("RPA_API_ENCRYPTION_KEY", os.urandom(32))

def encrypt(plaintext: str) -> str:
    aesgcm = AESGCM(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()

def decrypt(encoded: str) -> str:
    aesgcm = AESGCM(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
    raw = base64.b64decode(encoded)
    nonce, ciphertext = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
```

> **面试话术**："API 密钥采用 AES-256-GCM 加密存储，密钥从环境变量注入，不在代码中硬编码。前端只返回脱敏后的凭证标识（如 `amzn1.applica***`），密钥原文仅在 Worker 调用 API 时解密到内存，调用完毕后立即释放。这个方案符合 PCI-DSS 和 SOC2 的密钥管理要求。"

---

## 6. 子模块二：API 任务配置

### 6.1 功能概述

API 任务配置与现有的 Playwright 任务配置**共用 `task_config` 表**。通过新增字段 `collect_type` 区分（已有字段，值为 `api` / `browser`）。

### 6.2 页面布局

```
┌──────────────────────────────────────────────────────────────────┐
│  🔌 API 采集任务配置                              [+ 新增任务]    │
├──────────────────────────────────────────────────────────────────┤
│  ┌─ 平台筛选 ─────────────────────────────────────────────────┐  │
│  │ [全部] [Amazon] [Walmart] [Shopee] [自定义HTTP]             │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ 📋 Amazon 订单报表采集        Amazon · 每天 06:00 · ● 启用  │  │
│  │    端点: /orders/v0/orders   调度: cron(0 6 * * *)         │  │
│  │    [编辑] [手动执行] [查看日志] [停用] [删除]               │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │ 📋 Walmart 库存同步            Walmart · 手动触发 · ● 启用  │  │
│  │    端点: /v3/inventory        调度: 手动                    │  │
│  │    [编辑] [手动执行] [查看日志] [停用] [删除]               │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │ 📋 自定义数据接口              自定义HTTP · 每小时 · ○ 停用 │  │
│  │    端点: https://api.example.com/data                       │  │
│  │    [编辑] [手动执行] [查看日志] [启用] [删除]               │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 6.3 任务编辑器（模态框）

```
┌──────────────────────────────────────────────────────────────────┐
│  编辑 API 采集任务                                    [保存]     │
├──────────────────────────────────────────────────────────────────┤
│  任务名称: [Amazon 订单报表采集___________]                      │
│  凭证:     [Amazon SP-API (EcomIQ-US) ▼]    [管理凭证]          │
│  平台:     [Amazon ▼]                                           │
│  HTTP方法: [GET ▼]                                              │
│  API端点:  [/orders/v0/orders_______________]                    │
│                                                                   │
│  查询参数 (JSON):                                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ {                                                          │  │
│  │   "MarketplaceIds": ["ATVPDKIKX0DER"],                     │  │
│  │   "CreatedAfter": "{{yesterday}}"                          │  │
│  │ }                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│  可用变量: {{today}} {{yesterday}} {{start_of_week}} {{last_7d}} │
│                                                                   │
│  调度方式: [定时执行 ▼]                                          │
│  Cron表达式: [0 6 * * *___________]  (每天 06:00)               │
│  超时时间:  [300_____] 秒                                       │
│  重试次数:  [3_]                                                 │
│  限频:      [每 60 秒最多 10_____] 次请求                       │
│                                                                   │
│  数据目标:                                                       │
│  ODS表名: [ods_amazon_order_raw ▼]                              │
│  写入模式: [追加 ▼]  (追加 / 覆盖 / 增量合并)                    │
│  字段映射 (JSON): 留空则自动映射                                 │
│                                                                   │
│  状态: [● 启用]                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 6.4 与 Playwright 任务配置的统一

| 字段 | Playwright 任务 | API 任务 |
|:---|:---|:---|
| `task_name` | ✅ 共用 | ✅ 共用 |
| `script_name` | `"amazon_order"` 等 | `"api_collect"` |
| `collect_type` | `"browser"` | `"api"` (**新增区分**) |
| `platform` | ✅ 共用 | ✅ 共用 |
| `shop_name` | ✅ 共用 | ✅ 共用 |
| `schedule_type` | ✅ 共用 | ✅ 共用 |
| `cron_expression` | ✅ 共用 | ✅ 共用 |
| `executor_ip` | ✅ 共用 | ✅ 共用 |
| `timeout_sec` | ✅ 共用 | ✅ 共用 |
| **`api_endpoint`** | ❌ 不需要 | ✅ **新增** |
| **`api_params`** | ❌ 不需要 | ✅ **新增** (JSON) |
| **`credential_id`** | ❌ 不需要 | ✅ **新增** |

> **架构决策**：不新建 `api_task_config` 表。通过扩展现有 `task_config` 表字段，API 任务和 Playwright 任务在同一张表中管理，Worker 通过 `collect_type` 字段路由到不同的执行器。这避免了表分裂，简化了调度逻辑。

---

## 7. 子模块三：API 执行记录与监控

### 7.1 页面布局

```
┌──────────────────────────────────────────────────────────────────┐
│  🔌 API 执行记录                                    [导出]       │
├──────────────────────────────────────────────────────────────────┤
│  平台: [全部 ▼]  状态: [全部 ▼]  时间: [最近7天 ▼]  🔍 [搜索]  │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 时间              │ 任务            │ 状态   │ 耗时  │ 数据量 │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │ 2026-06-27 06:00 │ Amazon 订单报表  │ ✅ 成功 │ 12.3s │ 1,247条│
│  │ 2026-06-27 06:00 │ Walmart 库存同步 │ ❌ 失败 │ 8.2s  │ 0条    │
│  │                   │ 401 Unauthorized │ [查看详情] [重试]    │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │ 2026-06-26 06:00 │ Amazon 订单报表  │ ⚠️ 降级 │ 15.1s │ 892条  │
│  │                   │ 限频触发，降级重试│ [查看详情]          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                              ← 1 2 3 ... 7 →    │
└──────────────────────────────────────────────────────────────────┘
```

### 7.2 调用详情弹窗

点击某条记录展开：

```
┌──────────────────────────────────────────────────┐
│  API 调用详情                                     │
├──────────────────────────────────────────────────┤
│  任务: Amazon 订单报表采集                         │
│  端点: GET /orders/v0/orders                      │
│  时间: 2026-06-27 06:00:15 → 06:00:27 (12.3s)    │
│  状态: ✅ 成功 (HTTP 200)                         │
│  请求参数: {"MarketplaceIds":["ATV..."],...}      │
│  响应大小: 245,832 bytes                          │
│  数据条目: 1,247 条                               │
│  写入 ODS: ods_amazon_order_raw                   │
│  ──────────────────────────────────────────────── │
│  响应预览 (前 500 字符):                           │
│  {"payload":{"Orders":[{"AmazonOrderId":"...     │
│  ──────────────────────────────────────────────── │
│  限频信息:                                        │
│  X-Amzn-RateLimit-Limit: 10                       │
│  X-Amzn-RateLimit-Remaining: 8                    │
│  [重试此任务] [导出响应] [关闭]                    │
└──────────────────────────────────────────────────┘
```

---

## 8. 子模块四：API 适配器框架

### 8.1 适配器抽象基类

```python
# api_collectors/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import time
import requests
import json

@dataclass
class APICallResult:
    """API 调用结果"""
    success: bool
    http_status: int
    response_body: str
    record_count: int = 0
    duration_ms: int = 0
    error_message: str = ""
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[int] = None

class BaseAPICollector(ABC):
    """API 采集器抽象基类"""

    def __init__(self, credential: dict, config: dict):
        self.credential = credential      # 解密后的凭证
        self.config = config              # 任务配置
        self._session = requests.Session()
        self._rate_limit_remaining = None
        self._rate_limit_reset = None

    # ========== 子类必须实现 ==========

    @abstractmethod
    def authenticate(self) -> bool:
        """认证：OAuth / API Key / 签名"""
        ...

    @abstractmethod
    def call(self, endpoint: str, method: str = "GET", params: dict = None) -> APICallResult:
        """执行 API 调用"""
        ...

    @abstractmethod
    def parse_response(self, raw: str, target_ods_table: str) -> int:
        """解析响应 → 写入 ODS 表 → 返回记录数"""
        ...

    # ========== 通用方法 ==========

    def execute(self) -> APICallResult:
        """完整执行流程: 认证 → 调用 → 解析 → 记录"""
        t0 = time.time()
        try:
            if not self.authenticate():
                return APICallResult(False, 401, "", error_message="认证失败")
            result = self.call(
                self.config.get("api_endpoint", ""),
                self.config.get("http_method", "GET"),
                json.loads(self.config.get("api_params", "{}")),
            )
            if result.success:
                result.record_count = self.parse_response(
                    result.response_body,
                    self.config.get("target_ods_table", ""),
                )
            result.duration_ms = int((time.time() - t0) * 1000)
            return result
        except Exception as e:
            return APICallResult(False, 0, "", error_message=str(e),
                                duration_ms=int((time.time() - t0) * 1000))

    def _check_rate_limit(self, response_headers: dict):
        """从响应头提取限频信息"""
        self._rate_limit_remaining = response_headers.get("X-RateLimit-Remaining")
        self._rate_limit_reset = response_headers.get("X-RateLimit-Reset")

    def _rate_limit_wait(self):
        """等待限频重置"""
        if self._rate_limit_reset:
            wait = max(0, int(self._rate_limit_reset) - time.time())
            if wait > 0 and wait < 60:
                time.sleep(wait + 1)
```

### 8.2 通用 HTTP 适配器（覆盖 80% 场景）

```python
# api_collectors/generic_http.py
class GenericHTTPCollector(BaseAPICollector):
    """通用 HTTP API 采集器 — 支持 Bearer Token / Custom Headers"""

    def authenticate(self) -> bool:
        token = self.credential.get("access_token", "")
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        # 合并自定义 Header
        custom_headers = json.loads(self.credential.get("custom_headers", "{}"))
        self._session.headers.update(custom_headers)
        return True

    def call(self, endpoint: str, method: str = "GET", params: dict = None) -> APICallResult:
        url = self.credential.get("base_url", "") + endpoint
        resp = self._session.request(method, url, json=params, timeout=self.config.get("timeout_sec", 300))
        self._check_rate_limit(resp.headers)
        return APICallResult(
            success=200 <= resp.status_code < 300,
            http_status=resp.status_code,
            response_body=resp.text,
            rate_limit_remaining=self._rate_limit_remaining,
            rate_limit_reset=self._rate_limit_reset,
        )

    def parse_response(self, raw: str, target_ods_table: str) -> int:
        import pandas as pd
        data = json.loads(raw)
        # 自动探测 JSON 中的数据数组
        array_data = self._find_data_array(data)
        if not array_data:
            return 0
        df = pd.DataFrame(array_data)
        # 写入 ODS
        from core.db_operations import DatabaseManager
        db = DatabaseManager()
        db.write_to_ods(target_ods_table, df)
        return len(df)

    def _find_data_array(self, data: dict) -> Optional[list]:
        """自动探测嵌套 JSON 中的数据数组"""
        for key in ["payload", "data", "orders", "items", "results", "records"]:
            if key in data and isinstance(data[key], list):
                return data[key]
        for v in data.values():
            if isinstance(v, list):
                return v
        return None
```

### 8.3 Steam SP-API 适配器（二期）

```python
# api_collectors/amazon_sp_api.py
class AmazonSPAPICollector(BaseAPICollector):
    """Amazon Selling Partner API 适配器"""

    def authenticate(self) -> bool:
        # LWAAuth: client_id + client_secret + refresh_token → access_token
        ...

    def call(self, endpoint, method="GET", params=None):
        # 签名: AWS Signature V4
        ...

    def parse_response(self, raw, target_ods_table):
        # 解析 SP-API 响应格式
        ...
```

---

## 9. 数据库设计

### 9.1 新增表

> **原则**：最少新增表。API 任务配置复用 `task_config`，执行记录复用 `task_record`。

#### 9.1.1 API 凭证表（新增）

```sql
CREATE TABLE api_credentials (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(200)  NOT NULL COMMENT '凭证名称',
    platform        VARCHAR(50)   NOT NULL COMMENT 'Amazon/Walmart/Shopee/1688/custom',
    shop_name       VARCHAR(100)  DEFAULT NULL COMMENT '关联店铺(dim_shop_info.shop_name)',
    auth_type       VARCHAR(50)   NOT NULL COMMENT '认证方式: oauth2/api_key/bearer/hmac',
    base_url        VARCHAR(500)  DEFAULT NULL COMMENT 'API 基础URL',
    client_id       TEXT          DEFAULT NULL COMMENT 'Client ID / App Key (AES加密)',
    client_secret   TEXT          DEFAULT NULL COMMENT 'Client Secret (AES加密)',
    access_token    TEXT          DEFAULT NULL COMMENT 'Access Token (AES加密)',
    refresh_token   TEXT          DEFAULT NULL COMMENT 'Refresh Token (AES加密)',
    custom_headers  JSON          DEFAULT NULL COMMENT '自定义Header JSON',
    expires_at      DATETIME      DEFAULT NULL COMMENT 'Token过期时间',
    status          ENUM('active','expired','revoked') DEFAULT 'active',
    created_by      VARCHAR(50)   DEFAULT NULL,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_platform (platform),
    INDEX idx_shop (shop_name),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='API凭证表(加密存储)';
```

#### 9.1.2 API 调用日志表（新增）

```sql
CREATE TABLE api_call_logs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    task_uuid       VARCHAR(50)   DEFAULT NULL COMMENT '关联 task_queue.task_uuid',
    credential_id   INT           DEFAULT NULL COMMENT '关联 api_credentials.id',
    platform        VARCHAR(50)   DEFAULT NULL,
    endpoint        VARCHAR(500)  NOT NULL,
    http_method     VARCHAR(10)   DEFAULT 'GET',
    request_params  JSON          DEFAULT NULL,
    http_status     INT           DEFAULT NULL,
    response_size   INT           DEFAULT NULL COMMENT '响应大小(bytes)',
    record_count    INT           DEFAULT 0 COMMENT '入库记录数',
    duration_ms     INT           DEFAULT NULL COMMENT '耗时(毫秒)',
    error_message   TEXT          DEFAULT NULL,
    rate_limit_remaining INT     DEFAULT NULL,
    rate_limit_reset     INT     DEFAULT NULL,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_task (task_uuid),
    INDEX idx_platform (platform),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='API调用日志表';
```

### 9.2 扩展已有表

#### 9.2.1 task_config 表扩展

```sql
-- 扩展 task_config 表（已有），新增 API 采集字段
ALTER TABLE task_config
ADD COLUMN collect_type   VARCHAR(20) DEFAULT 'browser' COMMENT '采集类型: browser/api',
ADD COLUMN api_endpoint   VARCHAR(500) DEFAULT NULL COMMENT 'API 端点',
ADD COLUMN api_method     VARCHAR(10)  DEFAULT 'GET' COMMENT 'HTTP方法',
ADD COLUMN api_params     JSON         DEFAULT NULL COMMENT 'API参数JSON',
ADD COLUMN credential_id  INT          DEFAULT NULL COMMENT '关联 api_credentials.id',
ADD COLUMN target_ods_table VARCHAR(100) DEFAULT NULL COMMENT '目标ODS表',
ADD COLUMN write_mode     VARCHAR(20)  DEFAULT 'append' COMMENT '写入模式: append/overwrite/merge';
```

---

## 10. API 接口设计

### 10.1 凭证管理 API

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/rpa/api/api_collect/credentials` | 凭证列表 |
| `POST` | `/rpa/api/api_collect/credentials` | 创建凭证（加密存储） |
| `PUT` | `/rpa/api/api_collect/credentials/<id>` | 更新凭证 |
| `DELETE` | `/rpa/api/api_collect/credentials/<id>` | 删除凭证 |
| `GET` | `/rpa/api/api_collect/credentials/<id>/masked` | 获取脱敏凭证（用于回填编辑） |

### 10.2 任务配置 API（扩展现有）

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/rpa/api/tasks/config?collect_type=api` | API 任务列表（复用现有接口） |
| `POST` | `/rpa/api/tasks/config` | 创建任务（扩展字段支持 API） |

### 10.3 执行记录 API

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/rpa/api/api_collect/logs` | API 调用日志列表（分页+筛选） |
| `GET` | `/rpa/api/api_collect/logs/<id>` | 日志详情 |
| `POST` | `/rpa/api/api_collect/run/<task_config_id>` | 手动执行 API 任务 |

### 10.4 统一响应格式

```json
{
  "success": true,
  "data": {},
  "error": ""
}
```

---

## 11. 前端页面设计

### 11.1 页面清单

| 页面文件 | 路由 | 说明 |
|:---|:---|:---|
| `api_collect_config.html` | `/rpa/api_collect` | **重构**：Tab 切换「凭证管理」+「任务配置」 |
| `api_collect_logs.html` | `/rpa/api_collect/logs` | **重构**：API 调用日志列表 + 详情弹窗 |

### 11.2 交互规范

| 场景 | 交互方式 |
|:---|:---|
| 凭证管理 | 卡片列表 + 模态框编辑器 |
| 任务配置 | 表格列表 + 模态框编辑器 |
| 日志查看 | 表格 + 分页 + 筛选 + 行展开详情 |
| 密钥输入 | 密码框 + 显示/隐藏切换 + 加密存储提示 |
| 手动执行 | 按钮 → 确认对话框 → Toast 通知 |

### 11.3 侧边栏不变

API 采集侧边栏当前结构保持不变，但功能从占位变为完整：

```html
<li><a href="/rpa/api_collect"><i class="bi bi-sliders2"></i> API任务配置</a></li>
<li><a href="/rpa/api_collect/logs"><i class="bi bi-journal-text"></i> API执行记录</a></li>
```

---

## 12. 与现有系统的集成方案

### 12.1 调度集成

API 任务注册到 `task_config` 后，调度流程与现有 Playwright 任务**完全一致**：

1. 用户在页面点击"手动执行"或 Cron 触发
2. 调用 `/rpa/api/tasks/run/<config_id>`
3. 现有的 `task_run_now()` 函数（`blueprint.py` 第 928 行）构造 `task_msg`，写入 Redis MQ 或 DB
4. Worker 消费任务时，检查 `collect_type == "api"` → 路由到 `APICollectorExecutor`
5. API 执行器调用适配器完成认证 → 请求 → 解析 → 写入 ODS
6. 结果写入 `task_record` + `api_call_logs`

### 12.2 Worker 修改

```python
# worker.py 中新增路由:
if task.get("collect_type") == "api":
    from api_collectors.executor import execute_api_task
    execute_api_task(task)
else:
    # 现有 Playwright 采集逻辑
    run_collection(task)
```

### 12.3 店管理关联

- API 凭证 → 关联 `dim_shop_info.shop_name`
- API 任务 → 关联 `dim_shop_info.shop_name`
- 执行记录 → 关联 `task_queue.task_uuid`
- 数据写入目标 → 复用现有 ODS 表（如 `ods_amazon_order_raw`）

---

## 13. 开发分期计划

### 第一期（MVP · 1周）

**目标**：凭证管理 + 通用 HTTP 采集器 + 日志查看

| 任务 | 工期 | 产出 |
|:---|:---|:---|
| 创建 `api_credentials` 和 `api_call_logs` 表 | 0.5天 | DDL + 加密工具类 |
| API 凭证管理 CRUD + 前端 | 2天 | 凭证增删改查 + 模态框 |
| 通用 HTTP 适配器开发 | 1天 | `GenericHTTPCollector` |
| API 任务配置（扩展 task_config） | 1天 | 任务编辑模态框 + 调度集成 |
| API 执行日志列表 + 详情 | 1天 | 日志页面重构 |
| 联调测试 | 0.5天 | — |

### 第二期（平台适配 · 2周）

- Amazon SP-API 适配器
- 限频策略与重试机制
- 定时任务调度（Cron 集成）
- 数据校验（API vs Playwright 双轨对比）

### 第三期（扩展 · 2周）

- Walmart / Shopee / 1688 适配器
- OAuth 2.0 自动刷新 Token
- API 调用统计看板

---

## 14. 技术选型与约束

| 层级 | 选型 | 理由 |
|:---|:---|:---|
| **后端框架** | Flask (复用现有蓝图) | 零新增依赖 |
| **HTTP 客户端** | `requests` (已在 requirements.txt) | 已在项目中使用 |
| **加密库** | `cryptography` (需新增) | AES-256-GCM 工业标准 |
| **数据库** | MySQL 8.0 (复用现有 data 库) | 已有连接池 |
| **前端** | Bootstrap 5.3 + Vanilla JS | 与现有 Admin 一致 |
| **调度** | Redis MQ / DB 降级 (复用) | 已有基础设施 |
| **序列化** | JSON | 通用 |

### 新增依赖

| 包 | 用途 |
|:---|:---|
| `cryptography` | AES-256-GCM 加密 API 密钥 |

---

## 15. 风险与缓解措施

| 风险 | 等级 | 缓解措施 |
|:---|:---|:---|
| API 密钥泄露 | 🔴 高 | AES-256-GCM 加密 + 环境变量密钥 + 前端脱敏展示 |
| API 限频导致数据缺失 | 🟡 中 | 从响应头提取限频信息 → 自动等待 → 指数退避重试 |
| Token 过期 | 🟡 中 | 到期前 24 小时告警；OAuth 自动 refresh_token |
| 第三方 API 变更 | 🟡 中 | 适配器模式隔离 + 版本化端点 |
| Worker 执行超时 | 🟢 低 | task_config 中配置 timeout_sec + 数据库状态兜底 |
| 与现有 task_config 冲突 | 🟢 低 | 通过 `collect_type` 字段区分，默认 `"browser"` 向后兼容 |

---

## 附录 A：凭证脱敏规则

| 字段 | 脱敏规则 | 示例 |
|:---|:---|:---|
| `client_id` | 显示前 4 位 + `***` | `amzn***` |
| `client_secret` | 完全不返回 | `******` |
| `access_token` | 显示 `******` + 最后 4 位 | `******aB3d` |
| `refresh_token` | 完全不返回 | `******` |

---

## 附录 B：任务执行状态机

```
PENDING ──→ RUNNING ──→ SUCCESS
   │           │
   │           └──→ FAILED ──→ (重试) PENDING
   │
   └──→ (超时) CANCELLED
```

API 采集任务与 Playwright 任务共用 `task_queue.task_status` 状态字段。

---

> **文档结尾**  
> 本文档从架构师、RPA 实施工程师、技术经理三个视角出发，设计了 API 采集模块的完整方案。  
> 核心原则：**复用现有基础设施，适配器模式隔离平台差异，加密保障凭证安全。**  
> MVP 阶段聚焦于通用 HTTP 采集能力 + 凭证管理 + 日志追溯，为后续 Amazon SP-API 等平台适配打下基础。
