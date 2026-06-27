"""产物管理器 — 结果文件/截图/trace 管理"""
import shutil
from pathlib import Path
from datetime import datetime


class ArtifactManager:
    """管理采集过程中产生的文件产物"""

    def __init__(self, task_uuid: str, base_dir: str = None):
        self.task_uuid = task_uuid
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent / "artifacts"
        self.task_dir = self.base_dir / task_uuid
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in [self.task_dir, self.screenshots_dir, self.traces_dir, self.outputs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def screenshots_dir(self) -> Path:
        return self.task_dir / "screenshots"

    @property
    def traces_dir(self) -> Path:
        return self.task_dir / "traces"

    @property
    def outputs_dir(self) -> Path:
        return self.task_dir / "outputs"

    def save_screenshot(self, data: bytes, name: str = "") -> str:
        ts = datetime.now().strftime("%H%M%S")
        fname = f"{name or 'screenshot'}_{ts}.png"
        path = self.screenshots_dir / fname
        path.write_bytes(data)
        return str(path)

    def save_output(self, src_path: str, name: str = "") -> str:
        """保存输出文件到产物目录"""
        src = Path(src_path)
        if not src.exists():
            return ""
        dst = self.outputs_dir / (name or src.name)
        shutil.copy2(src, dst)
        return str(dst)

    def list_artifacts(self) -> dict:
        """列出所有产物"""
        result = {"screenshots": [], "traces": [], "outputs": []}
        for f in self.screenshots_dir.glob("*"):
            result["screenshots"].append(str(f))
        for f in self.traces_dir.glob("*"):
            result["traces"].append(str(f))
        for f in self.outputs_dir.glob("*"):
            result["outputs"].append(str(f))
        return result

    def cleanup(self, keep_days: int = 7):
        """清理过期产物"""
        import time
        cutoff = time.time() - keep_days * 86400
        for d in self.base_dir.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
