"""
API 速率限制中间件
==================
基于内存的简单令牌桶算法，防止 API 滥用。

生产环境建议替换为 Redis 版本或 Flask-Limiter。
"""

import time
import threading
from functools import wraps
from flask import request, jsonify


class TokenBucket:
    """令牌桶速率限制器

    Args:
        rate: 每秒允许的请求数
        burst: 突发允许的最大请求数
    """

    def __init__(self, rate: float = 10.0, burst: int = 20):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """尝试消费令牌，返回是否成功"""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


# 默认桶：每秒 10 个请求，突发 20 个
_default_bucket = TokenBucket(rate=10.0, burst=20)

# 按 IP 的桶缓存
_ip_buckets: dict = {}
_ip_buckets_lock = threading.Lock()


def _get_bucket_for_ip(ip: str, rate: float = 5.0, burst: int = 10) -> TokenBucket:
    """获取或创建 IP 对应的令牌桶"""
    with _ip_buckets_lock:
        if ip not in _ip_buckets:
            _ip_buckets[ip] = TokenBucket(rate=rate, burst=burst)
        return _ip_buckets[ip]


def rate_limit(rate: float = 5.0, burst: int = 10, per_ip: bool = True):
    """API 速率限制装饰器

    Args:
        rate: 每秒允许的请求数
        burst: 突发最大请求数
        per_ip: True=按IP限流, False=全局限流

    Usage:
        @app.route("/api/data")
        @rate_limit(rate=10, burst=20)
        def get_data():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if per_ip:
                ip = request.remote_addr or "127.0.0.1"
                bucket = _get_bucket_for_ip(ip, rate, burst)
            else:
                bucket = _default_bucket

            if not bucket.consume():
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "请求过于频繁，请稍后再试 (429 Too Many Requests)",
                    "message": "",
                }), 429
            return f(*args, **kwargs)
        return decorated
    return decorator


def clear_ip_buckets():
    """清理长时间未使用的 IP 桶（建议定时调用）"""
    with _ip_buckets_lock:
        _ip_buckets.clear()
