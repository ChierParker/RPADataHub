"""
CompetitorWatch 结构化日志配置模块
- 复用 RPADataHub 的 TraceLogger 设计模式
- 支持 trace_id 贯穿全链路
- 日志自动轮转 (RotatingFileHandler)
- 双通道输出: 控制台(INFO+) + 文件(DEBUG+)
"""

import logging
import os
import uuid
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

# 日志存放路径（与 CompetitorWatch 项目目录同级）
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# 日志轮转参数
MAX_LOG_SIZE = 50 * 1024 * 1024   # 50MB 单文件上限
BACKUP_COUNT = 30                  # 保留最近30个轮转文件


class TraceLogger:
    """
    带 trace_id 的结构化日志器
    用法:
        logger = TraceLogger("AmazonCollector")
        logger.info("开始采集", task_uuid)
        logger.error("采集失败", task_uuid, exc_info=True)
    """

    def __init__(self, name="CompetitorWatch", log_dir=None):
        self._name = name
        self._log_dir = log_dir or LOG_DIR
        self._logger = None
        self._init_logger()

    def _init_logger(self):
        """初始化底层 logging.Logger"""
        if not os.path.exists(self._log_dir):
            os.makedirs(self._log_dir, exist_ok=True)

        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = os.path.join(self._log_dir, f"competitor_watch_{now}.log")

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
        """生成新的 trace_id，用于一次采集任务全链路追踪"""
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
        """上下文管理器：自动记录操作耗时"""
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
        """装饰器：自动记录函数调用耗时"""
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

def setup_logger(name="CompetitorWatch"):
    """
    向后兼容的日志器工厂函数
    返回 TraceLogger 实例
    """
    return TraceLogger(name)
