"""执行上下文 — 贯穿整个任务生命周期的状态容器"""
import os
import socket
import uuid
from datetime import datetime
from schemas.task_schema import TaskConfig, TaskStatus


class ExecutionContext:
    """任务执行上下文"""

    def __init__(self, config: TaskConfig):
        self.config = config
        self.task_id = config.task_id or uuid.uuid4().hex[:16]
        self.trace_id = config.trace_id or uuid.uuid4().hex[:16]
        self.start_time = datetime.now()
        self.status = TaskStatus.PENDING
        self.machine_ip = socket.gethostbyname(socket.gethostname())
        self.pid = os.getpid()
        self.output_dir = ""
        self.error_count = 0

    def transition(self, new_status: TaskStatus):
        """状态流转"""
        from schemas.status_schema import can_transition
        if can_transition(self.status, new_status):
            self.status = new_status
            return True
        return False

    @property
    def elapsed_sec(self) -> int:
        return int((datetime.now() - self.start_time).total_seconds())

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "status": self.status.value,
            "machine_ip": self.machine_ip,
            "pid": self.pid,
            "elapsed_sec": self.elapsed_sec,
        }
