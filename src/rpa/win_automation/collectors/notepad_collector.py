"""
记事本采集器 — 演示 Win 控件级自动化
======================================
将文本写入记事本 → 保存文件 → 读取内容 → 关闭
"""

import os
import sys
import time
from pathlib import Path
from typing import Any

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from win_automation.base import WinCollector
from playwright_collection_script.schemas.task_schema import TaskConfig
from playwright_collection_script.schemas.result_schema import TaskSummary


class NotepadCollector(WinCollector):
    """
    记事本自动化采集器

    采集流程:
        1. 启动 notepad.exe
        2. 输入内容
        3. 保存文件 (Ctrl+S)
        4. 关闭记事本
        5. 读取保存的文件内容，作为采集结果

    适用场景:
        - 演示 Windows 控件操作
        - 测试 pywinauto 控件定位
        - 文本内容提取
    """

    collector_name = "notepad_collector"
    supported_apps = ["notepad"]
    target_exe = "notepad.exe"
    backend = "uia"
    default_ods_table = "notepad_data"

    def __init__(self):
        super().__init__()
        self._output_dir = Path(__file__).resolve().parent.parent.parent / "data" / "notepad_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._output_file = None

    def run(self, config: TaskConfig) -> TaskSummary:
        """执行记事本采集"""
        # 从配置中提取内容（如果提供的话）
        extra_params = getattr(config, 'extra_params', {}) or {}
        content = extra_params.get("content", f"RPADataHub Notepad Test\nTime: {time.strftime('%Y-%m-%d %H:%M:%S')}\n采集任务: {config.task_id}")
        filename = extra_params.get("filename", f"rpa_output_{int(time.time())}.txt")

        try:
            # 步骤1: 输入文本内容
            self._window.set_focus()
            time.sleep(0.3)
            self._window.Edit.type_keys(content, with_spaces=True)

            # 步骤2: 保存文件 (Ctrl+S → 输入文件名 → 保存)
            output_path = self._output_dir / filename
            self._window.type_keys("^s")  # Ctrl+S
            time.sleep(0.5)

            # 等待"另存为"对话框
            save_dlg = self.wait_window(title_re=".*另存为|.*Save As", timeout=10)
            if save_dlg:
                # 输入文件路径
                file_input_ctrl = save_dlg.child_window(control_type="Edit")
                file_input_ctrl.set_edit_text(str(output_path))
                time.sleep(0.3)

                # 点击保存按钮
                save_btn = save_dlg.child_window(title="保存", control_type="Button")
                if not save_btn.exists():
                    save_btn = save_dlg.child_window(title="Save", control_type="Button")
                save_btn.click()
                time.sleep(0.5)

                # 处理"文件已存在"确认
                confirm = save_dlg.child_window(title="是", control_type="Button")
                if confirm.exists():
                    confirm.click()
                    time.sleep(0.3)

            # 步骤3: 关闭记事本
            self._window.close()
            time.sleep(0.3)

            # 步骤4: 验证文件已保存，读取内容
            if output_path.exists():
                saved_content = output_path.read_text(encoding="utf-8")
                row_count = len(saved_content.strip().split("\n"))

                self.add_record(
                    shop_name="Notepad",
                    result="SUCCESS",
                    row_count=row_count,
                    duration=int(time.time() - self._start_time)
                )
            else:
                self.add_record(
                    shop_name="Notepad",
                    result="FAILED",
                    error="文件未保存成功"
                )

        except Exception as e:
            self.add_record(
                shop_name="Notepad",
                result="FAILED",
                error=str(e),
                duration=int(time.time() - self._start_time)
            )

        return self.build_summary()