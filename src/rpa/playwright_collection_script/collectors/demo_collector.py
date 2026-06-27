"""
Demo 模拟采集器 — 无需 Playwright，生成模拟数据直写完整链路
开源友好: clone 即跑，不依赖浏览器/登录态/代理
"""

import os, time, random, json, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from collectors.base import BaseCollector
from schemas.task_schema import TaskConfig, TaskStatus
from schemas.result_schema import TaskSummary

# 模拟店铺数据
DEMO_SHOPS = [
    {"name": "Demo-北美站", "platform": "Amazon", "marketplace": "Amazon.com"},
    {"name": "Demo-欧洲站", "platform": "Amazon", "marketplace": "Amazon.de"},
    {"name": "Demo-沃尔玛", "platform": "Walmart", "marketplace": "Walmart.com"},
    {"name": "Demo-日本站", "platform": "Amazon", "marketplace": "Amazon.co.jp"},
    {"name": "Demo-东南亚", "platform": "Shopee", "marketplace": "Shopee.sg"},
    {"name": "Demo-TEMU", "platform": "TEMU", "marketplace": "TEMU.com"},
    {"name": "Demo-澳洲站", "platform": "Amazon", "marketplace": "Amazon.com.au"},
    {"name": "Demo-拉美", "platform": "MercadoLibre", "marketplace": "MercadoLibre.com.br"},
]
DEMO_ASINS = [
    "B0A1B2C3D4E5", "B0F6G7H8I9J0", "B0K1L2M3N4O5", "B0P6Q7R8S9T0",
    "B0U1V2W3X4Y5", "B0Z6A7B8C9D0", "B0E1F2G3H4I5", "B0J6K7L8M9N0",
]


class DemoPOCollector(BaseCollector):
    """PO单采集 Demo — 模拟 Amazon PO 数据采集"""
    collector_name = "demo_po"
    supported_platforms = ["Amazon", "Walmart"]
    default_ods_table = "ods_order_raw"

    def run(self, config: TaskConfig) -> TaskSummary:
        rpa_output = Path(os.environ.get("RPA_WATCH_FOLDER", "D:/rpa_output"))
        output_dir = rpa_output / "demo_po"
        output_dir.mkdir(parents=True, exist_ok=True)

        total_rows = 0
        shops = [s for s in (config.shops or []) if s and s != "全部"]
        if not shops:
            shops = [s["name"] for s in DEMO_SHOPS[:5]]

        for shop_name in shops:
            shop = next((s for s in DEMO_SHOPS if s["name"] == shop_name), DEMO_SHOPS[0])
            t0 = time.time()

            try:
                # 模拟采集过程 (0.3-1.5秒)
                time.sleep(random.uniform(0.3, 1.5))

                # 10% 概率模拟失败
                if random.random() < 0.1:
                    self.add_record(shop_name, "FAILED", 0,
                                    "模拟异常: 页面加载超时 (demo)", int(time.time() - t0), shop["platform"])
                    continue

                # 生成订单数据
                rows = []
                business_date = config.start_date or datetime.now().strftime("%Y-%m-%d")
                for _ in range(random.randint(3, 15)):
                    rows.append({
                        "shop_name": shop_name,
                        "po_number": f"PO-DEMO-{random.randint(10000, 99999)}",
                        "asin": random.choice(DEMO_ASINS),
                        "sku": f"SKU-{random.randint(100, 999)}",
                        "order_date": business_date,
                        "quantity": random.randint(1, 10),
                        "amount": round(random.uniform(29, 899), 2),
                        "order_status": random.choice(["Shipped", "Pending", "Delivered"]),
                    })

                # 写 Excel 到 rpa_output (file_watcher 会自动消费)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"demo_po_{shop_name.replace(' ', '_')}_{ts}.xlsx"
                filepath = output_dir / filename
                pd.DataFrame(rows).to_excel(filepath, index=False)

                n = len(rows)
                total_rows += n
                self.add_record(shop_name, "SUCCESS", n, "", int(time.time() - t0), shop["platform"])

            except Exception as e:
                self.add_record(shop_name, "FAILED", 0, str(e), int(time.time() - t0), shop["platform"])

        summary = self.build_summary(total_rows=total_rows)
        summary.task_name = "PO单采集(Demo)"
        return summary


class DemoABACollector(BaseCollector):
    """ABA关键词采集 Demo — 模拟 Amazon Brand Analytics 数据"""
    collector_name = "demo_aba"
    supported_platforms = ["Amazon"]
    default_ods_table = "ods_aba_keyword_raw"

    def run(self, config: TaskConfig) -> TaskSummary:
        rpa_output = Path(os.environ.get("RPA_WATCH_FOLDER", "D:/rpa_output"))
        output_dir = rpa_output / "demo_aba"
        output_dir.mkdir(parents=True, exist_ok=True)

        total_rows = 0
        keywords = [
            "smart air conditioner", "portable ac", "mini fridge", "washing machine",
            "robot vacuum", "microwave oven", "air fryer", "dehumidifier",
            "electric water heater", "tower fan", "cordless vacuum", "IH rice cooker",
        ]
        shops = [s for s in (config.shops or []) if s and s != "全部"]
        if not shops:
            shops = [s["name"] for s in DEMO_SHOPS[:3]]

        for shop_name in shops:
            shop = next((s for s in DEMO_SHOPS if s["name"] == shop_name), DEMO_SHOPS[0])
            t0 = time.time()

            try:
                time.sleep(random.uniform(0.5, 2.0))

                if random.random() < 0.08:
                    self.add_record(shop_name, "FAILED", 0,
                                    "模拟异常: API限流 (demo)", int(time.time() - t0), shop["platform"])
                    continue

                rows = []
                business_date = config.start_date or datetime.now().strftime("%Y-%m-%d")
                for kw in keywords:
                    rank = random.randint(1, 50000)
                    rows.append({
                        "shop_name": shop_name,
                        "keyword": kw,
                        "search_rank": rank,
                        "clicked_brand_1": "BrandA" if random.random() > 0.3 else "BrandB",
                        "clicked_asin_1": random.choice(DEMO_ASINS),
                        "click_share_1": round(random.uniform(0.01, 0.40), 2),
                        "reported_date": business_date,
                        "collection_type": config.collection_type or "Daily",
                    })

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"demo_aba_{shop_name.replace(' ', '_')}_{ts}.xlsx"
                filepath = output_dir / filename
                pd.DataFrame(rows).to_excel(filepath, index=False)

                n = len(rows)
                total_rows += n
                self.add_record(shop_name, "SUCCESS", n, "", int(time.time() - t0), shop["platform"])

            except Exception as e:
                self.add_record(shop_name, "FAILED", 0, str(e), int(time.time() - t0), shop["platform"])

        summary = self.build_summary(total_rows=total_rows)
        summary.task_name = "ABA关键词采集(Demo)"
        return summary
