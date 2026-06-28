"""
RPA 执行器 Agent — Redis Streams MQ 消费 + DB 降级
v2.0: Redis Streams 实时消费, DB 仅作审计+降级兜底

启动: python worker.py
      python worker.py --db    (强制 DB 轮询模式)
"""
import os, sys, subprocess, socket, time, json
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 使用统一日志器（回退兼容）
try:
    from core.logger import setup_logger as _setup_logger
except ImportError:
    from logger_config import setup_logger as _setup_logger

logger = _setup_logger("Worker")

MACHINE_IP = socket.gethostbyname(socket.gethostname())
COLLECTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playwright_collection_script")



# 缓存已加载的收集器模块（--direct 模式使用）
_COLLECTOR_CACHE = {}


def _execute_direct(task_uuid, script_name, task_params):
    """进程内直接调用采集器（推荐，无 subprocess 开销）"""
    if script_name not in _COLLECTOR_CACHE:
        sys.path.insert(0, COLLECTION_DIR)
        try:
            mod = __import__(f"collectors.{script_name}", fromlist=["run"])
            _COLLECTOR_CACHE[script_name] = mod
        except ImportError:
            try:
                mod = __import__(script_name)
                _COLLECTOR_CACHE[script_name] = mod
            except ImportError as e:
                return False, f"无法加载采集器 '{script_name}': {e}"

    try:
        mod = _COLLECTOR_CACHE[script_name]
        if hasattr(mod, 'run'):
            result = mod.run(task_params)
            return True, str(result) if result else "OK"
        elif hasattr(mod, 'main'):
            result = mod.main(task_params)
            return True, str(result) if result else "OK"
        else:
            return False, f"采集器缺少 run() 或 main() 入口"
    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()[-1000:]}"
def execute_task(task: dict, use_direct: bool = False):
    """执行单个采集任务

    Args:
        task: 任务参数字典
        use_direct: True=进程内直接调用, False=subprocess（兼容）
    """
    task_uuid = task.get("task_uuid", "")
    script_name = task.get("script_name", "")
    task_params = task

    mode = "direct" if use_direct else "subprocess"
    logger.info(f"开始执行: {task_uuid} ({script_name}) [{mode}]", task_uuid)

    start = time.time()

    if use_direct:
        success, error_msg = _execute_direct(task_uuid, script_name, task_params)
    else:
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
    use_direct = "--subprocess" not in sys.argv  # 默认 direct，--subprocess 回退
    show_help = "--help" in sys.argv or "-h" in sys.argv

    # 默认 direct 模式，--subprocess 强制回退
    if use_direct:
        logger.info("使用 direct 模式（进程内调用，默认）")
        _orig_exec = execute_task

        def execute_task_direct(task):
            return _orig_exec(task, use_direct=True)
        _exec_fn = execute_task_direct
    else:
        _exec_fn = execute_task

    if show_help:
        print("RPA 执行器 Agent v2.1 (默认 direct)")
        print("  python worker.py              Redis+M direct 模式")
        print("  python worker.py --db        强制 DB 轮询")
        print("  python worker.py --subprocess 回退子进程模式（兼容）")
        print("  python worker.py --once      单次执行后退出")
        return

    logger.info(f"RPA 执行器 Agent v2.0 启动 | IP={MACHINE_IP} | 采集目录={COLLECTION_DIR}")

    if use_db_only:
        logger.info("强制 DB 轮询模式")
        from mq.redis_broker import RedisBroker
        broker = RedisBroker.__new__(RedisBroker)
        broker._redis_available = False
        broker.consume(_exec_fn)
    else:
        try:
            from mq.redis_broker import RedisBroker
            broker = RedisBroker()
            logger.info(f"MQ 模式: {'Redis Streams' if broker._redis_available else 'DB 轮询(Redis不可用)'}")
            broker.consume(_exec_fn)
        except ImportError:
            logger.warning("redis-py 未安装, 使用 DB 轮询")
            from mq.redis_broker import RedisBroker
            broker = RedisBroker.__new__(RedisBroker)
            broker._redis_available = False
            broker.consume(_exec_fn)


if __name__ == "__main__":
    main()
