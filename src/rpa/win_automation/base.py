"""
WinCollector 基类 — 所有 Windows 桌面采集器必须继承此类
提供标准化生命周期：启动应用 → 定位窗口 → 执行操作 → 采集数据 → 关闭应用
"""

import sys
import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Dict

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from playwright_collection_script.schemas.task_schema import TaskConfig
from playwright_collection_script.schemas.result_schema import ShopRecord, TaskSummary


class WinCollector(ABC):
    """
    Windows 桌面自动化采集器基类

    子类必须实现:
        run(config: TaskConfig) -> TaskSummary

    可选覆盖:
        _on_start(): 启动前钩子（打开应用、登录等）
        _on_finish(): 结束时钩子（关闭应用、清理等）

    内置能力:
        - OCR 文字识别
        - 图像模板匹配
        - 操作重试
        - 超时保护
    """

    collector_name: str = "win_base"
    supported_apps: list = []       # e.g., ["notepad", "excel", "sap"]
    target_exe: str = ""            # 目标应用路径，如 "notepad.exe" 或完整路径
    backend: str = "uia"            # pywinauto backend: "uia" | "win32"
    timeout_sec: int = 60           # 单步操作超时

    def __init__(self):
        self._ctx: Optional[TaskConfig] = None
        self._start_time: float = 0
        self._records: list = []
        self._errors: list = []
        self._app: Any = None           # pywinauto Application 实例
        self._window: Any = None        # 主窗口引用
        self._ocr = None                # OCR 引擎（懒加载）
        self._im = None                 # 图像引擎（懒加载）

    # ============================================================
    # 生命周期（模板方法）
    # ============================================================

    def execute(self, config: TaskConfig) -> TaskSummary:
        """统一执行入口"""
        self._ctx = config
        self._start_time = time.time()
        self._records = []
        self._errors = []

        try:
            self._on_start()
            summary = self.run(config)
            self._on_success(summary)
            return summary
        except Exception as e:
            summary = self._on_error(e)
            return summary
        finally:
            self._on_finish()

    def _on_start(self):
        """任务开始：打开目标应用"""
        if self.target_exe:
            self._app = self._launch_app(self.target_exe, self.backend)
            self._window = self._connect_window()

    def _on_success(self, summary: TaskSummary):
        summary.total_duration = int(time.time() - self._start_time)
        summary.compute()
        self._write_to_db(summary)

    def _on_error(self, error: Exception) -> TaskSummary:
        shop = (self._ctx.account or self._ctx.shops[0]
                if self._ctx and self._ctx.shops else "unknown")
        self.add_record(
            shop_name=shop,
            result="FAILED", error=str(error)[:500],
            duration=int(time.time() - self._start_time)
        )
        summary = TaskSummary(
            task_uuid=self._ctx.task_id if self._ctx else "",
            task_name=self.collector_name,
            total_shops=len(self._ctx.shops) if self._ctx else 1,
            failed_shops=len(self._ctx.shops) if self._ctx else 1,
            total_duration=int(time.time() - self._start_time),
            errors=[str(error), traceback.format_exc()]
        )
        summary.compute()
        return summary

    def _on_finish(self):
        """任务结束：关闭应用"""
        if self._app:
            try:
                self._app.kill()
            except Exception:
                pass
            self._app = None
            self._window = None

    # ============================================================
    # 子类必须实现
    # ============================================================

    @abstractmethod
    def run(self, config: TaskConfig) -> TaskSummary:
        """执行桌面自动化采集逻辑"""
        ...

    # ============================================================
    # 应用操作 API
    # ============================================================

    def _launch_app(self, exe_path: str, backend: str = "uia") -> Any:
        """启动 Windows 应用"""
        from pywinauto import Application
        app = Application(backend=backend).start(exe_path)
        time.sleep(2)  # 等待窗口加载
        return app

    def _connect_window(self, title_re: str = ".*") -> Any:
        """连接到目标窗口"""
        if not self._app:
            raise RuntimeError("应用未启动")
        return self._app.window(title_re=title_re)

    def click_button(self, name: str, timeout: int = None) -> bool:
        """点击按钮"""
        return self._action_with_retry(
            lambda: self._window.child_window(title=name, control_type="Button").click(),
            f"点击按钮 [{name}]", timeout
        )

    def input_text(self, text: str, target: str = "Edit", timeout: int = None):
        """输入文本到控件"""
        return self._action_with_retry(
            lambda: self._window.child_window(control_type=target).type_keys(text),
            f"输入文本到 [{target}]", timeout
        )

    def get_text(self, target: str = "Edit", timeout: int = None) -> str:
        """获取控件文本"""
        result = [""]

        def _get():
            result[0] = self._window.child_window(
                control_type=target
            ).window_text()
        self._action_with_retry(_get, f"获取文本 [{target}]", timeout)
        return result[0]

    def select_menu(self, menu_path: list, timeout: int = None):
        """选择菜单项，如 ['文件', '打开']"""
        return self._action_with_retry(
            lambda: self._window.menu_select(" -> ".join(menu_path)),
            f"选择菜单 {menu_path}", timeout
        )

    def wait_window(self, title_re: str, timeout: int = None) -> Any:
        """等待窗口出现"""
        t = timeout or self.timeout_sec
        return self._app.window(title_re=title_re).wait("visible", timeout=t)

    # ============================================================
    # OCR 操作 API
    # ============================================================

    @property
    def ocr(self):
        """懒加载 OCR 引擎"""
        if self._ocr is None:
            from .ocr_engine import OCREngine
            self._ocr = OCREngine()
        return self._ocr

    def find_text_on_screen(self, text: str, region: tuple = None) -> Optional[tuple]:
        """在屏幕上查找文字位置，返回 (x, y) 中心坐标"""
        return self.ocr.find_text(text, region)

    def read_text_from_region(self, region: tuple) -> str:
        """读取指定区域的全部文字"""
        return self.ocr.read_region(region)

    # ============================================================
    # 图像操作 API
    # ============================================================

    @property
    def image(self):
        """懒加载图像引擎"""
        if self._im is None:
            from .image_engine import ImageEngine
            self._im = ImageEngine()
        return self._im

    def find_image(self, template_path: str, confidence: float = 0.8,
                   region: tuple = None) -> Optional[tuple]:
        """在屏幕上查找模板图像位置"""
        return self.image.find_template(template_path, confidence, region)

    def click_image(self, template_path: str, confidence: float = 0.8,
                    region: tuple = None) -> bool:
        """找到图像并点击"""
        pos = self.find_image(template_path, confidence, region)
        if pos:
            import pyautogui
            pyautogui.click(pos)
            return True
        return False

    def take_screenshot(self, region: tuple = None, save_path: str = None) -> Any:
        """截图指定区域"""
        import pyautogui
        if region:
            img = pyautogui.screenshot(region=region)
        else:
            img = pyautogui.screenshot()
        if save_path:
            img.save(save_path)
        return img

    # ============================================================
    # 辅助方法
    # ============================================================

    def _action_with_retry(self, action, description: str,
                           timeout: int = None, max_retries: int = 3) -> bool:
        """带重试的操作执行"""
        t = timeout or self.timeout_sec
        for attempt in range(max_retries):
            try:
                action()
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    self._errors.append(f"{description}: {e}")
                    raise
                time.sleep(1.0 * (attempt + 1))
        return False

    def add_record(self, shop_name: str, result: str, row_count: int = 0,
                   error: str = "", duration: int = 0, platform: str = "Windows"):
        """记录采集结果"""
        self._records.append(ShopRecord(
            task_uuid=self._ctx.task_id if self._ctx else "",
            shop_name=shop_name,
            platform=platform,
            script_name=self.collector_name,
            ods_table=self.default_ods_table if hasattr(self, 'default_ods_table') else "",
            collect_start=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            collect_end=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            collect_result=result,
            row_count=row_count,
            error_message=error,
            duration_sec=duration
        ))

    def build_summary(self, total_rows: int = 0) -> TaskSummary:
        """从记录构建汇总"""
        success = sum(1 for r in self._records if r.collect_result == "SUCCESS")
        failed = sum(1 for r in self._records if r.collect_result == "FAILED")
        no_data = sum(1 for r in self._records if r.collect_result == "NO_DATA")
        return TaskSummary(
            task_uuid=self._ctx.task_id if self._ctx else "",
            task_name=self.collector_name,
            total_shops=len(self._records),
            success_shops=success,
            failed_shops=failed,
            no_data_shops=no_data,
            total_rows=total_rows,
        )

    @property
    def records(self) -> list:
        return self._records

    @property
    def default_ods_table(self) -> str:
        return ""