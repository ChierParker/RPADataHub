"""
标准化任务执行入口 — 接收命令行参数，路由到对应采集器
用法: python task_runner.py --params '{"task_uuid":"xxx","shop_name":"...",...}'
对应文档: 整体执行链路步骤5-7
"""

import os, sys, json, argparse, time, traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.settings import get_config
from logger_config import setup_logger

cfg = get_config()
logger = setup_logger("TaskRunner")


def log(msg, task_uuid="system"):
    """向后兼容的日志函数，内部使用 TraceLogger"""
    logger.info(msg, task_uuid)


def write_task_record(task_uuid, shop_name, platform, script_name, ods_table,
                      collect_result, row_count=0, error_msg="", duration=0):
    """写入单店铺采集明细"""
    from core.db_operations import DatabaseManager
    db = DatabaseManager(task_uuid)
    try:
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO task_record (task_uuid, shop_name, platform, script_name, ods_table,
                       collect_start, collect_end, collect_result, row_count, error_message, duration_sec)
                       VALUES (%s,%s,%s,%s,%s,NOW(),NOW(),%s,%s,%s,%s)""",
                    (task_uuid, shop_name, platform, script_name, ods_table,
                     collect_result, row_count, error_msg, duration)
                )
            conn.commit()
    except Exception as e:
        log(f"写入task_record失败: {e}", task_uuid)


def write_task_summary(task_uuid, task_name, total, success, failed, no_data, total_rows, duration):
    """写入任务汇总报告"""
    from core.db_operations import DatabaseManager
    db = DatabaseManager(task_uuid)
    try:
        with db.connection() as conn:
            with conn.cursor() as cur:
                rate = round(success / total * 100, 2) if total > 0 else 0
                cur.execute(
                    """INSERT INTO task_summary (task_uuid, task_name, total_shops, success_shops,
                       failed_shops, no_data_shops, total_rows, total_duration, success_rate)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE success_shops=VALUES(success_shops),
                       failed_shops=VALUES(failed_shops), no_data_shops=VALUES(no_data_shops),
                       total_rows=VALUES(total_rows), total_duration=VALUES(total_duration),
                       success_rate=VALUES(success_rate)""",
                    (task_uuid, task_name, total, success, failed, no_data, total_rows, duration, rate)
                )
            conn.commit()
        log(f"汇总: 总{total} 成功{success} 失败{failed} 无数据{no_data} 成功率{rate}%", task_uuid)
    except Exception as e:
        log(f"写入task_summary失败: {e}", task_uuid)


def run_collection(params):
    """
    执行采集流程（模拟-实际对接现有playwright脚本）
    params.dict: task_uuid, shop_name, business_date, script_name, ...
    """
    task_uuid = params.get("task_uuid", "unknown")
    script_name = params.get("script_name", "generic_collect")
    shops = params.get("shops", [params.get("shop_name", "default")])
    if isinstance(shops, str):
        shops = [shops]
    business_date = params.get("business_date", datetime.now().strftime("%Y-%m-%d"))

    log(f"开始执行任务: {script_name}, 店铺数={len(shops)}", task_uuid)

    total = len(shops)
    success = 0
    failed = 0
    no_data = 0
    total_rows = 0
    t_start = time.time()

    for shop in shops:
        shop_start = time.time()
        try:
            # ===== 此处对接实际Playwright采集逻辑 =====
            # 现有脚本改造点: 将硬编码参数改为从params读取
            # 例如: process(dict_config) → process(custom_params)
            log(f"采集店铺: {shop}", task_uuid)

            # 模拟采集过程（实际部署时替换为真实playwright调用）
            rows = 0  # 实际采集行数
            err = None

            # TODO: 实际调用
            # from process import process
            # result = process(params)
            # rows = result.get("row_count", 0)

            # ===== 模拟逻辑结束 =====

            dur = int(time.time() - shop_start)
            if err:
                write_task_record(task_uuid, shop, params.get("platform", ""),
                                  script_name, params.get("ods_table", ""),
                                  "FAILED", 0, str(err), dur)
                failed += 1
            elif rows == 0:
                write_task_record(task_uuid, shop, params.get("platform", ""),
                                  script_name, params.get("ods_table", ""),
                                  "NO_DATA", 0, "", dur)
                no_data += 1
            else:
                write_task_record(task_uuid, shop, params.get("platform", ""),
                                  script_name, params.get("ods_table", ""),
                                  "SUCCESS", rows, "", dur)
                success += 1
                total_rows += rows

        except Exception as e:
            dur = int(time.time() - shop_start)
            write_task_record(task_uuid, shop, params.get("platform", ""),
                              script_name, params.get("ods_table", ""),
                              "FAILED", 0, str(e), dur)
            failed += 1
            log(f"店铺 {shop} 失败: {e}", task_uuid)

    # 写汇总
    duration_total = int(time.time() - t_start)
    write_task_summary(task_uuid, script_name, total, success, failed, no_data, total_rows, duration_total)

    # 返回码: 全部失败才返回1
    return 0 if success > 0 or no_data == total else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", type=str, required=True, help="任务参数JSON")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        logger.error(f"参数解析失败: {e}")
        sys.exit(1)

    task_uuid = params.get("task_uuid", "unknown")
    try:
        exit_code = run_collection(params)
        log(f"任务完成 exit_code={exit_code}", task_uuid)
        sys.exit(exit_code)
    except Exception as e:
        log(f"任务异常: {e}\n{traceback.format_exc()}", task_uuid)
        sys.exit(1)


if __name__ == "__main__":
    main()
