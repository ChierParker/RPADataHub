"""
请求参数校验模块
================
提供统一的输入校验，防止注入和非法参数。

使用示例:
    from core.validators import validate_page, validate_shop_name, validate_date

    page = validate_page()
    shop = validate_shop_name()
    date_from, date_to = validate_date()
"""

import re
from datetime import datetime
from flask import request, abort


def validate_int(key: str, default: int = 0, min_val: int = 0, max_val: int = 999999) -> int:
    """安全解析整数参数"""
    try:
        val = int(request.args.get(key, default))
        val = max(min_val, min(max_val, val))
        return val
    except (ValueError, TypeError):
        return default


def validate_page(default: int = 1) -> int:
    """校验分页页码：1~9999"""
    return validate_int("page", default, min_val=1, max_val=9999)


def validate_per_page(default: int = 15) -> int:
    """校验每页条数：1~100"""
    return validate_int("per_page", default, min_val=1, max_val=100)


def validate_shop_name(key: str = "shop") -> str:
    """校验店铺名称：只允许字母数字中文横线"""
    val = request.args.get(key, "").strip()
    if val and not re.match(r'^[\w\u4e00-\u9fff\- ]{1,100}$', val):
        abort(400, description="非法店铺名称")
    return val


def validate_date(key: str = "date") -> str:
    """校验日期格式：YYYY-MM-DD"""
    val = request.args.get(key, "").strip()
    if not val:
        return ""
    try:
        datetime.strptime(val, "%Y-%m-%d")
        return val
    except ValueError:
        abort(400, description=f"日期格式错误: {val}，需要 YYYY-MM-DD")


def validate_date_range() -> tuple:
    """校验日期范围，返回 (date_from, date_to)"""
    date_from = validate_date("date_from")
    date_to = validate_date("date_to")
    if date_from and date_to and date_from > date_to:
        abort(400, description="起始日期不能晚于结束日期")
    return date_from, date_to


def validate_sort(key: str = "sort", allowed: list = None) -> str:
    """校验排序字段（白名单）"""
    val = request.args.get(key, "").strip()
    if not val:
        return ""
    if allowed and val not in allowed:
        abort(400, description=f"不支持的排序字段: {val}")
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$', val):
        abort(400, description="非法排序字段名")
    return val


def validate_order(key: str = "order") -> str:
    """校验排序方向：asc 或 desc"""
    val = request.args.get(key, "desc").strip().lower()
    if val not in ("asc", "desc"):
        abort(400, description="排序方向只能是 asc 或 desc")
    return val


def validate_uuid(key: str = "task_uuid") -> str:
    """校验 UUID 格式"""
    val = request.args.get(key, "").strip()
    if val and not re.match(r'^[a-fA-F0-9\-]{8,64}$', val):
        abort(400, description="非法 UUID 格式")
    return val


def validate_platform(key: str = "platform") -> str:
    """校验平台名称"""
    val = request.args.get(key, "").strip()
    if val and not re.match(r'^[\w\-]{1,50}$', val):
        abort(400, description="非法平台名称")
    return val
