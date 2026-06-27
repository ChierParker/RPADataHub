"""
统一流程引擎 — Flow Engine
============================
基于 YAML/JSON 配置的流程解释执行器，支持:
    - 浏览器操作 (Playwright)
    - Windows 应用操作 (pywinauto / uiautomation)
    - OCR 文字识别与点击
    - 图像模板匹配与点击
    - 逻辑控制 (if / loop / wait)
    - 数据提取与导出

配置格式 (YAML):
```yaml
name: "混合流程示例"
steps:
  - open_app: {path: "notepad.exe", backend: "uia"}
  - wait: {seconds: 2}
  - input: {target: "Edit", value: "Hello RPA"}
  - browser_open: {url: "https://example.com"}
  - browser_click: {selector: "#btn"}
  - ocr_click: {text: "提交", confidence: 0.8}
  - image_click: {template: "btn_ok.png", confidence: 0.8}
  - extract_table: {region: [0, 100, 800, 600]}
  - export_excel: {path: "result.xlsx"}
```
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Any, Dict, List

logger = logging.getLogger("WinAuto.Flow")


class FlowEngine:
    """
    流程引擎 — 解释执行 YAML/JSON 流程配置

    支持的步骤类型 (steps):
        # Windows 应用
        - open_app:   启动 Windows 应用
        - close_app:  关闭应用
        - click:      点击按钮/控件
        - input:      输入文本
        - get_text:   获取控件文本
        - select_menu:选择菜单
        - wait_window:等待窗口出现

        # 浏览器
        - browser_open:   打开URL
        - browser_click:  点击元素
        - browser_input:  输入文本
        - browser_get_text:获取页面文本
        - browser_wait:   等待元素/时间

        # OCR
        - ocr_click:      识别文字并点击
        - ocr_read:       读取区域文字
        - ocr_wait_text:  等待文字出现
        - ocr_extract_table: 提取表格

        # 图像识别
        - image_click:        找到图像并点击
        - image_wait:         等待图像出现
        - image_check:        检查图像是否可见

        # 逻辑控制
        - wait:      等待N秒
        - if:        条件判断
        - loop:      循环
        - screenshot:截图

        # 数据
        - extract_table:  提取表格数据
        - export_excel:   导出Excel
        - export_csv:     导出CSV
        - send_mail:      发送邮件
    """

    def __init__(self, log_dir: str = None):
        self._app = None
        self._window = None
        self._browser = None
        self._page = None
        self._ocr = None
        self._image = None
        self._data = {}         # 步骤间共享数据
        self._variables = {}    # 流程变量

        self._log_dir = Path(log_dir) if log_dir else (
            Path(__file__).resolve().parent.parent.parent / "data" / "flow_logs"
        )
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # 主入口
    # ============================================================

    def execute(self, config: dict) -> dict:
        """
        执行流程配置

        Args:
            config: 流程配置字典，或 YAML/JSON 文件路径

        Returns:
            {"success": bool, "steps_executed": int, "errors": [...], "data": {...}}
        """
        # 如果是文件路径，加载
        if isinstance(config, str):
            config = self._load_config(config)

        name = config.get("name", "Unnamed Flow")
        steps = config.get("steps", [])
        self._variables = config.get("variables", {})

        logger.info(f"开始流程: {name} ({len(steps)} 步骤)")

        result = {
            "success": True,
            "flow_name": name,
            "steps_executed": 0,
            "steps_failed": 0,
            "errors": [],
            "data": {},
        }

        try:
            for i, step in enumerate(steps):
                step_name = step.get("_name", list(step.keys())[0] if step else f"step_{i}")
                logger.info(f"  [{i+1}/{len(steps)}] {step_name}")

                try:
                    output = self._execute_step(step)
                    if output is not None:
                        self._data[step_name] = output
                    result["steps_executed"] += 1
                except Exception as e:
                    logger.error(f"  步骤失败 [{step_name}]: {e}", exc_info=True)
                    result["steps_failed"] += 1
                    result["errors"].append({
                        "step": i + 1,
                        "name": step_name,
                        "error": str(e)
                    })

                    # 检查是否允许继续
                    on_error = step.get("on_error", "stop")
                    if on_error == "stop":
                        result["success"] = False
                        break
                    elif on_error == "continue":
                        continue
                    elif on_error == "retry":
                        retries = step.get("retry", 3)
                        for attempt in range(retries):
                            try:
                                logger.info(f"  重试 {attempt+1}/{retries}")
                                self._execute_step(step)
                                break
                            except Exception:
                                if attempt == retries - 1:
                                    result["success"] = False
                                    raise
                                time.sleep(1)

        finally:
            self._cleanup()

        result["data"] = self._data
        logger.info(
            f"流程结束: {name} — 成功{result['steps_executed']}/{len(steps)} "
            f"失败{result['steps_failed']}"
        )
        return result

    # ============================================================
    # 步骤分发
    # ============================================================

    def _execute_step(self, step: dict) -> Optional[Any]:
        """根据步骤类型分发执行"""
        for action, params in step.items():
            if action.startswith("_"):
                continue  # 跳过元数据字段

            method = self._get_handler(action)
            if method is None:
                logger.warning(f"未知步骤类型: {action}")
                return None

            if params is None:
                return method()
            elif isinstance(params, dict):
                # 替换变量 {{var}}
                params = self._resolve_vars(params)
                return method(**params)
            else:
                return method(params)
        return None

    def _get_handler(self, action: str):
        """获取步骤处理方法"""
        handlers = {
            # Windows
            "open_app": self._do_open_app,
            "close_app": self._do_close_app,
            "click": self._do_click,
            "double_click": self._do_double_click,
            "input": self._do_input,
            "get_text": self._do_get_text,
            "select_menu": self._do_select_menu,
            "wait_window": self._do_wait_window,
            "send_keys": self._do_send_keys,

            # Browser
            "browser_open": self._do_browser_open,
            "browser_click": self._do_browser_click,
            "browser_input": self._do_browser_input,
            "browser_get_text": self._do_browser_get_text,
            "browser_wait": self._do_browser_wait,
            "browser_screenshot": self._do_browser_screenshot,
            "browser_close": self._do_browser_close,

            # OCR
            "ocr_click": self._do_ocr_click,
            "ocr_read": self._do_ocr_read,
            "ocr_wait_text": self._do_ocr_wait_text,
            "ocr_extract_table": self._do_ocr_extract_table,

            # Image
            "image_click": self._do_image_click,
            "image_wait": self._do_image_wait,
            "image_check": self._do_image_check,
            "image_find": self._do_image_find,

            # Logic
            "wait": self._do_wait,
            "screenshot": self._do_screenshot,
            "set_var": self._do_set_var,
            "print": self._do_print,

            # Data
            "extract_table": self._do_extract_table,
            "export_excel": self._do_export_excel,
            "export_csv": self._do_export_csv,
        }
        return handlers.get(action)

    # ============================================================
    # Windows 步骤
    # ============================================================

    def _do_open_app(self, path: str, backend: str = "uia",
                     connect_title: str = ".*", timeout: int = 30):
        """启动 Windows 应用"""
        from pywinauto import Application
        self._app = Application(backend=backend).start(path)
        time.sleep(2)
        self._window = self._app.window(title_re=connect_title)
        self._window.wait("visible", timeout=timeout)
        logger.info(f"应用已启动: {path}")
        return self._window

    def _do_close_app(self):
        """关闭应用"""
        if self._app:
            self._app.kill()
            self._app = None
            self._window = None

    def _do_click(self, name: str, control_type: str = "Button", timeout: int = 10):
        """点击控件"""
        self._ensure_window()
        ctrl = self._window.child_window(title=name, control_type=control_type)
        ctrl.wait("enabled", timeout=timeout)
        ctrl.click()
        logger.info(f"点击: [{control_type}] {name}")

    def _do_double_click(self, name: str, control_type: str = "ListItem",
                         timeout: int = 10):
        """双击控件"""
        self._ensure_window()
        ctrl = self._window.child_window(title=name, control_type=control_type)
        ctrl.wait("enabled", timeout=timeout)
        ctrl.double_click()

    def _do_input(self, value: str, target: str = "Edit",
                  control_name: str = None, timeout: int = 10):
        """输入文本"""
        self._ensure_window()
        if control_name:
            ctrl = self._window.child_window(title=control_name, control_type=target)
        else:
            ctrl = self._window.child_window(control_type=target)
        ctrl.wait("enabled", timeout=timeout)
        ctrl.type_keys(value, with_spaces=True)
        logger.info(f"输入: '{value[:50]}...' -> [{target}]")

    def _do_get_text(self, target: str = "Edit", control_name: str = None,
                     timeout: int = 10) -> str:
        """获取控件文本"""
        self._ensure_window()
        if control_name:
            ctrl = self._window.child_window(title=control_name, control_type=target)
        else:
            ctrl = self._window.child_window(control_type=target)
        ctrl.wait("visible", timeout=timeout)
        return ctrl.window_text()

    def _do_select_menu(self, path: list, timeout: int = 10):
        """选择菜单"""
        self._ensure_window()
        self._window.menu_select(" -> ".join(path))

    def _do_wait_window(self, title_re: str, timeout: int = 30):
        """等待窗口出现"""
        self._ensure_app()
        return self._app.window(title_re=title_re).wait("visible", timeout=timeout)

    def _do_send_keys(self, keys: str, pause: float = 0.05):
        """发送全局快捷键"""
        import pyautogui
        pyautogui.typewrite(keys, interval=pause)

    # ============================================================
    # 浏览器步骤
    # ============================================================

    def _get_browser(self):
        """懒加载浏览器"""
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=False)
            self._page = self._browser.new_page()
        return self._page

    def _do_browser_open(self, url: str, wait_until: str = "networkidle"):
        """打开网页"""
        page = self._get_browser()
        page.goto(url, wait_until=wait_until)
        logger.info(f"打开: {url}")

    def _do_browser_click(self, selector: str, timeout: int = 30000):
        """点击页面元素"""
        page = self._get_browser()
        page.click(selector, timeout=timeout)
        logger.info(f"点击: {selector}")

    def _do_browser_input(self, selector: str, value: str, clear: bool = True,
                          timeout: int = 30000):
        """输入文本"""
        page = self._get_browser()
        if clear:
            page.fill(selector, value, timeout=timeout)
        else:
            page.type(selector, value, timeout=timeout)
        logger.info(f"输入: '{value[:50]}' -> {selector}")

    def _do_browser_get_text(self, selector: str, timeout: int = 10000) -> str:
        """获取页面元素文本"""
        page = self._get_browser()
        return page.text_content(selector, timeout=timeout) or ""

    def _do_browser_wait(self, selector: str = None, seconds: int = 1,
                         timeout: int = 30000):
        """等待元素或时间"""
        if selector:
            page = self._get_browser()
            page.wait_for_selector(selector, timeout=timeout)
        else:
            time.sleep(seconds)

    def _do_browser_screenshot(self, path: str = None) -> str:
        """浏览器截图"""
        page = self._get_browser()
        if not path:
            path = str(self._log_dir / f"browser_{int(time.time())}.png")
        page.screenshot(path=path)
        return path

    def _do_browser_close(self):
        """关闭浏览器"""
        if self._browser:
            self._browser.close()
            self._browser = None
            self._page = None

    # ============================================================
    # OCR 步骤
    # ============================================================

    @property
    def _ocr_engine(self):
        if self._ocr is None:
            from .ocr_engine import OCREngine
            self._ocr = OCREngine()
        return self._ocr

    def _do_ocr_click(self, text: str, confidence: float = 0.7,
                      region: list = None, offset_x: int = 0, offset_y: int = 0):
        """OCR识别文字并点击"""
        import pyautogui
        reg = tuple(region) if region else None
        pos = self._ocr_engine.wait_for_text(text, timeout=10, region=reg)
        if pos is None:
            raise RuntimeError(f"OCR未找到文字: '{text}'")
        x, y = pos[0] + offset_x, pos[1] + offset_y
        pyautogui.click(x, y)
        logger.info(f"OCR点击: '{text}' @ ({x}, {y})")

    def _do_ocr_read(self, region: list = None) -> str:
        """OCR读取区域文字"""
        reg = tuple(region) if region else None
        return self._ocr_engine.read_region(reg) if reg else self._ocr_engine.read_fullscreen()

    def _do_ocr_wait_text(self, text: str, timeout: int = 30,
                          region: list = None):
        """等待文字出现"""
        reg = tuple(region) if region else None
        pos = self._ocr_engine.wait_for_text(text, timeout=timeout, region=reg)
        if pos is None:
            raise RuntimeError(f"等待文字超时: '{text}' ({timeout}s)")
        return pos

    def _do_ocr_extract_table(self, region: list) -> list:
        """OCR提取表格"""
        reg = tuple(region) if region else None
        return self._ocr_engine.extract_table(reg)

    # ============================================================
    # 图像识别步骤
    # ============================================================

    @property
    def _image_engine(self):
        if self._image is None:
            from .image_engine import ImageEngine
            self._image = ImageEngine()
        return self._image

    def _do_image_click(self, template: str, confidence: float = 0.8,
                        region: list = None, multiscale: bool = False):
        """图像识别并点击"""
        import pyautogui
        reg = tuple(region) if region else None

        if multiscale:
            result = self._image_engine.find_template_multiscale(
                template, confidence=confidence, region=reg
            )
            pos = result[:2] if result else None
        else:
            pos = self._image_engine.wait_for_template(
                template, timeout=10, confidence=confidence, region=reg
            )

        if pos is None:
            raise RuntimeError(f"图像未找到: {template}")
        pyautogui.click(pos)
        logger.info(f"图像点击: {template} @ ({pos[0]}, {pos[1]})")

    def _do_image_wait(self, template: str, timeout: int = 30,
                       confidence: float = 0.8, region: list = None):
        """等待图像出现"""
        reg = tuple(region) if region else None
        pos = self._image_engine.wait_for_template(
            template, timeout=timeout, confidence=confidence, region=reg
        )
        if pos is None:
            raise RuntimeError(f"等待图像超时: {template}")
        return pos

    def _do_image_check(self, template: str, confidence: float = 0.8,
                        region: list = None) -> bool:
        """检查图像是否可见"""
        reg = tuple(region) if region else None
        return self._image_engine.is_visible(template, confidence, reg)

    def _do_image_find(self, template: str, confidence: float = 0.8,
                       region: list = None) -> list:
        """查找图像位置（可多个）"""
        reg = tuple(region) if region else None
        return self._image_engine.find_all_templates(template, confidence, reg)

    # ============================================================
    # 逻辑步骤
    # ============================================================

    def _do_wait(self, seconds: float = 1):
        """等待"""
        time.sleep(seconds)

    def _do_screenshot(self, path: str = None, region: list = None):
        """截图"""
        import pyautogui
        reg = tuple(region) if region else None
        if not path:
            path = str(self._log_dir / f"screenshot_{int(time.time())}.png")
        img = pyautogui.screenshot(region=reg)
        img.save(path)
        logger.info(f"截图已保存: {path}")
        return path

    def _do_set_var(self, name: str, value):
        """设置变量"""
        self._variables[name] = value

    def _do_print(self, message: str):
        """打印消息"""
        logger.info(f"[Flow] {message}")

    # ============================================================
    # 数据步骤
    # ============================================================

    def _do_extract_table(self, region: list) -> list:
        """提取表格数据（使用OCR）"""
        import pyautogui
        reg = tuple(region) if region else (0, 0, *pyautogui.size())
        return self._ocr_engine.extract_table(reg)

    def _do_export_excel(self, data_key: str = None, path: str = "output.xlsx",
                         data: list = None):
        """导出数据到Excel"""
        import pandas as pd

        if data_key and data_key in self._data:
            data = self._data[data_key]
        elif data is None:
            data = list(self._data.values())

        if not data:
            logger.warning("无数据可导出")
            return

        # 尝试智能转换
        if isinstance(data, list):
            if data and isinstance(data[0], dict):
                df = pd.DataFrame(data)
            elif data and isinstance(data[0], list):
                df = pd.DataFrame(data[1:], columns=data[0] if data[0] else None)
            else:
                df = pd.DataFrame({"value": data})
        else:
            df = pd.DataFrame({"data": [data]})

        output = Path(path)
        df.to_excel(output, index=False)
        logger.info(f"数据已导出: {output} ({len(df)} 行)")
        return str(output)

    def _do_export_csv(self, data_key: str = None, path: str = "output.csv",
                       data: list = None):
        """导出数据到CSV"""
        import pandas as pd

        if data_key and data_key in self._data:
            data = self._data[data_key]
        elif data is None:
            data = list(self._data.values())

        if not data:
            logger.warning("无数据可导出")
            return

        if isinstance(data, list):
            if data and isinstance(data[0], dict):
                df = pd.DataFrame(data)
            elif data and isinstance(data[0], list):
                df = pd.DataFrame(data[1:], columns=data[0])
            else:
                df = pd.DataFrame({"value": data})
        else:
            df = pd.DataFrame({"data": [data]})

        output = Path(path)
        df.to_csv(output, index=False, encoding="utf-8-sig")
        logger.info(f"数据已导出: {output} ({len(df)} 行)")
        return str(output)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _ensure_app(self):
        if not self._app:
            raise RuntimeError("未启动应用")

    def _ensure_window(self):
        self._ensure_app()
        if not self._window:
            raise RuntimeError("未连接到窗口")

    def _resolve_vars(self, params: dict) -> dict:
        """替换参数中的 {{var}} 变量"""
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and "{{" in v:
                for var_name, var_val in self._variables.items():
                    v = v.replace(f"{{{{{var_name}}}}}", str(var_val))
            resolved[k] = v
        return resolved

    def _load_config(self, path: str) -> dict:
        """加载 YAML 或 JSON 配置文件"""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(p, "r", encoding="utf-8") as f:
            if p.suffix in (".yaml", ".yml"):
                try:
                    import yaml
                    return yaml.safe_load(f)
                except ImportError:
                    raise ImportError("PyYAML未安装，无法解析YAML配置")
            elif p.suffix == ".json":
                return json.load(f)
            else:
                raise ValueError(f"不支持的配置格式: {p.suffix}")

    def _cleanup(self):
        """清理资源"""
        # 关闭浏览器
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._page = None

        # 关闭 Windows 应用（默认不关闭，由 close_app 步骤控制）
        # 可在配置中设置 auto_close: true 启用