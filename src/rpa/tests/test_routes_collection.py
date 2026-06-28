"""
routes/routes_collection.py 集成测试
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from flask import Flask, Blueprint


@pytest.fixture
def collection_app():
    """创建带 collection 路由的测试应用"""
    app = Flask(__name__, template_folder="../templates")
    app.secret_key = "test"

    bp = Blueprint("rpa_data_hub", __name__, template_folder="../templates")

    # 模拟查询函数
    mock_query = MagicMock()
    mock_query.return_value = pd.DataFrame()

    mock_execute = MagicMock()
    mock_login = lambda f: f
    mock_perm = lambda f: f
    mock_get_perm = lambda: ["collection_health"]

    # 注册路由
    from routes.routes_collection import register
    register(bp, mock_query, mock_execute, mock_login, mock_perm, mock_get_perm)

    app.register_blueprint(bp, url_prefix="/rpa")
    return app, mock_query


class TestCollectionHealth:
    def test_page_loads(self, collection_app):
        app, mock_db = collection_app
        mock_db.return_value = pd.DataFrame({"shop_name": ["ShopA", "ShopB"]})

        with app.test_client() as client:
            resp = client.get("/rpa/collection/health")
            assert resp.status_code == 200

    def test_api_returns_records(self, collection_app):
        app, mock_db = collection_app
        mock_db.return_value = pd.DataFrame([
            {"shop_name": "ShopA", "dt": pd.Timestamp("2026-06-15"), "collect_result": "SUCCESS", "cnt": 5},
            {"shop_name": "ShopA", "dt": pd.Timestamp("2026-06-15"), "collect_result": "FAILED", "cnt": 1},
        ])

        with app.test_client() as client:
            resp = client.get("/rpa/api/collection/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "records" in data
            assert len(data["records"]) == 2

    def test_api_filter_by_shop(self, collection_app):
        app, mock_db = collection_app

        def query_side_effect(sql, params=None):
            # 验证参数化查询
            assert params is not None
            return pd.DataFrame()

        mock_db.side_effect = query_side_effect

        with app.test_client() as client:
            resp = client.get("/rpa/api/collection/health?shop=ShopA")
            assert resp.status_code == 200


class TestCollectionRecords:
    def test_page_loads(self, collection_app):
        app, _ = collection_app
        with app.test_client() as client:
            resp = client.get("/rpa/collection/records")
            assert resp.status_code == 200

    def test_api_with_filters(self, collection_app):
        app, mock_db = collection_app
        mock_db.return_value = pd.DataFrame()

        with app.test_client() as client:
            resp = client.get("/rpa/api/collection/records?task_uuid=abc-123&page=1&per_page=10")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "records" in data
            assert "total" in data


class TestCollectionMonitor:
    def test_page_loads(self, collection_app):
        app, _ = collection_app
        with app.test_client() as client:
            resp = client.get("/rpa/collection/monitor")
            assert resp.status_code == 200

    def test_api_summary(self, collection_app):
        app, mock_db = collection_app
        # mock COUNT query
        mock_db.side_effect = [
            pd.DataFrame({"c": [100]}),   # count
            pd.DataFrame(),                # records
        ]

        with app.test_client() as client:
            resp = client.get("/rpa/api/collection/summary?page=1&per_page=15")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["total"] == 100
            assert data["page"] == 1
