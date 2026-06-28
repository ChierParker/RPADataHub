"""
routes/routes_tasks.py 集成测试 — 任务管理核心流程
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock
from flask import Flask, Blueprint


@pytest.fixture
def tasks_app():
    app = Flask(__name__, template_folder="../templates")
    app.secret_key = "test"
    bp = Blueprint("test_bp", __name__, template_folder="../templates")

    mock_q = MagicMock()
    mock_q.return_value = pd.DataFrame()
    mock_ex = MagicMock()

    from routes.routes_tasks import register
    register(bp, mock_q, mock_ex, lambda f: f, lambda f: f, lambda: [])

    app.register_blueprint(bp)
    return app, mock_q, mock_ex


class TestTaskPage:
    def test_page_loads(self, tasks_app):
        app, _, _ = tasks_app
        with app.test_client() as c:
            resp = c.get("/tasks")
            assert resp.status_code == 200

    def test_page_with_configs(self, tasks_app):
        app, mock_q, _ = tasks_app
        mock_q.return_value = pd.DataFrame([{
            "id": 1, "task_name": "测试", "script_name": "demo",
            "platform": "Amazon", "shop_name": "ShopA",
            "schedule_type": "now", "cron_expression": None,
            "timeout_sec": 3600, "priority": 1, "status": 1,
        }])
        with app.test_client() as c:
            resp = c.get("/tasks")
            assert resp.status_code == 200


class TestTaskQueue:
    def test_queue_api(self, tasks_app):
        app, mock_q, _ = tasks_app
        mock_q.side_effect = [
            pd.DataFrame({"c": [50]}),   # count
            pd.DataFrame(),               # records
        ]
        with app.test_client() as c:
            resp = c.get("/api/tasks/queue?page=1&per_page=15")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["total"] == 50
            assert data["page"] == 1

    def test_queue_with_records(self, tasks_app):
        app, mock_q, _ = tasks_app
        mock_q.side_effect = [
            pd.DataFrame({"c": [2]}),
            pd.DataFrame([
                {"task_uuid": "abc", "script_name": "demo", "task_status": "SUCCESS",
                 "task_name": "T1", "start_time": None, "duration_sec": 45,
                 "error_message": None, "create_time": None, "end_time": None,
                 "config_id": 1},
                {"task_uuid": "def", "script_name": "demo", "task_status": "FAILED",
                 "task_name": "T2", "start_time": None, "duration_sec": 120,
                 "error_message": "Timeout", "create_time": None, "end_time": None,
                 "config_id": 2},
            ]),
        ]
        with app.test_client() as c:
            resp = c.get("/api/tasks/queue")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data["records"]) == 2


class TestTaskConfig:
    def test_create_task(self, tasks_app):
        app, mock_q, mock_ex = tasks_app
        with app.test_client() as c:
            resp = c.post("/api/tasks/config", json={
                "task_name": "新任务", "script_name": "demo_po",
                "platform": "Amazon", "schedule_type": "now",
                "timeout_sec": 3600, "priority": 1,
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert mock_ex.called  # execute was called

    def test_delete_task(self, tasks_app):
        app, _, mock_ex = tasks_app
        with app.test_client() as c:
            resp = c.delete("/api/tasks/config/1")
            assert resp.status_code == 200
            assert mock_ex.called

    def test_run_task_not_found(self, tasks_app):
        app, mock_q, _ = tasks_app
        mock_q.return_value = pd.DataFrame()  # empty = not found
        with app.test_client() as c:
            resp = c.post("/api/tasks/run/999")
            assert resp.status_code == 404

    def test_run_task_success(self, tasks_app):
        app, mock_q, mock_ex = tasks_app
        mock_q.return_value = pd.DataFrame([{
            "id": 1, "script_name": "demo_po", "task_name": "T1"
        }])
        with app.test_client() as c:
            resp = c.post("/api/tasks/run/1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "task_uuid" in data
