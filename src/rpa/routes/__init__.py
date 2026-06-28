"""
RPADataHub 路由模块
===================
从 blueprint.py 拆分，每个子模块负责一组相关路由。

注册入口: register_all(bp, query, execute, login_required, permission_required, get_user_permissions)
"""

from .routes_etl import register as _reg_etl
from .routes_monitor import register as _reg_monitor
from .routes_collection import register as _reg_collection
from .routes_tasks import register as _reg_tasks
from .routes_shops import register as _reg_shops
from .routes_bi import register as _reg_bi
from .routes_rbac import register as _reg_rbac


def register_all(bp, query, execute, login_required, permission_required, get_user_permissions):
    """向蓝图注册所有路由模块"""
    ctx = dict(
        bp=bp, query=query, execute=execute,
        login_required=login_required,
        permission_required=permission_required,
        get_user_permissions=get_user_permissions,
    )

    _reg_etl(**ctx)
    _reg_monitor(**ctx)
    _reg_collection(**ctx)
    _reg_tasks(**ctx)
    _reg_shops(**ctx)
    _reg_bi(**ctx)
    _reg_rbac(**ctx)
