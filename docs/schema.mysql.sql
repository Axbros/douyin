-- 抖音直播评论平台第一版数据库结构
-- 目标：MySQL 8.x / InnoDB / utf8mb4
-- 时间字段由应用统一写入 UTC。

CREATE DATABASE IF NOT EXISTS douyin
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE douyin;

-- 客户套餐。价格为空表示由平台线下报价，权益字段直接参与任务和账号额度校验。
CREATE TABLE subscription_plans (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(60) NOT NULL,
    tier_level INT UNSIGNED NOT NULL,
    duration_days INT UNSIGNED NOT NULL DEFAULT 30,
    base_douyin_account_quota INT UNSIGNED NOT NULL DEFAULT 3,
    platform_account_count INT UNSIGNED NOT NULL DEFAULT 3,
    max_active_tasks INT UNSIGNED NOT NULL DEFAULT 1,
    max_scripts_per_task INT UNSIGNED NOT NULL DEFAULT 100,
    price_cents BIGINT UNSIGNED NULL,
    features JSON NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_subscription_plans_code (code),
    KEY idx_subscription_plans_enabled (enabled, tier_level),
    KEY idx_subscription_plans_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO subscription_plans
    (code, name, tier_level, duration_days, base_douyin_account_quota, platform_account_count,
     max_active_tasks, max_scripts_per_task, features)
VALUES
    ('standard', '标准版', 1, 30, 3, 3, 1, 100, JSON_ARRAY('最多3个自有抖音号', '平台任务分配3个账号', '单任务最多100条话术')),
    ('advanced', '高级版', 2, 30, 5, 5, 1, 200, JSON_ARRAY('最多5个自有抖音号', '平台任务分配5个账号', '单任务最多200条话术')),
    ('ultimate', '至尊版', 3, 30, 10, 10, 1, 500, JSON_ARRAY('最多10个自有抖音号', '平台任务分配10个账号', '单任务最多500条话术'));

-- 客户和管理员账号
CREATE TABLE users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    role VARCHAR(20) NOT NULL COMMENT 'admin/customer',
    login VARCHAR(190) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT 'active/disabled',
    last_login_at DATETIME(3) NULL,
    expires_at DATETIME(3) NULL COMMENT '客户服务到期时间，管理员为空',
    extra_douyin_account_quota INT NOT NULL DEFAULT 0 COMMENT '客户额外自有抖音账号额度',
    subscription_plan_id BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_login (login),
    KEY idx_users_role_status (role, status),
    KEY idx_users_deleted_at (deleted_at),
    KEY idx_users_subscription_plan (subscription_plan_id),
    CONSTRAINT fk_users_subscription_plan FOREIGN KEY (subscription_plan_id) REFERENCES subscription_plans(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 客户套餐升级和额外账号额度购买订单。
CREATE TABLE purchase_orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no VARCHAR(40) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_type VARCHAR(30) NOT NULL COMMENT 'plan_upgrade/account_quota',
    plan_id BIGINT UNSIGNED NULL,
    quota_quantity INT UNSIGNED NULL,
    amount_cents BIGINT UNSIGNED NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending_payment' COMMENT 'pending_payment/paid/cancelled/refunded',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_purchase_orders_no (order_no),
    KEY idx_purchase_orders_customer_status (customer_id, status, created_at),
    KEY idx_purchase_orders_status (status, created_at),
    KEY idx_purchase_orders_deleted_at (deleted_at),
    CONSTRAINT fk_purchase_orders_customer FOREIGN KEY (customer_id) REFERENCES users(id),
    CONSTRAINT fk_purchase_orders_plan FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 执行 Playwright 的 Worker 进程
CREATE TABLE workers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    worker_key VARCHAR(100) NOT NULL,
    hostname VARCHAR(255) NOT NULL,
    process_id INT UNSIGNED NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'offline' COMMENT 'online/offline/draining/error',
    version VARCHAR(50) NULL,
    cpu_percent DECIMAL(6,2) NULL,
    memory_bytes BIGINT UNSIGNED NULL,
    last_heartbeat_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_workers_key (worker_key),
    KEY idx_workers_status_heartbeat (status, last_heartbeat_at),
    KEY idx_workers_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 平台账号与客户自有账号。storage_state 必须由应用层加密后写入。
CREATE TABLE douyin_accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    display_name VARCHAR(100) NOT NULL,
    account_uid VARCHAR(100) NULL,
    assigned_customer_id BIGINT UNSIGNED NULL,
    ownership_type VARCHAR(20) NOT NULL DEFAULT 'platform' COMMENT 'platform/customer',
    owner_customer_id BIGINT UNSIGNED NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'unlogged' COMMENT 'unlogged/available/assigned/running/risk_controlled/error/disabled',
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    encrypted_storage_state MEDIUMBLOB NULL,
    storage_state_version INT UNSIGNED NOT NULL DEFAULT 1,
    last_login_at DATETIME(3) NULL,
    last_heartbeat_at DATETIME(3) NULL,
    current_worker_id BIGINT UNSIGNED NULL,
    current_task_id BIGINT UNSIGNED NULL,
    risk_code VARCHAR(100) NULL,
    risk_message VARCHAR(500) NULL,
    last_error VARCHAR(1000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_douyin_account_uid (account_uid),
    KEY idx_douyin_accounts_available (enabled, status, last_heartbeat_at),
    KEY idx_douyin_accounts_customer (assigned_customer_id),
    KEY idx_douyin_accounts_owner (owner_customer_id, ownership_type, deleted_at),
    KEY idx_douyin_accounts_worker (current_worker_id),
    KEY idx_douyin_accounts_deleted_at (deleted_at),
    CONSTRAINT fk_douyin_account_customer FOREIGN KEY (assigned_customer_id) REFERENCES users(id),
    CONSTRAINT fk_douyin_accounts_owner FOREIGN KEY (owner_customer_id) REFERENCES users(id),
    CONSTRAINT fk_douyin_account_worker FOREIGN KEY (current_worker_id) REFERENCES workers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 管理员添加账号时的短期扫码会话。二维码原文和 token 不写入业务日志。
CREATE TABLE account_login_sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_id BIGINT UNSIGNED NOT NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    session_token_hash CHAR(64) NOT NULL,
    qr_payload MEDIUMTEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'waiting' COMMENT 'waiting/method_required/method_processing/password_required/password_verifying/verify_required/verifying/success/expired/failed/cancelled',
    expires_at DATETIME(3) NOT NULL,
    scanned_at DATETIME(3) NULL,
    completed_at DATETIME(3) NULL,
    failure_reason VARCHAR(500) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_login_session_token (session_token_hash),
    KEY idx_login_sessions_status_expiry (status, expires_at),
    KEY idx_login_sessions_deleted_at (deleted_at),
    CONSTRAINT fk_login_session_account FOREIGN KEY (account_id) REFERENCES douyin_accounts(id),
    CONSTRAINT fk_login_session_creator FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 客户话术；必须审核通过后才能绑定任务。
CREATE TABLE scripts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(150) NOT NULL,
    content VARCHAR(500) NOT NULL,
    weight INT UNSIGNED NOT NULL DEFAULT 1,
    status VARCHAR(30) NOT NULL DEFAULT 'draft' COMMENT 'draft/pending_review/approved/rejected/disabled',
    review_reason VARCHAR(500) NULL,
    reviewed_by BIGINT UNSIGNED NULL,
    reviewed_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_scripts_customer_status (customer_id, status),
    KEY idx_scripts_review_queue (status, created_at),
    KEY idx_scripts_deleted_at (deleted_at),
    CONSTRAINT fk_scripts_customer FOREIGN KEY (customer_id) REFERENCES users(id),
    CONSTRAINT fk_scripts_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 客户提交的直播间任务。
CREATE TABLE tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    live_url VARCHAR(500) NOT NULL COMMENT '从客户粘贴的分享内容中提取的抖音直播链接',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/paused/stopped/failed',
    target_account_count INT UNSIGNED NOT NULL DEFAULT 3,
    account_source VARCHAR(20) NOT NULL DEFAULT 'platform' COMMENT 'platform/customer',
    script_order_mode VARCHAR(20) NOT NULL DEFAULT 'random' COMMENT 'random/sequential',
    min_interval_seconds INT UNSIGNED NOT NULL DEFAULT 20,
    max_interval_seconds INT UNSIGNED NOT NULL DEFAULT 50,
    started_at DATETIME(3) NULL,
    paused_at DATETIME(3) NULL,
    stopped_at DATETIME(3) NULL,
    failure_reason VARCHAR(1000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_tasks_customer_status (customer_id, status, created_at),
    KEY idx_tasks_live_url_status (live_url(191), status),
    KEY idx_tasks_account_source (account_source),
    KEY idx_tasks_deleted_at (deleted_at),
    CONSTRAINT fk_tasks_customer FOREIGN KEY (customer_id) REFERENCES users(id),
    CONSTRAINT chk_tasks_intervals CHECK (max_interval_seconds >= min_interval_seconds)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 任务使用的话术。API 创建任务时只能绑定 approved 状态的话术。
CREATE TABLE task_scripts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id BIGINT UNSIGNED NOT NULL,
    script_id BIGINT UNSIGNED NOT NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '任务内话术顺序，从0开始',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_scripts_pair (task_id, script_id),
    KEY idx_task_scripts_deleted_at (deleted_at),
    CONSTRAINT fk_task_scripts_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_task_scripts_script FOREIGN KEY (script_id) REFERENCES scripts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 任务与抖音账号的分配关系。分配/移除必须在事务中完成。
CREATE TABLE task_accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id BIGINT UNSIGNED NOT NULL,
    account_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'assigned' COMMENT 'assigned/running/paused/removed/completed/error',
    assigned_by BIGINT UNSIGNED NULL,
    assigned_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    removed_at DATETIME(3) NULL,
    last_error VARCHAR(1000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_accounts_pair (task_id, account_id),
    KEY idx_task_accounts_account_status (account_id, status),
    KEY idx_task_accounts_task_status (task_id, status),
    KEY idx_task_accounts_deleted_at (deleted_at),
    CONSTRAINT fk_task_accounts_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_task_accounts_account FOREIGN KEY (account_id) REFERENCES douyin_accounts(id),
    CONSTRAINT fk_task_accounts_assigner FOREIGN KEY (assigned_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 每次评论、敏感词拦截和失败都必须留痕。
CREATE TABLE comment_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id BIGINT UNSIGNED NOT NULL,
    account_id BIGINT UNSIGNED NOT NULL,
    live_url VARCHAR(500) NOT NULL,
    content VARCHAR(500) NOT NULL,
    result VARCHAR(40) NOT NULL COMMENT 'sent/failed/blocked_by_sensitive_word/skipped',
    failure_code VARCHAR(100) NULL,
    failure_reason VARCHAR(500) NULL,
    sensitive_word VARCHAR(255) NULL,
    platform_request_id VARCHAR(255) NULL,
    sent_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_comment_logs_task_time (task_id, created_at),
    KEY idx_comment_logs_account_time (account_id, created_at),
    KEY idx_comment_logs_result_time (result, created_at),
    KEY idx_comment_logs_deleted_at (deleted_at),
    CONSTRAINT fk_comment_logs_task FOREIGN KEY (task_id) REFERENCES tasks(id),
    CONSTRAINT fk_comment_logs_account FOREIGN KEY (account_id) REFERENCES douyin_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 账号、登录、风控和浏览器异常日志。
CREATE TABLE account_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_id BIGINT UNSIGNED NOT NULL,
    worker_id BIGINT UNSIGNED NULL,
    event_type VARCHAR(60) NOT NULL,
    detail JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_account_logs_account_time (account_id, created_at),
    KEY idx_account_logs_event_time (event_type, created_at),
    KEY idx_account_logs_deleted_at (deleted_at),
    CONSTRAINT fk_account_logs_account FOREIGN KEY (account_id) REFERENCES douyin_accounts(id),
    CONSTRAINT fk_account_logs_worker FOREIGN KEY (worker_id) REFERENCES workers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 管理员维护的敏感词。
CREATE TABLE sensitive_words (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    word VARCHAR(255) NOT NULL,
    match_type VARCHAR(20) NOT NULL DEFAULT 'contains' COMMENT 'contains/exact/regex',
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sensitive_words_word (word),
    KEY idx_sensitive_words_enabled (enabled),
    KEY idx_sensitive_words_deleted_at (deleted_at),
    CONSTRAINT fk_sensitive_words_creator FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 全局后台配置，例如默认分配账号数。
CREATE TABLE system_settings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    setting_key VARCHAR(100) NOT NULL,
    setting_value JSON NOT NULL,
    updated_by BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_system_settings_key (setting_key),
    KEY idx_system_settings_deleted_at (deleted_at),
    CONSTRAINT fk_system_settings_updater FOREIGN KEY (updated_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO system_settings (setting_key, setting_value)
VALUES
    ('platform.comment_min_interval_seconds', JSON_OBJECT('value', 5)),
    ('platform.comment_max_interval_seconds', JSON_OBJECT('value', 3600)),
    ('platform.script_bulk_import_limit', JSON_OBJECT('value', 200)),
    ('platform.qr_expire_minutes', JSON_OBJECT('value', 5)),
    ('platform.worker_heartbeat_timeout_seconds', JSON_OBJECT('value', 20)),
    ('platform.account_reclaim_seconds', JSON_OBJECT('value', 60)),
    ('platform.extra_account_quota_price_cents', JSON_OBJECT('value', 0));
