"""
CompetitorWatch Collection Worker - Redis List BRPOP consumer + DB fallback
Reuses RPADataHub worker.py consumer pattern

Startup:
    python worker.py                              # Listen to all regions
    python worker.py --region international       # International only
    python worker.py --region domestic            # Domestic only
    python worker.py --region both                # Dual thread (default)
    python worker.py --db                         # Force DB fallback mode
    python worker.py --once                       # Single execution (test)
    python worker.py --workers 4                  # Multi-process (4 workers)

Consumer flow:
    1. BRPOP competitor:task:{region}
    2. Select collector by platform
    3. Execute Playwright collection
    4. Write to ods_price_snapshot
    5. LPUSH result to competitor:result:{region} back to Admin
"""

import json
import os
import sys
import time
import uuid
import signal
import socket
import threading
import traceback
from datetime import datetime
from multiprocessing import Process
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import get_config
from logger_config import setup_logger
from mq.redis_queue import CompetitorRedisQueue

logger = setup_logger("CompetitorWorker")

MACHINE_IP = socket.gethostbyname(socket.gethostname())

# Graceful shutdown flag
SHUTDOWN = threading.Event()

def shutdown_handler(signum, frame):
    """Handle SIGINT/SIGTERM gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    SHUTDOWN.set()


# ============================================================
# Collector factory
# ============================================================

def get_collector_for_platform(task_data: dict):
    """
    Select appropriate collector by platform/region.

    Parameters:
        task_data: task data dict

    Returns:
        BaseCompetitorCollector instance
    """
    platform = task_data.get("platform", "amazon").lower()
    region = task_data.get("region", "domestic")

    if region == "international":
        if platform == "amazon":
            from collectors.amazon_collector import AmazonCollector
            return AmazonCollector(task_data, headless=True)
        elif platform == "walmart":
            logger.warning(f"[Worker] Walmart collector not yet implemented, falling back to Amazon mode")
            from collectors.amazon_collector import AmazonCollector
            return AmazonCollector(task_data, headless=True)
        elif platform == "shopee":
            raise NotImplementedError(f"Shopee collector not yet implemented")
        else:
            raise ValueError(f"Unsupported international platform: {platform}")
    else:
        if platform in ("amazon",):
            from collectors.amazon_collector import AmazonCollector
            return AmazonCollector(task_data, headless=True)
        elif platform == "jd":
            from collectors.jd_collector import JDCollector
            return JDCollector(task_data, headless=True)
        elif platform == "taobao":
            from collectors.taobao_collector import TaobaoCollector
            return TaobaoCollector(task_data, headless=True)
        elif platform == "pdd":
            raise NotImplementedError(f"PDD collector not yet implemented")
        else:
            raise ValueError(f"Unsupported domestic platform: {platform}")


# ============================================================
# Single task execution
# ============================================================

def execute_task(task_data: dict, queue: CompetitorRedisQueue = None) -> dict:
    """
    Execute single competitor collection task.

    Flow:
        1. Parameter validation
        2. Start platform-specific collector
        3. Execute collect()
        4. Write to ods_price_snapshot
        5. Push result back to Redis

    Parameters:
        task_data: task parameters dict
        queue: Redis queue instance (for result pushback, optional)

    Returns:
        dict: execution result summary
    """
    task_uuid = task_data.get("task_uuid", uuid.uuid4().hex[:16])
    task_data["task_uuid"] = task_uuid

    competitor_name = task_data.get("competitor_name", "unknown")
    platform = task_data.get("platform", "unknown")
    region = task_data.get("region", "domestic")

    logger.info(
        f"[Worker] Starting task: uuid={task_uuid}, "
        f"competitor={competitor_name}, platform={platform}, region={region}",
        task_uuid
    )

    start_time = time.time()
    status = "FAILED"
    results = []
    errors = []
    error_message = ""

    try:
        # 1. Get collector
        collector = get_collector_for_platform(task_data)
        logger.info(f"[Worker] Using collector: {collector.__class__.__name__}", task_uuid)

        # 2. Execute collection
        collector.collect()
        results = collector.results
        errors = collector.errors

        # 3. Write to database
        if results:
            from core.db_operations import DatabaseManager
            db = DatabaseManager(trace_id=task_uuid)
            snap_count = db.insert_snapshots_batch(results)
            logger.info(f"[Worker] Wrote {snap_count} snapshots to ODS", task_uuid)

            # 4. Aggregate to DW
            from collections import defaultdict
            daily_aggs = defaultdict(lambda: {
                "prices": [], "ranks": [], "ads": 0,
                "reviews": [], "ratings": [],
            })
            snapshot_date = datetime.now().strftime("%Y-%m-%d")
            for r in results:
                key = (r.get("competitor_id"), r.get("platform", ""), snapshot_date)
                if r.get("current_price"):
                    daily_aggs[key]["prices"].append(float(r["current_price"]))
                if r.get("rank_position"):
                    daily_aggs[key]["ranks"].append(int(r["rank_position"]))
                if r.get("is_ad"):
                    daily_aggs[key]["ads"] += 1
                if r.get("review_count"):
                    daily_aggs[key]["reviews"].append(int(r["review_count"]))
                if r.get("rating"):
                    daily_aggs[key]["ratings"].append(float(r["rating"]))

            for (cid, plat, sdate), agg in daily_aggs.items():
                prices = agg["prices"]
                ranks = agg["ranks"]
                db.upsert_daily_aggregate({
                    "competitor_id": cid,
                    "platform": plat,
                    "snapshot_date": sdate,
                    "min_price": min(prices) if prices else None,
                    "max_price": max(prices) if prices else None,
                    "avg_price": sum(prices) / len(prices) if prices else None,
                    "median_price": sorted(prices)[len(prices)//2] if prices else None,
                    "price_volatility": None,
                    "snapshot_count": len(prices),
                    "ad_count": agg["ads"],
                    "avg_rank": sum(ranks) / len(ranks) if ranks else None,
                    "min_rank": min(ranks) if ranks else None,
                    "total_reviews": max(agg["reviews"]) if agg["reviews"] else None,
                    "rating_avg": sum(agg["ratings"]) / len(agg["ratings"]) if agg["ratings"] else None,
                })
            logger.info(f"[Worker] DW aggregate updated for {len(daily_aggs)} competitor(s)", task_uuid)

        status = "SUCCESS" if not errors else "PARTIAL"
    except Exception as e:
        error_message = str(e)
        errors.append({"message": error_message, "traceback": traceback.format_exc()})
        logger.error(f"[Worker] Task failed: uuid={task_uuid}, error={e}", task_uuid, exc_info=True)
        status = "FAILED"

    duration = round(time.time() - start_time, 2)
    result_data = {
        "task_uuid": task_uuid,
        "competitor_id": task_data.get("competitor_id"),
        "competitor_name": competitor_name,
        "platform": platform,
        "region": region,
        "status": status,
        "error_message": error_message,
        "result_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
        "duration_sec": duration,
        "worker_ip": MACHINE_IP,
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 6. Push result to Redis result queue
    if queue and queue.is_available:
        queue.publish_result(region, result_data)

    logger.info(
        f"[Worker] Task complete: uuid={task_uuid}, status={status}, "
        f"results={len(results)}, errors={len(errors)}, duration={duration}s",
        task_uuid
    )

    return result_data


# ============================================================
# Worker process entry point
# ============================================================

def worker_process(region: str, db_fallback: bool, worker_id: int = 0):
    """
    Single worker process entry point.

    Parameters:
        region: region to listen (international/domestic)
        db_fallback: force DB fallback mode
        worker_id: unique worker identifier
    """
    proc_name = f"Worker-{region}-{worker_id}"
    wlogger = setup_logger(proc_name)

    cfg = get_config()

    # Initialize Redis queue
    if cfg.redis.url:
        queue = CompetitorRedisQueue(redis_url=cfg.redis.url)
    else:
        queue = CompetitorRedisQueue(
            redis_host=cfg.redis.host,
            redis_port=cfg.redis.port,
            redis_db=cfg.redis.db,
            redis_password=cfg.redis.password,
        )

    if db_fallback:
        queue._redis_available = False
        wlogger.warning(f"{proc_name}: Forced DB fallback mode")

    wlogger.info(
        f"{proc_name} started | "
        f"Redis: {cfg.redis.host}:{cfg.redis.port} | "
        f"Region: {region} | "
        f"Available: {queue.is_available}"
    )

    # Consume loop
    task_key = f"competitor:task:{region}"
    consecutive_errors = 0
    max_consecutive_errors = 10

    while not SHUTDOWN.is_set():
        try:
            task_data = queue.pop_task(region, timeout=5)
            if task_data:
                execute_task(task_data, queue)
                consecutive_errors = 0
            else:
                # No task in queue, brief sleep to avoid busy loop
                time.sleep(1)
                consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            wlogger.error(f"{proc_name}: Error in consume loop ({consecutive_errors}): {e}")
            if consecutive_errors >= max_consecutive_errors:
                wlogger.critical(f"{proc_name}: Too many consecutive errors, exiting")
                break
            time.sleep(min(consecutive_errors * 2, 30))  # Exponential backoff capped at 30s

    wlogger.info(f"{proc_name}: Shutting down")


# ============================================================
# Main entry
# ============================================================

def main():
    """Worker main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CompetitorWatch Collection Worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python worker.py                              # Dual regions
  python worker.py --region international       # International only
  python worker.py --region domestic            # Domestic only
  python worker.py --once --region international # Single test
  python worker.py --db                         # DB fallback mode
  python worker.py --workers 4                  # 4 worker processes
        """,
    )
    parser.add_argument(
        "--region", type=str, default="both",
        choices=["international", "domestic", "both"],
        help="Region to monitor (default: both)"
    )
    parser.add_argument(
        "--db", action="store_true",
        help="Force DB fallback mode"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Single execution then exit (test use, requires --region)"
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Number of worker processes per region (default: 1)"
    )

    args = parser.parse_args()

    cfg = get_config()

    logger.info(
        f"CompetitorWatch Worker v1.1 starting\n"
        f"  Machine IP: {MACHINE_IP}\n"
        f"  Redis: {cfg.redis.host}:{cfg.redis.port}/{cfg.redis.db}\n"
        f"  Region: {args.region}\n"
        f"  Workers per region: {args.workers}\n"
        f"  Mode: {'DB fallback' if args.db else 'Redis MQ'}"
    )

    # Register signal handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Determine regions
    regions = ["international", "domestic"] if args.region == "both" else [args.region]

    # Once mode
    if args.once:
        logger.info(f"Once mode: {args.region}")
        for region in regions:
            queue = CompetitorRedisQueue(redis_url=cfg.redis.url)
            if args.db:
                queue._redis_available = False
            task_key = f"competitor:task:{region}"
            try:
                task_data = queue.pop_task(region, timeout=5)
                if task_data:
                    execute_task(task_data, queue)
                else:
                    logger.info(f"Queue {task_key} is empty")
            except Exception as e:
                logger.error(f"Once execution failed: {e}")
        return

    # Multi-process mode
    processes = []
    worker_id = 0

    for region in regions:
        for i in range(args.workers):
            worker_id += 1
            p = Process(
                target=worker_process,
                args=(region, args.db, worker_id),
                daemon=True,
                name=f"Worker-{region}-{worker_id}",
            )
            processes.append(p)
            p.start()
            logger.info(f"Started process: Worker-{region}-{worker_id} (PID {p.pid})")

    # Wait for all processes
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, Worker shutting down...")
        SHUTDOWN.set()
        for p in processes:
            p.terminate()
            p.join(timeout=10)
        logger.info("All workers stopped")


if __name__ == "__main__":
    main()
