"""
ServiceIQ — 模拟数据生成器 (MVP)
================================
生成约 50 条模拟客服消息，用于测试收件箱功能
运行: python -m src.main.generate_mock_data
"""
import sys
import os
import random
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "RPADataHub"))
from config.settings import get_config
import pymysql

cfg = get_config()
db_config = cfg.database.as_dict()

# ============================================================
# 模拟数据模板
# ============================================================
CUSTOMERS = [
    {"name": "John D.", "email": "john.d@email.com"},
    {"name": "Maria S.", "email": "maria.s@email.com"},
    {"name": "Lisa W.", "email": "lisa.w@email.com"},
    {"name": "Robert K.", "email": "robert.k@email.com"},
    {"name": "Emily C.", "email": "emily.c@email.com"},
    {"name": "David L.", "email": "david.l@email.com"},
    {"name": "Sophia M.", "email": "sophia.m@email.com"},
    {"name": "James T.", "email": "james.t@email.com"},
    {"name": "Olivia P.", "email": "olivia.p@email.com"},
    {"name": "Daniel R.", "email": "daniel.r@email.com"},
    {"name": "王小明", "email": "wangxm@email.com"},
    {"name": "张丽华", "email": "zhanglihua@email.com"},
]

SHOPS = ["EcomIQ-US", "EcomIQ-EU", "EcomIQ-Global"]
ASINS = ["B0XXXX001", "B0XXXX002", "B0XXXX003", "B0XXXX004", "B0XXXX005",
         "B0XXXX006", "B0XXXX007", "B0XXXX008"]
PRODUCTS = ["Wireless Earbuds Pro", "Smart Watch X1", "USB-C Hub 7-in-1", "Bluetooth Speaker Mini",
            "Phone Case Armor", "Fast Charger 65W", "Keyboard Mechanical", "LED Desk Lamp"]

# 消息场景
SCENARIOS = {
    "return": {
        "category": "return",
        "subjects": ["Return Request", "Refund Request", "Item damaged", "Wrong item received", "Exchange request"],
        "templates": [
            "I received the product {product} but it arrived damaged. The box was crushed and the item has scratches. I want to return it and get a full refund. Order #{order_id}.",
            "I ordered {product} but received a completely different item. Please help me exchange it for the correct one. Order #{order_id}.",
            "The {product} I received is not working properly. It keeps disconnecting every few minutes. I would like a refund please. Order #{order_id}.",
            "I changed my mind about the {product}. It's still sealed in the original packaging. Can I return it for a refund? Order #{order_id}.",
            "The size of {product} doesn't fit. I need to exchange it for a larger size. Order #{order_id}.",
            "Product {product} has a manufacturing defect. The button is loose and the color is different from the listing photos. Order #{order_id}.",
            "I received the {product} 3 days ago and it already stopped working. Very disappointed. I want a full refund. Order #{order_id}.",
        ],
        "priority_weights": [0.5, 0.3, 0.2],  # urgent, normal, low
    },
    "logistics": {
        "category": "logistics",
        "subjects": ["Shipping Status", "Where is my order?", "Tracking number request", "Delivery delay", "Estimated delivery"],
        "templates": [
            "I placed my order #{order_id} 5 days ago and it still shows 'Processing'. When will it ship? I need the {product} urgently.",
            "Can you provide the tracking number for order #{order_id}? I haven't received any shipping confirmation yet.",
            "My package for order #{order_id} was supposed to arrive yesterday but it's not here. Can you check what happened?",
            "The tracking shows my package was delivered but I didn't receive anything. Order #{order_id} for {product}. Please investigate.",
            "I need to change the shipping address for order #{order_id}. The current address is wrong.",
            "How long does standard shipping usually take for {product}? I'm in California.",
        ],
        "priority_weights": [0.2, 0.5, 0.3],
    },
    "inquiry": {
        "category": "inquiry",
        "subjects": ["Product question", "Compatibility check", "Size inquiry", "Material question", "Usage question"],
        "templates": [
            "Hi, does the {product} work with iPhone 15? I want to make sure it's compatible before purchasing.",
            "What material is the {product} made of? Is it waterproof? I plan to use it outdoors.",
            "Can you tell me the exact dimensions of the {product}? I need to check if it fits in my bag.",
            "Does the {product} come with a warranty? How long is the warranty period?",
            "Is the {product} available in black color? I only see blue and white options on the listing.",
            "Can I use the {product} while it's charging? The manual doesn't mention this.",
            "What's the battery life of the {product}? I need something that lasts all day.",
        ],
        "priority_weights": [0.05, 0.7, 0.25],
    },
    "complaint": {
        "category": "complaint",
        "subjects": ["Complaint about service", "Poor product quality", "Bad experience", "Not as described", "Unhappy customer"],
        "templates": [
            "I am extremely disappointed with the {product}. The quality is terrible compared to what was advertised. This is false advertising. Order #{order_id}.",
            "Your customer service is the worst I've ever experienced. I've been trying to reach someone for 3 days about my order #{order_id}. Completely unacceptable!",
            "The {product} arrived late, was poorly packaged, and looks nothing like the photos. I want a full refund and I will be leaving a negative review. Order #{order_id}.",
            "I've been a loyal customer for years but this experience has been terrible. The {product} broke after 2 uses. Order #{order_id}.",
        ],
        "priority_weights": [0.8, 0.15, 0.05],
    },
    "other": {
        "category": "other",
        "subjects": ["Thank you", "Great product", "Review question", "General feedback", "Other"],
        "templates": [
            "Just wanted to say the {product} is amazing! Best purchase I've made this year. Thank you!",
            "Love the {product}! I've already recommended it to my friends. Great quality and fast shipping.",
            "Is there a loyalty program or discount for repeat customers? I want to buy another {product}.",
            "Can I get an invoice for my order #{order_id}? I need it for my business records.",
            "Do you ship to Canada? I want to order the {product} but I'm not sure about international shipping.",
        ],
        "priority_weights": [0.0, 0.3, 0.7],
    },
}

PLATFORMS = ["Amazon", "Walmart", "Shopee", "1688"]
PLATFORM_WEIGHTS = [0.45, 0.25, 0.2, 0.1]

def generate_mock_messages(count=50):
    """生成模拟消息数据"""
    messages = []
    now = datetime.now()

    for i in range(count):
        # 随机选择场景
        scenario_key = random.choices(
            list(SCENARIOS.keys()),
            weights=[0.25, 0.20, 0.25, 0.10, 0.20],
            k=1
        )[0]
        scenario = SCENARIOS[scenario_key]

        # 随机选择客户和产品
        customer = random.choice(CUSTOMERS)
        product = random.choice(PRODUCTS)
        asin = random.choice(ASINS)
        shop = random.choice(SHOPS)
        platform = random.choices(PLATFORMS, weights=PLATFORM_WEIGHTS, k=1)[0]

        # 生成订单号
        order_id = f"#{random.randint(100000, 999999)}"

        # 选择模板并填充
        template = random.choice(scenario["templates"])
        content = template.format(product=product, order_id=order_id)

        # 优先级
        priority = random.choices(["urgent", "normal", "low"], weights=scenario["priority_weights"], k=1)[0]

        # 生成时间：过去 14 天内随机分布
        days_ago = random.randint(0, 14)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        received_at = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

        # 随机一些已回复/已关闭的消息
        status_weights = [0.4, 0.35, 0.2, 0.05]  # pending, replied, closed, spam
        status = random.choices(["pending", "replied", "closed", "spam"], weights=status_weights, k=1)[0]

        first_reply_at = None
        closed_at = None
        if status in ("replied", "closed"):
            first_reply_at = received_at + timedelta(minutes=random.randint(5, 120))
        if status == "closed":
            closed_at = first_reply_at + timedelta(hours=random.randint(1, 48))

        # 约 40% 的消息已做 AI 分析
        sentiment = None
        ai_intent = None
        if random.random() < 0.4:
            sentiment_map = {
                "return": random.choices(["negative", "angry"], weights=[0.6, 0.4])[0],
                "logistics": random.choices(["neutral", "negative"], weights=[0.5, 0.5])[0],
                "inquiry": "neutral",
                "complaint": random.choices(["angry", "negative"], weights=[0.7, 0.3])[0],
                "other": random.choice(["positive", "neutral"]),
            }
            sentiment = sentiment_map.get(scenario_key, "neutral")
            ai_intent = scenario_key

        # 生成 platform_msg_id
        platform_msg_id = f"{platform.lower()}-msg-{random.randint(10000, 99999)}"

        messages.append({
            "platform": platform,
            "platform_msg_id": platform_msg_id,
            "shop_name": shop,
            "customer_name": customer["name"],
            "customer_email": customer["email"],
            "order_id": order_id,
            "asin": asin,
            "subject": random.choice(scenario["subjects"]),
            "content": content,
            "priority": priority,
            "status": status,
            "category": scenario["category"],
            "sentiment": sentiment,
            "ai_intent": ai_intent,
            "ai_confidence": round(random.uniform(0.70, 0.98), 2) if sentiment else None,
            "first_reply_at": first_reply_at,
            "closed_at": closed_at,
            "received_at": received_at,
            "tags": json.dumps(["vip"] if random.random() < 0.1 else []),
        })

    # 按时间倒序排列
    messages.sort(key=lambda x: x["received_at"], reverse=True)
    return messages


def insert_mock_data():
    """将模拟数据插入数据库"""
    # 先检查是否已有数据
    conn = pymysql.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM cs_messages")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"[ServiceIQ] cs_messages 表中已有 {existing} 条数据，跳过插入")
        cur.close()
        conn.close()
        return

    messages = generate_mock_messages(50)
    insert_sql = """
        INSERT INTO cs_messages
        (platform, platform_msg_id, shop_name, customer_name, customer_email,
         order_id, asin, subject, content, priority, status, category,
         sentiment, ai_intent, ai_confidence, first_reply_at, closed_at,
         tags, received_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    inserted = 0
    for msg in messages:
        try:
            cur.execute(insert_sql, (
                msg["platform"], msg["platform_msg_id"], msg["shop_name"],
                msg["customer_name"], msg["customer_email"],
                msg["order_id"], msg["asin"], msg["subject"], msg["content"],
                msg["priority"], msg["status"], msg["category"],
                msg["sentiment"], msg["ai_intent"], msg["ai_confidence"],
                msg["first_reply_at"], msg["closed_at"],
                msg["tags"], msg["received_at"]
            ))
            inserted += 1
        except pymysql.err.IntegrityError:
            # 跳过重复的 platform_msg_id
            pass

    conn.commit()

    # 为一些已回复的消息添加模拟回复
    cur.execute("SELECT id, status, customer_name FROM cs_messages WHERE status IN ('replied','closed') LIMIT 20")
    replied = cur.fetchall()
    reply_templates = [
        "Dear {name}, thank you for your message. We are looking into your issue and will get back to you shortly.",
        "Hi {name}, we have processed your request. Please allow 24-48 hours for the update to reflect in your account.",
        "Dear {name}, we apologize for the inconvenience. A replacement has been initiated for your order.",
        "Hello {name}, your refund has been approved and will be processed within 3-5 business days.",
        "Hi {name}, your tracking number will be sent to your email within 24 hours. Thank you for your patience!",
    ]
    for msg_id, status, name in replied:
        reply_content = random.choice(reply_templates).format(name=name)
        reply_type = random.choice(["manual", "template"])
        cur.execute(
            "INSERT INTO cs_conversations (message_id, reply_content, reply_type, is_ai_assisted) "
            "VALUES (%s, %s, %s, %s)",
            (msg_id, reply_content, reply_type, 1 if random.random() < 0.3 else 0)
        )
    conn.commit()

    cur.close()
    conn.close()

    # 统计
    print(f"[ServiceIQ] 已插入 {inserted} 条模拟消息")
    statuses = {}
    for m in messages:
        statuses[m["status"]] = statuses.get(m["status"], 0) + 1
    print(f"  状态分布: {statuses}")
    categories = {}
    for m in messages:
        categories[m["category"]] = categories.get(m["category"], 0) + 1
    print(f"  分类分布: {categories}")
    print(f"  已添加 {len(replied)} 条模拟回复")
    print("\n[ServiceIQ] 模拟数据生成完成!")


if __name__ == "__main__":
    insert_mock_data()