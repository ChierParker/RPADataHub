"""日志模型 — 结构化日志输出"""
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json


class LogLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


@dataclass
class LogEntry:
    """单条结构化日志"""
    timestamp: str = ""
    level: str = "INFO"
    task_uuid: str = ""
    step: str = ""
    message: str = ""
    duration_ms: int = 0
    extra: dict = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        if self.extra is None:
            self.extra = {}

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def info(cls, task_uuid: str, step: str, message: str, **extra) -> "LogEntry":
        return cls(level="INFO", task_uuid=task_uuid, step=step, message=message, extra=extra)

    @classmethod
    def error(cls, task_uuid: str, step: str, message: str, **extra) -> "LogEntry":
        return cls(level="ERROR", task_uuid=task_uuid, step=step, message=message, extra=extra)

    @classmethod
    def warn(cls, task_uuid: str, step: str, message: str, **extra) -> "LogEntry":
        return cls(level="WARN", task_uuid=task_uuid, step=step, message=message, extra=extra)
