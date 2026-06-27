"""消息生产者 — 将任务写入 task_queue（测试/手动触发）"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    from config.settings import get_config
    import pymysql
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


def enqueue_task(config_id: int, task_uuid: str, script_name: str,
                 task_params: dict, executor_ip: str = None) -> bool:
    """
    将任务写入 task_queue（生产消息）

    参数:
        config_id: task_config.id
        task_uuid: 任务实例UUID
        script_name: 采集器名称
        task_params: 采集参数字典
        executor_ip: 指定执行机器

    返回: 是否成功
    """
    if not DB_AVAILABLE:
        print("[Producer] DB不可用")
        return False

    cfg = get_config()
    conn = None
    try:
        conn = pymysql.connect(**cfg.database.as_dict())
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO task_queue (config_id, task_uuid, script_name, task_params, executor_ip)
               VALUES (%s, %s, %s, %s, %s)""",
            (config_id, task_uuid, script_name,
             json.dumps(task_params, ensure_ascii=False), executor_ip)
        )
        conn.commit()
        print(f"[Producer] 任务入队: {task_uuid}")
        return True
    except Exception as e:
        print(f"[Producer] 入队失败: {e}")
        return False
    finally:
        if conn:
            conn.close()
