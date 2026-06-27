"""运行时结构化日志 — 输出到控制台 + 文件"""
import json
import sys
from datetime import datetime
from pathlib import Path
from schemas.log_schema import LogEntry, LogLevel


class RuntimeLogger:
    """结构化日志器"""

    def __init__(self, task_uuid: str = "system", log_dir: str = None):
        self.task_uuid = task_uuid
        self._log_dir = Path(log_dir) if log_dir else Path(__file__).resolve().parent.parent / "logs"
        self._log_dir.mkdir(exist_ok=True)
        self._log_file = self._log_dir / f"task_{task_uuid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    def _emit(self, entry: LogEntry):
        line = entry.to_json()
        print(line)
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except:
            pass

    def info(self, step: str, message: str, **extra):
        self._emit(LogEntry.info(self.task_uuid, step, message, **extra))

    def warn(self, step: str, message: str, **extra):
        self._emit(LogEntry.warn(self.task_uuid, step, message, **extra))

    def error(self, step: str, message: str, **extra):
        self._emit(LogEntry.error(self.task_uuid, step, message, **extra))

    def progress(self, current: int, total: int, message: str = ""):
        pct = round(current / total * 100, 1) if total > 0 else 0
        self.info("PROGRESS", f"[{current}/{total}] {pct}% {message}", current=current, total=total, pct=pct)
