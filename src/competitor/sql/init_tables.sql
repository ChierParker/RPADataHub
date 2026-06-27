-- ============================================================
-- CompetitorWatch 竞品竞价采集系统 — 数据库初始化 SQL
-- 适用数据库：MySQL 5.7+ / 8.0
-- 字符集：utf8mb4
-- 分层模型：ODS（操作数据层）→ DW（数据仓库层）
-- 创建时间：2026-06-14
-- ============================================================

-- 确保使用正确数据库
-- CREATE DATABASE IF NOT EXISTS ecomiq_rpa DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE ecomiq_rpa;

-- ============================================================
-- 1. 竞品配置表（维表层）
-- 存储每个竞品的监控配置，包括平台、关键词、ASIN等
-- ============================================================
CREATE TABLE IF NOT EXISTS competitor_config (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    competitor_name VARCHAR(256) NOT NULL COMMENT '竞品名称/品牌名',
    keywords TEXT NOT NULL COMMENT '搜索关键词（JSON数组格式，如["anker charger","power bank"]）',
    asin_list TEXT COMMENT 'Amazon ASIN列表（JSON数组格式，如["B0XXXXXXX","B0YYYYYYY"]）',
    walmart_id VARCHAR(64) COMMENT 'Walmart商品ID',
    jd_sku VARCHAR(64) COMMENT '京东SKU',
    taobao_url VARCHAR(512) COMMENT '淘宝商品链接',
    region ENUM('international', 'domestic') NOT NULL COMMENT '板块：international=国际, domestic=国内',
    platform VARCHAR(64) DEFAULT 'amazon' COMMENT '目标平台（amazon/walmart/shopee/taobao/jd/pdd）',
    monitor_price TINYINT(1) DEFAULT 1 COMMENT '是否监控价格：1=是, 0=否',
    monitor_ad TINYINT(1) DEFAULT 1 COMMENT '是否监控广告位：1=是, 0=否',
    monitor_ranking TINYINT(1) DEFAULT 1 COMMENT '是否监控排名：1=是, 0=否',
    crawl_interval_hours INT DEFAULT 24 COMMENT '采集间隔（小时），默认每天一次',
    status TINYINT(1) DEFAULT 1 COMMENT '状态：1=启用, 0=停用',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    INDEX idx_region (region),
    INDEX idx_platform (platform),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='竞品配置表';

-- ============================================================
-- 2. 价格快照表（ODS层）
-- 存储每次采集的原始价格快照数据
-- 对应技术方案 4.2 节
-- ============================================================
CREATE TABLE IF NOT EXISTS ods_price_snapshot (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    competitor_id INT NOT NULL COMMENT '关联 competitor_config.id',
    task_uuid VARCHAR(64) COMMENT '采集任务UUID，用于链路追踪',
    platform VARCHAR(32) NOT NULL COMMENT '平台名称（amazon/walmart/shopee/taobao/jd/pdd）',
    product_url VARCHAR(512) COMMENT '商品详情页链接',
    title VARCHAR(512) COMMENT '商品标题',
    current_price DECIMAL(10,2) COMMENT '当前售价',
    original_price DECIMAL(10,2) COMMENT '原价/划线价',
    currency VARCHAR(8) DEFAULT 'USD' COMMENT '币种（USD/CNY/EUR等）',
    rank_position INT COMMENT '自然搜索排名位置',
    is_ad TINYINT(1) DEFAULT 0 COMMENT '是否为广告位：1=是, 0=否',
    ad_type VARCHAR(32) COMMENT '广告类型（sponsored/banner/recommended）',
    review_count INT COMMENT '评论数',
    rating FLOAT COMMENT '评分（1-5）',
    seller_name VARCHAR(256) COMMENT '卖家名称',
    snapshot_time DATETIME NOT NULL COMMENT '快照采集时间',
    raw_json TEXT COMMENT '原始采集数据（JSON格式，用于后续回溯）',
    etl_status TINYINT(1) DEFAULT 0 COMMENT 'ETL加工状态：0=未加工, 1=已加工',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    KEY idx_competitor (competitor_id),
    KEY idx_platform (platform),
    KEY idx_snapshot_time (snapshot_time),
    KEY idx_etl_status (etl_status),
    KEY idx_task_uuid (task_uuid),
    CONSTRAINT fk_snapshot_competitor FOREIGN KEY (competitor_id) REFERENCES competitor_config(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS层：竞品价格快照表';

-- ============================================================
-- 3. 竞品日聚合表（DW层）
-- 按天汇总每个竞品的价格/排名/广告位信息
-- 对应技术方案 4.3 节
-- ============================================================
CREATE TABLE IF NOT EXISTS dw_competitor_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    competitor_id INT NOT NULL COMMENT '关联 competitor_config.id',
    platform VARCHAR(32) NOT NULL COMMENT '平台名称',
    snapshot_date DATE NOT NULL COMMENT '快照日期',
    min_price DECIMAL(10,2) COMMENT '当日最低价',
    max_price DECIMAL(10,2) COMMENT '当日最高价',
    avg_price DECIMAL(10,2) COMMENT '当日均价',
    median_price DECIMAL(10,2) COMMENT '当日中位数价格',
    price_volatility DECIMAL(10,4) COMMENT '价格波动率（标准差/均值）',
    snapshot_count INT DEFAULT 0 COMMENT '当日采集次数',
    ad_count INT DEFAULT 0 COMMENT '当日广告位出现次数',
    avg_rank DECIMAL(5,1) COMMENT '当日平均排名',
    min_rank INT COMMENT '当日最佳排名',
    total_reviews INT COMMENT '累计评论数',
    rating_avg FLOAT COMMENT '当日平均评分',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    UNIQUE KEY uk_competitor_date (competitor_id, platform, snapshot_date),
    CONSTRAINT fk_daily_competitor FOREIGN KEY (competitor_id) REFERENCES competitor_config(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DW层：竞品日聚合表';

-- ============================================================
-- 4. AI分析报告表（应用层）
-- 存储AI生成的竞品分析报告
-- ============================================================
CREATE TABLE IF NOT EXISTS competitor_report (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    competitor_id INT NOT NULL COMMENT '关联 competitor_config.id',
    report_type ENUM('daily', 'weekly', 'anomaly') NOT NULL COMMENT '报告类型：daily=日报, weekly=周报, anomaly=异常即时报告',
    report_date DATE NOT NULL COMMENT '报告日期',
    content TEXT NOT NULL COMMENT 'AI生成的报告正文（Markdown格式）',
    summary VARCHAR(512) COMMENT '报告摘要（一句话总结）',
    alert_level ENUM('info', 'warning', 'critical') DEFAULT 'info' COMMENT '告警级别',
    is_sent TINYINT(1) DEFAULT 0 COMMENT '是否已推送（Bark/邮件）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    KEY idx_competitor_date (competitor_id, report_date),
    KEY idx_report_type (report_type),
    KEY idx_alert (alert_level, is_sent),
    CONSTRAINT fk_report_competitor FOREIGN KEY (competitor_id) REFERENCES competitor_config(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI分析报告表';
