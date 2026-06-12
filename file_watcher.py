"""
RPA文件监听 + ETL清洗 + 维表校验 + 幂等入库 + 文件夹路由 + 分级告警 + 自愈重试 + 断点续传
基于白皮书四层架构：采集层→处理层→存储层→监控层

核心设计原则（v3.0）:
  文件夹即表  — 一个文件夹对应一张ODS表，路由匹配不再依赖文件名
  DB即校验    — 字段类型/非空/唯一约束由MySQL Schema兜底，代码不做字段级预校验
  模板化接入  — 新接入一张表只需：建表→建文件夹→配路由，无需改代码

处理管线:
  文件检测 → 断点检查 → 文件夹路由 → 读取+L0空文件检查 →
  维表白名单 → L1数据量骤降 → 通用ODS写入(MySQL校验) →
  异常分类处理 → DW聚合 → 归档+checkpoint
"""

import time
import os
import sys
import pandas as pd
import pymysql
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger_config import setup_logger
from config.settings import get_config
from core.db_operations import DatabaseManager
from core.data_validator import DataValidator, ShopWhitelistValidator, CheckResult
from core.alert_manager import AlertManager, LowFrequencyManager, AlertLevel
from core.retry_manager import RetryManager
from core.checkpoint import ProcessCheckpoint
from core.error_classifier import classify_mysql_error, ErrorSeverity
from routers.route_matcher import RouteMatcher, RouteResult

# ============================================================
# 初始化
# ============================================================

app_config = get_config()
logger = setup_logger("RPAWatcher")


# ============================================================
# 文件事件处理器
# ============================================================

class RpaFileHandler(FileSystemEventHandler):
    """
    文件事件处理器（文件夹路由 + DB校验）

    处理管线:
      1. 文件检测 → 校验是否已处理(checkpoint)
      2. 路由匹配 → 文件夹优先，确定目标ODS/DW表
      3. 读取数据 + L0空文件检查
      4. 维表白名单校验（脏数据拦截）
      5. L1数据量骤降检测（监控用，不阻断）
      6. 通用ODS幂等写入（MySQL Schema兜底校验）
      7. DW聚合写入
      8. 异常分类 + 分级告警
      9. 文件归档 + 更新checkpoint + 店铺活跃状态
      全流程 trace_id 贯穿
    """

    def __init__(self):
        super().__init__()
        self._alert_mgr = AlertManager(logger)
        self._retry_mgr = RetryManager(logger, self._alert_mgr)
        self._route_matcher = RouteMatcher()

    # ============================================================
    # 文件创建回调
    # ============================================================

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        file_name = os.path.basename(file_path)

        # 提取相对路径
        file_dir = os.path.dirname(file_path)
        relative_path = os.path.relpath(file_dir, app_config.paths.watch_folder)
        if relative_path == ".":
            relative_path = ""

        # 只处理Excel文件
        if not file_name.endswith(('.xlsx', '.xls')):
            return

        # 等待文件完全写入
        time.sleep(1)

        # 生成全链路 trace_id
        trace_id = logger.new_trace_id()

        logger.info(f"\n{'='*60}", trace_id)
        logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] 检测到新文件: {file_name}", trace_id)
        logger.info(f"  相对路径: {relative_path if relative_path else '(根目录)'}", trace_id)

        # 初始化各模块
        db = DatabaseManager(trace_id)
        checkpoint = ProcessCheckpoint(db)
        dq_validator = DataValidator(db, trace_id)
        low_freq_mgr = LowFrequencyManager(db, self._alert_mgr, trace_id)

        conn = None
        ods_table = None
        dw_table = None
        success_count = 0
        dirty_count = 0
        already_archived = False

        try:
            conn = db.get_connection()

            # ============================================================
            # 阶段1: 断点检查
            # ============================================================
            if checkpoint.is_already_processed(conn, file_name):
                logger.info(f"[跳过] 文件已处理过: {file_name}", trace_id)
                self._archive_file(file_path, file_name, trace_id)
                return

            # ============================================================
            # 阶段2: 文件夹路由匹配
            # ============================================================
            route = self._route_matcher.match(conn, file_name, relative_path)
            ods_table = route.ods_table
            dw_table = route.dw_table
            dw_sql = route.dw_sql
            skip_whitelist = route.skip_whitelist  # 非电商数据跳过维表校验

            if not ods_table:
                logger.info(f"[跳过] 未找到匹配路由: {file_name}", trace_id)
                return

            logger.info(f"  路由命中[{route.method}]: ODS={ods_table}, "
                        f"DW={dw_table}, DW_SQL={'已配置' if dw_sql else '无'}", trace_id)
            checkpoint.mark_processing(conn, trace_id, file_name, ods_table, dw_table)

            # ============================================================
            # 阶段3: 读取数据 + L0空文件检查
            # ============================================================
            with logger.timed_operation("文件读取", trace_id):
                df = pd.read_excel(file_path)
                # 统一列名小写（兼容RPA各种输出格式）
                df.columns = [str(c).lower().strip() for c in df.columns]

            # L0: 空文件检查
            reports_l0, should_abort = dq_validator.check_empty_file(df, file_name)
            for r in reports_l0:
                logger.info(f"  {r}", trace_id)
                db.log_validation(conn, trace_id, file_name,
                                  r.layer, r.rule_name, r.result.value, r.detail)

            if should_abort:
                self._alert_mgr.send_p1("RPA数据告警", f"文件为空: {file_name}", trace_id)
                checkpoint.mark_failed(conn, trace_id, "文件为空")
                self._archive_file(file_path, file_name, trace_id)
                already_archived = True
                return

            logger.info(f"  读取到 {len(df)} 条原始数据", trace_id)

            # ============================================================
            # 阶段4: 维表白名单校验
            # ============================================================
            with logger.timed_operation("维表校验", trace_id):
                if skip_whitelist:
                    logger.info(f"  跳过维表校验 (非电商数据)", trace_id)
                    valid_df, dirty_df = df, pd.DataFrame()
                    shop_col = df.columns[0] if len(df.columns) > 0 else "unknown"
                else:
                    shop_validator = ShopWhitelistValidator.from_db(conn)
                    shop_col = shop_validator.detect_shop_column(df)
                    logger.info(f"  维表白名单: {shop_validator.shop_count} 个活跃店铺 | 标识列: {shop_col}",
                                trace_id)
                    valid_df, dirty_df = shop_validator.filter_valid(df, shop_col)

                last_dirty_shop = ""
                for _, dirty_row in dirty_df.iterrows():
                    shop_identifier = str(dirty_row.get(shop_col, "")).strip()
                    db.log_dirty_data(conn, file_name, shop_identifier, "店铺名称不在维表中")
                    logger.info(f"[拦截] 脏数据: {shop_col}='{shop_identifier}'", trace_id)
                    dirty_count += 1
                    last_dirty_shop = shop_identifier

                # 全部被维表拦截
                if valid_df.empty:
                    logger.warning(
                        f"[全部拦截] 文件{file_name}共{len(df)}行全部被维表拦截", trace_id
                    )
                    if dirty_count >= app_config.validation.dirty_data_block_threshold:
                        self._alert_mgr.send_p1(
                            "RPA脏数据批量告警",
                            f"文件: {file_name}\n全部{len(df)}行被拦截\n示例: {last_dirty_shop}",
                            trace_id
                        )
                    checkpoint.mark_failed(conn, trace_id, f"全部{len(df)}行被维表拦截")
                    already_archived = True
                    return

            # ============================================================
            # 阶段5: L1数据量骤降检测（监控用，不阻断入库）
            # ============================================================
            reports_l1 = dq_validator.check_volume_drop(valid_df, ods_table, conn)
            for r in reports_l1:
                logger.info(f"  {r}", trace_id)
                db.log_validation(conn, trace_id, file_name,
                                  r.layer, r.rule_name, r.result.value, r.detail)
                if r.result == CheckResult.WARN:
                    self._alert_mgr.send_p1("数据量骤降", f"{file_name}: {r.detail}", trace_id)

            # ============================================================
            # 阶段6: 通用ODS幂等写入（MySQL Schema兜底校验）
            #
            # 核心理念: 不预设表的字段结构，从DataFrame动态提取列名
            #           字段类型/非空/唯一约束全部由MySQL在写入时校验
            #           捕获MySQL异常 → 分类 → 友好化 → 告警
            # ============================================================
            with logger.timed_operation("ODS写入", trace_id):
                for _, row in valid_df.iterrows():
                    row_dict = row.to_dict()
                    row_label = str(row.get(shop_col, row.iloc[0] if len(row) > 0 else "?"))

                    try:
                        self._retry_mgr.call_with_retry(
                            lambda r=row_dict: db.upsert_to_ods_generic(
                                conn, r, file_name, ods_table,
                                unique_keys=self._infer_unique_keys(conn, ods_table)
                            ),
                            f"ODS写入[{row_label}]",
                            trace_id
                        )
                        success_count += 1
                        low_freq_mgr.check_and_update(conn, row_label, "", has_data=True)

                    except Exception as write_error:
                        # 分类MySQL错误
                        classified = classify_mysql_error(write_error)

                        if classified.severity == ErrorSeverity.IGNORE:
                            # 幂等重复，正常
                            logger.info(f"[幂等] {classified.message} | {row_label}", trace_id)

                        elif classified.severity == ErrorSeverity.FATAL:
                            # 不可恢复（类型不匹配/字段不存在/非空），立即告警
                            logger.error(
                                f"[DB校验失败] {classified} | {row_label} | {classified.suggestion}",
                                trace_id
                            )
                            db.log_alert(conn, trace_id, "P0", "DB校验失败",
                                         f"文件{file_name}: {classified.message}",
                                         f"{classified.suggestion}\n原始错误: {write_error}")
                            self._alert_mgr.send_p0(
                                f"数据入库失败 - {classified.message}",
                                f"文件: {file_name}\n"
                                f"行: {row_label}\n"
                                f"原因: {classified.message}\n"
                                f"建议: {classified.suggestion}\n"
                                f"trace_id: {trace_id}",
                                trace_id
                            )
                            # 降级：写入兜底文件
                            self._retry_mgr.fallback_to_file(row_dict, file_name, trace_id)

                        else:
                            # WARN级别，记日志继续
                            logger.warning(f"[DB校验WARN] {classified} | {row_label}", trace_id)

            # ============================================================
            # 阶段7: DW加工（配置驱动，数据开发工程师编写SQL）
            # 核心理念: ODS→DW的转换逻辑由配置表 dw_transform_sql 驱动
            #           代码只负责执行，不猜测业务逻辑
            # ============================================================
            dw_affected = 0
            if dw_sql and success_count > 0:
                with logger.timed_operation("DW加工", trace_id):
                    try:
                        dw_affected = self._retry_mgr.call_with_retry(
                            lambda: db.execute_dw_sql(conn, dw_sql, ods_table),
                            "DW加工", trace_id
                        )
                        logger.info(f"  DW层加工完成: 影响{dw_affected}行", trace_id)
                    except Exception as dw_error:
                        classified = classify_mysql_error(dw_error)
                        logger.error(f"[DW加工失败] {classified}", trace_id, exc_info=True)
                        self._alert_mgr.send_p1(
                            "DW加工失败",
                            f"文件: {file_name}\nODS表: {ods_table}\n"
                            f"原因: {classified.message}\n"
                            f"建议: 检查路由表中的 dw_transform_sql 配置",
                            trace_id
                        )

            # ============================================================
            # 阶段8: 脏数据告警 + 完成
            # ============================================================
            if dirty_count > 0:
                if dirty_count >= app_config.validation.dirty_data_block_threshold:
                    self._alert_mgr.send_p1(
                        "RPA脏数据批量告警",
                        f"文件: {file_name}\n拦截: {dirty_count}条\n示例: {last_dirty_shop}",
                        trace_id
                    )
                else:
                    self._alert_mgr.send_p2(
                        "RPA脏数据",
                        f"文件: {file_name}\n拦截: {dirty_count}条",
                        trace_id
                    )

            checkpoint.mark_success(conn, trace_id, success_count, dirty_count)

            logger.info(
                f"文件处理完成 | trace_id={trace_id} | "
                f"文件名: {file_name} | "
                f"ODS表: {ods_table} | "
                f"成功: {success_count}条 | 拦截: {dirty_count}条 | "
                f"DW聚合: {dw_affected}行",
                trace_id
            )

        except pymysql.Error as db_error:
            # 顶层数据库异常
            classified = classify_mysql_error(db_error)
            logger.error(f"[数据库异常] {classified}: {db_error}", trace_id, exc_info=True)
            self._alert_mgr.send_p0(
                f"数据库异常 - {classified.message}",
                f"文件: {file_name}\n原因: {classified.message}\n建议: {classified.suggestion}",
                trace_id
            )
            if conn:
                try:
                    checkpoint.mark_failed(conn, trace_id, str(db_error)[:500])
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[异常] 处理失败: {e}", trace_id, exc_info=True)
            self._alert_mgr.send_p0(
                "RPA处理异常",
                f"文件: {file_name}\n错误: {str(e)[:200]}\ntrace_id: {trace_id}",
                trace_id
            )
            if conn:
                try:
                    checkpoint.mark_failed(conn, trace_id, str(e)[:500])
                except Exception:
                    pass

        finally:
            if conn:
                conn.close()
            if not already_archived:
                self._archive_file(file_path, file_name, trace_id)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _infer_unique_keys(self, conn, ods_table):
        """从数据库Schema推断表的唯一键列名"""
        try:
            sql = f"""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = 'PRIMARY'
                ORDER BY SEQ_IN_INDEX
            """
            df = pd.read_sql(sql, conn, params=(app_config.database.database, ods_table))
            keys = df["COLUMN_NAME"].tolist()
            if keys:
                # 排除自增id（通常不是业务唯一键）
                keys = [k for k in keys if k.lower() not in ("id",)]
            # 如果主键只有id，尝试找UNIQUE索引
            if not keys:
                sql2 = f"""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.STATISTICS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                      AND INDEX_NAME != 'PRIMARY' AND NON_UNIQUE = 0
                    ORDER BY INDEX_NAME, SEQ_IN_INDEX
                """
                df2 = pd.read_sql(sql2, conn, params=(app_config.database.database, ods_table))
                keys = df2["COLUMN_NAME"].tolist()
            return keys if keys else None
        except Exception:
            return None

    def _archive_file(self, file_path, file_name, trace_id):
        """将已处理的文件移到归档目录（幂等）"""
        if not os.path.exists(file_path):
            return

        archive_folder = app_config.paths.archive_folder
        if not os.path.exists(archive_folder):
            os.makedirs(archive_folder)

        archive_path = os.path.join(archive_folder, file_name)
        if os.path.exists(archive_path):
            name, ext = os.path.splitext(file_name)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_path = os.path.join(archive_folder, f"{name}_{timestamp}{ext}")

        try:
            os.rename(file_path, archive_path)
            logger.info(f"  已归档: {archive_path}", trace_id)
        except Exception as e:
            logger.error(f"[归档失败] {file_path}: {e}", trace_id)


# ============================================================
# 启动监听
# ============================================================

def main():
    watch_folder = app_config.paths.watch_folder
    archive_folder = app_config.paths.archive_folder

    logger.info("=" * 60, trace_id="STARTUP")
    logger.info("RPA文件监听服务启动 v3.0", trace_id="STARTUP")
    logger.info("架构: 采集层→处理层→存储层→监控层", trace_id="STARTUP")
    logger.info(f"路由策略: 文件夹优先", trace_id="STARTUP")
    logger.info(f"校验策略: DB Schema兜底（类型/非空/唯一）", trace_id="STARTUP")
    logger.info(f"监听目录: {watch_folder}", trace_id="STARTUP")
    logger.info(f"归档目录: {archive_folder}", trace_id="STARTUP")
    logger.info("=" * 60, trace_id="STARTUP")

    if not os.path.exists(watch_folder):
        os.makedirs(watch_folder)

    # 启动时恢复僵尸记录
    try:
        db = DatabaseManager("STARTUP")
        checkpoint = ProcessCheckpoint(db)
        with db.connection() as conn:
            zombies = checkpoint.recover_zombies(conn, "STARTUP")
            if zombies > 0:
                logger.info(f"[启动恢复] 清理了 {zombies} 条僵尸处理记录", trace_id="STARTUP")
    except Exception as e:
        logger.warning(f"[启动恢复] 数据库不可用: {e}", trace_id="STARTUP")

    event_handler = RpaFileHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_folder, recursive=True)
    observer.start()

    logger.info("服务已启动，等待文件变更...", trace_id="STARTUP")

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...", trace_id="STARTUP")
        observer.stop()

    observer.join()
    logger.info("服务已停止。", trace_id="STARTUP")


if __name__ == "__main__":
    main()
