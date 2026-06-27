"""
图像识别引擎 — 模板匹配 + 区域检测
====================================
基于 OpenCV 的模板匹配，用于无控件场景（Citrix/VMware/老ERP/远程桌面）
支持灰度匹配、多尺度匹配、截图比对
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, List

import cv2
import numpy as np
import pyautogui
from PIL import Image

logger = logging.getLogger("WinAuto.Image")


class ImageEngine:
    """
    OpenCV 图像识别引擎

    核心方法:
        - find_template(path, confidence): 在屏幕上查找模板图像
        - find_all_templates(path, confidence): 查找所有匹配位置
        - wait_for_template(path, timeout): 轮询等待模板出现
        - is_visible(path): 判断图像是否可见
    """

    def __init__(self, template_dir: str = None):
        self.template_dir = Path(template_dir) if template_dir else (
            Path(__file__).resolve().parent.parent / "templates" / "images"
        )
        self.template_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # 公共 API
    # ============================================================

    def find_template(self, template_path: str, confidence: float = 0.8,
                      region: tuple = None, grayscale: bool = True) -> Optional[Tuple[int, int]]:
        """
        在屏幕上查找模板图像位置，返回中心坐标

        Args:
            template_path: 模板图片路径（相对template_dir或绝对路径）
            confidence: 匹配置信度 0~1
            region: (left, top, width, height) 搜索区域
            grayscale: 是否灰度匹配（更快）

        Returns:
            (center_x, center_y) 模板中心坐标，未找到返回 None
        """
        template = self._load_template(template_path)
        if template is None:
            return None

        # 截取屏幕
        screenshot = self._screenshot(region)
        if screenshot is None:
            return None

        # 匹配
        location, max_val = self._match_template(screenshot, template, grayscale)
        if max_val < confidence:
            logger.debug(
                f"模板匹配失败: {template_path} (conf={max_val:.3f} < {confidence})"
            )
            return None

        # 计算中心坐标
        h, w = template.shape[:2]
        center_x = location[0] + w // 2
        center_y = location[1] + h // 2

        # 如果指定了region，需要加上region的偏移
        if region:
            center_x += region[0]
            center_y += region[1]

        logger.info(
            f"模板匹配成功: {template_path} @ ({center_x}, {center_y}) conf={max_val:.3f}"
        )
        return (center_x, center_y)

    def find_all_templates(self, template_path: str, confidence: float = 0.8,
                           region: tuple = None, grayscale: bool = True,
                           max_matches: int = 20) -> List[Tuple[int, int, float]]:
        """
        查找所有匹配位置

        Returns:
            [(center_x, center_y, confidence), ...] 按置信度降序
        """
        template = self._load_template(template_path)
        if template is None:
            return []

        screenshot = self._screenshot(region)
        if screenshot is None:
            return []

        # 多目标匹配
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED
                                   if not grayscale else None)

        if grayscale:
            result = cv2.matchTemplate(
                cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(template, cv2.COLOR_BGR2GRAY),
                cv2.TM_CCOEFF_NORMED
            )
        else:
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)

        h, w = template.shape[:2]
        locations = []

        # 非极大值抑制：找到高于阈值的所有位置
        threshold = confidence
        ys, xs = np.where(result >= threshold)
        scores = result[ys, xs]

        # 按分数排序
        sorted_idx = np.argsort(scores)[::-1][:max_matches]

        for idx in sorted_idx:
            x, y = xs[idx], ys[idx]
            score = scores[idx]
            center_x = x + w // 2
            center_y = y + h // 2
            if region:
                center_x += region[0]
                center_y += region[1]
            locations.append((center_x, center_y, float(score)))

        return locations

    def wait_for_template(self, template_path: str, timeout: float = 30,
                          interval: float = 0.5, confidence: float = 0.8,
                          region: tuple = None) -> Optional[Tuple[int, int]]:
        """
        轮询等待模板出现

        Args:
            template_path: 模板路径
            timeout: 超时秒数
            interval: 轮询间隔
            confidence: 置信度阈值
            region: 搜索区域

        Returns:
            (x, y) 坐标，超时返回 None
        """
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            pos = self.find_template(template_path, confidence, region)
            if pos:
                return pos
            time.sleep(interval)
        logger.warning(f"等待模板超时: {template_path} ({timeout}s)")
        return None

    def is_visible(self, template_path: str, confidence: float = 0.8,
                   region: tuple = None) -> bool:
        """判断模板图像是否可见"""
        return self.find_template(template_path, confidence, region) is not None

    def compare_screenshots(self, img1, img2, threshold: float = 0.95) -> bool:
        """
        比较两张截图是否相似

        Args:
            img1: PIL Image 或 numpy array 或 文件路径
            img2: PIL Image 或 numpy array 或 文件路径
            threshold: 相似度阈值

        Returns:
            True 表示相似
        """
        a = self._to_numpy(img1)
        b = self._to_numpy(img2)
        if a is None or b is None:
            return False

        # 缩放到相同尺寸
        if a.shape != b.shape:
            b = cv2.resize(b, (a.shape[1], a.shape[0]))

        # 灰度直方图比较
        a_gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        b_gray = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

        hist_a = cv2.calcHist([a_gray], [0], None, [256], [0, 256])
        hist_b = cv2.calcHist([b_gray], [0], None, [256], [0, 256])

        similarity = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)
        return similarity >= threshold

    def get_pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """获取指定像素的颜色 (R, G, B)"""
        screenshot = pyautogui.screenshot()
        pixel = screenshot.getpixel((x, y))
        return pixel

    def pixel_matches(self, x: int, y: int, expected_color: Tuple[int, int, int],
                      tolerance: int = 10) -> bool:
        """检查像素颜色是否匹配"""
        actual = self.get_pixel_color(x, y)
        return all(abs(actual[i] - expected_color[i]) <= tolerance for i in range(3))

    # ============================================================
    # 内部方法
    # ============================================================

    def _load_template(self, path: str) -> Optional[np.ndarray]:
        """加载模板图像"""
        # 尝试绝对路径
        p = Path(path)
        if not p.is_absolute():
            p = self.template_dir / path

        if not p.exists():
            logger.error(f"模板文件不存在: {p}")
            return None

        try:
            img = cv2.imread(str(p))
            if img is None:
                logger.error(f"无法读取模板: {p}")
            return img
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
            return None

    def _screenshot(self, region: tuple = None) -> Optional[np.ndarray]:
        """截图并转为 OpenCV numpy 数组"""
        try:
            if region:
                img = pyautogui.screenshot(region=region)
            else:
                img = pyautogui.screenshot()
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    def _match_template(self, screenshot: np.ndarray, template: np.ndarray,
                        grayscale: bool = True) -> Tuple[Tuple[int, int], float]:
        """模板匹配"""
        if grayscale:
            scr = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        else:
            scr, tpl = screenshot, template

        result = cv2.matchTemplate(scr, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return max_loc, max_val

    def _to_numpy(self, img) -> Optional[np.ndarray]:
        """将多种输入转为 numpy 数组"""
        if img is None:
            return None
        if isinstance(img, np.ndarray):
            return img
        if isinstance(img, Image.Image):
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        if isinstance(img, (str, Path)):
            return cv2.imread(str(img))
        return None

    # ============================================================
    # 高级匹配：多尺度
    # ============================================================

    def find_template_multiscale(self, template_path: str,
                                  scales: List[float] = None,
                                  confidence: float = 0.8,
                                  region: tuple = None) -> Optional[Tuple[int, int, float]]:
        """
        多尺度模板匹配（应对分辨率变化）

        Args:
            template_path: 模板路径
            scales: 缩放比例列表，默认 [0.5, 0.75, 1.0, 1.25, 1.5]
            confidence: 置信度阈值
            region: 搜索区域

        Returns:
            (center_x, center_y, best_scale)，未找到返回 None
        """
        if scales is None:
            scales = [0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5]

        template = self._load_template(template_path)
        if template is None:
            return None

        screenshot = self._screenshot(region)
        if screenshot is None:
            return None

        best_val = 0
        best_loc = None
        best_scale = 1.0

        for scale in scales:
            # 缩放模板
            new_w = int(template.shape[1] * scale)
            new_h = int(template.shape[0] * scale)
            if new_w < 10 or new_h < 10:
                continue
            if new_w > screenshot.shape[1] or new_h > screenshot.shape[0]:
                continue

            resized = cv2.resize(template, (new_w, new_h))

            try:
                loc, val = self._match_template(screenshot, resized, grayscale=True)
                if val > best_val:
                    best_val = val
                    best_loc = loc
                    best_scale = scale
                    best_w, best_h = new_w, new_h
            except Exception:
                continue

        if best_val < confidence or best_loc is None:
            return None

        center_x = best_loc[0] + best_w // 2
        center_y = best_loc[1] + best_h // 2
        if region:
            center_x += region[0]
            center_y += region[1]

        return (center_x, center_y, best_scale)