"""
Flask 应用启动辅助工具
====================
解决两个常见问题：

1. 启动信息打印两遍
   Flask debug=True 模式下，Werkzeug reloader 会 fork 一个子进程，
   导致 if __name__ == "__main__" 中的代码执行两次。
   通过检测环境变量 WERKZEUG_RUN_MAIN 来判断是否在 reloader 子进程中。

2. 生产环境部署
   Flask 自带开发服务器不适合生产环境。
   当 debug=False 时，优先使用 waitress（已安装则自动启用），
   否则给出明确的部署建议。
"""

import os
import sys


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def is_reloader_child() -> bool:
    """
    判断当前进程是否为 Werkzeug reloader 的子进程。

    Flask debug=True 时：
      - 主进程: WERKZEUG_RUN_MAIN 不存在
      - 子进程: WERKZEUG_RUN_MAIN == "true"
    """
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def should_print_startup(debug: bool) -> bool:
    """
    判断是否应该打印启动信息（避免在 reloader 子进程中重复打印）。

    逻辑：
      - debug=False → 总是打印（没有 reloader）
      - debug=True  → 只在 reloader 子进程中打印一次（那才是真正提供服务的进程）
                      或者在没有 reloader 的主进程中打印（use_reloader=False 时）
    """
    if not debug:
        return True
    # debug=True: 子进程才需要打印，主进程跳过（避免重复）
    return is_reloader_child()


def run_flask_app(
    app,
    host: str = "0.0.0.0",
    port: int = 5000,
    debug: bool = False,
    **kwargs
) -> None:
    """
    统一 Flask 应用启动入口，自动处理开发/生产环境切换。

    用法：
        from shared.runner import run_flask_app
        run_flask_app(app, host="0.0.0.0", port=5000, debug=False)

    行为：
      - debug=True  → 使用 Flask 自带开发服务器（含热重载）
      - debug=False → 尝试使用 waitress 生产服务器；
                       若未安装则使用 Flask 开发服务器（并打印警告）
    """
    # --------------------------------------------------
    # 生产模式：优先使用 waitress
    # --------------------------------------------------
    if not debug:
        try:
            from waitress import serve
            print(f"[runner] 生产模式 → waitress @ {host}:{port}")
            serve(app, host=host, port=port, **kwargs)
            return
        except ImportError:
            print(
                "[runner] ⚠ 未安装 waitress，将使用 Flask 开发服务器。\n"
                "         生产部署请执行: pip install waitress\n"
                "         然后重新启动即可自动切换。"
            )
            # 即使 debug=False，也禁用 reloader
            kwargs.setdefault("use_reloader", False)

    # --------------------------------------------------
    # 开发模式：使用 Flask 自带服务器
    # --------------------------------------------------
    app.run(host=host, port=port, debug=debug, **kwargs)
