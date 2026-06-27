"""Tests for core/db_operations.py module.

Tests use mocking to avoid requiring a real MySQL connection.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from core.db_operations import DatabaseManager


class TestDatabaseManager:

    @pytest.fixture
    def db(self):
        """Create DatabaseManager with mocked pymysql."""
        with patch("core.db_operations.pymysql") as mock_pymysql:
            with patch("core.db_operations.get_config") as mock_config:
                mock_cfg = MagicMock()
                mock_cfg.database.host = "localhost"
                mock_cfg.database.port = 3306
                mock_cfg.database.user = "root"
                mock_cfg.database.password = ""
                mock_cfg.database.database = "ecomiq_rpa"
                mock_cfg.database.charset = "utf8mb4"
                mock_cfg.database.connect_timeout = 10
                mock_config.return_value = mock_cfg

                yield DatabaseManager(trace_id="test-001")

    def test_init_stores_config(self, db):
        """DatabaseManager should store config from settings."""
        assert db._config["host"] == "localhost"
        assert db._config["port"] == 3306
        assert db._config["database"] == "ecomiq_rpa"
        assert db._trace_id == "test-001"

    def test_get_competitor_list(self, db):
        """Should execute parameterized query and return list."""
        mock_row = {
            "id": 1,
            "competitor_name": "Test Brand",
            "keywords": '["test"]',
            "region": "international",
            "platform": "amazon",
            "status": 1,
        }

        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [mock_row]
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            result = db.get_competitor_list()

            assert len(result) == 1
            assert result[0]["competitor_name"] == "Test Brand"

    def test_get_competitor_list_with_region(self, db):
        """Should add region filter when provided."""
        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            db.get_competitor_list(region="international")

            args, _ = mock_cursor.execute.call_args
            assert "international" in args[1]

    def test_insert_competitor(self, db):
        """Should return new record ID on insert."""
        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.lastrowid = 42
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            new_id = db.insert_competitor({
                "competitor_name": "New Brand",
                "keywords": '["keyword"]',
                "region": "domestic",
                "platform": "taobao",
            })

            assert new_id == 42

    def test_update_competitor(self, db):
        """Should update only provided fields."""
        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.__enter__.return_value = mock_cur
            mock_cur.execute.return_value = 1  # Return int not MagicMock
            mock_conn.cursor.return_value = mock_cur
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            result = db.update_competitor(1, {"competitor_name": "Updated"})

            assert result is True

    def test_update_competitor_empty(self, db):
        """Should return False when no fields to update."""
        result = db.update_competitor(1, {})
        assert result is False

    def test_toggle_competitor(self, db):
        """Should toggle status."""
        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.rowcount = 1
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            result = db.toggle_competitor(1)
            assert result is True

    def test_delete_competitor(self, db):
        """Should delete by ID."""
        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.rowcount = 1
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            result = db.delete_competitor(1)
            assert result is True

    def test_get_price_trend(self, db):
        """Should return price trend data."""
        mock_rows = [
            {"snapshot_date": "2026-06-01", "min_price": 10.0, "max_price": 20.0, "avg_price": 15.0},
            {"snapshot_date": "2026-06-02", "min_price": 12.0, "max_price": 22.0, "avg_price": 17.0},
        ]

        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = mock_rows
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            result = db.get_price_trend(1, days=30)
            assert len(result) == 2

    def test_save_report(self, db):
        """Should save AI report and return ID."""
        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.lastrowid = 100
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            report_id = db.save_report(1, "daily", "2026-06-14", "# Report", "Summary")

            assert report_id == 100

    def test_get_reports(self, db):
        """Should return report list."""
        mock_reports = [{"id": 1, "competitor_name": "Brand X", "report_type": "daily"}]

        with patch.object(db, "connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = mock_reports
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn_ctx.return_value.__enter__.return_value = mock_conn

            result = db.get_reports()
            assert len(result) == 1
