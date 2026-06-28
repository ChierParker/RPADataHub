"""
routes/routes_etl.py 集成测试 — ETL 管线核心流程
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock
from flask import Flask, Blueprint


@pytest.fixture
def etl_app():
    app = Flask(__name__, template_folder="../templates")
    app.secret_key = "test"
    bp = Blueprint("test_bp", __name__, template_folder="../templates")

    mock_q = MagicMock()
    mock_q.side_effect = lambda sql, params=None: pd.DataFrame()
    mock_ex = MagicMock()

    from routes.routes_etl import register
    register(bp, mock_q, mock_ex, lambda f: f, lambda f: f, lambda: [])

    app.register_blueprint(bp)
    return app, mock_q, mock_ex


class TestETLDashboard:
    def test_dashboard_loads(self, etl_app):
        app, mock_q, _ = etl_app
        # Mock stats + total + records queries
        mock_q.side_effect = [
            pd.DataFrame([{"status": "SUCCESS", "cnt": 50}, {"status": "FAILED", "cnt": 5}]),
            pd.DataFrame({"c": [55]}),
            pd.DataFrame(),
        ]
        with app.test_client() as c:
            resp = c.get("/dashboard")
            assert resp.status_code == 200

    def test_dashboard_with_filter(self, etl_app):
        app, mock_q, _ = etl_app
        mock_q.side_effect = [
            pd.DataFrame([{"status": "FAILED", "cnt": 5}]),
            pd.DataFrame({"c": [5]}),
            pd.DataFrame(),
        ]
        with app.test_client() as c:
            resp = c.get("/dashboard?status=FAILED")
            assert resp.status_code == 200

    def test_dashboard_empty(self, etl_app):
        app, mock_q, _ = etl_app
        mock_q.side_effect = [
            pd.DataFrame(),
            pd.DataFrame({"c": [0]}),
            pd.DataFrame(),
        ]
        with app.test_client() as c:
            resp = c.get("/dashboard")
            assert resp.status_code == 200


class TestETLRecordDetail:
    def test_record_detail(self, etl_app):
        app, mock_q, _ = etl_app
        mock_q.side_effect = [
            pd.DataFrame([{"trace_id": "abc", "file_name": "test.xlsx", "status": "SUCCESS"}]),
            pd.DataFrame(),
        ]
        with app.test_client() as c:
            resp = c.get("/api/etl_record/abc")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["etl"] is not None
            assert data["etl"]["status"] == "SUCCESS"

    def test_record_not_found(self, etl_app):
        app, mock_q, _ = etl_app
        mock_q.side_effect = [pd.DataFrame(), pd.DataFrame()]
        with app.test_client() as c:
            resp = c.get("/api/etl_record/nonexist")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["etl"] is None


class TestHealthPage:
    def test_health_loads(self, etl_app):
        app, mock_q, _ = etl_app
        mock_q.side_effect = [
            pd.DataFrame([{"t": 10, "s": 8, "f": 2}]),
            pd.DataFrame({"total": [100]}),
            pd.DataFrame({"c": [3]}),
            pd.DataFrame({"c": [1]}),
            pd.DataFrame({"r": [95.5]}),
        ]
        with app.test_client() as c:
            resp = c.get("/health")
            assert resp.status_code == 200
