-- ============================================================
-- RPA Admin 管理平台 — 数据库表 (v2.0)
-- 功能：ETL运行看板 / 运维SQL调度 / 路由配置管理 / 告警状态管理
-- ============================================================

-- 1. 管理员用户表
CREATE TABLE IF NOT EXISTS `admin_users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(64) NOT NULL UNIQUE,
    `password_hash` VARCHAR(256) NOT NULL COMMENT 'SHA256哈希',
    `role` ENUM('admin', 'viewer') DEFAULT 'admin' COMMENT '角色',
    `is_active` TINYINT(1) DEFAULT 1,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO `admin_users` (`username`, `password_hash`, `role`) VALUES
('admin', 'SHA256_OF_YOUR_PASSWORD', 'admin');


-- 2. 运维监控SQL模板表（v2: 增加负责人）
CREATE TABLE IF NOT EXISTS `monitor_sql_templates` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(128) NOT NULL COMMENT '监控名称',
    `description` VARCHAR(512) COMMENT '监控说明',
    `sql_text` TEXT NOT NULL COMMENT '监控SQL（测试工程师编写）',
    `target_table` VARCHAR(128) COMMENT '关联表名',
    `severity` ENUM('P0', 'P1', 'P2') DEFAULT 'P1' COMMENT '异常严重程度',
    `responsible_person` VARCHAR(128) DEFAULT 'admin' COMMENT '告警负责人（可多名，逗号分隔）',
    `schedule_cron` VARCHAR(64) COMMENT '调度cron（如 0 9 * * *）',
    `is_active` TINYINT(1) DEFAULT 1,
    `created_by` VARCHAR(64) DEFAULT 'admin',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ALTER: 给已有表加负责人字段
-- ALTER TABLE `monitor_sql_templates` ADD COLUMN `responsible_person` VARCHAR(128) DEFAULT 'admin' COMMENT '告警负责人' AFTER `severity`;

-- 预置监控SQL
INSERT INTO `monitor_sql_templates` (`name`, `description`, `sql_text`, `target_table`, `severity`, `responsible_person`, `schedule_cron`) VALUES
('协议表采集完整性', '检查今天哪些店铺的协议数据未入库',
'SELECT ds.shop_name AS "店铺名称", ds.platform AS "平台", MAX(o.crawl_time) AS "最近采集时间",
 DATEDIFF(NOW(), MAX(o.crawl_time)) AS "未采集天数",
 CASE WHEN MAX(o.crawl_time) IS NULL THEN ''今日无数据''
      WHEN DATE(MAX(o.crawl_time)) < CURDATE() THEN ''采集滞后'' ELSE ''正常'' END AS "状态"
FROM dim_shop_info ds LEFT JOIN ods_agreement_raw o ON ds.shop_name = o.account AND DATE(o.crawl_time) = CURDATE()
WHERE ds.status = 1 GROUP BY ds.shop_name, ds.platform
HAVING MAX(o.crawl_time) IS NULL OR DATE(MAX(o.crawl_time)) < CURDATE() ORDER BY 未采集天数 DESC',
'ods_agreement_raw', 'P1', 'YourName', '0 9 * * *'),

('订单表采集完整性', '检查今天哪些店铺的订单数据未入库',
'SELECT ds.shop_name AS "店铺名称", ds.platform AS "平台", MAX(o.create_time) AS "最近入库时间",
 COUNT(o.id) AS "今日入库数", CASE WHEN COUNT(o.id)=0 THEN ''今日无数据'' ELSE ''正常'' END AS "状态"
FROM dim_shop_info ds LEFT JOIN ods_amazon_order_raw o ON ds.shop_name=o.shop_name AND DATE(o.create_time)=CURDATE()
WHERE ds.status=1 GROUP BY ds.shop_name, ds.platform HAVING COUNT(o.id)=0 ORDER BY ds.shop_name',
'ods_amazon_order_raw', 'P1', 'YourName', '0 9 * * *');


-- 3. 运维SQL执行结果表（v2: 增加告警状态/分类/原因/方案）
CREATE TABLE IF NOT EXISTS `monitor_sql_results` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `template_id` INT NOT NULL COMMENT '关联 monitor_sql_templates.id',
    `executed_by` VARCHAR(64) DEFAULT 'system' COMMENT '执行人',
    `exec_status` ENUM('SUCCESS', 'FAILED', 'WARN') NOT NULL COMMENT 'SQL执行状态',
    `total_rows` INT DEFAULT 0 COMMENT '异常行数',
    `result_preview` TEXT COMMENT '结果预览JSON',
    `error_msg` TEXT COMMENT '错误信息',

    -- v2 新增：告警处理状态
    `alert_status` ENUM('pending', 'resolved', 'ignored') DEFAULT 'pending' COMMENT '处理状态: 待处理/已处理/无需处理',
    `alert_category` VARCHAR(64) DEFAULT '' COMMENT '告警分类: 亚马逊登录失败/访问异常/其他/程序异常/网络异常/账号无数据',
    `error_reason` TEXT COMMENT '错误原因（人工填写）',
    `solution` TEXT COMMENT '解决方案（人工填写）',
    `resolved_by` VARCHAR(64) DEFAULT '' COMMENT '处理人',
    `resolved_at` DATETIME COMMENT '处理时间',

    `executed_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_template` (`template_id`),
    INDEX `idx_alert_status` (`alert_status`),
    INDEX `idx_executed_at` (`executed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 告警去重索引：同模板+同一天只保留最新一条
-- ALTER TABLE monitor_sql_results ADD UNIQUE INDEX uk_template_date (template_id, (CAST(executed_at AS DATE)));

-- ALTER: 给已有表加告警处理字段
-- ALTER TABLE `monitor_sql_results` ADD COLUMN `alert_status` ENUM('pending','resolved','ignored') DEFAULT 'pending' COMMENT '处理状态' AFTER `error_msg`;
-- ALTER TABLE `monitor_sql_results` ADD COLUMN `alert_category` VARCHAR(64) DEFAULT '' COMMENT '告警分类' AFTER `alert_status`;
-- ALTER TABLE `monitor_sql_results` ADD COLUMN `error_reason` TEXT COMMENT '错误原因' AFTER `alert_category`;
-- ALTER TABLE `monitor_sql_results` ADD COLUMN `solution` TEXT COMMENT '解决方案' AFTER `error_reason`;
-- ALTER TABLE `monitor_sql_results` ADD COLUMN `resolved_by` VARCHAR(64) DEFAULT '' COMMENT '处理人' AFTER `solution`;
-- ALTER TABLE `monitor_sql_results` ADD COLUMN `resolved_at` DATETIME COMMENT '处理时间' AFTER `resolved_by`;
-- ALTER TABLE `monitor_sql_results` CHANGE COLUMN `status` `exec_status` ENUM('SUCCESS','FAILED','WARN') NOT NULL COMMENT 'SQL执行状态';
