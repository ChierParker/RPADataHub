"""任务模型 — 描述一个采集任务的完整参数"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass
class TaskConfig:
    """任务配置（映射 task_config 表 + MQ 消息）"""
    task_id: str = ""
    trace_id: str = ""
    script_code: str = ""           # collector 注册键
    collector_type: str = "playwright"
    machine_code: str = ""
    timeout_sec: int = 3600
    priority: str = "NORMAL"

    # 采集参数
    account: str = ""
    countries: list = field(default_factory=list)
    shops: list = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    recollect: bool = False
    collection_type: str = "Daily"
    exclude_country: list = field(default_factory=list)

    # 回调
    callback: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, s: str) -> "TaskConfig":
        d = json.loads(s) if isinstance(s, str) else s
        params = d.get("params", {})
        cb = d.get("callback", {})
        return cls(
            task_id=d.get("taskId", d.get("task_uuid", "")),
            trace_id=d.get("traceId", d.get("trace_id", "")),
            script_code=d.get("scriptCode", d.get("script_name", "")),
            collector_type=d.get("collectorType", "playwright"),
            machine_code=d.get("machineCode", ""),
            timeout_sec=d.get("timeoutSec", 3600),
            priority=d.get("priority", "NORMAL"),
            account=params.get("account", d.get("shop_name", "")),
            countries=params.get("countries", []),
            shops=params.get("shops", []) or [params.get("shop_name", "")],
            start_date=params.get("startDate", d.get("business_date", "")),
            end_date=params.get("endDate", ""),
            recollect=params.get("recollect", False),
            collection_type=params.get("collectionType", d.get("collect_type", "Daily")),
            exclude_country=params.get("excludeCountry", []),
            callback=cb,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def to_cli_args(self) -> list:
        """转换为命令行参数列表"""
        args = []
        if self.account: args += ["--account", self.account]
        if self.countries: args += ["--country"] + self.countries
        if self.start_date: args += ["--start_date", self.start_date]
        if self.end_date: args += ["--end_date", self.end_date]
        if self.recollect: args += ["--recollect", "1"]
        if self.collection_type: args += ["--collection_type", self.collection_type]
        if self.exclude_country: args += ["--exclude_country"] + self.exclude_country
        return args
