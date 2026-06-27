# Playwright Collection Script

> 电商数据采集器集合 — 基于 BaseCollector 标准化接口，支持 Redis MQ 分布式调度

## 架构

```
Admin 下发任务
    ↓
Redis MQ (LPUSH/BRPOP) 或 task_queue 表
    ↓
Worker 领取 → main.py --task <collector_name>
    ↓
CollectorRegistry → BaseCollector.execute()
    ↓
采集输出 → D:/rpa_output/ → file_watcher 消费 → ODS 入库
```

## 快速开始

```bash
pip install -r requirements.txt

# 列出可用采集器
python main.py --list

# 执行采集
python main.py --task sina_finance       # 新浪财经要闻
python main.py --task demo_po            # PO单采集(Demo)
python main.py --task demo_aba           # ABA关键词(Demo)

# Worker 模式 (持续轮询)
python main.py --worker
```

## 可用采集器

| 名称 | 类型 | 依赖 | 说明 |
|------|------|------|------|
| `sina_finance` | 公开网站 | Playwright | 新浪财经要闻采集 |
| `demo_po` | Demo | 无 | PO 单模拟采集，生成随机订单数据 |
| `demo_aba` | Demo | 无 | ABA 关键词模拟采集，生成搜索排名数据 |

## 目录结构

```
playwright_collection_script/
├── main.py                    # 统一任务入口
├── collector_registry.py      # 采集器注册中心
├── schemas/                   # 数据模型
│   ├── task_schema.py         #   TaskConfig
│   ├── result_schema.py       #   ShopRecord / TaskSummary
│   ├── log_schema.py          #   结构化日志
│   └── status_schema.py       #   状态机
├── collectors/                # 采集器集合
│   ├── base.py                #   BaseCollector 基类
│   ├── sina_finance.py        #   新浪财经采集器
│   └── demo_collector.py      #   PO + ABA Demo
├── runtime/                   # 运行时
│   ├── context.py             #   执行上下文
│   ├── logger.py              #   结构化日志
│   ├── reporter.py            #   状态/结果上报 DB
│   ├── artifact_manager.py    #   产物管理
│   ├── process_guard.py       #   超时/取消/单实例锁
│   └── exception_handler.py   #   异常分类
├── mq/                        # 消息队列
│   ├── consumer.py            #   TaskConsumer (DB 轮询)
│   ├── producer.py            #   任务入队
│   └── message_adapter.py     #   消息 ↔ TaskConfig
├── library/                   # 工具库
└── requirements.txt
```

## 新增采集器

继承 `BaseCollector` 实现 `run(config) -> TaskSummary`：

```python
from collectors.base import BaseCollector
from schemas.task_schema import TaskConfig, TaskSummary

class MyCollector(BaseCollector):
    collector_name = "my_collector"
    default_ods_table = "ods_my_table"

    def run(self, config: TaskConfig) -> TaskSummary:
        for shop in config.shops:
            # 采集逻辑
            self.add_record(shop, "SUCCESS", row_count=100)
        return self.build_summary(total_rows=total)
```

然后在 `collector_registry.py` 注册：

```python
from collectors.my_collector import MyCollector
_registry.register("my_collector", MyCollector)
```

Admin → 任务管理 → 新增任务 → 脚本名填 `my_collector` 即可。

## Demo 模式

无需任何外部依赖即可验证全链路：

```bash
python main.py --task demo_po    # 生成模拟订单 Excel → D:/rpa_output/demo_po/
python main.py --task demo_aba   # 生成模拟关键词 Excel → D:/rpa_output/demo_aba/
```

输出文件会被 `file_watcher.py` 自动消费入库到 ODS 层。

## 技术栈

- **Playwright** — 浏览器自动化
- **Redis List** — LPUSH/BRPOP 消息队列
- **MySQL** — task_queue 审计 + 降级兜底
- **Pandas** — Excel 读写
- **BaseCollector** — 模板方法模式（生命周期钩子）
