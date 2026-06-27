"""
OCR 引擎 — 文字识别与定位
==========================
支持 PaddleOCR（首选，中文识别强）和 Tesseract（轻量备选）
注意：此引擎内部使用 pyautogui，不依赖应用句柄，可用于远程桌面/VM等无控件场景
"""

import os
import io
import time
import logging
from pathlib import Path
from typing import Optional, List, Tuple

import pyautogui
from PIL import Image

logger = logging.getLogger("WinAuto.OCR")


class OCREngine:
    """
    OCR 文字识别引擎

    双引擎策略:
        - PaddleOCR: 中文识别优秀，适合中英文混合场景
        - Tesseract: 轻量，适合纯英文短文本

    核心方法:
        - find_text(text, region): 在屏幕上查找文字位置
        - read_region(region): 读取指定区域全部文字
        - read_fullscreen(): 读取全屏文字
    """

    def __init__(self):
        self._paddle = None
        self._tesseract = None
        self._primary = self._detect_engine()
        self._screenshot_dir = Path(__file__).resolve().parent.parent.parent / "data" / "ocr_screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    def _detect_engine(self) -> str:
        """自动检测可用引擎"""
        try:
            from paddleocr import PaddleOCR
            PaddleOCR(lang='ch', show_log=False)
            logger.info("OCR引擎: PaddleOCR (主)")
            return "paddle"
        except Exception:
            logger.info("PaddleOCR不可用，使用 Tesseract (备选)")
            return "tesseract"

    @property
    def paddle(self):
        """懒加载 PaddleOCR"""
        if self._paddle is None and self._primary == "paddle":
            try:
                from paddleocr import PaddleOCR
                self._paddle = PaddleOCR(lang='ch', show_log=False, use_angle_cls=True)
            except Exception as e:
                logger.warning(f"PaddleOCR加载失败: {e}，降级为Tesseract")
                self._primary = "tesseract"
        return self._paddle

    @property
    def tesseract(self):
        """懒加载 Tesseract"""
        if self._tesseract is None:
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                self._tesseract = pytesseract
            except Exception:
                logger.warning("Tesseract未安装或未配置路径")
        return self._tesseract

    def find_text(self, text: str, region: tuple = None,
                  confidence: float = 0.7) -> Optional[tuple]:
        """
        在屏幕上查找文字，返回 (center_x, center_y)

        Args:
            text: 要查找的文字
            region: (left, top, width, height) 搜索区域
            confidence: 最低置信度

        Returns:
            (x, y) 文字中心坐标，未找到返回 None
        """
        screenshot = self._screenshot(region)
        if screenshot is None:
            return None

        if self._primary == "paddle" and self.paddle:
            return self._find_with_paddle(screenshot, text, confidence)
        elif self.tesseract:
            return self._find_with_tesseract(screenshot, text, confidence)

        return None

    def read_region(self, region: tuple) -> str:
        """
        读取指定区域的文字

        Args:
            region: (left, top, width, height)

        Returns:
            识别出的全部文字
        """
        screenshot = self._screenshot(region)
        if screenshot is None:
            return ""

        if self._primary == "paddle" and self.paddle:
            return self._read_with_paddle(screenshot)
        elif self.tesseract:
            return self._read_with_tesseract(screenshot)

        return ""

    def read_fullscreen(self) -> str:
        """读取全屏文字"""
        screenshot = pyautogui.screenshot()
        if self._primary == "paddle" and self.paddle:
            return self._read_with_paddle(screenshot)
        elif self.tesseract:
            return self._read_with_tesseract(screenshot)
        return ""

    def wait_for_text(self, text: str, timeout: float = 30,
                      interval: float = 0.5, region: tuple = None) -> Optional[tuple]:
        """
        等待文字出现（轮询）

        Args:
            text: 等待的文字
            timeout: 超时秒数
            interval: 轮询间隔
            region: 搜索区域

        Returns:
            (x, y) 坐标，超时返回 None
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            pos = self.find_text(text, region)
            if pos:
                return pos
            time.sleep(interval)
        logger.warning(f"等待文字超时: '{text}' ({timeout}s)")
        return None

    # ============================================================
    # 内部方法
    # ============================================================

    def _screenshot(self, region: tuple = None) -> Optional[Image.Image]:
        """截图"""
        try:
            if region:
                return pyautogui.screenshot(region=region)
            return pyautogui.screenshot()
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    def _find_with_paddle(self, img: Image.Image, text: str,
                          confidence: float) -> Optional[tuple]:
        """PaddleOCR 查找文字"""
        try:
            # 转为 numpy 数组
            import numpy as np
            img_np = np.array(img)

            results = self.paddle.ocr(img_np, cls=True)
            if not results or not results[0]:
                return None

            for line in results[0]:
                box = line[0]          # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                txt = line[1][0]       # 识别文字
                conf = line[1][1]      # 置信度

                if text in txt and conf >= confidence:
                    # 计算中心坐标
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    return (sum(xs) / 4, sum(ys) / 4)

            return None
        except Exception as e:
            logger.error(f"PaddleOCR查找失败: {e}")
            return None

    def _find_with_tesseract(self, img: Image.Image, text: str,
                             confidence: float) -> Optional[tuple]:
        """Tesseract 查找文字"""
        try:
            import pytesseract
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            for i, word in enumerate(data['text']):
                if text in word and int(data['conf'][i]) >= confidence * 100:
                    x = data['left'][i] + data['width'][i] // 2
                    y = data['top'][i] + data['height'][i] // 2
                    return (x, y)
            return None
        except Exception as e:
            logger.error(f"Tesseract查找失败: {e}")
            return None

    def _read_with_paddle(self, img: Image.Image) -> str:
        """PaddleOCR 读取全部文字"""
        try:
            import numpy as np
            img_np = np.array(img)
            results = self.paddle.ocr(img_np, cls=True)
            if not results or not results[0]:
                return ""
            lines = [line[1][0] for line in results[0]]
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"PaddleOCR读取失败: {e}")
            return ""

    def _read_with_tesseract(self, img: Image.Image) -> str:
        """Tesseract 读取全部文字"""
        try:
            return self.tesseract.image_to_string(img, lang='chi_sim+eng')
        except Exception as e:
            logger.error(f"Tesseract读取失败: {e}")
            return ""

    def extract_table(self, region: tuple) -> List[List[str]]:
        """
        提取区域内的表格数据（尝试解析行列结构）

        Returns:
            [[cell11, cell12], [cell21, cell22], ...]
        """
        text = self.read_region(region)
        lines = text.strip().split("\n")
        # 简单的按空格/tab分割
        table = []
        for line in lines:
            cells = [c.strip() for c in line.split() if c.strip()]
            if cells:
                table.append(cells)
        return table