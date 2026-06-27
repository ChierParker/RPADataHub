"""
Excel 采集器 — 演示 Office 应用自动化
=====================================
打开 Excel → 创建/读取工作表 → 提取数据 → 关闭
适用于从 Excel/金蝶/用友 等 Office 应用中采集数据
"""

import sys
import time
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from win_automation.base import WinCollector
from playwright_collection_script.schemas.task_schema import TaskConfig
from playwright_collection_script.schemas.result_schema import TaskSummary


class ExcelCollector(WinCollector):
    """
    Excel 自动化采集器

    采集流程:
        1. 启动 EXCEL.EXE
        2. 等待 Excel 窗口加载
        3. 在 A1 单元格输入数据
        4. 读取指定区域的数据
        5. 保存/关闭

    适用场景:
        - Excel 报表数据提取
        - 金蝶/用友等基于 Office 的 ERP 数据采集
        - 批量 Excel 文件处理
    """

    collector_name = "excel_collector"
    supported_apps = ["excel", "金蝶", "用友"]
    target_exe = "EXCEL.EXE"
    backend = "uia"
    default_ods_table = "excel_data"

    def __init__(self):
        super().__init__()
        self._output_dir = Path(__file__).resolve().parent.parent.parent / "data" / "excel_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, config: TaskConfig) -> TaskSummary:
        """执行 Excel 采集"""
        extra_params = getattr(config, 'extra_params', {}) or {}
        file_path = extra_params.get("file_path")
        cell_data = extra_params.get("cell_data", {})
        read_range = extra_params.get("read_range")  # e.g., "A1:C10"

        try:
            # 等待 Excel 完全加载
            time.sleep(2)
            self._window.set_focus()

            # 步骤1: 如果有文件路径，打开文件
            if file_path:
                self._window.type_keys("^o")  # Ctrl+O
                time.sleep(0.5)
                open_dlg = self.wait_window(title_re=".*打开|.*Open", timeout=10)
                if open_dlg:
                    file_input = open_dlg.child_window(control_type="Edit")
                    file_input.set_edit_text(str(file_path))
                    time.sleep(0.3)
                    open_btn = open_dlg.child_window(title="打开", control_type="Button")
                    if not open_btn.exists():
                        open_btn = open_dlg.child_window(title="Open", control_type="Button")
                    open_btn.click()
                    time.sleep(1)

            # 步骤2: 向指定单元格写入数据
            if cell_data:
                for cell_ref, value in cell_data.items():
                    self._navigate_to_cell(cell_ref)
                    self._window.type_keys(str(value))
                    time.sleep(0.1)

            # 步骤3: 读取指定范围的数据
            extracted_data = []
            if read_range:
                # 解析范围 e.g., "A1:C10"
                start_cell, end_cell = self._parse_range(read_range)
                if start_cell and end_cell:
                    extracted_data = self._read_cell_range(start_cell, end_cell)

                    self.add_record(
                        shop_name="Excel",
                        result="SUCCESS",
                        row_count=len(extracted_data),
                        duration=int(time.time() - self._start_time)
                    )
            elif cell_data:
                self.add_record(
                    shop_name="Excel",
                    result="SUCCESS",
                    row_count=len(cell_data),
                    duration=int(time.time() - self._start_time)
                )
            else:
                self.add_record(
                    shop_name="Excel",
                    result="NO_DATA",
                    row_count=0,
                    duration=int(time.time() - self._start_time)
                )

        except Exception as e:
            self.add_record(
                shop_name="Excel",
                result="FAILED",
                error=str(e),
                duration=int(time.time() - self._start_time)
            )

        finally:
            # 保存并关闭
            try:
                self._window.type_keys("^s")  # Ctrl+S 保存
                time.sleep(0.3)
            except Exception:
                pass

        return self.build_summary()

    def _navigate_to_cell(self, cell_ref: str):
        """导航到指定单元格"""
        # Excel 使用 Ctrl+G 打开定位对话框
        self._window.type_keys("^g")
        time.sleep(0.3)
        # 输入单元格引用
        goto_dlg = None
        try:
            goto_dlg = self._app.window(title_re=".*定位|.*Go To")
            if goto_dlg.exists():
                input_ctrl = goto_dlg.child_window(control_type="Edit")
                input_ctrl.set_edit_text(cell_ref)
                time.sleep(0.1)
                ok_btn = goto_dlg.child_window(title="确定", control_type="Button")
                if not ok_btn.exists():
                    ok_btn = goto_dlg.child_window(title="OK", control_type="Button")
                ok_btn.click()
                time.sleep(0.1)
        except Exception:
            # 降级：直接用方向键粗略定位
            pass

    def _read_cell_range(self, start: str, end: str) -> list:
        """读取单元格范围数据"""
        # 选中范围
        self._navigate_to_cell(start)
        # 复制数据的方式：直接在名称框中输入范围按回车
        self._window.type_keys("^g")
        time.sleep(0.3)
        try:
            goto_dlg = self._app.window(title_re=".*定位|.*Go To")
            if goto_dlg.exists():
                input_ctrl = goto_dlg.child_window(control_type="Edit")
                input_ctrl.set_edit_text(f"{start}:{end}")
                time.sleep(0.1)
                ok_btn = goto_dlg.child_window(title="确定", control_type="Button")
                if not ok_btn.exists():
                    ok_btn = goto_dlg.child_window(title="OK", control_type="Button")
                ok_btn.click()
                time.sleep(0.2)

                # 复制选中区域
                self._window.type_keys("^c")
                time.sleep(0.3)

                # 从剪贴板读取
                import pyperclip
                text = pyperclip.paste()
                lines = text.strip().split("\r\n")
                return [line.split("\t") for line in lines]
        except Exception as e:
            pass
        return []

    def _parse_range(self, range_str: str):
        """解析范围字符串"""
        try:
            parts = range_str.split(":")
            if len(parts) == 2:
                return parts[0], parts[1]
            return parts[0], parts[0]
        except Exception:
            return None, None