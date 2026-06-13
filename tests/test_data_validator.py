"""
data_validator 模块单元测试
测试目标: ShopWhitelistValidator / DataValidator.check_empty_file（纯逻辑）
使用标准库 unittest
"""

import sys
import os
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from core.data_validator import (
    DataValidator, ShopWhitelistValidator,
    CheckResult, ValidationReport,
)


class TestCheckResult(unittest.TestCase):

    def test_enum_values(self):
        self.assertEqual(CheckResult.PASS.value, "PASS")
        self.assertEqual(CheckResult.WARN.value, "WARN")
        self.assertEqual(CheckResult.BLOCK.value, "BLOCK")


class TestValidationReport(unittest.TestCase):

    def test_repr_format(self):
        report = ValidationReport("L0", "空文件", CheckResult.BLOCK, "无数据行")
        self.assertIn("[L0|BLOCK]", repr(report))
        self.assertIn("空文件", repr(report))
        self.assertIn("无数据行", repr(report))


class TestShopWhitelistValidator(unittest.TestCase):

    def test_valid_shop_is_recognized(self):
        validator = ShopWhitelistValidator(["ShopA", "ShopB", "ShopC"])
        self.assertTrue(validator.is_valid("ShopA"))
        self.assertTrue(validator.is_valid("ShopB"))
        self.assertFalse(validator.is_valid("UnknownShop"))

    def test_shop_name_is_stripped(self):
        validator = ShopWhitelistValidator(["ShopA"])
        self.assertTrue(validator.is_valid("  ShopA  "))

    def test_empty_whitelist_rejects_all(self):
        validator = ShopWhitelistValidator([])
        self.assertFalse(validator.is_valid("Anything"))

    def test_shop_count(self):
        validator = ShopWhitelistValidator(["A", "B", "C"])
        self.assertEqual(validator.shop_count, 3)

    def test_detect_shop_column_prefers_shop_name(self):
        validator = ShopWhitelistValidator([])
        df = pd.DataFrame({"shop_name": ["A"], "account": ["B"], "other": [1]})
        col = validator.detect_shop_column(df)
        self.assertEqual(col, "shop_name")

    def test_detect_shop_column_falls_back_to_account(self):
        validator = ShopWhitelistValidator([])
        df = pd.DataFrame({"account": ["B"], "other": [1]})
        col = validator.detect_shop_column(df)
        self.assertEqual(col, "account")

    def test_detect_shop_column_uses_first_column_as_fallback(self):
        validator = ShopWhitelistValidator([])
        df = pd.DataFrame({"unknown_col": [1], "col2": [2]})
        col = validator.detect_shop_column(df)
        self.assertEqual(col, "unknown_col")

    def test_detect_shop_column_empty_df_returns_none(self):
        validator = ShopWhitelistValidator([])
        df = pd.DataFrame()
        col = validator.detect_shop_column(df)
        self.assertIsNone(col)

    def test_filter_valid_separates_correctly(self):
        validator = ShopWhitelistValidator(["ShopA", "ShopC"])
        df = pd.DataFrame({
            "shop_name": ["ShopA", "ShopB", "ShopC", "ShopD"],
            "value": [1, 2, 3, 4],
        })
        valid, dirty = validator.filter_valid(df, "shop_name")
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(dirty), 2)
        self.assertEqual(list(valid["shop_name"]), ["ShopA", "ShopC"])
        self.assertEqual(list(dirty["shop_name"]), ["ShopB", "ShopD"])


class TestDataValidatorCheckEmptyFile(unittest.TestCase):

    def test_none_df_is_blocked(self):
        validator = DataValidator(db_manager=None)
        reports, should_abort = validator.check_empty_file(None, "test.xlsx")
        self.assertTrue(should_abort)
        self.assertEqual(reports[0].result, CheckResult.BLOCK)
        self.assertIn("test.xlsx", reports[0].detail)

    def test_empty_df_is_blocked(self):
        validator = DataValidator(db_manager=None)
        reports, should_abort = validator.check_empty_file(pd.DataFrame(), "empty.xlsx")
        self.assertTrue(should_abort)
        self.assertEqual(reports[0].result, CheckResult.BLOCK)

    def test_non_empty_df_passes(self):
        validator = DataValidator(db_manager=None)
        df = pd.DataFrame({"col": [1, 2, 3]})
        reports, should_abort = validator.check_empty_file(df, "data.xlsx")
        self.assertFalse(should_abort)
        self.assertEqual(reports[0].result, CheckResult.PASS)
        self.assertIn("3 条", reports[0].detail)


class TestShopWhitelistValidatorConstructor(unittest.TestCase):

    def test_default_constructor_creates_empty_set(self):
        validator = ShopWhitelistValidator()
        self.assertEqual(validator.shop_count, 0)
        self.assertFalse(validator.is_valid("AnyShop"))

    def test_no_shops_provided(self):
        validator = ShopWhitelistValidator(None)
        self.assertEqual(validator.shop_count, 0)


if __name__ == "__main__":
    unittest.main()
