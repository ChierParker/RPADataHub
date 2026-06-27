"""结果模型 — 采集器返回的标准结果"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


class CollectResult(str):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NO_DATA = "NO_DATA"


@dataclass
class ShopRecord:
    """单店铺采集明细（写入 task_record 表）"""
    task_uuid: str = ""
    shop_name: str = ""
    platform: str = ""
    script_name: str = ""
    ods_table: str = ""
    collect_start: str = ""
    collect_end: str = ""
    collect_result: str = "SUCCESS"
    row_count: int = 0
    error_message: str = ""
    duration_sec: int = 0

    def to_db_row(self) -> tuple:
        return (
            self.task_uuid, self.shop_name, self.platform, self.script_name,
            self.ods_table, self.collect_start, self.collect_end,
            self.collect_result, self.row_count, self.error_message, self.duration_sec
        )


@dataclass
class TaskSummary:
    """任务汇总（写入 task_summary 表）"""
    task_uuid: str = ""
    task_name: str = ""
    total_shops: int = 0
    success_shops: int = 0
    failed_shops: int = 0
    no_data_shops: int = 0
    total_rows: int = 0
    total_duration: int = 0
    success_rate: float = 0.0
    output_files: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def compute(self):
        if self.total_shops > 0:
            self.success_rate = round(self.success_shops / self.total_shops * 100, 2)

    def to_dict(self) -> dict:
        return asdict(self)
