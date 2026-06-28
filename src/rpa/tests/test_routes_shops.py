"""
routes/routes_shops.py 集成测试 — 店铺管理 + 路由配置
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock
from flask import Flask, Blueprint


@pytest.fixture
def shops_app():
    app = Flask(__name__, template_folder="../templates")
    app.secret_key = "test"
    bp = Blueprint("test_bp", __name__, template_folder="../templates")

    mock_q = MagicMock()
    mock_q.return_value = pd.DataFrame()
    mock_ex = MagicMock()

    from routes.routes_shops import register
    register(bp, mock_q, mock_ex, lambda f: f, lambda f: f, lambda: [])

    app.register_blueprint(bp)
    return app, mock_q, mock_ex


class TestShopsData:
    def test_list_empty(self, shops_app):
        app, mock_q, _ = shops_app
        mock_q.side_effect = [
            pd.DataFrame({"c": [0]}),   # count
            pd.DataFrame(),              # records
            pd.DataFrame(),              # platforms
        ]
        with app.test_client() as c:
            resp = c.get("/api/shops/data?page=1&per_page=15")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["total"] == 0
            assert "platforms" in data

    def test_list_with_data(self, shops_app):
        app, mock_q, _ = shops_app
        mock_q.side_effect = [
            pd.DataFrame({"c": [3]}),
            pd.DataFrame([
                {"shop_id": "S1", "shop_name": "A店", "platform": "Amazon", "bu": "NA", "email": "a@t.com", "status": 1, "create_time": None},
                {"shop_id": "S2", "shop_name": "B店", "platform": "Walmart", "bu": "NA", "email": "b@t.com", "status": 0, "create_time": None},
            ]),
            pd.DataFrame({"platform": ["Amazon", "Walmart"]}),
        ]
        with app.test_client() as c:
            resp = c.get("/api/shops/data")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data["records"]) == 2
            assert len(data["platforms"]) == 2

    def test_search_filter(self, shops_app):
        app, mock_q, _ = shops_app
        mock_q.side_effect = [
            pd.DataFrame({"c": [1]}),
            pd.DataFrame([{"shop_id": "X99", "shop_name": "搜索测试", "platform": "Amazon", "bu": "NA", "email": "", "status": 1, "create_time": None}]),
            pd.DataFrame({"platform": ["Amazon"]}),
        ]
        with app.test_client() as c:
            resp = c.get("/api/shops/data?search=搜索&platform=Amazon")
            assert resp.status_code == 200
            assert len(resp.get_json()["records"]) == 1


class TestShopsSave:
    def test_create_new_shop(self, shops_app):
        app, mock_q, mock_ex = shops_app
        mock_q.return_value = pd.DataFrame()  # not exists
        with app.test_client() as c:
            resp = c.post("/api/shops/save", json={
                "shop_id": "NEW001", "shop_name": "新店铺",
                "platform": "Amazon", "status": 1,
            })
            assert resp.status_code == 200
            assert resp.get_json()["success"] is True
            assert mock_ex.called

    def test_update_existing_shop(self, shops_app):
        app, mock_q, mock_ex = shops_app
        mock_q.return_value = pd.DataFrame([{"1": 1}])  # exists
        with app.test_client() as c:
            resp = c.post("/api/shops/save", json={
                "shop_id": "OLD001", "shop_name": "改名店铺",
            })
            assert resp.status_code == 200
            assert resp.get_json()["success"] is True

    def test_missing_required(self, shops_app):
        app, _, _ = shops_app
        with app.test_client() as c:
            resp = c.post("/api/shops/save", json={"shop_name": "缺ID"})
            data = resp.get_json()
            assert data["success"] is False


class TestRouteConfig:
    def test_route_list_empty(self, shops_app):
        app, mock_q, _ = shops_app
        mock_q.return_value = pd.DataFrame()
        with app.test_client() as c:
            resp = c.get("/routes")
            assert resp.status_code == 200

    def test_route_data_not_found(self, shops_app):
        app, mock_q, _ = shops_app
        mock_q.return_value = pd.DataFrame()
        with app.test_client() as c:
            resp = c.get("/api/route/999/data")
            assert resp.status_code == 404

    def test_route_save_new(self, shops_app):
        app, _, mock_ex = shops_app
        with app.test_client() as c:
            resp = c.post("/api/route", json={
                "path_pattern": "/data/amazon/*.xlsx",
                "target_ods_table": "ods_test",
                "is_active": 1,
            })
            assert resp.status_code == 200
            assert resp.get_json()["success"] is True

    def test_route_delete(self, shops_app):
        app, _, mock_ex = shops_app
        with app.test_client() as c:
            resp = c.delete("/api/route/1")
            assert resp.status_code == 200
