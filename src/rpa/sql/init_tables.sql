-- ============================================================
-- RPA数据采集系统 — 运维监控表结构初始化
-- 对应白皮书 第6章：数据质量监控与运维体系
--           第7章：告警与运维自动化
-- 作者：YourName
-- 日期：2026-03-28
-- ============================================================

-- ============================================================
-- 1. ETL处理状态追踪表（断点续传核心表）
-- 对应白皮书 3.3.4 节：断点续传机制
-- 状态机: PROCESSING → SUCCESS / FAILED
-- ============================================================
CREATE TABLE IF NOT EXISTS `etl_process_log` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `trace_id` VARCHAR(32) NOT NULL COMMENT '全链路追踪ID，关联日志',
    `file_name` VARCHAR(255) NOT NULL COMMENT '处理的文件名',
    `ods_table` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '目标ODS表',
    `dw_table` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '目标DW表',
    `status` ENUM('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED') NOT NULL DEFAULT 'PENDING' COMMENT '处理状态',
    `row_count` INT DEFAULT 0 COMMENT '成功入库行数',
    `dirty_count` INT DEFAULT 0 COMMENT '拦截脏数据行数',
    `error_msg` TEXT COMMENT '错误信息（失败时记录）',
    `start_time` DATETIME COMMENT '处理开始时间',
    `end_time` DATETIME COMMENT '处理完成时间',
    INDEX `idx_trace_id` (`trace_id`),
    INDEX `idx_file_name` (`file_name`),
    INDEX `idx_status` (`status`),
    INDEX `idx_start_time` (`start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETL处理状态追踪表（断点续传）';


-- ============================================================
-- 2. 数据质量监控规则配置表
-- 对应白皮书 6.2.1 节：30+条校验规则，配置表管理
-- 规则类型: EXISTENCE(存在性) / CONSISTENCY(一致性) / COMPLETENESS(完整性)
-- 严重程度: BLOCK(阻断) / WARN(警告) / INFO(信息)
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_quality_rules` (
    `rule_id` INT AUTO_INCREMENT PRIMARY KEY,
    `rule_name` VARCHAR(128) NOT NULL COMMENT '规则名称',
    `rule_type` ENUM('EXISTENCE', 'CONSISTENCY', 'COMPLETENESS') NOT NULL COMMENT '校验层次(L1/L2/L3)',
    `check_sql` TEXT COMMENT '校验SQL（动态执行）',
    `threshold` VARCHAR(64) COMMENT '阈值（如 ">0", "<50%" 等）',
    `severity` ENUM('BLOCK', 'WARN', 'INFO') NOT NULL DEFAULT 'WARN' COMMENT '严重程度',
    `target_table` VARCHAR(128) COMMENT '目标监测表',
    `description` VARCHAR(512) COMMENT '规则描述',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用 1=是 0=否',
    `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_type` (`rule_type`),
    INDEX `idx_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据质量监控规则配置表';


-- 预置校验规则（代码层只做MySQL做不到的校验）
-- L0: 文件存在性/可读性 — 代码层
-- L1: 数据量骤降检测 — 代码层（对比7日均值）
-- L2: 维表白名单 — 代码层（业务规则，FK无法表达status过滤）
-- 字段类型/非空/唯一/格式 → 全部由MySQL Schema兜底
INSERT INTO `data_quality_rules` (`rule_name`, `rule_type`, `check_sql`, `threshold`, `severity`, `target_table`, `description`) VALUES
('店铺今日数据存在性', 'EXISTENCE', NULL, '>0', 'WARN', 'ods_*', '每个店铺今日应有至少1条采集数据'),
('数据量骤降检测', 'EXISTENCE', NULL, '降幅<50%', 'WARN', 'ods_*', '今日数据量对比7日均值降幅超过50%触发告警'),
('跨表ODS-DW一致性', 'CONSISTENCY', NULL, '=0', 'WARN', 'ods_*', 'ODS层有数据超过1小时未聚合到DW');


-- ============================================================
-- 3. 告警记录表
-- 对应白皮书 7.1/7.2 节：告警发现与通知
-- 告警等级: P0-紧急 / P1-重要 / P2-一般
-- ============================================================
CREATE TABLE IF NOT EXISTS `rpa_alert_log` (
    `alert_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `trace_id` VARCHAR(32) NOT NULL COMMENT '关联的处理追踪ID',
    `alert_level` ENUM('P0', 'P1', 'P2') NOT NULL COMMENT '告警等级 P0紧急/P1重要/P2一般',
    `alert_type` VARCHAR(64) NOT NULL COMMENT '告警类型: ETL阻断/数据校验WARN/脏数据/处理异常/低频标记',
    `title` VARCHAR(256) NOT NULL COMMENT '告警标题',
    `content` TEXT COMMENT '告警详情',
    `is_sent` TINYINT(1) DEFAULT 0 COMMENT '是否已推送 1=是 0=否',
    `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '告警时间',
    INDEX `idx_trace_id` (`trace_id`),
    INDEX `idx_level` (`alert_level`),
    INDEX `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警记录表';


-- ============================================================
-- 4. 低频账号管理表
-- 对应白皮书 7.3 节：低频账号降频机制
-- 触发条件: 连续7天无数据
-- 执行动作: 标记为低频，监控频率降至每周二一次
-- 恢复条件: 数据恢复后自动移出低频名单
-- ============================================================
CREATE TABLE IF NOT EXISTS `low_frequency_shops` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `shop_name` VARCHAR(128) NOT NULL COMMENT '店铺名称',
    `platform` VARCHAR(64) DEFAULT '' COMMENT '来源平台',
    `consecutive_empty_days` INT DEFAULT 0 COMMENT '连续无数据天数',
    `is_low_freq` TINYINT(1) DEFAULT 0 COMMENT '是否低频 1=是 0=否',
    `last_data_date` DATETIME COMMENT '最近一次有数据的日期',
    `next_check_date` DATE COMMENT '下次检查日期（低频期间每周二）',
    `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_shop_name` (`shop_name`),
    INDEX `idx_is_low_freq` (`is_low_freq`),
    INDEX `idx_next_check_date` (`next_check_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='低频账号管理表';


-- ============================================================
-- 5. 数据校验结果记录表
-- 对应白皮书 6.2.2 节：校验失败 → 运维看板记录
-- 校验层次: L1-存在性 / L2-一致性 / L3-完整性
-- 校验结果: PASS / WARN / BLOCK
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_validation_log` (
    `validation_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `trace_id` VARCHAR(32) NOT NULL COMMENT '关联的处理追踪ID',
    `file_name` VARCHAR(255) NOT NULL COMMENT '校验的文件名',
    `check_layer` VARCHAR(32) NOT NULL COMMENT '校验层次(L1-存在性/L2-一致性/L3-完整性)',
    `check_rule` VARCHAR(128) NOT NULL COMMENT '校验规则名称',
    `check_result` ENUM('PASS', 'WARN', 'BLOCK') NOT NULL COMMENT '校验结果',
    `detail` TEXT COMMENT '校验详情（含数据指标）',
    `check_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '校验时间',
    INDEX `idx_trace_id` (`trace_id`),
    INDEX `idx_file_name` (`file_name`),
    INDEX `idx_check_result` (`check_result`),
    INDEX `idx_check_time` (`check_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验结果记录表';


-- ============================================================
-- ============================================================
-- 6. 路由表增强：增加 DW 加工SQL 字段
-- 对应白皮书 4.2 节：模板化接入，DW加工逻辑配置化
-- 理念：数据开发工程师在 DW 层编写加工SQL，配置到路由表即可
--       ODS → DW 的转换由配置驱动，不需要改 Python 代码
-- ============================================================
-- ALTER TABLE `etl_path_route` ADD COLUMN `dw_transform_sql` TEXT COMMENT 'ODS→DW加工SQL（支持{ods_table}占位符）' AFTER `target_dw_table`;
-- ALTER TABLE `etl_route_config` ADD COLUMN `dw_transform_sql` TEXT COMMENT 'ODS→DW加工SQL（支持{ods_table}占位符）' AFTER `target_dw_table`;

-- 示例：协议表DW加工SQL
-- UPDATE etl_path_route SET dw_transform_sql =
-- 'INSERT INTO dw_agreement_daily (account, crawl_date, total_records, distinct_count, delete_count, update_time)
--  SELECT account, DATE(crawl_time), COUNT(DISTINCT agreement_id), COUNT(DISTINCT asin),
--         SUM(CASE WHEN delete_flag=1 THEN 1 ELSE 0 END), NOW()
--  FROM {ods_table} WHERE etl_status=0
--  GROUP BY account, DATE(crawl_time)
--  ON DUPLICATE KEY UPDATE total_records=VALUES(total_records), distinct_count=VALUES(distinct_count),
--                          delete_count=VALUES(delete_count), update_time=NOW()'
-- WHERE path_pattern='agreement';

-- 示例：订单表DW加工SQL
-- UPDATE etl_path_route SET dw_transform_sql =
-- 'INSERT INTO dw_order_daily_summary (shop_name, shop_id, platform, order_date, total_orders, total_quantity, total_amount, asin_count)
--  SELECT o.shop_name, d.shop_id, d.platform, o.order_date,
--         COUNT(DISTINCT o.po_number), SUM(o.quantity), SUM(o.amount), COUNT(DISTINCT o.asin)
--  FROM {ods_table} o INNER JOIN dim_shop_info d ON o.shop_name=d.shop_name
--  WHERE o.etl_status=0 GROUP BY o.shop_name, d.shop_id, d.platform, o.order_date
--  ON DUPLICATE KEY UPDATE total_orders=VALUES(total_orders), total_quantity=VALUES(total_quantity),
--                          total_amount=VALUES(total_amount), asin_count=VALUES(asin_count), update_time=NOW()'
-- WHERE path_pattern='Order';

-- ============================================================
-- 7. 脏数据日志表（增强版：添加 trace_id 关联）
-- 在原有 rpa_dirty_data_log 基础上增强
-- ============================================================
-- ALTER TABLE `rpa_dirty_data_log` ADD COLUMN `trace_id` VARCHAR(32) DEFAULT '' COMMENT '关联处理追踪ID' AFTER `id`;
-- ALTER TABLE `rpa_dirty_data_log` ADD COLUMN `platform` VARCHAR(64) DEFAULT '' COMMENT '来源平台' AFTER `shop_name`;
