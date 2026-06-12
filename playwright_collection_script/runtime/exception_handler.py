"""统一异常封装 — 将Playwright/网络/业务异常转为标准格式"""
import traceback
from datetime import datetime
from schemas.log_schema import LogEntry


class ExceptionHandler:
    """异常处理器 — 分类并标准化异常"""

    EXCEPTION_CLASSIFIER = {
        "login": ["login", "cookie", "authentication", "密码", "验证码", "captcha"],
        "element": ["element", "selector", "xpath", "定位", "not found", "not attached"],
        "network": ["timeout", "connection", "network", "net::", "ERR_", "socket"],
        "data": ["empty", "no data", "0 rows", "null", "none"],
        "database": ["mysql", "database", "db", "sql", "duplicate"],
        "permission": ["403", "permission", "access denied", "forbidden"],
    }

    def classify(self, error: Exception) -> str:
        """分类异常类型"""
        msg = str(error).lower()
        for etype, keywords in self.EXCEPTION_CLASSIFIER.items():
            if any(kw in msg for kw in keywords):
                return etype
        return "unknown"

    def to_entry(self, error: Exception, task_uuid: str = "", step: str = "") -> dict:
        """将异常转为标准日志条目"""
        return {
            "exception_type": self.classify(error),
            "error_message": str(error)[:2000],
            "traceback": traceback.format_exc()[-2000:],
            "task_uuid": task_uuid,
            "step": step,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def is_retryable(self, error: Exception) -> bool:
        """判断异常是否可重试"""
        etype = self.classify(error)
        return etype in ("network", "element", "database")
