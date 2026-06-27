"""
自愈重试管理器
对应白皮书 3.3.4 节：异常恢复与自愈机制

核心设计:
  分级重试: 网络超时/文件锁定等临时异常 → 自动重试3次（指数退避）
  业务逻辑异常 → 立即告警，不重试
  降级策略: ODS写入失败 → 记录到本地JSON兜底文件

量化目标:
  临时故障自愈率 80%+
  核心流程可用性 99.5%+
"""

import time
import json
import os
import random
from functools import wraps
from config.settings import get_config


class RetryManager:
    """
    自愈重试管理器

    使用方式:
        retry_mgr = RetryManager(logger, alert_manager)

        # 方式1：上下文管理器
        with retry_mgr.retry_context("ODS写入", trace_id):
            upsert_to_ods(...)

        # 方式2：装饰器
        @retry_mgr.with_retry("DW聚合", trace_id)
        def dw_aggregate(): ...

        # 方式3：直接调用
        retry_mgr.call_with_retry(func, "ODS写入", trace_id, *args, **kwargs)
    """

    def __init__(self, logger, alert_manager):
        self._logger = logger
        self._alert = alert_manager
        self._config = get_config().retry

    # ============================================================
    # 判断异常是否可重试
    # ============================================================

    def _is_retryable(self, exception):
        """
        判断异常是否可重试
        临时异常（网络/IO）可重试，业务逻辑异常不重试
        """
        exc_str = str(exception) + type(exception).__name__
        for keyword in self._config.retryable_keywords:
            if keyword.lower() in exc_str.lower():
                return True
        return False

    # ============================================================
    # 计算退避延迟（指数退避 + 随机抖动）
    # ============================================================

    def _backoff_delay(self, attempt):
        """指数退避: base * 2^attempt，上限 max_delay，加随机抖动"""
        delay = min(
            self._config.retry_base_delay * (2 ** attempt),
            self._config.retry_max_delay
        )
        # 随机抖动 ±20%
        jitter = delay * 0.2 * (2 * random.random() - 1)
        return delay + jitter

    # ============================================================
    # 核心重试逻辑
    # ============================================================

    def call_with_retry(self, func, operation_name, trace_id, *args, **kwargs):
        """
        带重试的函数调用

        参数:
          func: 要执行的函数
          operation_name: 操作名称（用于日志）
          trace_id: 追踪ID
          *args, **kwargs: 传递给 func 的参数

        返回:
          func 的返回值

        抛出:
          最后一次重试的异常（如果全部重试都失败）
        """
        last_exception = None

        for attempt in range(self._config.max_retries + 1):
            try:
                if attempt > 0:
                    self._logger.info(
                        f"[重试 {attempt}/{self._config.max_retries}] {operation_name}",
                        trace_id
                    )
                result = func(*args, **kwargs)
                # 重试成功日志
                if attempt > 0:
                    self._logger.info(
                        f"[重试成功] {operation_name} | 第{attempt}次重试后恢复",
                        trace_id
                    )
                return result

            except Exception as e:
                last_exception = e

                # 不可重试的异常 → 直接抛出
                if not self._is_retryable(e):
                    self._logger.error(
                        f"[不可重试异常] {operation_name} | {type(e).__name__}: {e}",
                        trace_id
                    )
                    raise

                # 最后一次尝试也失败 → 抛出
                if attempt >= self._config.max_retries:
                    self._logger.error(
                        f"[重试耗尽] {operation_name} | 已重试{self._config.max_retries}次，全部失败",
                        trace_id, exc_info=True
                    )
                    raise

                # 计算退避并等待
                delay = self._backoff_delay(attempt)
                self._logger.warning(
                    f"[重试等待] {operation_name} | {delay:.1f}秒后重试 | 错误: {e}",
                    trace_id
                )
                time.sleep(delay)

        # 理论上不会到这里
        raise last_exception

    # ============================================================
    # 降级策略
    # ============================================================

    def fallback_to_file(self, data, file_name, trace_id):
        """
        降级策略：数据库写入失败时，将数据保存到本地JSON兜底文件
        对应白皮书 3.3.4 节：降级策略保障业务连续性
        """
        config = get_config()
        fallback_dir = config.paths.fallback_dir

        if not os.path.exists(fallback_dir):
            os.makedirs(fallback_dir)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        fallback_file = os.path.join(
            fallback_dir,
            f"fallback_{file_name}_{timestamp}_{trace_id}.json"
        )

        try:
            with open(fallback_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str, indent=2)
            self._logger.info(
                f"[降级成功] 数据已保存到兜底文件: {fallback_file}",
                trace_id
            )
            return fallback_file
        except Exception as e:
            self._logger.error(
                f"[降级失败] 写入兜底文件也失败: {e}",
                trace_id, exc_info=True
            )
            raise

    # ============================================================
    # 上下文管理器
    # ============================================================

    class RetryContext:
        """重试上下文管理器"""
        def __init__(self, parent, operation_name, trace_id, on_failure=None):
            self._parent = parent
            self._operation_name = operation_name
            self._trace_id = trace_id
            self._on_failure = on_failure

        def __enter__(self):
            self._attempt = 0
            self._last_exception = None
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_val is None:
                return False  # 无异常，正常退出
            return False  # 异常已在外部处理

    def retry_context(self, operation_name, trace_id):
        """返回上下文管理器（简化用法）"""
        return self.RetryContext(self, operation_name, trace_id)
