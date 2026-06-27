"""
RPA 执行器 Agent — Redis Streams MQ 消费 + DB 降级
v2.0: Redis Streams 实时消费, DB 仅作审计+降级兜底

启动: python worker.py
      python worker.py --db    (强制 DB 轮询模式)
"""
import os, sys, subprocess, socket, time, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logger_config import setup_logger

logger = setup_logger("Worker")

MACHINE_IP = socket.gethostbyname(socket.gethostname())
COLLECTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playwright_collection_script")


def execute_task(task: dict):
    """执行单个采集任务"""
    task_uuid = task.get("task_uuid", "")
    script_name = task.get("script_name", "")
    # 整个 task 就是参数（Redis 消息无嵌套 task_params 字段）
    task_params = task

    logger.info(f"开始执行: {task_uuid} ({script_name})", task_uuid)

    start = time.time()
    success = False
    error_msg = ""

    try:
        # 通过 main.py 执行
        result = subprocess.run(
            [sys.executable, "main.py", "--task", script_name, "--params", json.dumps(task_params, ensure_ascii=False)],
            capture_output=True, text=True,
            timeout=task_params.get("timeout_sec", 3600),
            cwd=COLLECTION_DIR
        )
        success = result.returncode == 0
        error_msg = (result.stderr or result.stdout)[-2000:] if not success else ""

        if result.stdout:
            for line in result.stdout.split("\n")[-10:]:
                if line.strip():
                    logger.debug(f"[out] {line.strip()[:200]}", task_uuid)
        if result.stderr:
            for line in result.stderr.split("\n")[-5:]:
                if line.strip():
                    logger.warning(f"[stderr] {line.strip()[:200]}", task_uuid)

    except subprocess.TimeoutExpired:
        error_msg = f"任务超时({task_params.get('timeout_sec', 3600)}s)"
        logger.error(error_msg, task_uuid)
    except Exception as e:
        error_msg = str(e)[:2000]
        logger.error(f"任务异常: {error_msg}", task_uuid, exc_info=True)

    duration = int(time.time() - start)
    new_status = "SUCCESS" if success else "FAILED"

    # 更新 task_queue 状态
    try:
        from core.db_operations import DatabaseManager
        db = DatabaseManager(task_uuid)
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE task_queue SET task_status=%s, end_time=NOW(), duration_sec=%s, error_message=%s WHERE task_uuid=%s",
                    (new_status, duration, error_msg, task_uuid)
                )
            conn.commit()
    except Exception as e:
        logger.error(f"状态更新失败: {e}", task_uuid)

    logger.info(f"完成: {task_uuid} -> {new_status} ({duration}s)", task_uuid)
    return new_status


def main():
    use_db_only = "--db" in sys.argv
    show_help = "--help" in sys.argv or "-h" in sys.argv

    if show_help:
        print("RPA 执行器 Agent v2.0")
        print("  python worker.py           Redis Streams MQ 模式（自动降级）")
        print("  python worker.py --db     强制 DB 轮询模式")
        print("  python worker.py --once   单次执行后退出（DB 模式）")
        return

    logger.info(f"RPA 执行器 Agent v2.0 启动 | IP={MACHINE_IP} | 采集目录={COLLECTION_DIR}")

    if use_db_only:
        logger.info("强制 DB 轮询模式")
        from mq.redis_broker import RedisBroker
        broker = RedisBroker.__new__(RedisBroker)
        broker._redis_available = False
        broker.consume(execute_task)
    else:
        try:
            from mq.redis_broker import RedisBroker
            broker = RedisBroker()
            logger.info(f"MQ 模式: {'Redis Streams' if broker._redis_available else 'DB 轮询(Redis不可用)'}")
            broker.consume(execute_task)
        except ImportError:
            logger.warning("redis-py 未安装, 使用 DB 轮询")
            from mq.redis_broker import RedisBroker
            broker = RedisBroker.__new__(RedisBroker)
            broker._redis_available = False
            broker.consume(execute_task)


if __name__ == "__main__":
    main()
