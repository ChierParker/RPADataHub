"""
结构化日志配置模块
- TraceLogger: 支持 trace_id 贯穿全链路
- 日志自动轮转 (RotatingFileHandler)
- 双通道输出: 控制台(INFO+) + 文件(DEBUG+)
- 每次启动服务生成独立日志文件，文件超过50MB自动轮转
基于白皮书：统一日志规范，包含trace_id、时间戳、执行耗时、错误堆栈
"""

import logging
import os
import uuid
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

# 日志存放路径
LOG_DIR = r"D:\EcomIQ-RPA\rpa_logs"

# 日志轮转参数
MAX_LOG_SIZE = 50 * 1024 * 1024  # 50MB 单文件上限
BACKUP_COUNT = 30                 # 保留最近30个轮转文件


class TraceLogger:
    """
    带 trace_id 的结构化日志器
    对应白皮书 3.3.1 节：所有流程输出结构化日志，包含 trace_id/时间戳/耗时/错误堆栈
    """

    def __init__(self, name="RPAWatcher", log_dir=None):
        self._name = name
        self._log_dir = log_dir or LOG_DIR
        self._logger = None
        self._init_logger()

    def _init_logger(self):
        """初始化底层 logging.Logger"""
        if not os.path.exists(self._log_dir):
            os.makedirs(self._log_dir)

        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = os.path.join(self._log_dir, f"rpa_watcher_{now}.log")

        self._logger = logging.getLogger(self._name)
        self._logger.setLevel(logging.DEBUG)

        # 避免重复添加 handler
        if self._logger.handlers:
            return

        # 结构化格式: 时间 | 级别 | trace_id | 模块 | 消息
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(trace_id)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 文件处理器：DEBUG级别，支持轮转
        file_handler = RotatingFileHandler(
            log_file, encoding="utf-8",
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)

        # 控制台处理器：INFO级别
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

    # ============================================================
    # 公开 API
    # ============================================================

    def new_trace_id(self):
        """生成新的 trace_id，用于一次文件处理全链路追踪"""
        return uuid.uuid4().hex[:16]

    def _log(self, level, msg, trace_id="-", extra=None):
        """内部日志方法，注入 trace_id 到 extra"""
        extra = extra or {}
        extra.setdefault("trace_id", trace_id or "-")
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg, trace_id="-"):
        self._log(logging.DEBUG, msg, trace_id)

    def info(self, msg, trace_id="-"):
        self._log(logging.INFO, msg, trace_id)

    def warning(self, msg, trace_id="-"):
        self._log(logging.WARNING, msg, trace_id)

    def error(self, msg, trace_id="-", exc_info=False):
        self._logger.error(msg, extra={"trace_id": trace_id or "-"}, exc_info=exc_info)

    def critical(self, msg, trace_id="-"):
        self._log(logging.CRITICAL, msg, trace_id)

    @contextmanager
    def timed_operation(self, operation_name, trace_id="-"):
        """
        上下文管理器：自动记录操作耗时
        用法:
            with logger.timed_operation("ODS写入", trace_id):
                upsert_to_ods(...)
        """
        start = time.time()
        self.info(f"[开始] {operation_name}", trace_id)
        try:
            yield
            elapsed = time.time() - start
            self.info(f"[完成] {operation_name} | 耗时: {elapsed:.2f}s", trace_id)
        except Exception:
            elapsed = time.time() - start
            self.error(f"[失败] {operation_name} | 耗时: {elapsed:.2f}s", trace_id, exc_info=True)
            raise

    def trace_func(self, trace_id="-"):
        """
        装饰器：自动记录函数调用耗时
        用法:
            @logger.trace_func(trace_id)
            def my_func(): ...
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                self.debug(f"[调用] {func.__name__}", trace_id)
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start
                    self.debug(f"[返回] {func.__name__} | 耗时: {elapsed:.2f}s", trace_id)
                    return result
                except Exception:
                    elapsed = time.time() - start
                    self.error(f"[异常] {func.__name__} | 耗时: {elapsed:.2f}s", trace_id, exc_info=True)
                    raise
            return wrapper
        return decorator


# ============================================================
# 向后兼容：保持原有 setup_logger 接口
# ============================================================

def setup_logger(name="RPAWatcher"):
    """
    向后兼容的日志器工厂函数
    返回 TraceLogger 实例，同时兼容原有 logging.Logger 接口
    """
    return TraceLogger(name)
