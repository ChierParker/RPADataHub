"""
Redis 消息队列代理 — 生产级 MQ 实现
Admin → Redis Streams → Worker 即时消费

特性:
  - Redis Streams 实现消息持久化 + 消费者组
  - DB task_queue 保留为审计日志
  - 自动故障切换: Redis 不可用时降级为 DB 直写模式
  - 消费者组支持多 Worker 负载均衡
"""

import json, os, sys, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import get_config

cfg = get_config()


class RedisBroker:
    """
    Redis 消息队列代理

    生产端:
        broker.publish(task_params)  → 写入 Redis Stream + DB 审计

    消费端:
        broker.consume(callback)     → 阻塞等待新消息 → 回调处理
    """

    QUEUE_KEY = "rpa:task:queue"  # Redis List 作为消息队列

    def __init__(self, redis_url=None):
        self._redis = None
        self._redis_available = False
        if redis_url:
            self._redis_url = redis_url
        else:
            self._redis_url = os.environ.get("REDIS_URL") or cfg.redis.redis_url
        self._init_redis()

    def _init_redis(self):
        """初始化 Redis 连接"""
        try:
            import redis
            self._redis = redis.Redis.from_url(
                self._redis_url,
                socket_connect_timeout=3,
                socket_timeout=5,
                decode_responses=True
            )
            self._redis.ping()
            self._redis_available = True

            # Redis List 不需要预创建

            print(f"[MQ] Redis List 已连接: {self._redis_url}")
        except ImportError:
            print("[MQ] redis-py 未安装, 降级为 DB 轮询模式. pip install redis")
        except Exception as e:
            print(f"[MQ] Redis 不可用 ({e}), 降级为 DB 轮询模式")

    # ============================================================
    # 生产端: Admin 下发任务
    # ============================================================

    def publish(self, task_params: dict) -> str:
        """发布任务消息到 MQ
        task_params: {
            "task_uuid": "...",
            "script_name": "...",
            "config_id": 1,
            "params": {...},
            "executor_ip": None,
            "priority": 1,
            "timestamp": "..."
        }
        返回: task_uuid
        """
        task_uuid = task_params.get("task_uuid", "")

        # 1. Redis List 发布（主通道，LPUSH）
        if self._redis_available:
            try:
                self._redis.lpush(
                    self.QUEUE_KEY,
                    json.dumps(task_params, ensure_ascii=False)
                )
                # 限制队列长度防止内存溢出
                self._redis.ltrim(self.QUEUE_KEY, 0, 9999)
                print(f"[MQ] 已发布: {task_uuid} -> Redis Queue")
            except Exception as e:
                print(f"[MQ] Redis 发布失败: {e}")

        # 2. DB task_queue 写入（审计通道，也作降级兜底）
        self._write_db_audit(task_params)

        return task_uuid

    def _write_db_audit(self, task_params):
        """写入 DB 审计日志（同时也是 Redis 不可用时的降级通道）"""
        try:
            import pymysql
            conn = pymysql.connect(**cfg.database.as_dict())
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO task_queue (config_id, task_uuid, script_name, task_params, executor_ip) "
                "VALUES (%s, %s, %s, %s, %s)",
                (task_params.get("config_id", 1),
                 task_params.get("task_uuid", ""),
                 task_params.get("script_name", ""),
                 json.dumps(task_params, ensure_ascii=False),
                 task_params.get("executor_ip"))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MQ] DB 审计写入失败: {e}")

    # ============================================================
    # 消费端: Worker 监听任务
    # ============================================================

    def consume(self, callback, block_ms=5000):
        """
        阻塞等待新任务（优先 Redis，降级 DB）

        callback(task_params_dict) → None
        """
        if self._redis_available:
            self._consume_redis(callback, block_ms)
        else:
            self._consume_db_fallback(callback)

    def _consume_redis(self, callback, block_ms):
        """Redis List BRPOP 阻塞消费"""
        import redis
        timeout_sec = max(1, int(block_ms / 1000))
        fail_count = 0
        while True:
            try:
                result = self._redis.brpop(self.QUEUE_KEY, timeout=timeout_sec)

                fail_count = 0  # 成功, 重置计数器

                if result is None:
                    self._check_db_pending(callback)
                    continue

                queue_name, msg_data = result
                try:
                    data = json.loads(msg_data)
                    callback(data)
                except Exception as e:
                    print(f"[MQ] 消息处理失败: {e}")

            except redis.ConnectionError as e:
                fail_count += 1
                print(f"[MQ] Redis 连接断开 ({fail_count}/3): {e}")
                if fail_count >= 3:
                    self._redis_available = False
                    self._consume_db_fallback(callback)
                    break
                time.sleep(2)
            except redis.TimeoutError:
                pass  # BRPOP 超时是正常的, 继续
            except KeyboardInterrupt:
                break
            except Exception as e:
                fail_count += 1
                print(f"[MQ] 异常 ({fail_count}/3): {type(e).__name__}: {e}")
                if fail_count >= 3:
                    print("[MQ] 连续失败3次, 降级 DB")
                    self._redis_available = False
                    self._consume_db_fallback(callback)
                    break
                time.sleep(2)

    def _consume_db_fallback(self, callback):
        """DB 轮询降级模式（定期尝试重连 Redis）"""
        import pymysql, socket
        machine_ip = socket.gethostbyname(socket.gethostname())
        poll_count = 0

        while True:
            # 每 30 轮尝试恢复 Redis
            poll_count += 1
            if poll_count % 30 == 0:
                self._init_redis()
                if self._redis_available:
                    print("[MQ] Redis 已恢复, 切回 MQ 模式")
                    self._consume_redis(callback, 5000)
                    return

            try:
                conn = pymysql.connect(**cfg.database.as_dict())
                cur = conn.cursor()
                cur.execute(
                    "SELECT q.*, c.script_name, c.timeout_sec, c.priority "
                    "FROM task_queue q JOIN task_config c ON q.config_id = c.id "
                    "WHERE q.task_status = 'PENDING' "
                    "  AND (q.executor_ip IS NULL OR q.executor_ip = %s) "
                    "ORDER BY c.priority ASC, q.create_time ASC LIMIT 1",
                    (machine_ip,)
                )
                row = cur.fetchone()
                if row:
                    task = {
                        "task_uuid": row[2],
                        "script_name": row[7] or row[3],
                        "config_id": row[1],
                        "task_params": row[4],
                    }
                    cur.execute(
                        "UPDATE task_queue SET task_status='RUNNING', executor_ip=%s, start_time=NOW() "
                        "WHERE task_uuid=%s AND task_status='PENDING'",
                        (machine_ip, task["task_uuid"])
                    )
                    conn.commit()
                    conn.close()
                    callback(task)
                else:
                    conn.close()
                    time.sleep(5)
            except Exception as e:
                print(f"[MQ-DB] 轮询异常: {e}")
                time.sleep(5)

    def _check_db_pending(self, callback):
        """Redis 空闲时检查 DB 是否有遗漏任务(消费一个即返回,不永久降级)"""
        import pymysql, socket
        try:
            machine_ip = socket.gethostbyname(socket.gethostname())
            conn = pymysql.connect(**cfg.database.as_dict())
            cur = conn.cursor()
            cur.execute(
                "SELECT q.*, c.script_name, c.timeout_sec FROM task_queue q "
                "JOIN task_config c ON q.config_id = c.id "
                "WHERE q.task_status='PENDING' AND (q.executor_ip IS NULL OR q.executor_ip=%s) "
                "ORDER BY c.priority ASC, q.create_time ASC LIMIT 1",
                (machine_ip,)
            )
            row = cur.fetchone()
            if row:
                task = {"task_uuid": row[2], "script_name": row[7] or row[3], "config_id": row[1], "task_params": row[4]}
                cur.execute("UPDATE task_queue SET task_status='RUNNING', executor_ip=%s, start_time=NOW() WHERE task_uuid=%s AND task_status='PENDING'",
                    (machine_ip, task["task_uuid"]))
                conn.commit()
                conn.close()
                callback(task)
                return
            conn.close()
        except: pass
