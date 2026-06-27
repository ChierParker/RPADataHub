"""
ServiceIQ 智能客服模块 — 数据库初始化脚本 (MVP)
================================================
创建 cs_messages / cs_conversations / cs_templates 三张表
运行: python src/main/sql/setup_service_iq.py
"""
import sys
import os

# 确保能导入 RPADataHub 配置
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "RPADataHub"))
from config.settings import get_config
import pymysql

cfg = get_config()
db_config = cfg.database.as_dict()
print(f"[ServiceIQ] 连接数据库 {db_config['host']}:{db_config['port']}/{db_config['database']}...")

conn = pymysql.connect(**db_config)
cur = conn.cursor()

# ============================================================
# 三张 MVP 核心表 DDL
# ============================================================
SQL_TABLES = [
    # 1. 客服消息表
    """
    CREATE TABLE IF NOT EXISTS cs_messages (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        platform        VARCHAR(20)   NOT NULL COMMENT '消息来源: Amazon/Walmart/Shopee/1688/manual_import',
        platform_msg_id VARCHAR(100)  DEFAULT NULL COMMENT '平台消息唯一ID（手动导入时可为空）',
        shop_name       VARCHAR(100)  DEFAULT NULL COMMENT '关联店铺',
        customer_name   VARCHAR(200)  DEFAULT NULL COMMENT '客户名称',
        customer_email  VARCHAR(200)  DEFAULT NULL,
        order_id        VARCHAR(100)  DEFAULT NULL COMMENT '关联订单号',
        asin            VARCHAR(50)   DEFAULT NULL COMMENT '关联产品ASIN',
        subject         VARCHAR(500)  DEFAULT NULL COMMENT '消息主题',
        content         TEXT          NOT NULL COMMENT '消息正文',
        priority        ENUM('urgent','normal','low') DEFAULT 'normal' COMMENT '优先级',
        status          ENUM('pending','replied','closed','spam') DEFAULT 'pending' COMMENT '处理状态',
        category        VARCHAR(50)   DEFAULT NULL COMMENT '分类: return/logistics/inquiry/complaint/other',
        sentiment       VARCHAR(30)   DEFAULT NULL COMMENT 'AI情感分析: positive/neutral/negative/angry',
        ai_intent       VARCHAR(50)   DEFAULT NULL COMMENT 'AI识别的意图',
        ai_confidence   DECIMAL(4,2)  DEFAULT NULL COMMENT 'AI置信度 0-100',
        agent_id        INT           DEFAULT NULL COMMENT '处理客服ID',
        first_reply_at  DATETIME      DEFAULT NULL COMMENT '首次回复时间',
        closed_at       DATETIME      DEFAULT NULL COMMENT '关闭时间',
        tags            JSON          DEFAULT NULL COMMENT '标签数组, 如 ["urgent","vip"]',
        received_at     DATETIME      NOT NULL COMMENT '消息接收时间',
        created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_platform_msg (platform, platform_msg_id),
        INDEX idx_status (status),
        INDEX idx_priority (priority),
        INDEX idx_category (category),
        INDEX idx_received (received_at),
        INDEX idx_shop (shop_name),
        INDEX idx_order (order_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客服消息表';
    """,

    # 2. 对话回复表
    """
    CREATE TABLE IF NOT EXISTS cs_conversations (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        message_id      INT           NOT NULL COMMENT '关联消息ID',
        reply_content   TEXT          NOT NULL COMMENT '回复内容',
        reply_type      ENUM('manual','template','ai_generated','auto_rule') DEFAULT 'manual' COMMENT '回复类型',
        template_id     INT           DEFAULT NULL COMMENT '使用的模板ID',
        agent_id        INT           DEFAULT NULL COMMENT '操作客服ID',
        is_ai_assisted  TINYINT(1)    DEFAULT 0 COMMENT '是否AI辅助',
        sent_status     ENUM('pending','sent','failed') DEFAULT 'sent' COMMENT '发送状态',
        created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (message_id) REFERENCES cs_messages(id) ON DELETE CASCADE,
        INDEX idx_message (message_id),
        INDEX idx_agent (agent_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话回复表';
    """,

    # 3. 回复模板表
    """
    CREATE TABLE IF NOT EXISTS cs_templates (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        name            VARCHAR(200)  NOT NULL COMMENT '模板名称',
        category        VARCHAR(50)   DEFAULT 'custom' COMMENT '分类',
        language        VARCHAR(20)   DEFAULT 'en' COMMENT '语言',
        platform        VARCHAR(100)  DEFAULT NULL COMMENT '适用平台,逗号分隔',
        content         TEXT          NOT NULL COMMENT '模板内容（含{{变量}}）',
        usage_count     INT           DEFAULT 0 COMMENT '使用次数',
        is_active       TINYINT(1)    DEFAULT 1 COMMENT '启用/停用',
        created_by      VARCHAR(50)   DEFAULT NULL,
        created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_category (category),
        INDEX idx_active (is_active),
        INDEX idx_usage (usage_count)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回复模板表';
    """,

    # 4. 知识库表（含文档路径和语义向量）
    """
    CREATE TABLE IF NOT EXISTS cs_knowledge (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        question        VARCHAR(500)  DEFAULT NULL COMMENT 'FAQ问题（纯文本FAQ时使用）',
        answer          TEXT          DEFAULT NULL COMMENT 'FAQ答案',
        category        VARCHAR(50)   DEFAULT 'product' COMMENT '分类',
        keywords        VARCHAR(500)  DEFAULT NULL COMMENT '搜索关键词,逗号分隔',
        language        VARCHAR(20)   DEFAULT 'zh' COMMENT '语言',
        asin            VARCHAR(50)   DEFAULT NULL COMMENT '关联产品',
        usage_count     INT           DEFAULT 0 COMMENT '被引用次数',
        satisfaction    DECIMAL(4,2)  DEFAULT NULL COMMENT '满意率',
        document_path   VARCHAR(500)  DEFAULT NULL COMMENT '上传文档路径（NULL=纯文本FAQ）',
        document_name   VARCHAR(200)  DEFAULT NULL COMMENT '原始文件名',
        document_size   INT           DEFAULT NULL COMMENT '文件大小(bytes)',
        content_text    LONGTEXT      DEFAULT NULL COMMENT '文档解析后的全文内容',
        content_vector  TEXT          DEFAULT NULL COMMENT '语义向量JSON（预留DeepSeek Embedding）',
        is_published    TINYINT(1)    DEFAULT 1 COMMENT '已发布/草稿',
        created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_category (category),
        INDEX idx_asin (asin),
        INDEX idx_published (is_published),
    FULLTEXT INDEX ft_qa (question, answer, keywords, content_text) WITH PARSER ngram
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='FAQ知识库表';
    """
]

for stmt in SQL_TABLES:
    stmt = stmt.strip()
    table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[1].split(" (")[0] if "CREATE TABLE IF NOT EXISTS" in stmt else "unknown"
    try:
        cur.execute(stmt)
        print(f"  ✓ {table_name}")
    except pymysql.err.OperationalError as e:
        if e.args[0] == 1050:
            print(f"  ○ {table_name} (已存在)")
        else:
            print(f"  ✗ {table_name} ERROR: {e}")

conn.commit()

# ============================================================
# 验证
# ============================================================
print("\n[ServiceIQ] 表验证:")
for table in ['cs_messages', 'cs_conversations', 'cs_templates']:
    cur.execute(f"SHOW TABLES LIKE '{table}'")
    exists = bool(cur.fetchone())
    print(f"  {table}: {'✓ 已创建' if exists else '✗ 缺失'}")

# ============================================================
# 预置默认回复模板
# ============================================================
cur.execute("SELECT COUNT(*) as cnt FROM cs_templates")
template_count = cur.fetchone()[0]
if template_count == 0:
    default_templates = [
        ("退货确认模板", "return", "en", "Amazon,Walmart,Shopee",
         "Dear {{customer_name}},\n\nThank you for contacting us regarding your order {{order_id}}. We are sorry to hear that you are not satisfied with the product {{product_name}}.\n\nWe offer a free return and full refund of {{order_amount}}. Here's how:\n1. Pack the item in its original packaging\n2. Use the prepaid return label we'll send\n3. Drop off at any carrier location\n\nOnce we receive the returned item, a full refund will be processed within 3-5 business days.\n\nIf you have any further questions, please don't hesitate to contact us.\n\nBest regards,\n{{shop_name}} Customer Service Team",
         "admin"),

        ("物流查询回复", "logistics", "zh", "Amazon,Walmart,Shopee",
         "尊敬的 {{customer_name}}，\n\n感谢您联系 {{shop_name}} 客服团队。\n\n关于您查询的订单 {{order_id}}，我们正在为您核实物流状态。快递追踪号将在发货后24小时内更新至您的订单详情页。\n\n如果您有任何其他疑问，请随时联系我们。\n\n此致\n{{shop_name}} 客服团队",
         "admin"),

        ("道歉补偿模板", "complaint", "en", "Amazon,Walmart,Shopee",
         "Dear {{customer_name}},\n\nWe sincerely apologize for the inconvenience caused by your recent experience with our product {{product_name}}.\n\nWe take your feedback very seriously. To make things right, we would like to offer you:\n• A full refund of {{order_amount}}\n• Or a free replacement with express shipping\n\nPlease let us know which option you prefer and we'll process it immediately.\n\nYour satisfaction is our top priority.\n\nBest regards,\n{{shop_name}} Customer Service Team",
         "admin"),

        ("产品咨询模板", "inquiry", "en", "Amazon,Walmart,Shopee",
         "Dear {{customer_name}},\n\nThank you for your interest in our product {{product_name}}!\n\nHere are the details you asked about:\n[Product information will be provided here]\n\nIf you have any other questions, feel free to reach out. We're happy to help!\n\nBest regards,\n{{shop_name}} Customer Service Team",
         "admin"),

        ("好评感谢模板", "other", "en", "Amazon,Walmart,Shopee",
         "Dear {{customer_name}},\n\nThank you so much for your kind words! We're thrilled to hear that you're enjoying {{product_name}}.\n\nYour support means the world to us. If there's anything else we can do for you, please don't hesitate to let us know.\n\nWe'd also greatly appreciate it if you could share your experience by leaving a review on the product page.\n\nWarm regards,\n{{shop_name}} Customer Service Team",
         "admin"),
    ]
    for name, category, lang, platform, content, created_by in default_templates:
        cur.execute(
            "INSERT INTO cs_templates (name, category, language, platform, content, usage_count, is_active, created_by) "
            "VALUES (%s, %s, %s, %s, %s, 0, 1, %s)",
            (name, category, lang, platform, content, created_by)
        )
    conn.commit()
    print(f"\n[ServiceIQ] 已预置 {len(default_templates)} 个默认回复模板")

cur.close()
conn.close()
print("\n[ServiceIQ] 数据库初始化完成!")