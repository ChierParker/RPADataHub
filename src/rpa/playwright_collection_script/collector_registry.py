"""
Collector 注册中心 — 按 scriptCode 路由到对应采集器
用法:
    from collector_registry import get_collector
    collector = get_collector("sina_finance")
    summary = collector.execute(config)
"""

from typing import Dict, Optional, Type
from collectors.base import BaseCollector


class CollectorRegistry:
    """采集器注册中心"""

    _instance: Optional["CollectorRegistry"] = None
    _collectors: Dict[str, Type[BaseCollector]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, code: str, collector_cls: Type[BaseCollector]):
        """注册一个采集器"""
        self._collectors[code] = collector_cls
        print(f"[Registry] 注册采集器: {code} -> {collector_cls.__name__}")

    def get(self, code: str) -> Optional[Type[BaseCollector]]:
        """获取采集器类"""
        return self._collectors.get(code)

    def create(self, code: str) -> Optional[BaseCollector]:
        """创建采集器实例"""
        cls = self.get(code)
        return cls() if cls else None

    def list_all(self) -> list:
        """列出所有已注册采集器"""
        return list(self._collectors.keys())

    def discover(self):
        """自动发现并注册内置采集器"""
        # 新浪财经
        from collectors.sina_finance import SinaFinanceCollector
        self.register("sina_finance", SinaFinanceCollector)
        self.register("新浪财经-要闻采集", SinaFinanceCollector)

        # Demo 采集器（无需 Playwright）
        from collectors.demo_collector import DemoPOCollector, DemoABACollector
        self.register("demo_po", DemoPOCollector)
        self.register("demo_aba", DemoABACollector)

        # ============================================================
        # Win 桌面采集器注册（pywinauto + uiautomation）
        # ============================================================
        try:
            from win_automation.collectors.notepad_collector import NotepadCollector
            from win_automation.collectors.calculator_collector import CalculatorCollector
            from win_automation.collectors.excel_collector import ExcelCollector
            self.register("notepad_collector", NotepadCollector)
            self.register("calculator_collector", CalculatorCollector)
            self.register("excel_collector", ExcelCollector)
            # 中文别名
            self.register("记事本采集", NotepadCollector)
            self.register("计算器采集", CalculatorCollector)
            self.register("Excel采集", ExcelCollector)
        except ImportError as e:
            print(f"[Registry] Win 采集器注册失败（可能缺少 pywinauto 等依赖）: {e}")
        except Exception as e:
            print(f"[Registry] Win 采集器注册异常: {e}")


# 全局单例
_registry = CollectorRegistry()


def get_collector(code: str) -> Optional[BaseCollector]:
    """获取采集器实例"""
    _registry.discover()
    return _registry.create(code)


def register_collector(code: str, cls: Type[BaseCollector]):
    _registry.register(code, cls)


def list_collectors() -> list:
    _registry.discover()
    return _registry.list_all()
