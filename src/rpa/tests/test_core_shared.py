"""
core/shared.py 单元测试
"""

import pytest
import hashlib
from unittest.mock import MagicMock, patch


class TestSharedUtilities:
    """测试共享工具函数"""

    def test_sha256(self):
        from core.shared import sha256
        assert sha256("test") == hashlib.sha256(b"test").hexdigest()
        assert len(sha256("hello")) == 64
        assert sha256("a") != sha256("b")

    def test_clean_json_records_nan(self):
        from core.shared import clean_json_records
        import pandas as pd
        import math

        records = [{"a": 1, "b": float("nan")}]
        result = clean_json_records(records)
        assert result[0]["a"] == 1
        assert result[0]["b"] is None

    def test_clean_json_records_datetime(self):
        from core.shared import clean_json_records
        import pandas as pd
        from datetime import datetime

        dt = datetime(2026, 1, 15, 10, 30)
        records = [{"dt": dt, "val": 99}]
        result = clean_json_records(records)
        assert result[0]["dt"] == "2026-01-15 10:30:00"
        assert result[0]["val"] == 99


class TestAPIEnvelope:
    """测试 API 响应信封"""

    def test_api_ok_default(self):
        from core.shared import api_ok
        with patch("core.shared.jsonify", side_effect=lambda x, **kw: (x, kw.get("status_code", 200))):
            data, code = api_ok()
            assert data["success"] is True
            assert data["error"] == ""
            assert code == 200

    def test_api_ok_with_data(self):
        from core.shared import api_ok
        with patch("core.shared.jsonify", side_effect=lambda x, **kw: (x, kw.get("status_code", 200))):
            data, code = api_ok({"items": [1, 2]}, message="OK")
            assert data["success"] is True
            assert data["data"] == {"items": [1, 2]}
            assert data["message"] == "OK"

    def test_api_fail(self):
        from core.shared import api_fail
        with patch("core.shared.jsonify", side_effect=lambda x, **kw: (x, kw.get("status_code", 400))):
            data, code = api_fail("参数错误", status_code=422)
            assert data["success"] is False
            assert data["error"] == "参数错误"
            assert code == 422


class TestDatabasePool:
    """测试数据库连接池"""

    def test_init_fallback(self):
        """DBUtils 不可用时回退到 threading.local()"""
        with patch("core.shared.DatabasePool.__init__", autospec=True) as mock_init:
            mock_init.return_value = None
            from core.shared import DatabasePool
            pool = DatabasePool.__new__(DatabasePool)
            pool._use_pool = False
            pool._config = {"host": "localhost"}
            import threading
            pool._local = threading.local()

            # 降级模式下 get_conn 应创建连接（mock pymysql）
            with patch("core.shared.pymysql.connect") as mock_connect:
                mock_connect.return_value = MagicMock()
                pool.get_conn()
                assert mock_connect.called

    def test_query_delegates_to_pandas(self):
        from core.shared import DatabasePool
        import threading
        pool = DatabasePool.__new__(DatabasePool)
        pool._use_pool = False
        pool._config = {"host": "localhost"}
        pool._local = threading.local()

        mock_conn = MagicMock()
        with patch("core.shared.pymysql.connect", return_value=mock_conn):
            with patch("core.shared.pd.read_sql") as mock_read:
                mock_read.return_value = MagicMock()
                pool.query("SELECT 1")
                assert mock_read.called


class TestPermissionManager:
    """测试权限管理器"""

    @pytest.fixture
    def perm_mgr(self, mock_db):
        from core.shared import PermissionManager
        return PermissionManager(mock_db)

    def test_login_required_decorator(self, perm_mgr, app_context):
        @perm_mgr.login_required
        def test_view():
            return "ok"

        with app_context.test_request_context("/"):
            # 没有 session 应该 redirect
            from flask import session
            session.clear()
            resp = test_view()
            assert resp.status_code == 302  # redirect to login

    def test_permission_denied(self, perm_mgr, app_context):
        """无权限时返回 permission_denied 模板"""
        perm_mgr.get_user_permissions = lambda: ["dashboard"]

        @perm_mgr.permission_required("tasks_page")
        def protected_view():
            return "allowed"

        with app_context.test_request_context("/"):
            from flask import session
            session["user"] = {"role_id": 2}
            resp = protected_view()
            # 缺少 tasks_page 权限，应返回 200 并渲染 permission_denied
            assert "permission_denied" in resp or resp != "allowed"
