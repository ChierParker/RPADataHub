-- ============================================================
-- RBAC 权限体系 — 用户角色 + 页面权限 + 权限审批
-- ============================================================

-- 增强 admin_users 表
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS phone VARCHAR(32) DEFAULT '' COMMENT '手机号' AFTER email;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS wechat VARCHAR(64) DEFAULT '' COMMENT '微信号' AFTER phone;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS role_id INT DEFAULT 2 COMMENT '角色ID' AFTER is_active;

-- 角色表
CREATE TABLE IF NOT EXISTS user_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL COMMENT '角色名称',
    description VARCHAR(256) DEFAULT '' COMMENT '角色描述',
    permissions TEXT NOT NULL COMMENT '权限列表JSON: ["dashboard","monitor",...]',
    is_system TINYINT(1) DEFAULT 0 COMMENT '系统角色不可删除',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 预置角色
INSERT IGNORE INTO user_roles (id,name,description,permissions,is_system) VALUES
(1,'超级管理员','全部权限','["dashboard","monitor","monitor_dashboard","health_dashboard","tasks","collection_monitor","collection_records","collection_health","bi_dashboard","business_dashboard","shops","routes","ai_assistant","task_execute","member_manage","approval_manage"]',1),
(2,'观察者','默认只读权限','["dashboard","monitor","health_dashboard","collection_records","collection_health"]',1),
(3,'运营编辑','可查看+采集+导出','["dashboard","monitor","monitor_dashboard","health_dashboard","tasks","collection_monitor","collection_records","collection_health","bi_dashboard","business_dashboard","shops","ai_assistant"]',1);

-- 权限申请表
CREATE TABLE IF NOT EXISTS permission_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '申请人ID',
    username VARCHAR(64) NOT NULL COMMENT '申请人用户名',
    requested_permissions TEXT NOT NULL COMMENT '申请的权限列表JSON',
    reason TEXT COMMENT '申请理由',
    status ENUM('pending','approved','rejected') DEFAULT 'pending',
    reviewed_by VARCHAR(64) DEFAULT '' COMMENT '审批人',
    review_comment TEXT COMMENT '审批意见',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    review_time DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 更新现有admin用户为超级管理员
UPDATE admin_users SET role_id=1 WHERE username='admin';
