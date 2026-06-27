"""
计算器采集器 — 演示简单 Win 应用自动化
=======================================
打开 Windows 计算器 → 执行运算 → 读取结果 → 关闭
"""

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from win_automation.base import WinCollector
from playwright_collection_script.schemas.task_schema import TaskConfig
from playwright_collection_script.schemas.result_schema import TaskSummary


class CalculatorCollector(WinCollector):
    """
    Windows 计算器自动化采集器

    采集流程:
        1. 启动 calc.exe
        2. 执行指定的算术运算
        3. 读取计算结果
        4. 关闭计算器

    适用场景:
        - 演示控件级自动化
        - 数据验证（用计算器交叉验证）
        - 财务数据核验
    """

    collector_name = "calculator_collector"
    supported_apps = ["calculator", "calc"]
    target_exe = "calc.exe"
    backend = "uia"
    default_ods_table = "calculator_data"

    def run(self, config: TaskConfig) -> TaskSummary:
        """执行计算器采集"""
        extra_params = getattr(config, 'extra_params', {}) or {}
        expression = extra_params.get("expression")  # e.g., "2+3*4-1"
        operations = extra_params.get("operations", [])

        try:
            time.sleep(1.5)  # 等待计算器完全加载
            self._window.set_focus()

            if expression:
                # 输入完整表达式
                self._do_expression(expression)
            elif operations:
                # 逐步执行操作序列
                for op in operations:
                    self._do_operation(op)

            # 读取结果
            result_text = self._get_result()

            if result_text:
                self.add_record(
                    shop_name="Calculator",
                    result="SUCCESS",
                    row_count=1,
                    duration=int(time.time() - self._start_time)
                )
                # 将结果存储为额外数据
                self._last_result = result_text
            else:
                self.add_record(
                    shop_name="Calculator",
                    result="NO_DATA",
                    row_count=0,
                    duration=int(time.time() - self._start_time)
                )

        except Exception as e:
            self.add_record(
                shop_name="Calculator",
                result="FAILED",
                error=str(e),
                duration=int(time.time() - self._start_time)
            )

        return self.build_summary()

    def _do_expression(self, expr: str):
        """输入完整表达式"""
        # 映射到计算器按钮
        for char in expr:
            self._press_key(char)
            time.sleep(0.05)

    def _do_operation(self, op: dict):
        """执行单个操作"""
        op_type = op.get("type", "key")
        value = op.get("value", "")

        if op_type == "key":
            self._press_key(value)
        elif op_type == "wait":
            time.sleep(float(value))

    def _press_key(self, key: str):
        """按下计算器按键"""
        # 直接使用键盘发送，计算器支持键盘输入
        self._window.type_keys(key, pause=0.05)

    def _get_result(self) -> str:
        """获取计算结果"""
        # 尝试从显示区域获取
        try:
            # 计算器显示区域的控件
            result_ctrl = self._window.child_window(auto_id="CalculatorResults")
            if result_ctrl.exists():
                return result_ctrl.window_text()
        except Exception:
            pass

        try:
            # 备选：查找 TextBlock 类型控件
            from time import sleep
            children = self._window.children()
            for child in children:
                try:
                    text = child.window_text()
                    if text and any(c.isdigit() for c in text) and len(text) <= 30:
                        return text.replace("显示为", "").strip()
                except Exception:
                    continue
        except Exception:
            pass

        try:
            # 截图OCR读取
            result_text = self.read_text_from_region(
                self._window.rectangle()
            )
            return result_text.strip() if result_text else ""
        except Exception:
            pass

        return ""