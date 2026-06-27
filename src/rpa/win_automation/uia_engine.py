"""
UIAutomation 引擎 — 微软原生 UI Automation 封装
================================================
基于 uiautomation 库，提供底层控件树遍历、属性获取、事件监听
适合需要精细控制 UIA 属性、或 pywinauto 无法定位的场景

对比 pywinauto:
    - pywinauto: 更高层封装，简洁易用
    - uiautomation: 更底层，控件的每个属性都可访问，Delphi/SAP等特殊控件兼容更好
"""

import time
import logging
from typing import Optional, List, Any, Tuple
from ctypes import windll

logger = logging.getLogger("WinAuto.UIA")


class UIAEngine:
    """
    微软 UI Automation 引擎

    核心方法:
        - find_window(name): 查找窗口
        - find_control(window, **kwargs): 基于属性查找控件
        - get_control_tree(window, depth): 获取控件树
        - send_keys(control, text): 发送按键
        - invoke(control): 执行控件的默认动作（点击）
    """

    def __init__(self):
        self._uia = None

    @property
    def uia(self):
        """懒加载 uiautomation"""
        if self._uia is None:
            import uiautomation as auto
            self._uia = auto
        return self._uia

    # ============================================================
    # 窗口操作
    # ============================================================

    def find_window(self, name: str = None, class_name: str = None,
                    search_depth: int = 2, timeout: float = 30) -> Optional[Any]:
        """
        查找窗口

        Args:
            name: 窗口标题（支持正则子串匹配）
            class_name: 窗口类名
            search_depth: 搜索深度
            timeout: 等待超时

        Returns:
            uiautomation.WindowControl 对象，未找到返回 None
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            window = self.uia.WindowControl(
                searchDepth=search_depth,
                Name=name or "",
                ClassName=class_name or ""
            )
            if window.Exists(0):
                return window
            time.sleep(0.5)
        logger.warning(f"找不到窗口: name={name}, class={class_name}")
        return None

    def get_active_window(self) -> Optional[Any]:
        """获取当前活动窗口"""
        return self.uia.GetFocusedControl()

    def set_window_topmost(self, window):
        """设置窗口置顶"""
        if window:
            try:
                hwnd = window.NativeWindowHandle
                windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 3)
            except Exception as e:
                logger.warning(f"设置窗口置顶失败: {e}")

    def close_window(self, window):
        """关闭窗口"""
        if window:
            try:
                window.GetWindowPattern().Close()
            except Exception:
                pass

    def maximize_window(self, window):
        """最大化窗口"""
        if window:
            try:
                window.Maximize()
            except Exception:
                pass

    def minimize_window(self, window):
        """最小化窗口"""
        if window:
            try:
                window.Minimize()
            except Exception:
                pass

    # ============================================================
    # 控件查找
    # ============================================================

    def find_control(self, parent, control_type: str = None,
                     name: str = None, automation_id: str = None,
                     class_name: str = None, search_depth: int = 0xFFFFFFFF,
                     timeout: float = 10, wait: bool = True) -> Optional[Any]:
        """
        在父控件下查找子控件

        Args:
            parent: 父控件（WindowControl 等）
            control_type: 控件类型名，如 "Button", "Edit", "ComboBox"
            name: 控件 Name 属性
            automation_id: 控件 AutomationId
            class_name: 控件 ClassName
            search_depth: 搜索深度（默认无限）
            timeout: wait模式下等待超时
            wait: 是否等待控件出现

        Returns:
            Control 对象，未找到返回 None

        Example:
            btn = engine.find_control(window, control_type="Button", name="确定")
            edit = engine.find_control(window, control_type="Edit", automation_id="txtInput")
        """
        if not parent:
            return None

        # 构建 Control 类型
        ctrl_type_map = {
            "Button": self.uia.ButtonControl,
            "Edit": self.uia.EditControl,
            "ComboBox": self.uia.ComboBoxControl,
            "CheckBox": self.uia.CheckBoxControl,
            "RadioButton": self.uia.RadioButtonControl,
            "ListItem": self.uia.ListItemControl,
            "List": self.uia.ListControl,
            "TreeItem": self.uia.TreeItemControl,
            "Tree": self.uia.TreeControl,
            "TabItem": self.uia.TabItemControl,
            "Tab": self.uia.TabControl,
            "MenuItem": self.uia.MenuItemControl,
            "Menu": self.uia.MenuControl,
            "DataGrid": self.uia.DataGridControl,
            "DataItem": self.uia.DataItemControl,
            "Header": self.uia.HeaderControl,
            "HeaderItem": self.uia.HeaderItemControl,
            "Text": self.uia.TextControl,
            "Hyperlink": self.uia.HyperlinkControl,
            "Image": self.uia.ImageControl,
            "Document": self.uia.DocumentControl,
            "Pane": self.uia.PaneControl,
            "Group": self.uia.GroupControl,
            "ToolBar": self.uia.ToolBarControl,
            "ScrollBar": self.uia.ScrollBarControl,
            "StatusBar": self.uia.StatusBarControl,
            "SplitButton": self.uia.SplitButtonControl,
            "Separator": self.uia.SeparatorControl,
        }

        ctrl_cls = ctrl_type_map.get(control_type, self.uia.Control)
        condition = {}

        # 构建条件字典（使用更精确的 ControlCondition）
        try:
            condition = self.uia.ControlCondition(
                Name=name or "",
                AutomationId=automation_id or "",
                ClassName=class_name or ""
            )
        except Exception:
            # 降级为逐个参数过滤
            pass

        if wait:
            # 等待控件出现
            try:
                ctrl = parent.Control(
                    control_cls, condition,
                    searchDepth=search_depth
                )
                if ctrl.Exists(timeout):
                    return ctrl
            except Exception:
                pass
        else:
            # 直接查找
            try:
                ctrl = parent.Control(control_cls, searchDepth=search_depth)
                if ctrl.Exists(0):
                    return ctrl
            except Exception:
                pass

        return None

    def find_all_controls(self, parent, control_type: str = None,
                          name: str = None, search_depth: int = 0xFFFFFFFF,
                          max_count: int = 100) -> List[Any]:
        """查找所有匹配的控件"""
        results = []
        if not parent:
            return results

        try:
            all_children = parent.GetChildren()
            for child in all_children:
                if control_type and child.ControlTypeName != control_type:
                    continue
                if name and name not in child.Name:
                    continue
                results.append(child)
                if len(results) >= max_count:
                    break
        except Exception as e:
            logger.error(f"查找子控件失败: {e}")

        return results

    # ============================================================
    # 控件操作
    # ============================================================

    def click(self, control) -> bool:
        """点击控件"""
        if control:
            try:
                control.Click()
                return True
            except Exception as e:
                logger.error(f"点击失败: {e}")
        return False

    def double_click(self, control) -> bool:
        """双击控件"""
        if control:
            try:
                control.DoubleClick()
                return True
            except Exception as e:
                logger.error(f"双击失败: {e}")
        return False

    def right_click(self, control) -> bool:
        """右键点击控件"""
        if control:
            try:
                control.RightClick()
                return True
            except Exception as e:
                logger.error(f"右键点击失败: {e}")
        return False

    def invoke(self, control) -> bool:
        """调用控件的 Invoke 模式（等价于点击按钮）"""
        if control:
            try:
                inv_pattern = control.GetInvokePattern()
                if inv_pattern:
                    inv_pattern.Invoke()
                    return True
            except Exception:
                pass
        return False

    def send_keys(self, control, text: str, clear_first: bool = True) -> bool:
        """
        向控件发送文本

        Args:
            control: EditControl 等可输入控件
            text: 文本内容
            clear_first: 是否先清除已有内容
        """
        if control:
            try:
                # 先聚焦
                control.SetFocus()
                time.sleep(0.1)

                if clear_first:
                    # 获取 ValuePattern 尝试清空
                    try:
                        value_pattern = control.GetValuePattern()
                        if value_pattern:
                            value_pattern.SetValue("")
                    except Exception:
                        control.SendKeys("{Ctrl}a{Delete}")

                control.SendKeys(text)
                return True
            except Exception as e:
                logger.error(f"发送按键失败: {e}")
        return False

    def get_value(self, control) -> str:
        """获取控件的值（文本内容）"""
        if control:
            try:
                value_pattern = control.GetValuePattern()
                if value_pattern:
                    return value_pattern.Value or ""
            except Exception:
                pass
            try:
                return control.Name or ""
            except Exception:
                pass
        return ""

    def set_value(self, control, value: str) -> bool:
        """设置控件的值（适用于 ValuePattern 控件）"""
        if control:
            try:
                value_pattern = control.GetValuePattern()
                if value_pattern:
                    value_pattern.SetValue(value)
                    return True
            except Exception as e:
                logger.error(f"设置值失败: {e}")
        return False

    def select_item(self, combo_or_list, item_name: str) -> bool:
        """
        在下拉框/列表中选择指定项

        Args:
            combo_or_list: ComboBox或List控件
            item_name: 要选择的项名称
        """
        if not combo_or_list:
            return False
        try:
            # 展开下拉
            try:
                expand_pattern = combo_or_list.GetExpandCollapsePattern()
                if expand_pattern:
                    expand_pattern.Expand()
                    time.sleep(0.3)
            except Exception:
                pass

            # 查找目标项
            items = combo_or_list.GetChildren()
            for item in items:
                if item_name in item.Name:
                    self.click(item)
                    return True

            # 尝试通过 SelectionItem 选中
            for item in items:
                try:
                    sel_pattern = item.GetSelectionItemPattern()
                    if sel_pattern and item_name in item.Name:
                        sel_pattern.Select()
                        return True
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"选择列表项失败: {e}")
        return False

    def scroll_to_bottom(self, control) -> bool:
        """滚动到底部"""
        if control:
            try:
                scroll_pattern = control.GetScrollPattern()
                if scroll_pattern:
                    scroll_pattern.SetScrollPercent(-1, 100)
                    return True
            except Exception:
                pass

            # 降级方案：发送End键
            try:
                control.SetFocus()
                control.SendKeys("{End}")
                return True
            except Exception:
                pass
        return False

    # ============================================================
    # 控件树遍历
    # ============================================================

    def get_control_tree(self, control, max_depth: int = 3,
                         current_depth: int = 0) -> List[dict]:
        """
        获取控件树结构（用于调试）

        Returns:
            [{"name": "...", "type": "...", "children": [...]}]
        """
        if current_depth >= max_depth or not control:
            return []

        result = []
        try:
            children = control.GetChildren()
            for child in children:
                node = {
                    "name": child.Name,
                    "type": child.ControlTypeName,
                    "class": child.ClassName,
                    "automation_id": child.AutomationId,
                    "rect": child.BoundingRectangle,
                    "children": self.get_control_tree(
                        child, max_depth, current_depth + 1
                    )
                }
                result.append(node)
        except Exception:
            pass
        return result

    def dump_control_tree(self, control, indent: int = 0):
        """打印控件树到日志"""
        if not control:
            return
        prefix = "  " * indent
        try:
            name = control.Name
            ctype = control.ControlTypeName
            aid = control.AutomationId
            logger.debug(f"{prefix}├─ [{ctype}] name='{name}' id='{aid}'")
            for child in control.GetChildren():
                self.dump_control_tree(child, indent + 1)
        except Exception:
            pass

    # ============================================================
    # 高级查找
    # ============================================================

    def find_by_text(self, parent, text: str,
                     partial: bool = True, timeout: float = 10) -> Optional[Any]:
        """
        遍历所有控件，查找包含指定文本的控件

        Args:
            parent: 父控件
            text: 要查找的文本
            partial: 是否部分匹配
            timeout: 超时

        Returns:
            第一个匹配控件
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                children = parent.GetChildren()
                for child in children:
                    if partial and text in child.Name:
                        return child
                    if not partial and child.Name == text:
                        return child
            except Exception:
                pass
            time.sleep(0.5)
        return None

    def find_by_automation_id(self, parent, automation_id: str,
                              timeout: float = 10) -> Optional[Any]:
        """通过 AutomationId 查找控件"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                control = parent.Control(
                    self.uia.Control,
                    self.uia.ControlCondition(AutomationId=automation_id),
                    searchDepth=0xFFFFFFFF
                )
                if control.Exists(0):
                    return control
            except Exception:
                pass
            time.sleep(0.5)
        return None

    # ============================================================
    # 等待与状态
    # ============================================================

    def wait_for_control(self, parent, control_type: str = None,
                         name: str = None, automation_id: str = None,
                         timeout: float = 30) -> Optional[Any]:
        """等待控件出现"""
        return self.find_control(parent, control_type, name, automation_id,
                                 timeout=timeout, wait=True)

    def wait_for_control_disappear(self, parent, control_type: str = None,
                                   name: str = None, timeout: float = 30) -> bool:
        """等待控件消失"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ctrl = self.find_control(parent, control_type, name, wait=False)
            if not ctrl:
                return True
            time.sleep(0.5)
        return False

    def wait_for_window_close(self, name: str, timeout: float = 30) -> bool:
        """等待窗口关闭"""
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                w = self.uia.WindowControl(searchDepth=1, Name=name)
                if not w.Exists(0):
                    return True
            except Exception:
                return True
            _time.sleep(0.5)
        return False

    def is_control_enabled(self, control) -> bool:
        """检查控件是否可用"""
        if control:
            try:
                return control.IsEnabled
            except Exception:
                pass
        return False

    def get_bounding_rect(self, control) -> Optional[Tuple[int, int, int, int]]:
        """获取控件边界矩形 (left, top, right, bottom)"""
        if control:
            try:
                return control.BoundingRectangle
            except Exception:
                pass
        return None

    def get_center_point(self, control) -> Optional[Tuple[int, int]]:
        """获取控件中心坐标"""
        rect = self.get_bounding_rect(control)
        if rect:
            return ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
        return None