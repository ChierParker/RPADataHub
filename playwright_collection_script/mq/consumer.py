"""
MQ消费端 — 轮询 task_queue 表，模拟消息队列消费
实际部署时可替换为 RabbitMQ / Kafka / Redis Stream
"""

import json
import time
import socket
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    from config.settings import get_config
    import pymysql
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


class TaskConsumer:
    """任务消费者 — 轮询 task_queue 表取 PENDING 任务"""

    def __init__(self, machine_ip: str = None, poll_interval: int = 5):
        self.machine_ip = machine_ip or socket.gethostbyname(socket.gethostname())
        self.poll_interval = poll_interval
        self._running = False

    def _get_conn(self):
        if not DB_AVAILABLE:
            return None
        cfg = get_config()
        return pymysql.connect(**cfg.database.as_dict())

    def fetch_task(self) -> Optional[dict]:
        """获取一个待执行任务"""
        conn = self._get_conn()
        if not conn: return None
        try:
            cur = conn.cursor()
            # 取本机或未指定机器的PENDING任务，按优先级排序
            cur.execute(
                """SELECT q.*, c.script_name, c.timeout_sec, c.priority
                   FROM task_queue q
                   JOIN task_config c ON q.config_id = c.id
                   WHERE q.task_status = 'PENDING'
                     AND (q.executor_ip IS NULL OR q.executor_ip = %s)
                   ORDER BY c.priority ASC, q.create_time ASC
                   LIMIT 1""",
                (self.machine_ip,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0], "config_id": row[1], "task_uuid": row[2],
                    "script_name": row[3], "task_params": row[4], "task_status": row[5],
                    "executor_ip": row[6],
                }
        except Exception as e:
            print(f"[Consumer] 拉取任务失败: {e}")
        finally:
            conn.close()
        return None

    def claim_task(self, task_uuid: str) -> bool:
        """认领任务（PENDING → RUNNING）"""
        conn = self._get_conn()
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE task_queue SET task_status='RUNNING', executor_ip=%s, start_time=NOW()
                   WHERE task_uuid=%s AND task_status='PENDING'""",
                (self.machine_ip, task_uuid)
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[Consumer] 认领任务失败: {e}")
        finally:
            conn.close()
        return False

    def report_result(self, task_uuid: str, status: str, error: str = "", duration: int = 0):
        """上报任务结果"""
        conn = self._get_conn()
        if not conn: return
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE task_queue SET task_status=%s, end_time=NOW(), duration_sec=%s,
                   error_message=%s WHERE task_uuid=%s""",
                (status, duration, error[:2000], task_uuid)
            )
            conn.commit()
        except Exception as e:
            print(f"[Consumer] 上报结果失败: {e}")
        finally:
            conn.close()

    def run_loop(self, on_task=None):
        """持续轮询，有任务时回调 on_task(task_dict)"""
        self._running = True
        print(f"[Consumer] 启动轮询 (机器: {self.machine_ip}, 间隔: {self.poll_interval}s)")
        while self._running:
            try:
                task = self.fetch_task()
                if task and self.claim_task(task["task_uuid"]):
                    print(f"[Consumer] 领取任务: {task['task_uuid']} ({task['script_name']})")
                    if on_task:
                        on_task(task)
            except Exception as e:
                print(f"[Consumer] 轮询异常: {e}")
            time.sleep(self.poll_interval)

    def stop(self):
        self._running = False


def poll_task(machine_ip: str = None) -> Optional[dict]:
    """便捷函数：拉取并认领一个任务"""
    consumer = TaskConsumer(machine_ip=machine_ip)
    task = consumer.fetch_task()
    if task and consumer.claim_task(task["task_uuid"]):
        return task
    return None
