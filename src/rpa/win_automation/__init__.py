"""
WinAutomation — Windows 桌面应用自动化模块
============================================
为 RPADataHub 提供 WinForm / WPF / UWP / ERP客户端 等桌面应用自动化能力

技术栈:
    - pywinauto: 控件级操作 (Win32 / UIA)
    - uiautomation: 微软原生 UIA 封装
    - pyautogui: 鼠标键盘模拟 (兜底)
    - OpenCV: 图像识别定位
    - PaddleOCR: 中文OCR识别

架构:
    WinCollector (Base)
        ├── pywinauto 引擎
        ├── uiautomation 引擎
        ├── OCR 模块
        └── 图像识别模块
"""

__version__ = "1.0.0"