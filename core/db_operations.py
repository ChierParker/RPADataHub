"""
数据库操作层
- 连接池管理
- ODS幂等写入（增强：记录 trace_id）
- DW聚合写入
- 维表加载
- 脏数据日志
- 新增：处理状态追踪 / 告警记录 / 校验结果 / 低频店铺管理
对应白皮书：
  2.2.3 存储层：ODS层 → DW层 → DM层 三级分层建模
  2.5 数据治理方案：维表驱动的质量校验
  6.2.2 ETL联动阻断机制
"""

import pymysql
import pandas as pd
from datetime import datetime
from contextlib import contextmanager
from config.settings import get_config


class DatabaseManager:
    """数据库操作管理器，封装所有数据库IO"""

    def __init__(self, trace_id="-"):
        self._config = get_config().database
        self._trace_id = trace_id

    # ============================================================
    # 连接管理
    # ============================================================

    def get_connection(self):
        """获取MySQL连接"""
        return pymysql.connect(**self._config.as_dict())

    @contextmanager
    def connection(self):
        """上下文管理器：自动关闭连接"""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    # ============================================================
    # 维表操作
    # ============================================================

    def load_valid_shops(self, conn):
        """从店铺维表加载合法店铺名称白名单
        对应白皮书 2.5 节：店铺维表驱动的数据校验——白名单守门人
        """
        sql = """
            SELECT shop_id, shop_name, platform, bu, status
            FROM dim_shop_info
            WHERE status = 1
        """
        return pd.read_sql(sql, conn)

    def load_quality_rules(self, conn):
        """加载数据质量监控规则配置
        对应白皮书 6.2.1 节：配置表管理30+条校验规则
        """
        sql = """
            SELECT rule_id, rule_name, rule_type, check_sql, threshold, severity, is_active
            FROM data_quality_rules
            WHERE is_active = 1
        """
        return pd.read_sql(sql, conn)

    def load_routes(self, conn):
        """加载路由配置
        对应白皮书 2.3.2 节：配置化路由
        """
        path_routes = pd.read_sql(
            "SELECT path_pattern, target_ods_table, target_dw_table, priority FROM etl_path_route WHERE is_active = 1",
            conn
        )
        file_routes = pd.read_sql(
            "SELECT file_pattern, target_ods_table, target_dw_table, priority FROM etl_route_config WHERE is_active = 1",
            conn
        )
        return path_routes, file_routes

    # ============================================================
    # ODS层操作（幂等写入）
    # ============================================================

    def upsert_to_ods(self, conn, row, file_name, ods_table):
        """幂等写入ODS层（订单专用，保留向后兼容）
        对应白皮书 3.2.2/3.3.6 节：主键幂等，重复执行不产生脏数据
        基于 shop_name + po_number + asin 复合唯一键
        """
        sql = f"""
            INSERT INTO {ods_table}
                (shop_name, po_number, asin, sku, order_date, quantity, amount, order_status, raw_file_name)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                sku = VALUES(sku),
                order_date = VALUES(order_date),
                quantity = VALUES(quantity),
                amount = VALUES(amount),
                order_status = VALUES(order_status),
                raw_file_name = VALUES(raw_file_name)
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (
                row.get("shop_name", ""),
                row.get("po_number", ""),
                row.get("asin", ""),
                row.get("sku", ""),
                row.get("order_date"),
                row.get("quantity", 0),
                row.get("amount", 0.00),
                row.get("order_status", ""),
                file_name
            ))
        conn.commit()

    def upsert_to_ods_generic(self, conn, row, file_name, ods_table, unique_keys=None):
        """通用幂等写入ODS层（支持任意表结构）
        对应白皮书 4.2 节：模板化接入

        参数:
          row: dict/Series，key为列名
          file_name: 来源文件名
          ods_table: 目标ODS表名
          unique_keys: 唯一键列名列表，用于 ON DUPLICATE KEY UPDATE
                       默认用于识别哪些列是主键（不更新），其余列更新
        """
        if unique_keys is None:
            unique_keys = []

        # 从 row 提取列名和值（NaN → None 兼容 MySQL）
        import math
        columns = list(row.keys())
        values = []
        for c in columns:
            v = row.get(c)
            if isinstance(v, float) and math.isnan(v):
                v = None
            values.append(v)

        # 添加 raw_file_name（如果表中有此列但 row 中没有）
        if "raw_file_name" not in columns:
            columns.append("raw_file_name")
            values.append(file_name)

        # 构建 INSERT 列名和占位符
        col_str = ", ".join(columns)
        placeholder_str = ", ".join(["%s"] * len(columns))

        # 构建 ON DUPLICATE KEY UPDATE 子句
        # 规则：唯一键列不更新，其余列更新为新值
        update_cols = [c for c in columns if c not in unique_keys and c != "raw_file_name"]
        if update_cols:
            update_parts = [f"{c} = VALUES({c})" for c in update_cols]
            update_str = "ON DUPLICATE KEY UPDATE " + ", ".join(update_parts)
        else:
            update_str = ""

        sql = f"""
            INSERT INTO {ods_table} ({col_str})
            VALUES ({placeholder_str})
            {update_str}
        """

        with conn.cursor() as cursor:
            cursor.execute(sql, values)
        conn.commit()

    # ============================================================
    # DW层操作（聚合写入）
    # ============================================================

    def execute_dw_sql(self, conn, dw_sql, ods_table):
        """
        执行 DW 加工SQL（配置驱动）
        对应白皮书 4.2 节：数据开发工程师编写加工SQL，配置到路由表

        参数:
          dw_sql: 从 etl_path_route.dw_transform_sql 读取的SQL
                 支持 {ods_table} 占位符，运行时替换为实际ODS表名
          ods_table: 当前ODS表名

        返回:
          受影响行数
        """
        # 占位符替换
        sql = dw_sql.replace("{ods_table}", ods_table)

        # 拆分多条语句（加工SQL + 标记SQL）
        statements = [s.strip() for s in sql.split(";") if s.strip()]

        affected = 0
        with conn.cursor() as cursor:
            for stmt in statements:
                cursor.execute(stmt)
                affected += cursor.rowcount

        # 如果加工SQL中没有更新etl_status，这里兜底标记
        if "etl_status" not in dw_sql.lower():
            sql_mark = f"UPDATE {ods_table} SET etl_status = 1 WHERE etl_status = 0"
            with conn.cursor() as cursor:
                cursor.execute(sql_mark)

        conn.commit()
        return affected

    # ============================================================
    # 脏数据记录
    # ============================================================

    def log_dirty_data(self, conn, file_name, shop_name, reason):
        """记录脏数据到日志表
        对应白皮书 6.2.2 节：校验失败 → 运维看板记录异常
        """
        sql = """
            INSERT INTO rpa_dirty_data_log (file_name, shop_name, reason, detect_time)
            VALUES (%s, %s, %s, %s)
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (file_name, shop_name, reason, datetime.now()))
        conn.commit()

    # ============================================================
    # 新增：处理状态追踪（断点续传）
    # ============================================================

    def log_process_start(self, conn, trace_id, file_name, ods_table, dw_table):
        """文件处理开始 → 写入 etl_process_log (PENDING)"""
        sql = """
            INSERT INTO etl_process_log (trace_id, file_name, ods_table, dw_table, status, start_time)
            VALUES (%s, %s, %s, %s, 'PROCESSING', %s)
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (trace_id, file_name, ods_table, dw_table, datetime.now()))
        conn.commit()

    def log_process_finish(self, conn, trace_id, status, row_count=0, dirty_count=0, error_msg=None):
        """文件处理完成 → 更新 etl_process_log"""
        sql = """
            UPDATE etl_process_log
            SET status = %s, row_count = %s, dirty_count = %s, error_msg = %s, end_time = %s
            WHERE trace_id = %s
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (status, row_count, dirty_count, error_msg, datetime.now(), trace_id))
        conn.commit()

    def get_pending_processes(self, conn):
        """获取未完成的处理记录（用于断点恢复）"""
        sql = """
            SELECT trace_id, file_name, ods_table, dw_table, start_time
            FROM etl_process_log
            WHERE status = 'PROCESSING'
        """
        return pd.read_sql(sql, conn)

    def is_file_processed(self, conn, file_name):
        """检查文件是否已成功处理"""
        sql = """
            SELECT COUNT(*) as cnt FROM etl_process_log
            WHERE file_name = %s AND status = 'SUCCESS'
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (file_name,))
            result = cursor.fetchone()
        return result[0] > 0 if result else False

    # ============================================================
    # 新增：告警记录
    # ============================================================

    def log_alert(self, conn, trace_id, alert_level, alert_type, title, content, is_sent=True):
        """记录告警到 rpa_alert_log"""
        sql = """
            INSERT INTO rpa_alert_log (trace_id, alert_level, alert_type, title, content, is_sent, create_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (trace_id, alert_level, alert_type, title, content, int(is_sent), datetime.now()))
        conn.commit()

    # ============================================================
    # 新增：数据校验结果记录
    # ============================================================

    def log_validation(self, conn, trace_id, file_name, check_layer, check_rule, check_result, detail=""):
        """记录校验结果到 data_validation_log"""
        sql = """
            INSERT INTO data_validation_log (trace_id, file_name, check_layer, check_rule, check_result, detail, check_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (trace_id, file_name, check_layer, check_rule, check_result, detail, datetime.now()))
        conn.commit()

    # ============================================================
    # 新增：低频账号管理
    # ============================================================

    def update_shop_activity(self, conn, shop_name, platform, has_data):
        """更新店铺活跃状态"""
        if has_data:
            sql = """
                INSERT INTO low_frequency_shops (shop_name, platform, consecutive_empty_days, is_low_freq, last_data_date)
                VALUES (%s, %s, 0, 0, %s)
                ON DUPLICATE KEY UPDATE
                    consecutive_empty_days = 0,
                    is_low_freq = 0,
                    last_data_date = VALUES(last_data_date),
                    next_check_date = NULL
            """
            with conn.cursor() as cursor:
                cursor.execute(sql, (shop_name, platform, datetime.now()))
        else:
            sql = """
                INSERT INTO low_frequency_shops (shop_name, platform, consecutive_empty_days, is_low_freq, last_data_date)
                VALUES (%s, %s, 1, 0, %s)
                ON DUPLICATE KEY UPDATE
                    consecutive_empty_days = consecutive_empty_days + 1,
                    last_data_date = VALUES(last_data_date)
            """
            with conn.cursor() as cursor:
                cursor.execute(sql, (shop_name, platform, datetime.now()))
        conn.commit()

    def get_low_frequency_shops(self, conn):
        """获取需降频监控的店铺列表"""
        sql = """
            SELECT shop_name, platform, consecutive_empty_days
            FROM low_frequency_shops
            WHERE consecutive_empty_days >= 7 AND is_low_freq = 0
        """
        return pd.read_sql(sql, conn)

    def mark_low_frequency(self, conn, shop_name):
        """标记店铺为低频"""
        sql = """
            UPDATE low_frequency_shops
            SET is_low_freq = 1, next_check_date = DATE_ADD(CURDATE(), INTERVAL (7 - WEEKDAY(CURDATE()) + 1) DAY)
            WHERE shop_name = %s
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (shop_name,))
        conn.commit()

    # ============================================================
    # 新增：存在性校验查询（数据量骤降检测）
    # ============================================================

    def get_7day_avg_rows(self, conn, ods_table):
        """获取最近7天（不含今天）的日均入库行数"""
        sql = f"""
            SELECT AVG(daily_cnt) as avg_cnt
            FROM (
                SELECT DATE(create_time) as dt, COUNT(*) as daily_cnt
                FROM {ods_table}
                WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                  AND create_time < CURDATE()
                GROUP BY DATE(create_time)
            ) t
        """
        return pd.read_sql(sql, conn)

    def get_today_row_count(self, conn, ods_table):
        """获取今日入库行数"""
        sql = f"""
            SELECT COUNT(*) as cnt FROM {ods_table}
            WHERE DATE(create_time) = CURDATE()
        """
        with conn.cursor() as cursor:
            cursor.execute(sql)
            result = cursor.fetchone()
        return result[0] if result else 0

    # ============================================================
    # 新增：一致性校验查询（ODS vs DW 交叉校验）
    # ============================================================

    def check_ods_dw_consistency(self, conn, ods_table, dw_table):
        """检查ODS与DW数据一致性：ODS有数据但DW未聚合的记录数"""
        sql = f"""
            SELECT COUNT(*) as inconsistent_cnt
            FROM {ods_table} o
            WHERE o.etl_status = 0
              AND o.create_time < DATE_SUB(NOW(), INTERVAL 1 HOUR)
        """
        with conn.cursor() as cursor:
            cursor.execute(sql)
            result = cursor.fetchone()
        return result[0] if result else 0
