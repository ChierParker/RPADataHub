"""进程守护 — 超时控制 / 单任务锁 / 取消控制"""
import signal
import time
from threading import Event, Thread
from schemas.task_schema import TaskConfig


class ProcessGuard:
    """进程守护器"""

    def __init__(self, config: TaskConfig):
        self.timeout_sec = config.timeout_sec or 3600
        self._start_time = time.time()
        self._cancel_event = Event()
        self._timeout_callback = None

    @property
    def elapsed(self) -> int:
        return int(time.time() - self._start_time)

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self):
        """请求取消"""
        self._cancel_event.set()

    def check_timeout(self) -> bool:
        """检查是否超时，超时返回True"""
        if self.elapsed > self.timeout_sec:
            self._cancel_event.set()
            return True
        return False

    def on_timeout(self, callback):
        """注册超时回调"""
        self._timeout_callback = callback

    def wrap_with_timeout(self, func, *args, **kwargs):
        """在超时保护下执行函数"""
        result = [None]
        exception = [None]

        def _run():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e

        t = Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=self.timeout_sec)

        if t.is_alive():
            self._cancel_event.set()
            if self._timeout_callback:
                self._timeout_callback()
            raise TimeoutError(f"操作超时({self.timeout_sec}s)")

        if exception[0]:
            raise exception[0]

        return result[0]


def keep_one_instance(lock_file: str = "/tmp/rpa_collector.lock"):
    """确保只有一个实例运行（Unix）"""
    import os
    try:
        import fcntl
        fp = open(lock_file, 'w')
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fp
    except (ImportError, IOError):
        print("WARNING: 单实例锁不可用")
        return None
