"""状态/结果上报器 — 写入 task_record / task_summary 表 + task_queue 状态更新"""
import json
import sys
from pathlib import Path
from datetime import datetime
from schemas.result_schema import ShopRecord, TaskSummary

# 动态导入项目数据库配置
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    from config.settings import get_config
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


class StatusReporter:
    """上报任务状态和结果到数据库"""

    def __init__(self, trace_id: str = ""):
        self.trace_id = trace_id

    def _get_conn(self):
        if not DB_AVAILABLE:
            return None
        import pymysql
        cfg = get_config()
        return pymysql.connect(**cfg.database.as_dict())

    def report_record(self, record: ShopRecord):
        """写入单店铺采集明细"""
        conn = self._get_conn()
        if not conn: return
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO task_record (task_uuid, shop_name, platform, script_name, ods_table,
                   collect_start, collect_end, collect_result, row_count, error_message, duration_sec)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                record.to_db_row()
            )
            conn.commit()
        except Exception as e:
            print(f"[Reporter] 写入记录失败: {e}")
        finally:
            conn.close()

    def report_summary(self, summary: TaskSummary):
        """写入任务汇总"""
        conn = self._get_conn()
        if not conn: return
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO task_summary (task_uuid, task_name, total_shops, success_shops,
                   failed_shops, no_data_shops, total_rows, total_duration, success_rate, summary_json)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE success_shops=VALUES(success_shops),
                   failed_shops=VALUES(failed_shops), no_data_shops=VALUES(no_data_shops),
                   total_rows=VALUES(total_rows), total_duration=VALUES(total_duration),
                   success_rate=VALUES(success_rate)""",
                (summary.task_uuid, summary.task_name, summary.total_shops,
                 summary.success_shops, summary.failed_shops, summary.no_data_shops,
                 summary.total_rows, summary.total_duration, summary.success_rate,
                 json.dumps(summary.to_dict(), ensure_ascii=False))
            )
            conn.commit()
        except Exception as e:
            print(f"[Reporter] 写入汇总失败: {e}")
        finally:
            conn.close()

    def update_task_status(self, task_uuid: str, status: str, error: str = ""):
        """更新 task_queue 状态"""
        conn = self._get_conn()
        if not conn: return
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE task_queue SET task_status=%s, end_time=NOW(), error_message=%s
                   WHERE task_uuid=%s""",
                (status, error[:2000], task_uuid)
            )
            conn.commit()
        except Exception as e:
            print(f"[Reporter] 更新状态失败: {e}")
        finally:
            conn.close()
