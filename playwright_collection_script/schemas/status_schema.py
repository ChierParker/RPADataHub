"""状态模型 — 任务执行过程中的状态枚举与转换"""
from enum import Enum


class StatusState(str, Enum):
    """任务状态机"""
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


# 合法的状态转换
TRANSITIONS = {
    StatusState.PENDING:   [StatusState.RECEIVED],
    StatusState.RECEIVED:  [StatusState.RUNNING],
    StatusState.RUNNING:   [StatusState.SUCCESS, StatusState.FAILED, StatusState.TIMEOUT],
    StatusState.FAILED:    [],
    StatusState.SUCCESS:   [],
    StatusState.TIMEOUT:   [],
}


def can_transition(frm: StatusState, to: StatusState) -> bool:
    return to in TRANSITIONS.get(frm, [])
