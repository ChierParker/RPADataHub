"""
core/rate_limit.py 单元测试
"""

import time
import pytest
from unittest.mock import patch
from flask import Flask


class TestTokenBucket:
    def test_initial_tokens(self):
        from core.rate_limit import TokenBucket
        bucket = TokenBucket(rate=10.0, burst=20)
        assert bucket.tokens == 20.0

    def test_consume_ok(self):
        from core.rate_limit import TokenBucket
        bucket = TokenBucket(rate=10.0, burst=20)
        assert bucket.consume(1) is True
        assert bucket.tokens < 20.0  # tokens decreased

    def test_consume_exhausted(self):
        from core.rate_limit import TokenBucket
        bucket = TokenBucket(rate=0.01, burst=1)  # very slow refill
        assert bucket.consume(1) is True
        assert bucket.consume(1) is False  # no more tokens

    def test_refill_over_time(self):
        from core.rate_limit import TokenBucket
        bucket = TokenBucket(rate=100.0, burst=10)
        assert bucket.consume(10) is True  # consume all
        assert bucket.consume(1) is False  # empty

        # simulate time passing
        bucket.last_refill = time.monotonic() - 1.0  # 1 second ago
        assert bucket.consume(1) is True  # refilled

    def test_cannot_exceed_burst(self):
        from core.rate_limit import TokenBucket
        bucket = TokenBucket(rate=1000.0, burst=5)
        bucket.last_refill = time.monotonic() - 10.0  # long time
        bucket.consume(1)  # triggers refill
        assert bucket.tokens <= 5.0  # capped at burst


class TestRateLimitDecorator:
    @pytest.fixture
    def app(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        return app

    def test_allows_request(self, app):
        from core.rate_limit import rate_limit

        @app.route("/test")
        @rate_limit(rate=100, burst=100)
        def test_view():
            return "ok"

        with app.test_client() as client:
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_blocks_excessive_requests(self, app):
        from core.rate_limit import rate_limit, clear_ip_buckets

        clear_ip_buckets()

        @app.route("/limited")
        @rate_limit(rate=0.001, burst=1, per_ip=True)  # 1 request per 1000s
        def limited_view():
            return "ok"

        with app.test_client() as client:
            resp1 = client.get("/limited")
            assert resp1.status_code == 200

            resp2 = client.get("/limited")
            assert resp2.status_code == 429  # rate limited
            data = resp2.get_json()
            assert data["success"] is False
            assert "频繁" in data["error"]
