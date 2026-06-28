"""
pytest 共享 fixtures — 数据库连接、测试客户端、模拟数据
"""

import os
import sys
import pytest

# 确保模块路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from unittest.mock import MagicMock, patch
import pandas as pd


@pytest.fixture
def mock_db():
    """模拟数据库连接池"""
    mock = MagicMock()
    mock.query.return_value = pd.DataFrame()
    mock.execute.return_value = None
    return mock


@pytest.fixture
def mock_perm():
    """模拟权限管理器"""
    mock = MagicMock()
    mock.get_user_permissions.return_value = ["dashboard", "collection_health"]
    mock.login_required = lambda f: f  # no-op decorator
    mock.permission_required = lambda p: lambda f: f
    return mock


@pytest.fixture
def app_context():
    """创建 Flask 测试应用"""
    app = Flask(__name__, template_folder="../templates")
    app.secret_key = "test-secret"
    app.config["TESTING"] = True

    with app.app_context():
        yield app


@pytest.fixture
def sample_shop_data():
    """模拟店铺数据"""
    return pd.DataFrame([
        {"shop_id": "S001", "shop_name": "测试店铺1", "platform": "Amazon", "bu": "北美", "email": "s1@test.com", "status": 1},
        {"shop_id": "S002", "shop_name": "测试店铺2", "platform": "Walmart", "bu": "北美", "email": "s2@test.com", "status": 1},
        {"shop_id": "S003", "shop_name": "测试店铺3", "platform": "Shopee", "bu": "东南亚", "email": "s3@test.com", "status": 0},
    ])


@pytest.fixture
def sample_task_data():
    """模拟任务队列数据"""
    return pd.DataFrame([
        {"task_uuid": "abc-123", "script_name": "demo_po", "task_status": "SUCCESS",
         "start_time": "2026-01-01 10:00:00", "duration_sec": 45, "error_message": None},
        {"task_uuid": "def-456", "script_name": "demo_po", "task_status": "FAILED",
         "start_time": "2026-01-01 11:00:00", "duration_sec": 120, "error_message": "Timeout"},
    ])


@pytest.fixture
def sample_etl_data():
    """模拟 ETL 数据"""
    return pd.DataFrame([
        {"trace_id": "t1", "file_name": "test.xlsx", "ods_table": "ods_order_raw", "status": "SUCCESS",
         "row_count": 100, "dirty_count": 0, "error_msg": None, "start_time": "2026-01-01 09:00:00"},
        {"trace_id": "t2", "file_name": "bad.csv", "ods_table": "ods_sales_raw", "status": "FAILED",
         "row_count": 0, "dirty_count": 50, "error_msg": "Column not found", "start_time": "2026-01-01 10:00:00"},
    ])
