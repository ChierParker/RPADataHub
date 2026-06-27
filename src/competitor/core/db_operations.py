""" 
CompetitorWatch database operations layer
- Connection management (parameterized queries to prevent SQL injection)
- ODS price snapshot writes
- DW daily aggregate writes
- Competitor config CRUD
- Reuses RPADataHub connection pool pattern

All SQL uses parameterized queries; no user-input concatenation allowed.
"""

import pymysql
from datetime import datetime
from contextlib import contextmanager
from typing import Optional

from config.settings import get_config
from logger_config import setup_logger

logger = setup_logger("DatabaseManager")


class DatabaseManager:
    """Competitor system database operations manager"""

    def __init__(self, trace_id="-"):
        cfg = get_config()
        self._config = {
            "host": cfg.database.host,
            "port": cfg.database.port,
            "user": cfg.database.user,
            "password": cfg.database.password,
            "database": cfg.database.database,
            "charset": cfg.database.charset,
            "connect_timeout": cfg.database.connect_timeout,
        }
        self._trace_id = trace_id

    # ============================================================
    # Connection management
    # ============================================================

    def get_connection(self):
        """Get MySQL connection"""
        return pymysql.connect(**self._config)

    @contextmanager
    def connection(self):
        """Context manager: auto-close connection"""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    # ============================================================
    # Competitor config CRUD
    # ============================================================

    def get_competitor_list(self, region: Optional[str] = None,
                            status: int = 1) -> list:
        """
        Get competitor config list

        Parameters:
            region: region filter (international/domestic), None = all
            status: status filter (1=enabled, 0=disabled)

        Returns:
            list[dict]: competitor config list
        """
        sql = """
            SELECT id, competitor_name, keywords, asin_list, walmart_id,
                   jd_sku, taobao_url, region, platform,
                   monitor_price, monitor_ad, monitor_ranking,
                   crawl_interval_hours, status, created_at, updated_at
            FROM competitor_config
            WHERE status = %s
        """
        params = [status]

        if region:
            sql += " AND region = %s"
            params.append(region)

        sql += " ORDER BY id DESC"

        with self.connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def get_competitor_by_id(self, competitor_id: int) -> Optional[dict]:
        """Get single competitor config by ID"""
        sql = """
            SELECT id, competitor_name, keywords, asin_list, walmart_id,
                   jd_sku, taobao_url, region, platform,
                   monitor_price, monitor_ad, monitor_ranking,
                   crawl_interval_hours, status, created_at, updated_at
            FROM competitor_config
            WHERE id = %s
        """
        with self.connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, (competitor_id,))
                return cur.fetchone()

    def insert_competitor(self, data: dict) -> int:
        """
        Insert new competitor config

        Parameters:
            data: competitor config dict

        Returns:
            int: new record ID
        """
        sql = """
            INSERT INTO competitor_config
                (competitor_name, keywords, asin_list, walmart_id,
                 jd_sku, taobao_url, region, platform,
                 monitor_price, monitor_ad, monitor_ranking,
                 crawl_interval_hours, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    data.get("competitor_name", ""),
                    data.get("keywords", "[]"),
                    data.get("asin_list", "[]"),
                    data.get("walmart_id", ""),
                    data.get("jd_sku", ""),
                    data.get("taobao_url", ""),
                    data.get("region", "domestic"),
                    data.get("platform", "amazon"),
                    data.get("monitor_price", 1),
                    data.get("monitor_ad", 1),
                    data.get("monitor_ranking", 1),
                    data.get("crawl_interval_hours", 24),
                    data.get("status", 1),
                ))
                new_id = cur.lastrowid
            conn.commit()
        logger.info(f"[DB] New competitor: id={new_id}, name={data.get('competitor_name', '')}")
        return new_id

    def update_competitor(self, competitor_id: int, data: dict) -> bool:
        """Update competitor config"""
        fields = []
        params = []
        updatable = [
            "competitor_name", "keywords", "asin_list", "walmart_id",
            "jd_sku", "taobao_url", "region", "platform",
            "monitor_price", "monitor_ad", "monitor_ranking",
            "crawl_interval_hours",
        ]
        for key in updatable:
            if key in data:
                fields.append(f"{key} = %s")
                params.append(data[key])

        if not fields:
            return False

        params.append(competitor_id)
        sql = f"UPDATE competitor_config SET {', '.join(fields)} WHERE id = %s"

        with self.connection() as conn:
            with conn.cursor() as cur:
                affected = cur.execute(sql, params)
            conn.commit()
        logger.info(f"[DB] Updated competitor: id={competitor_id}, affected={affected}")
        return affected > 0

    def toggle_competitor(self, competitor_id: int) -> bool:
        """Toggle competitor enable/disable status"""
        sql = """
            UPDATE competitor_config
            SET status = CASE WHEN status = 1 THEN 0 ELSE 1 END
            WHERE id = %s
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (competitor_id,))
                affected = cur.rowcount
            conn.commit()
        logger.info(f"[DB] Toggled competitor: id={competitor_id}, affected={affected}")
        return affected > 0

    def delete_competitor(self, competitor_id: int) -> bool:
        """Delete competitor config"""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM competitor_config WHERE id = %s", (competitor_id,))
                affected = cur.rowcount
            conn.commit()
        logger.info(f"[DB] Deleted competitor: id={competitor_id}, affected={affected}")
        return affected > 0

    # ============================================================
    # ODS layer: price snapshot CRUD
    # ============================================================

    def insert_snapshot(self, record: dict) -> int:
        """
        Insert ODS price snapshot

        Parameters:
            record: snapshot record dict

        Returns:
            int: new record ID
        """
        sql = """
            INSERT INTO ods_price_snapshot
                (competitor_id, task_uuid, platform, product_url, title,
                 current_price, original_price, currency,
                 rank_position, is_ad, ad_type, review_count, rating,
                 seller_name, snapshot_time, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    record.get("competitor_id"),
                    record.get("task_uuid", ""),
                    record.get("platform", ""),
                    record.get("product_url", ""),
                    record.get("title", ""),
                    record.get("current_price"),
                    record.get("original_price"),
                    record.get("currency", "USD"),
                    record.get("rank_position"),
                    record.get("is_ad", 0),
                    record.get("ad_type", ""),
                    record.get("review_count"),
                    record.get("rating"),
                    record.get("seller_name", ""),
                    record.get("snapshot_time", datetime.now()),
                    record.get("raw_json", "{}"),
                ))
                snap_id = cur.lastrowid
            conn.commit()
        logger.info(f"[DB] Snapshot: id={snap_id}, competitor_id={record.get('competitor_id')}")
        return snap_id

    def insert_snapshots_batch(self, records: list) -> int:
        """Batch insert ODS price snapshots"""
        if not records:
            return 0
        sql = """
            INSERT INTO ods_price_snapshot
                (competitor_id, task_uuid, platform, product_url, title,
                 current_price, original_price, currency,
                 rank_position, is_ad, ad_type, review_count, rating,
                 seller_name, snapshot_time, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        now = datetime.now()
        params_list = []
        for rec in records:
            params_list.append((
                rec.get("competitor_id"),
                rec.get("task_uuid", ""),
                rec.get("platform", ""),
                rec.get("product_url", ""),
                rec.get("title", ""),
                rec.get("current_price"),
                rec.get("original_price"),
                rec.get("currency", "USD"),
                rec.get("rank_position"),
                rec.get("is_ad", 0),
                rec.get("ad_type", ""),
                rec.get("review_count"),
                rec.get("rating"),
                rec.get("seller_name", ""),
                rec.get("snapshot_time", now),
                rec.get("raw_json", "{}"),
            ))

        with self.connection() as conn:
            with conn.cursor() as cur:
                affected = cur.executemany(sql, params_list)
            conn.commit()
        logger.info(f"[DB] Batch snapshot: {affected} records, competitor_id={records[0].get('competitor_id') if records else 'N/A'}")
        return affected

    # ============================================================
    # DW layer: daily aggregate writes
    # ============================================================

    def upsert_daily_aggregate(self, record: dict) -> bool:
        """
        Upsert DW daily aggregate (INSERT ON DUPLICATE KEY UPDATE)

        Parameters:
            record: daily aggregate record dict

        Returns:
            bool: success
        """
        sql = """
            INSERT INTO dw_competitor_daily
                (competitor_id, platform, snapshot_date,
                 min_price, max_price, avg_price, median_price,
                 price_volatility, snapshot_count, ad_count,
                 avg_rank, min_rank, total_reviews, rating_avg)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                min_price = VALUES(min_price),
                max_price = VALUES(max_price),
                avg_price = VALUES(avg_price),
                median_price = VALUES(median_price),
                price_volatility = VALUES(price_volatility),
                snapshot_count = VALUES(snapshot_count),
                ad_count = VALUES(ad_count),
                avg_rank = VALUES(avg_rank),
                min_rank = VALUES(min_rank),
                total_reviews = VALUES(total_reviews),
                rating_avg = VALUES(rating_avg)
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    record.get("competitor_id"),
                    record.get("platform", ""),
                    record.get("snapshot_date"),
                    record.get("min_price"),
                    record.get("max_price"),
                    record.get("avg_price"),
                    record.get("median_price"),
                    record.get("price_volatility"),
                    record.get("snapshot_count", 0),
                    record.get("ad_count", 0),
                    record.get("avg_rank"),
                    record.get("min_rank"),
                    record.get("total_reviews"),
                    record.get("rating_avg"),
                ))
            conn.commit()
        logger.info(f"[DB] DW daily aggregate: competitor_id={record.get('competitor_id')}")
        return True

    def mark_snapshots_etl_done(self, competitor_id: int, snapshot_date: str) -> int:
        """Mark ODS snapshots as ETL processed for given date"""
        sql = """
            UPDATE ods_price_snapshot
            SET etl_status = 1
            WHERE competitor_id = %s
              AND DATE(snapshot_time) = %s
              AND etl_status = 0
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                affected = cur.execute(sql, (competitor_id, snapshot_date))
            conn.commit()
        logger.info(f"[DB] ETL marked: {affected} records, competitor_id={competitor_id}, date={snapshot_date}")
        return affected

    # ============================================================
    # Data queries (dashboard use)
    # ============================================================

    def get_price_trend(self, competitor_id: int, days: int = 30) -> list:
        """
        Get competitor price trend data (dashboard chart)

        Parameters:
            competitor_id: competitor ID
            days: query recent days

        Returns:
            list[dict]: daily price trend list
        """
        sql = """
            SELECT snapshot_date, min_price, max_price, avg_price,
                   ad_count, avg_rank, snapshot_count
            FROM dw_competitor_daily
            WHERE competitor_id = %s
              AND snapshot_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            ORDER BY snapshot_date ASC
        """
        with self.connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, (competitor_id, days))
                return cur.fetchall()

    def get_recent_snapshots(self, competitor_id: int, limit: int = 50) -> list:
        """Get recent price snapshots with details"""
        sql = """
            SELECT id, competitor_id, task_uuid, platform, product_url,
                   title, current_price, original_price, currency,
                   rank_position, is_ad, ad_type, review_count,
                   rating, snapshot_time, etl_status
            FROM ods_price_snapshot
            WHERE competitor_id = %s
            ORDER BY snapshot_time DESC
            LIMIT %s
        """
        with self.connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, (competitor_id, limit))
                return cur.fetchall()

    # ============================================================
    # AI report related
    # ============================================================

    def save_report(self, competitor_id: int, report_type: str,
                    report_date: str, content: str, summary: str = "",
                    alert_level: str = "info") -> int:
        """Save AI analysis report"""
        sql = """
            INSERT INTO competitor_report
                (competitor_id, report_type, report_date, content, summary, alert_level)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    competitor_id, report_type, report_date,
                    content, summary, alert_level
                ))
                report_id = cur.lastrowid
            conn.commit()
        logger.info(f"[DB] Report saved: id={report_id}, type={report_type}, competitor_id={competitor_id}")
        return report_id

    def get_reports(self, competitor_id: int = None,
                    report_type: str = None, limit: int = 20) -> list:
        """Query AI analysis report list"""
        sql = """
            SELECT r.id, r.competitor_id, c.competitor_name,
                   r.report_type, r.report_date, r.summary,
                   r.alert_level, r.is_sent, r.created_at
            FROM competitor_report r
            LEFT JOIN competitor_config c ON r.competitor_id = c.id
            WHERE 1=1
        """
        params = []
        if competitor_id:
            sql += " AND r.competitor_id = %s"
            params.append(competitor_id)
        if report_type:
            sql += " AND r.report_type = %s"
            params.append(report_type)

        sql += " ORDER BY r.created_at DESC LIMIT %s"
        params.append(limit)

        with self.connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def get_report_content(self, report_id: int) -> Optional[dict]:
        """Get full report content by ID"""
        sql = """
            SELECT r.*, c.competitor_name
            FROM competitor_report r
            LEFT JOIN competitor_config c ON r.competitor_id = c.id
            WHERE r.id = %s
        """
        with self.connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, (report_id,))
                return cur.fetchone()

    def mark_report_sent(self, report_id: int):
        """Mark report as sent/pushed"""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE competitor_report SET is_sent = 1 WHERE id = %s",
                    (report_id,)
                )
            conn.commit()
