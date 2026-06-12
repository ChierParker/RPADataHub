import time
from functools import wraps
from time import sleep
from traceback import format_exc

from library.logger import logger
from library.send_midea_connect_report import send_report_error


class Retry:
    def __init__(self, retry_count: int = 3, wait_seconds: int = 15, send_error_report: bool = False):

        self.retry_count = retry_count
        self.wait_seconds = wait_seconds
        self.send_error_report = send_error_report

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            retry_count = self.retry_count  # 重置重试次数
            while retry_count > 0:
                try:
                    # 尝试执行函数，如果成功则直接返回结果
                    result = func(*args, **kwargs)
                    # 成功执行，返回结果并跳出循环
                    return result
                except Exception as e:
                    logger.error(format_exc())
                    retry_count -= 1  # 减少重试次数
                    logger.warning(
                        f"执行失败，将在 {self.wait_seconds} 秒后重试。剩余重试次数：{retry_count}。错误信息：{e}")
                    sleep(self.wait_seconds)

                    # 如果重试次数用完，抛出异常
                    if retry_count == 0:
                        logger.error("达到最大重试次数，程序将退出。")
                        if self.send_error_report:
                            send_report_error(format_exc())
                        raise e

        return wrapper


class PeriodicRun:
    def __init__(self, run_interval: int = 60, log_interval: int = 60):
        """
        初始化装饰器参数。

        """
        self.run_interval = run_interval
        self.log_interval = log_interval

    def __call__(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            run_count = 0
            while True:

                func(*args, **kwargs)
                run_count += 1

                if run_count > 0 and (run_count % self.log_interval) == 0:
                    logger.info(f"持续运行中，已经运行了 {run_count} 次")

                logger.info(f"等待 {self.run_interval} 秒后再次运行")
                time.sleep(self.run_interval)

        return wrapped


@Retry()
def demo(name):
    logger.info(f"Hello {name}")
    sleep(1)
    raise ValueError("测试:故意抛出一个异常")


if __name__ == '__main__':
    demo("world")
