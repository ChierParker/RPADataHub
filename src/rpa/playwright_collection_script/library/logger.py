import os
from pathlib import Path
from datetime import datetime
from loguru import logger as lg
from library.utils import get_app_name, get_app_data_dir, get_app_data_file



def init_logger():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    file_path_log = get_app_data_file("04_运行日志", get_app_name() + "_" + timestamp +".log")

    # 添加新的日志处理器，设置日志文件路径和编码
    lg.add(file_path_log, encoding="utf-8")
    lg.info(f"日志文件路径: {file_path_log}")

    return lg


logger = init_logger()

if __name__ == "__main__":
    logger.info(f"init_logger")
