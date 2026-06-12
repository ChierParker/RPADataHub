"""
断点续传/处理状态追踪
对应白皮书 3.3.4 节：断点续传机制

处理状态机:
  PENDING    → 待处理（服务启动后扫描到的未处理文件）
  PROCESSING → 处理中
  SUCCESS    → 成功完成
  FAILED     → 处理失败

断点恢复:
  - 启动时检查 status=PROCESSING 的记录
  - 对于 PROCESSING 超过N分钟的记录，标记为 FAILED 并重新处理
  - 避免文件重复处理（通过 file_name + status=SUCCESS 去重）

对应白皮书 3.3.1 节：采集与处理解耦，任一环节故障不影响整体
"""

import time
import os
from datetime import datetime, timedelta
from config.settings import get_config


class ProcessCheckpoint:
    """
    处理状态追踪器（断点续传）

    使用方式:
        checkpoint = ProcessCheckpoint(db_manager)

        # 开始处理
        checkpoint.mark_processing(conn, trace_id, file_name, ods_table, dw_table)

        # 完成
        checkpoint.mark_success(conn, trace_id, row_count=100, dirty_count=3)

        # 失败
        checkpoint.mark_failed(conn, trace_id, "数据库连接超时")

        # 启动时恢复
        pending = checkpoint.get_pending_files(conn)
    """

    # PROCESSING 状态超时时间（分钟）：超过此时间视为僵尸记录
    PROCESSING_TIMEOUT_MIN = 30

    def __init__(self, db_manager):
        self._db = db_manager

    # ============================================================
    # 状态标记
    # ============================================================

    def mark_processing(self, conn, trace_id, file_name, ods_table, dw_table):
        """标记文件开始处理"""
        self._db.log_process_start(conn, trace_id, file_name, ods_table, dw_table)

    def mark_success(self, conn, trace_id, row_count=0, dirty_count=0):
        """标记处理成功"""
        self._db.log_process_finish(conn, trace_id, "SUCCESS", row_count, dirty_count)

    def mark_failed(self, conn, trace_id, error_msg=""):
        """标记处理失败"""
        self._db.log_process_finish(conn, trace_id, "FAILED", error_msg=error_msg)

    # ============================================================
    # 断点恢复
    # ============================================================

    def is_already_processed(self, conn, file_name):
        """检查文件是否已成功处理过（避免重复处理）"""
        return self._db.is_file_processed(conn, file_name)

    def get_pending_files(self, conn):
        """
        获取待恢复的处理记录
        返回: DataFrame (trace_id, file_name, ods_table, dw_table, start_time)
        """
        df = self._db.get_pending_processes(conn)
        if df is None or df.empty:
            return df

        # 筛选超时的 PROCESSING 记录
        timeout_threshold = datetime.now() - timedelta(minutes=self.PROCESSING_TIMEOUT_MIN)

        # 只返回超时的记录（表示上次处理中断）
        pending = []
        for _, row in df.iterrows():
            start_time = row.get("start_time")
            if start_time and start_time < timeout_threshold:
                pending.append(row)
            # 未超时的可能是正在处理中，跳过

        import pandas as pd
        return pd.DataFrame(pending) if pending else pd.DataFrame()

    def recover_zombies(self, conn, trace_id):
        """
        恢复僵尸处理记录：
        将超时的 PROCESSING 记录标记为 FAILED
        """
        df = self._db.get_pending_processes(conn)
        if df is None or df.empty:
            return 0

        timeout_threshold = datetime.now() - timedelta(minutes=self.PROCESSING_TIMEOUT_MIN)
        recovered = 0
        for _, row in df.iterrows():
            start_time = row.get("start_time")
            if start_time and start_time < timeout_threshold:
                old_trace_id = row.get("trace_id")
                self._db.log_process_finish(
                    conn, old_trace_id, "FAILED",
                    error_msg=f"僵尸恢复: 处理超时({self.PROCESSING_TIMEOUT_MIN}分钟)，由{trace_id}标记"
                )
                recovered += 1

        return recovered
