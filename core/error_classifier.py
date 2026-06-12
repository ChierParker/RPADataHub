"""
MySQL错误分类器
核心理念（白皮书 4.2 节模板化接入）:
  数据库 Schema 本身就是最可靠的校验层。
  字段类型、非空约束、唯一约束全部由 MySQL 兜底，
  代码仅负责捕获异常并翻译为运维可读的消息。

MySQL错误码映射:
  https://dev.mysql.com/doc/refman/8.0/en/server-error-reference.html
"""

import re
from enum import Enum


class ErrorSeverity(Enum):
    """错误严重程度"""
    FATAL = "FATAL"     # 不可恢复，需人工介入
    WARN = "WARN"       # 可降级处理
    IGNORE = "IGNORE"   # 可忽略（如幂等重复）


class ClassifiedError:
    """分类后的错误信息"""

    def __init__(self, code: int, severity: ErrorSeverity, message: str, suggestion: str = ""):
        self.code = code
        self.severity = severity
        self.message = message
        self.suggestion = suggestion

    def __str__(self):
        return f"[{self.severity.value}] {self.message}"


# MySQL 错误码 → 分类映射
ERROR_MAP = {
    # 字段/表不存在
    1054: (ErrorSeverity.FATAL, "字段不存在", "Excel列名与数据库表字段不匹配，检查列名是否一致（已自动转小写）"),
    1146: (ErrorSeverity.FATAL, "目标表不存在", "检查路由配置中的ODS/DW表名是否正确"),

    # 类型不匹配
    1366: (ErrorSeverity.FATAL, "字段类型不匹配", "Excel中的数据类型与数据库列定义不一致（如文本写入INT列）"),
    1265: (ErrorSeverity.FATAL, "字段类型不匹配", "数据格式与列类型不符"),
    1367: (ErrorSeverity.FATAL, "非法数值", "字段包含无法解析为数字的值"),

    # 非空约束
    1048: (ErrorSeverity.FATAL, "必填字段为空", "某些NOT NULL列缺少值，检查Excel对应列是否有空单元格"),
    1136: (ErrorSeverity.FATAL, "列数与值数不匹配", "Excel列数与数据库表列数不一致"),

    # 唯一约束（幂等写入场景属正常）
    1062: (ErrorSeverity.IGNORE, "重复键（幂等跳过）", "数据已存在，根据唯一键策略跳过或更新"),

    # 数据过长
    1406: (ErrorSeverity.FATAL, "数据过长", "字段值超过数据库列定义的最大长度"),
    1264: (ErrorSeverity.FATAL, "数值超出范围", "数值超过列定义的范围"),

    # 连接/超时
    2002: (ErrorSeverity.FATAL, "数据库连接失败", "检查MySQL服务状态和连接配置"),
    2003: (ErrorSeverity.FATAL, "数据库连接超时", "检查网络连接和防火墙设置"),
    2006: (ErrorSeverity.FATAL, "MySQL服务断开", "可能因超时或服务重启导致"),
    2013: (ErrorSeverity.FATAL, "查询超时", "SQL执行时间过长"),
}


def classify_mysql_error(exception) -> ClassifiedError:
    """
    将 pymysql 异常分类为运维可读的消息

    参数:
      exception: pymysql.err.OperationalError 或其他数据库异常

    返回:
      ClassifiedError 对象
    """
    # 提取错误码
    code = None
    raw_msg = str(exception)

    # pymysql.err.OperationalError 格式: (code, "message")
    if hasattr(exception, "args") and len(exception.args) >= 1:
        arg = exception.args[0]
        if isinstance(arg, int):
            code = arg
        elif isinstance(arg, str):
            match = re.match(r"^\(?(\d+)", arg)
            if match:
                code = int(match.group(1))

    # pymysql.err.IntegrityError 格式: (1062, "Duplicate entry ...")
    if code is None and hasattr(exception, "args"):
        for arg in exception.args:
            if isinstance(arg, int):
                code = arg
                break

    # Pandas DatabaseError 包装了原始异常
    if code is None:
        raw_msg = str(exception)
        code_match = re.search(r"\((\d{4}),", raw_msg)
        if code_match:
            code = int(code_match.group(1))

    # 查找映射
    if code and code in ERROR_MAP:
        severity, message, suggestion = ERROR_MAP[code]
        return ClassifiedError(code, severity, message, suggestion)

    # 默认：未知错误
    return ClassifiedError(
        code or 0,
        ErrorSeverity.FATAL,
        f"数据库写入异常: {raw_msg[:200]}",
        "查看完整错误日志以定位原因"
    )
