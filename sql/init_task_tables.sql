-- ============================================================
-- RPA任务调度系统 — 数据库表
-- 功能：任务配置 / 任务队列 / 采集记录 / 汇总报告 / 异常日志 / AI知识库
-- 适用：分布式RPA采集调度 + AI告警分析
-- ============================================================

-- === P0: 任务配置表 ===
CREATE TABLE IF NOT EXISTS `task_config` (
    `id`              INT AUTO_INCREMENT PRIMARY KEY,
    `task_name`       VARCHAR(128) NOT NULL COMMENT '任务名称',
    `script_name`     VARCHAR(128) NOT NULL COMMENT '要执行的Python脚本名',
    `platform`        VARCHAR(32)  DEFAULT NULL COMMENT '平台 (Amazon/Walmart/Shopee)',
    `country`         VARCHAR(8)   DEFAULT NULL COMMENT '国家代码 (US/DE/JP)',
    `shop_name`       VARCHAR(128) DEFAULT NULL COMMENT '店铺名称(NULL=全部店铺)',
    `collect_type`    VARCHAR(16)  DEFAULT '日度' COMMENT '日度/周度/月度',
    `business_date`   VARCHAR(16)  DEFAULT NULL COMMENT '业务日期 YYYY-MM-DD',
    `executor_ip`     VARCHAR(32)  DEFAULT NULL COMMENT '指定执行机器IP',
    `schedule_type`   VARCHAR(16)  NOT NULL DEFAULT 'now' COMMENT 'now=立即 cron=定时',
    `cron_expression` VARCHAR(64)  DEFAULT NULL COMMENT 'Cron表达式',
    `timeout_sec`     INT          DEFAULT 3600 COMMENT '超时时间(秒)',
    `priority`        INT          DEFAULT 1 COMMENT '优先级(越小越优先)',
    `retry_count`     INT          DEFAULT 0 COMMENT '失败重试次数',
    `status`          TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=启用 0=停用',
    `create_time`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`     DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA任务配置表';

-- === P0: 任务队列表 ===
CREATE TABLE IF NOT EXISTS `task_queue` (
    `id`              INT AUTO_INCREMENT PRIMARY KEY,
    `config_id`       INT          NOT NULL COMMENT '关联task_config.id',
    `task_uuid`       VARCHAR(64)  NOT NULL COMMENT '任务实例UUID',
    `script_name`     VARCHAR(128) NOT NULL COMMENT '执行脚本名',
    `task_params`     TEXT         COMMENT '执行参数JSON',
    `task_status`     VARCHAR(16)  NOT NULL DEFAULT 'PENDING'
                      COMMENT 'PENDING→RECEIVED→RUNNING→SUCCESS/FAILED/TIMEOUT',
    `executor_ip`     VARCHAR(32)  DEFAULT NULL COMMENT '实际执行机器IP',
    `start_time`      DATETIME     DEFAULT NULL,
    `end_time`        DATETIME     DEFAULT NULL,
    `duration_sec`    INT          DEFAULT NULL COMMENT '执行耗时(秒)',
    `error_message`   TEXT         DEFAULT NULL,
    `total_shops`     INT          DEFAULT 0 COMMENT '总店铺数',
    `success_shops`   INT          DEFAULT 0 COMMENT '成功店铺数',
    `failed_shops`    INT          DEFAULT 0 COMMENT '失败店铺数',
    `no_data_shops`   INT          DEFAULT 0 COMMENT '无数据店铺数',
    `create_time`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_uuid` (`task_uuid`),
    INDEX `idx_status` (`task_status`),
    INDEX `idx_create` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA任务队列表';

-- === P0: 采集记录表(单店铺明细) ===
CREATE TABLE IF NOT EXISTS `task_record` (
    `id`              INT AUTO_INCREMENT PRIMARY KEY,
    `task_uuid`       VARCHAR(64)  NOT NULL COMMENT '关联task_queue.task_uuid',
    `shop_name`       VARCHAR(128) NOT NULL COMMENT '店铺名称',
    `platform`        VARCHAR(32)  DEFAULT '' COMMENT '平台',
    `script_name`     VARCHAR(128) DEFAULT '' COMMENT '采集脚本',
    `ods_table`       VARCHAR(128) DEFAULT '' COMMENT '目标ODS表',
    `collect_start`   DATETIME     DEFAULT NULL COMMENT '采集开始时间',
    `collect_end`     DATETIME     DEFAULT NULL COMMENT '采集结束时间',
    `collect_result`  VARCHAR(16)  DEFAULT 'SUCCESS'
                      COMMENT '采集结果: SUCCESS/FAILED/NO_DATA',
    `row_count`       INT          DEFAULT 0 COMMENT '采集数据行数',
    `error_message`   TEXT         DEFAULT NULL COMMENT '错误信息',
    `duration_sec`    INT          DEFAULT NULL COMMENT '耗时(秒)',
    `create_time`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_task_uuid` (`task_uuid`),
    INDEX `idx_shop` (`shop_name`),
    INDEX `idx_result` (`collect_result`),
    INDEX `idx_create` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采集执行记录表(单店铺)';

-- === P0: 汇总报告表(任务级) ===
CREATE TABLE IF NOT EXISTS `task_summary` (
    `id`              INT AUTO_INCREMENT PRIMARY KEY,
    `task_uuid`       VARCHAR(64) NOT NULL COMMENT '关联task_queue.task_uuid',
    `task_name`       VARCHAR(128) DEFAULT '' COMMENT '任务名称',
    `total_shops`     INT         DEFAULT 0 COMMENT '总店铺数',
    `success_shops`   INT         DEFAULT 0 COMMENT '成功数',
    `failed_shops`    INT         DEFAULT 0 COMMENT '失败数',
    `no_data_shops`   INT         DEFAULT 0 COMMENT '无数据数',
    `total_rows`      INT         DEFAULT 0 COMMENT '采集总行数',
    `total_duration`  INT         DEFAULT 0 COMMENT '总耗时(秒)',
    `success_rate`    DECIMAL(5,2) DEFAULT 0 COMMENT '成功率%',
    `summary_json`    TEXT        COMMENT '详细汇总JSON',
    `create_time`     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_uuid` (`task_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采集汇总报告表(任务级)';

-- === P3: 异常日志表 ===
CREATE TABLE IF NOT EXISTS `rpa_exception_log` (
    `id`              INT AUTO_INCREMENT PRIMARY KEY,
    `trace_id`        VARCHAR(32)  DEFAULT '' COMMENT '全链路追踪ID',
    `task_uuid`       VARCHAR(64)  DEFAULT '' COMMENT '关联任务UUID',
    `exception_type`  VARCHAR(128) NOT NULL COMMENT '异常类型(登录失败/数据为空/元素定位失败/网络超时/DB异常)',
    `error_message`   TEXT         COMMENT '原始错误信息',
    `file_name`       VARCHAR(255) DEFAULT '' COMMENT '触发异常的文件名',
    `shop_name`       VARCHAR(128) DEFAULT '' COMMENT '关联店铺',
    `ai_analysis`     TEXT         COMMENT 'AI分析结果JSON',
    `ai_root_cause`   TEXT         COMMENT 'AI推测根因',
    `ai_suggestion`   TEXT         COMMENT 'AI推荐方案',
    `ai_business_impact` TEXT      COMMENT 'AI评估业务影响',
    `ai_notification` TEXT         COMMENT 'AI生成的业务通报',
    `alert_status`    VARCHAR(16)  DEFAULT 'pending' COMMENT 'pending/resolved/ignored',
    `resolved_by`     VARCHAR(64)  DEFAULT '' COMMENT '处理人',
    `resolved_at`     DATETIME     DEFAULT NULL,
    `create_time`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_type` (`exception_type`),
    INDEX `idx_trace` (`trace_id`),
    INDEX `idx_task` (`task_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA异常日志表';

-- === P3: AI告警知识库 ===
CREATE TABLE IF NOT EXISTS `alert_knowledge_base` (
    `id`              INT AUTO_INCREMENT PRIMARY KEY,
    `exception_type`  VARCHAR(128) NOT NULL COMMENT '异常类型',
    `error_pattern`   VARCHAR(256) DEFAULT NULL COMMENT '错误关键字匹配模式',
    `root_cause`      TEXT         COMMENT '根因分析',
    `solution`        TEXT         NOT NULL COMMENT '解决方案',
    `business_impact` TEXT         COMMENT '业务影响描述',
    `occur_count`     INT          DEFAULT 1 COMMENT '发生次数',
    `last_occur_time` DATETIME     DEFAULT NULL COMMENT '最近发生时间',
    `create_time`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI告警知识库';

-- 预置知识库数据
INSERT INTO `alert_knowledge_base` (`exception_type`, `error_pattern`, `root_cause`, `solution`, `business_impact`) VALUES
('登录失败', 'login failed|cookie expired|authentication', 'Cookie过期或登录态失效', '1.重新登录刷新Cookie\n2.检查账号密码是否变更\n3.确认未触发平台风控', '该店铺今日数据将全部缺失，需24h内补采'),
('元素定位失败', 'element not found|selector|timeout waiting', '页面结构变更或加载超时', '1.检查页面是否正常打开(截图确认)\n2.更新选择器配置\n3.增加等待时间重试', '该字段数据可能缺失，影响下游报表完整性'),
('数据为空', 'empty|no data|0 rows', '目标页面无数据或数据未更新', '1.确认业务日期是否有数据产生\n2.检查是否为平台数据延迟\n3.标记为无数据,不再重试', '低影响，该店铺当日无业务数据'),
('网络超时', 'timeout|connection|network', '网络波动或代理异常', '1.检查机器网络连接\n2.切换代理重试\n3.降低并发数', '可能导致部分店铺数据缺失'),
('DB异常', 'database|mysql|connection refused', '数据库服务异常', '1.检查MySQL服务状态\n2.确认连接数和连接池配置\n3.重启数据库服务', '高影响，所有入库操作受影响');
