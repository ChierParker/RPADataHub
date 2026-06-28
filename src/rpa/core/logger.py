"""
统一日志模块
============
替代各模块分散的 logger_config.py / TraceLogger / print()。
基于标准库 logging，统一格式、级别、轮转策略。
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(
    name: str,
    log_dir: str = None,
    level: int = logging.INFO,
    max_bytes: int = 50 * 1024 * 1024,  # 50MB
    backup_count: int = 30,
    also_console: bool = True,
) -> logging.Logger:
    """创建统一格式的日志器

    Args:
        name: 日志器名称（通常是模块名）
        log_dir: 日志目录，默认自动查找项目 logs/ 目录
        level: 日志级别
        max_bytes: 单个日志文件最大字节数
        backup_count: 保留的历史日志文件数
        also_console: 是否同时输出到控制台

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 统一格式
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    if also_console:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

    # 文件输出（带轮转）
    if log_dir is None:
        # 自动查找项目 logs/ 目录
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs"
        )
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# 便捷函数：获取预配置的常用日志器
def get_rpa_logger() -> logging.Logger:
    """RPA 模块通用日志器"""
    return setup_logger("rpa")


def get_worker_logger() -> logging.Logger:
    """Worker 执行器日志器"""
    return setup_logger("worker")


def get_api_logger() -> logging.Logger:
    """API 请求日志器"""
    return setup_logger("api")
