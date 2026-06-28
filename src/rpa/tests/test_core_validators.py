"""
core/validators.py 单元测试
"""

import pytest
from unittest.mock import patch
from flask import Flask


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


class TestValidateInt:
    def test_normal(self, app):
        from core.validators import validate_int
        with app.test_request_context("/?page=5"):
            assert validate_int("page", 1) == 5

    def test_default(self, app):
        from core.validators import validate_int
        with app.test_request_context("/"):
            assert validate_int("page", 1) == 1

    def test_negative_clamped(self, app):
        from core.validators import validate_int
        with app.test_request_context("/?page=-1"):
            assert validate_int("page", 1, min_val=0) == 0

    def test_invalid_string(self, app):
        from core.validators import validate_int
        with app.test_request_context("/?page=abc"):
            assert validate_int("page", 1) == 1  # returns default


class TestValidatePage:
    def test_page_min_1(self, app):
        from core.validators import validate_page
        with app.test_request_context("/?page=0"):
            assert validate_page() == 1

    def test_page_max(self, app):
        from core.validators import validate_page
        with app.test_request_context("/?page=99999"):
            assert validate_page() == 9999  # clamped


class TestValidatePerPage:
    def test_per_page_max(self, app):
        from core.validators import validate_per_page
        with app.test_request_context("/?per_page=500"):
            assert validate_per_page() == 100

    def test_per_page_min(self, app):
        from core.validators import validate_per_page
        with app.test_request_context("/?per_page=0"):
            assert validate_per_page() == 1


class TestValidateDate:
    def test_valid_date(self, app):
        from core.validators import validate_date
        with app.test_request_context("/?date=2026-06-15"):
            assert validate_date("date") == "2026-06-15"

    def test_invalid_date(self, app):
        from core.validators import validate_date
        with app.test_request_context("/?date=not-a-date"):
            with pytest.raises(Exception):  # abort(400)
                validate_date("date")

    def test_empty_date(self, app):
        from core.validators import validate_date
        with app.test_request_context("/"):
            assert validate_date("date") == ""


class TestValidateSort:
    def test_whitelist_allowed(self, app):
        from core.validators import validate_sort
        with app.test_request_context("/?sort=shop_name"):
            assert validate_sort(allowed=["shop_name", "platform"]) == "shop_name"

    def test_whitelist_blocked(self, app):
        from core.validators import validate_sort
        with app.test_request_context("/?sort=DROP TABLE"):
            with pytest.raises(Exception):
                validate_sort(allowed=["shop_name"])


class TestValidateOrder:
    def test_asc(self, app):
        from core.validators import validate_order
        with app.test_request_context("/?order=asc"):
            assert validate_order() == "asc"

    def test_desc(self, app):
        from core.validators import validate_order
        with app.test_request_context("/?order=DESC"):
            assert validate_order() == "desc"

    def test_invalid(self, app):
        from core.validators import validate_order
        with app.test_request_context("/?order=random"):
            with pytest.raises(Exception):
                validate_order()
