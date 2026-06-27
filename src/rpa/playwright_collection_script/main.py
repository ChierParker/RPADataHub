"""
RPA采集平台 — 统一任务入口 (v2.0)
支持: CLI参数 / task_runner模式 / Worker轮询
用法:
    # CLI直接执行采集器
    python main.py --task sina_finance

    # 通过TaskConfig JSON执行
    python main.py --params '{"scriptCode":"sina_finance","params":{"max_articles":20}}'

    # Worker模式(持续轮询task_queue)
    python main.py --worker

    # 原有模式
    python main.py --task aba --collection_type Weekly --country 英国
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from traceback import format_exc

# 确保项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from schemas.task_schema import TaskConfig, TaskStatus
from schemas.result_schema import TaskSummary
from runtime.context import ExecutionContext
from runtime.logger import RuntimeLogger
from runtime.reporter import StatusReporter
from runtime.process_guard import ProcessGuard
from runtime.exception_handler import ExceptionHandler
from collector_registry import get_collector, list_collectors, _registry
from mq.consumer import TaskConsumer
from mq.message_adapter import message_to_task_config


def run_by_config(task_config: TaskConfig) -> TaskSummary:
    """通过 TaskConfig 执行采集（新架构入口）"""
    ctx = ExecutionContext(task_config)
    logger = RuntimeLogger(ctx.task_id)
    reporter = StatusReporter(ctx.trace_id)
    guard = ProcessGuard(task_config)
    exc_handler = ExceptionHandler()

    logger.info("START", f"任务启动: {task_config.script_code}",
                task_config=task_config.to_dict())

    # 状态: PENDING → RUNNING
    ctx.transition(TaskStatus.RUNNING)
    reporter.update_task_status(ctx.task_id, "RUNNING")

    try:
        # 获取采集器（确保已发现）
        _registry.discover()
        collector = get_collector(task_config.script_code)
        if not collector:
            # 降级: 兼容原有命令行模式
            logger.warn("FALLBACK", f"未注册采集器: {task_config.script_code}, 尝试原始命令")
            return _run_legacy(task_config)

        logger.info("COLLECTOR", f"使用采集器: {collector.collector_name}")

        # 执行采集
        summary = guard.wrap_with_timeout(collector.execute, task_config)

        # 上报结果
        for record in collector.records:
            reporter.report_record(record)
        reporter.report_summary(summary)

        ctx.transition(TaskStatus.SUCCESS)
        reporter.update_task_status(ctx.task_id, "SUCCESS")

        logger.info("SUCCESS",
                    f"完成: {summary.success_shops}/{summary.total_shops} 店铺成功, "
                    f"{summary.total_rows} 行数据, 耗时 {summary.total_duration}s")
        return summary

    except TimeoutError:
        ctx.transition(TaskStatus.TIMEOUT)
        reporter.update_task_status(ctx.task_id, "TIMEOUT", f"超时({task_config.timeout_sec}s)")
        logger.error("TIMEOUT", f"任务超时: {task_config.timeout_sec}s")
        return TaskSummary(task_uuid=ctx.task_id, task_name=task_config.script_code,
                           failed_shops=1, total_shops=1)

    except Exception as e:
        entry = exc_handler.to_entry(e, ctx.task_id, "RUN")
        ctx.transition(TaskStatus.FAILED)
        reporter.update_task_status(ctx.task_id, "FAILED", str(e))

        logger.error("FAILED", str(e), exception=entry)
        return TaskSummary(task_uuid=ctx.task_id, task_name=task_config.script_code,
                           failed_shops=1, total_shops=1, errors=[str(e)])


def _run_legacy(task_config: TaskConfig) -> TaskSummary:
    """降级: 尝试 collector_registry 中未注册的采集器"""
    raise ValueError(f"采集器 '{task_config.script_code}' 未注册。可用: {list_collectors()}")


def run_worker(poll_interval: int = 5):
    """Worker 模式: 持续轮询 task_queue 执行任务"""
    consumer = TaskConsumer(poll_interval=poll_interval)

    def handle_task(task: dict):
        config = message_to_task_config(task)
        print(f"\n{'='*50}\n[Worker] 执行: {config.task_id} ({config.script_code})\n{'='*50}")
        summary = run_by_config(config)
        consumer.report_result(
            config.task_id,
            "SUCCESS" if summary.success_shops > 0 else "FAILED",
            str(summary.errors[0]) if summary.errors else "",
            summary.total_duration
        )

    consumer.run_loop(on_task=handle_task)


def main():
    parser = argparse.ArgumentParser(description="RPA采集平台")
    parser.add_argument("--task", type=str, help="采集器名称 (sina_finance/aba/amazon_po/login)")
    parser.add_argument("--params", type=str, help="任务参数JSON")
    parser.add_argument("--worker", action="store_true", help="Worker轮询模式")
    parser.add_argument("--list", action="store_true", help="列出所有采集器")
    parser.add_argument("--account", type=str, help="账号")
    parser.add_argument("--country", type=str, nargs='+', help="国家")
    parser.add_argument("--start_date", type=str, help="开始日期")
    parser.add_argument("--end_date", type=str, help="结束日期")
    parser.add_argument("--collection_type", type=str, help="采集类型")
    parser.add_argument("--recollect", type=str, help="是否补采")
    parser.add_argument("--exclude_country", type=str, help="排除国家")
    parser.add_argument("--max_thread_count", type=str, help="最大线程数")
    parser.add_argument("--mode", type=str, choices=["full", "incremental"], default="full")

    args = parser.parse_args()

    # --list: 列出采集器
    if args.list:
        _registry.discover()
        collectors = list_collectors()
        print(f"已注册采集器 ({len(collectors)}):")
        for c in collectors:
            print(f"  - {c}")
        return

    # --worker: Worker模式
    if args.worker:
        run_worker()
        return

    # --params: TaskConfig JSON模式
    if args.params:
        config = TaskConfig.from_json(args.params)
        summary = run_by_config(config)
        sys.exit(0 if summary.success_shops > 0 else 1)

    # --task: CLI 直接模式
    if args.task:
        # 先尝试新架构
        _registry.discover()
        collector = get_collector(args.task)
        if collector:
            config = TaskConfig(
                script_code=args.task,
                account=args.account or "",
                countries=args.country or [],
                start_date=args.start_date or "",
                end_date=args.end_date or "",
                collection_type=args.collection_type or "Daily",
                recollect=bool(args.recollect),
                exclude_country=[args.exclude_country] if args.exclude_country else [],
            )
            summary = collector.execute(config)
            print(f"\n结果: {summary.total_shops}店铺, 成功{summary.success_shops}, "
                  f"{summary.total_rows}行, {summary.total_duration}s")
            sys.exit(0 if summary.success_shops > 0 else 1)
        else:
            print(f"未知任务: {args.task}")
            print(f"可用采集器: {list_collectors()}")
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    # Windows 多进程支持
    import multiprocessing
    multiprocessing.freeze_support()
    main()
