"""
Collector 基类 — 所有采集器必须继承此类
提供标准化的: 执行上下文 / 结果上报 / 异常处理 / 输出管理
"""

import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import Optional

from schemas.task_schema import TaskConfig
from schemas.result_schema import ShopRecord, TaskSummary


class BaseCollector(ABC):
    """
    采集器基类

    子类必须实现:
        run(config: TaskConfig) -> TaskSummary
    """

    # 子类覆盖这些属性
    collector_name: str = "base"
    supported_platforms: list = []
    default_ods_table: str = ""

    def __init__(self):
        self._ctx: Optional[TaskConfig] = None
        self._start_time: float = 0
        self._records: list = []
        self._errors: list = []

    # ============================================================
    # 生命周期
    # ============================================================

    def execute(self, config: TaskConfig) -> TaskSummary:
        """统一执行入口（模板方法）"""
        self._ctx = config
        self._start_time = time.time()
        self._records = []
        self._errors = []

        try:
            self._on_start()
            summary = self.run(config)
            self._on_success(summary)
            return summary
        except Exception as e:
            summary = self._on_error(e)
            return summary
        finally:
            self._on_finish()

    def _write_to_db(self, summary: TaskSummary):
        """将采集记录和汇总写入数据库"""
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
            from config.settings import get_config
            import pymysql

            cfg = get_config()
            conn = pymysql.connect(**cfg.database.as_dict())
            cur = conn.cursor()

            # 写入单店铺明细
            for rec in self._records:
                cur.execute(
                    """INSERT INTO task_record (task_uuid, shop_name, platform, script_name, ods_table,
                       collect_start, collect_end, collect_result, row_count, error_message, duration_sec)
                       VALUES (%s,%s,%s,%s,%s,NOW(),NOW(),%s,%s,%s,%s)""",
                    (summary.task_uuid, rec.shop_name, rec.platform, self.collector_name,
                     self.default_ods_table, rec.collect_result, rec.row_count,
                     rec.error_message, rec.duration_sec)
                )

            # 写入任务汇总
            cur.execute(
                """INSERT INTO task_summary (task_uuid, task_name, total_shops, success_shops,
                   failed_shops, no_data_shops, total_rows, total_duration, success_rate)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE success_shops=VALUES(success_shops),
                   failed_shops=VALUES(failed_shops), no_data_shops=VALUES(no_data_shops),
                   total_rows=VALUES(total_rows), total_duration=VALUES(total_duration),
                   success_rate=VALUES(success_rate)""",
                (summary.task_uuid, summary.task_name or self.collector_name,
                 summary.total_shops, summary.success_shops, summary.failed_shops,
                 summary.no_data_shops, summary.total_rows, summary.total_duration,
                 summary.success_rate)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[BaseCollector] DB写入失败: {e}")

    def _on_start(self):
        """任务开始钩子"""
        pass

    def _on_success(self, summary: TaskSummary):
        """任务成功钩子"""
        summary.total_duration = int(time.time() - self._start_time)
        summary.compute()
        self._write_to_db(summary)

    def _on_error(self, error: Exception) -> TaskSummary:
        """任务失败钩子"""
        self.add_record(
            shop_name=self._ctx.account or self._ctx.shops[0] if self._ctx and self._ctx.shops else "unknown",
            result="FAILED", error=str(error)[:500],
            duration=int(time.time() - self._start_time)
        )
        summary = TaskSummary(
            task_uuid=self._ctx.task_id if self._ctx else "",
            task_name=self.collector_name,
            total_shops=len(self._ctx.shops) if self._ctx else 1,
            failed_shops=len(self._ctx.shops) if self._ctx else 1,
            total_duration=int(time.time() - self._start_time),
            errors=[str(error), traceback.format_exc()]
        )
        summary.compute()
        return summary

    def _on_finish(self):
        """任务结束钩子（无论成功失败）"""
        pass

    # ============================================================
    # 子类必须实现
    # ============================================================

    @abstractmethod
    def run(self, config: TaskConfig) -> TaskSummary:
        """
        执行采集逻辑

        参数:
            config: 任务参数

        返回:
            TaskSummary: 任务汇总结果
        """
        ...

    # ============================================================
    # 辅助方法（子类可调用）
    # ============================================================

    def add_record(self, shop_name: str, result: str, row_count: int = 0,
                   error: str = "", duration: int = 0, platform: str = ""):
        """记录单店铺采集结果"""
        self._records.append(ShopRecord(
            task_uuid=self._ctx.task_id if self._ctx else "",
            shop_name=shop_name,
            platform=platform or (self._ctx.platform if hasattr(self._ctx, 'platform') else ""),
            script_name=self.collector_name,
            ods_table=self.default_ods_table,
            collect_start=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            collect_end=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            collect_result=result,
            row_count=row_count,
            error_message=error,
            duration_sec=duration
        ))

    def build_summary(self, total_rows: int = 0) -> TaskSummary:
        """从记录列表构建汇总"""
        success = sum(1 for r in self._records if r.collect_result == "SUCCESS")
        failed = sum(1 for r in self._records if r.collect_result == "FAILED")
        no_data = sum(1 for r in self._records if r.collect_result == "NO_DATA")

        return TaskSummary(
            task_uuid=self._ctx.task_id if self._ctx else "",
            task_name=self.collector_name,
            total_shops=len(self._records),
            success_shops=success,
            failed_shops=failed,
            no_data_shops=no_data,
            total_rows=total_rows,
        )

    def get_output_dir(self) -> Path:
        """获取输出目录"""
        base = Path(__file__).resolve().parent.parent / "output"
        base.mkdir(exist_ok=True)
        return base

    @property
    def records(self) -> list:
        return self._records
