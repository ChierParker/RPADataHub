"""
CompetitorWatch Redis message queue management
- Task queue: competitor:task:{region}  (Admin -> Worker)
- Result queue: competitor:result:{region} (Worker -> Admin)
- Consumer pattern: Redis List BRPOP (reuses RPADataHub pattern)
- Fallback: direct DB write when Redis unavailable
"""

import json
import os
import time
from typing import Optional, Callable

from logger_config import setup_logger

logger = setup_logger("RedisQueue")

# Queue naming convention
TASK_QUEUE_PREFIX = "competitor:task"      # -> competitor:task:international / domestic
RESULT_QUEUE_PREFIX = "competitor:result"  # -> competitor:result:international / domestic

# Max queue length (prevent memory overflow)
MAX_QUEUE_LENGTH = 10000


class CompetitorRedisQueue:
    """
    Competitor collection Redis message queue

    Producer (Admin):
        queue.publish_task(region, task_data)
        queue.consume_result(region, callback)

    Consumer (Worker):
        queue.pop_task(region, timeout) -> dict | None
        queue.publish_result(region, result_data)
    """

    def __init__(self, redis_host="localhost", redis_port=6379, redis_db=0,
                 redis_password=None, redis_url=None):
        """
        Initialize Redis connection

        Parameters:
            redis_host: Redis host address
            redis_port: Redis port
            redis_db: Redis database number
            redis_password: Redis password
            redis_url: Full Redis URL (overrides host/port/db)
        """
        self._redis = None
        self._redis_available = False

        if redis_url:
            self._redis_url = redis_url
        elif redis_password:
            self._redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
        else:
            self._redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            import redis
            self._redis = redis.Redis.from_url(
                self._redis_url,
                socket_connect_timeout=5,
                socket_timeout=15,
                decode_responses=True
            )
            self._redis.ping()
            self._redis_available = True
            logger.info(f"Redis connected: {self._redis_url}")
        except ImportError:
            logger.warning("redis-py not installed; using fallback mode. Install: pip install redis")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), using fallback mode")

    @property
    def is_available(self) -> bool:
        return self._redis_available

    # ============================================================
    # Task publish (Admin side)
    # ============================================================

    def publish_task(self, region: str, task_data: dict) -> bool:
        """
        Publish collection task to queue (Admin -> Worker)

        Parameters:
            region: region (international/domestic)
            task_data: task data dict containing:
                - task_uuid, competitor_id, competitor_name
                - keywords, asin_list, platform, region
                - marketplace, crawl_type
                - monitor_price, monitor_ad, monitor_ranking
                - created_at

        Returns:
            bool: publish success
        """
        task_json = json.dumps(task_data, ensure_ascii=False)
        queue_key = f"{TASK_QUEUE_PREFIX}:{region}"

        if self._redis_available:
            try:
                self._redis.lpush(queue_key, task_json)
                self._redis.ltrim(queue_key, 0, MAX_QUEUE_LENGTH)
                logger.info(
                    f"[MQ] Task published -> {queue_key}: "
                    f"task_uuid={task_data.get('task_uuid', 'N/A')}"
                )
                return True
            except Exception as e:
                logger.error(f"[MQ] Redis publish failed: {e}")

        # DB fallback when Redis unavailable
        self._write_task_to_db(task_data)
        return False

    def _write_task_to_db(self, task_data: dict):
        """Fallback: write task directly to DB pending table"""
        logger.warning(f"[MQ Fallback] Task written to DB: {task_data.get('task_uuid', 'N/A')}")

    # ============================================================
    # Task consume (Worker side)
    # ============================================================

    def pop_task(self, region: str, timeout: int = 5) -> Optional[dict]:
        """
        Pop a single task from the queue (non-blocking wrapper).

        Parameters:
            region: region (international/domestic)
            timeout: BRPOP timeout in seconds

        Returns:
            dict or None: task data dict, None if queue empty
        """
        if not self._redis_available:
            return None

        queue_key = f"{TASK_QUEUE_PREFIX}:{region}"
        try:
            import redis as redis_lib
            result = self._redis.brpop(queue_key, timeout=timeout)
            if result is None:
                return None
            _, msg_data = result
            try:
                return json.loads(msg_data)
            except json.JSONDecodeError as e:
                logger.error(f"[MQ] Message parse failed: {e}")
                return None
        except redis_lib.ConnectionError as e:
            logger.warning(f"[MQ] Redis connection error: {e}")
            self._redis_available = False
            return None
        except redis_lib.TimeoutError:
            return None  # BRPOP timeout is normal idle
        except Exception as e:
            logger.error(f"[MQ] pop_task error: {e}")
            return None

    def consume_tasks(self, region: str, callback: Callable[[dict], None],
                      block_sec: int = 5):
        """
        Blocking task queue consumer (BRPOP).

        Parameters:
            region: region (international/domestic)
            callback: task handler callback(task_data: dict)
            block_sec: BRPOP block wait seconds
        """
        queue_key = f"{TASK_QUEUE_PREFIX}:{region}"

        if not self._redis_available:
            logger.warning(f"[MQ] Redis unavailable, cannot start consumer: {region}")
            return

        fail_count = 0
        import redis as redis_lib

        logger.info(f"[MQ Consumer] Listening: {queue_key}")

        while True:
            try:
                result = self._redis.brpop(queue_key, timeout=block_sec)
                if result is None:
                    continue

                fail_count = 0
                _, msg_data = result
                try:
                    task_data = json.loads(msg_data)
                    logger.info(
                        f"[MQ Consumer] Received task: task_uuid={task_data.get('task_uuid', 'N/A')}, "
                        f"region={region}"
                    )
                    callback(task_data)
                except json.JSONDecodeError as e:
                    logger.error(f"[MQ Consumer] Parse failed: {e}, raw={msg_data[:200]}")
                except Exception as e:
                    logger.error(f"[MQ Consumer] Handler error: {e}", exc_info=True)

            except redis_lib.ConnectionError as e:
                fail_count += 1
                logger.warning(f"[MQ Consumer] Connection lost ({fail_count}/3): {e}")
                if fail_count >= 3:
                    logger.error("[MQ Consumer] 3 consecutive failures, stopping")
                    break
                time.sleep(2)
            except redis_lib.TimeoutError:
                pass
            except KeyboardInterrupt:
                logger.info(f"[MQ Consumer] Interrupted: {region}")
                break
            except Exception as e:
                fail_count += 1
                logger.error(f"[MQ Consumer] Unknown error ({fail_count}/3): {e}", exc_info=True)
                if fail_count >= 3:
                    break
                time.sleep(2)

    # ============================================================
    # Result pushback (Worker -> Admin)
    # ============================================================

    def publish_result(self, region: str, result_data: dict) -> bool:
        """
        Push collection result to result queue (Worker -> Admin)

        Parameters:
            region: region (international/domestic)
            result_data: result dict containing:
                - task_uuid, competitor_id, status
                - total_results, error_count
                - results, errors, duration_sec, completed_at

        Returns:
            bool: push success
        """
        result_json = json.dumps(result_data, ensure_ascii=False)
        queue_key = f"{RESULT_QUEUE_PREFIX}:{region}"

        if self._redis_available:
            try:
                self._redis.lpush(queue_key, result_json)
                self._redis.ltrim(queue_key, 0, MAX_QUEUE_LENGTH)
                logger.info(
                    f"[MQ] Result pushed -> {queue_key}: "
                    f"task_uuid={result_data.get('task_uuid', 'N/A')}, "
                    f"status={result_data.get('status', '?')}"
                )
                return True
            except Exception as e:
                logger.error(f"[MQ] Result push failed: {e}")

        # Fallback: direct MySQL write
        self._write_result_direct(result_data)
        return False

    def consume_results(self, region: str, callback: Callable[[dict], None],
                        block_sec: int = 5):
        """
        Consume result queue (Admin side consumes Worker results)

        Parameters:
            region: region (international/domestic)
            callback: result handler callback(result_data: dict)
            block_sec: BRPOP block wait seconds
        """
        queue_key = f"{RESULT_QUEUE_PREFIX}:{region}"
        if not self._redis_available:
            logger.warning(f"[MQ] Redis unavailable, cannot consume results: {region}")
            return

        import redis as redis_lib
        logger.info(f"[MQ Consumer] Listening results: {queue_key}")

        while True:
            try:
                result = self._redis.brpop(queue_key, timeout=block_sec)
                if result is None:
                    continue
                _, msg_data = result
                try:
                    result_data = json.loads(msg_data)
                    callback(result_data)
                except Exception as e:
                    logger.error(f"[MQ Consumer] Result handler error: {e}")
            except redis_lib.ConnectionError:
                logger.warning("[MQ Consumer] Redis connection lost")
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"[MQ Consumer] Error: {e}")
                time.sleep(2)


    # ============================================================
    # Crawl status tracking (real-time progress)
    # ============================================================

    CRAWL_STATUS_PREFIX = "competitor:crawl_status"

    def set_crawl_status(self, task_uuid: str, status: str, detail: str = ""):
        """Set real-time crawl status for a task (frontend polling)."""
        key = f"{self.CRAWL_STATUS_PREFIX}:{task_uuid}"
        data = json.dumps({
            "task_uuid": task_uuid,
            "status": status,
            "detail": detail,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False)
        try:
            if self._redis_available:
                self._redis.setex(key, 600, data)  # TTL 10 min
        except Exception:
            pass

    def get_crawl_status(self, task_uuid: str) -> Optional[dict]:
        """Get current crawl status for a task."""
        key = f"{self.CRAWL_STATUS_PREFIX}:{task_uuid}"
        try:
            if self._redis_available:
                raw = self._redis.get(key)
                if raw:
                    return json.loads(raw)
        except Exception:
            pass
        return None

    def _write_result_direct(self, result_data: dict):
        """Fallback: write result directly to database"""
        try:
            from core.db_operations import DatabaseManager
            db = DatabaseManager(result_data.get("task_uuid", "-"))
            with db.connection() as conn:
                with conn.cursor() as cur:
                    for row in result_data.get("results", []):
                        cur.execute(
                            """INSERT INTO ods_price_snapshot
                               (competitor_id, task_uuid, platform, product_url,
                                title, current_price, original_price, currency,
                                rank_position, is_ad, ad_type, review_count,
                                rating, snapshot_time, raw_json, etl_status)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)""",
                            (
                                row.get("competitor_id"),
                                row.get("task_uuid"),
                                row.get("platform"),
                                row.get("product_url", ""),
                                row.get("title", ""),
                                row.get("current_price"),
                                row.get("original_price"),
                                row.get("currency", "USD"),
                                row.get("rank_position"),
                                row.get("is_ad", 0),
                                row.get("ad_type", ""),
                                row.get("review_count"),
                                row.get("rating"),
                                row.get("snapshot_time"),
                                row.get("raw_json", "{}"),
                            )
                        )
                conn.commit()
            logger.info(
                f"[MQ Fallback] Results written to DB: {len(result_data.get('results', []))} rows, "
                f"task_uuid={result_data.get('task_uuid', 'N/A')}"
            )
        except Exception as e:
            logger.error(f"[MQ Fallback] DB write failed: {e}", exc_info=True)
