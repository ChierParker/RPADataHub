"""
error_classifier 模块单元测试
测试目标: classify_mysql_error 函数（纯逻辑，无外部依赖）
使用标准库 unittest
"""

import sys
import os
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.error_classifier import (
    classify_mysql_error, ErrorSeverity, ClassifiedError, ERROR_MAP,
)


class TestClassifyMysqlError(unittest.TestCase):

    def test_duplicate_key_is_ignorable(self):
        """1062 重复键应返回 IGNORE 级别（幂等写入场景）"""
        err = Exception()
        err.args = (1062, "Duplicate entry 'xxx' for key 'PRIMARY'")
        result = classify_mysql_error(err)
        self.assertEqual(result.code, 1062)
        self.assertEqual(result.severity, ErrorSeverity.IGNORE)
        self.assertIn("重复键", result.message)

    def test_column_not_found_is_fatal(self):
        """1054 字段不存在应返回 FATAL"""
        err = Exception()
        err.args = (1054, "Unknown column 'bad_col' in 'field list'")
        result = classify_mysql_error(err)
        self.assertEqual(result.code, 1054)
        self.assertEqual(result.severity, ErrorSeverity.FATAL)
        self.assertIn("字段不存在", result.message)

    def test_connection_refused_is_fatal(self):
        """2002 连接失败应返回 FATAL"""
        err = Exception()
        err.args = (2002, "Can't connect to MySQL server")
        result = classify_mysql_error(err)
        self.assertEqual(result.severity, ErrorSeverity.FATAL)
        self.assertIn("连接失败", result.message)

    def test_null_not_allowed_is_fatal(self):
        """1048 NOT NULL 约束违反应返回 FATAL"""
        err = Exception()
        err.args = (1048, "Column 'shop_name' cannot be null")
        result = classify_mysql_error(err)
        self.assertEqual(result.code, 1048)
        self.assertEqual(result.severity, ErrorSeverity.FATAL)
        self.assertIn("必填", result.message)

    def test_data_too_long_is_fatal(self):
        """1406 数据过长应返回 FATAL"""
        err = Exception()
        err.args = (1406, "Data too long for column 'name'")
        result = classify_mysql_error(err)
        self.assertEqual(result.code, 1406)
        self.assertEqual(result.severity, ErrorSeverity.FATAL)

    def test_unknown_error_returns_fatal_with_raw_message(self):
        """未知错误码默认返回 FATAL 并保留原始消息"""
        err = Exception("Something totally unexpected happened")
        result = classify_mysql_error(err)
        self.assertEqual(result.severity, ErrorSeverity.FATAL)
        self.assertIn("Something totally unexpected", result.message)

    def test_pymysql_tuple_format(self):
        """pymysql 标准格式: (1062, message)"""
        err = Exception()
        err.args = (1146, "Table 'data.unknown' doesn't exist")
        result = classify_mysql_error(err)
        self.assertEqual(result.code, 1146)
        self.assertEqual(result.severity, ErrorSeverity.FATAL)

    def test_code_in_message_string(self):
        """错误码嵌入在文本消息中"""
        err = Exception()
        err.args = ("(1054, Unknown column)",)
        result = classify_mysql_error(err)
        self.assertEqual(result.code, 1054)


class TestClassifiedError(unittest.TestCase):

    def test_string_representation(self):
        ce = ClassifiedError(1062, ErrorSeverity.IGNORE, "重复键", "可跳过")
        self.assertIn("[IGNORE]", str(ce))
        self.assertIn("重复键", str(ce))


class TestErrorSeverity(unittest.TestCase):

    def test_all_severities_defined(self):
        self.assertEqual(ErrorSeverity.FATAL.value, "FATAL")
        self.assertEqual(ErrorSeverity.WARN.value, "WARN")
        self.assertEqual(ErrorSeverity.IGNORE.value, "IGNORE")


class TestErrorMap(unittest.TestCase):

    def test_key_codes_present(self):
        """确认关键错误码已映射"""
        expected_codes = [1054, 1062, 1048, 1146, 1366, 1406, 2002, 2003]
        for code in expected_codes:
            self.assertIn(code, ERROR_MAP, f"缺少错误码 {code}")

    def test_all_entries_have_three_elements(self):
        for code, entry in ERROR_MAP.items():
            self.assertEqual(len(entry), 3, f"错误码 {code}: 应为 (severity, message, suggestion)")


if __name__ == "__main__":
    unittest.main()
