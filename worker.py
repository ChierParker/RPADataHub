"""
RPA 执行器 Agent — Redis Streams MQ 消费 + DB 降级
v2.0: Redis Streams 实时消费, DB 仅作审计+降级兜底

启动: python worker.py
      python worker.py --db    (强制 DB 轮询模式)
"""
import os, sys, subprocess, socket, time, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MACHINE_IP = socket.gethostbyname(socket.gethostname())
COLLECTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playwright_collection_script")


def execute_task(task: dict):
    """执行单个采集任务"""
    task_uuid = task.get("task_uuid", "")
    script_name = task.get("script_name", "")
    # 整个 task 就是参数（Redis 消息无嵌套 task_params 字段）
    task_params = task

    print(f"\n{'='*50}")
    print(f"[{datetime.now()}] 执行任务: {task_uuid} ({script_name})")
    print(f"{'='*50}")

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
                    print(f"  [out] {line.strip()[:200]}")
        if result.stderr:
            for line in result.stderr.split("\n")[-5:]:
                if line.strip():
                    print(f"  [ERR] {line.strip()[:200]}")

    except subprocess.TimeoutExpired:
        error_msg = f"任务超时({task_params.get('timeout_sec', 3600)}s)"
    except Exception as e:
        error_msg = str(e)[:2000]

    duration = int(time.time() - start)
    new_status = "SUCCESS" if success else "FAILED"

    # 更新 task_queue 状态
    try:
        from config.settings import get_config
        import pymysql
        cfg = get_config()
        conn = pymysql.connect(**cfg.database.as_dict())
        cur = conn.cursor()
        cur.execute(
            "UPDATE task_queue SET task_status=%s, end_time=NOW(), duration_sec=%s, error_message=%s WHERE task_uuid=%s",
            (new_status, duration, error_msg, task_uuid)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Worker] 状态更新失败: {e}")

    print(f"[{datetime.now()}] 完成: {task_uuid} → {new_status} ({duration}s)")
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

    print(f"[{datetime.now()}] RPA 执行器 Agent v2.0")
    print(f"  机器IP: {MACHINE_IP}")
    print(f"  采集目录: {COLLECTION_DIR}")
    print(f"{'='*50}")

    if use_db_only:
        print("[Worker] 强制 DB 轮询模式")
        from mq.redis_broker import RedisBroker
        broker = RedisBroker.__new__(RedisBroker)
        broker._redis_available = False
        broker.consume(execute_task)
    else:
        try:
            from mq.redis_broker import RedisBroker
            broker = RedisBroker()
            print(f"[Worker] MQ 模式: {'Redis Streams' if broker._redis_available else 'DB 轮询(Redis不可用)'}")
            broker.consume(execute_task)
        except ImportError:
            print("[Worker] redis-py 未安装, 使用 DB 轮询")
            from mq.redis_broker import RedisBroker
            broker = RedisBroker.__new__(RedisBroker)
            broker._redis_available = False
            broker.consume(execute_task)


if __name__ == "__main__":
    main()
