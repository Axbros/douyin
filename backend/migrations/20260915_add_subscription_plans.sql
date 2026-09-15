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
    price_cents BIGINT UNSIGNED NULL COMMENT '未配置表示由平台报价',
    extra_account_price_cents BIGINT UNSIGNED NULL COMMENT '每个额外账号额度价格，未配置表示由平台报价',
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

ALTER TABLE users
    ADD COLUMN subscription_plan_id BIGINT UNSIGNED NULL AFTER extra_douyin_account_quota,
    ADD KEY idx_users_subscription_plan (subscription_plan_id),
    ADD CONSTRAINT fk_users_subscription_plan FOREIGN KEY (subscription_plan_id) REFERENCES subscription_plans(id);

UPDATE users
SET subscription_plan_id = (SELECT id FROM subscription_plans WHERE code = 'standard')
WHERE role = 'customer' AND subscription_plan_id IS NULL;

CREATE TABLE purchase_orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no VARCHAR(40) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_type VARCHAR(30) NOT NULL COMMENT 'plan_upgrade/account_quota',
    plan_id BIGINT UNSIGNED NULL,
    quota_quantity INT UNSIGNED NULL,
    amount_cents BIGINT UNSIGNED NULL COMMENT '管理员确认的订单金额',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/rejected/cancelled',
    reviewed_by BIGINT UNSIGNED NULL,
    reviewed_at DATETIME(3) NULL,
    note VARCHAR(500) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_purchase_orders_no (order_no),
    KEY idx_purchase_orders_customer_status (customer_id, status, created_at),
    KEY idx_purchase_orders_status (status, created_at),
    KEY idx_purchase_orders_deleted_at (deleted_at),
    CONSTRAINT fk_purchase_orders_customer FOREIGN KEY (customer_id) REFERENCES users(id),
    CONSTRAINT fk_purchase_orders_plan FOREIGN KEY (plan_id) REFERENCES subscription_plans(id),
    CONSTRAINT fk_purchase_orders_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

ALTER TABLE tasks DROP COLUMN billing_amount_cents;

UPDATE system_settings
SET deleted_at = CURRENT_TIMESTAMP(3)
WHERE setting_key IN (
    'task.default_target_account_count',
    'platform.default_customer_account_quota',
    'platform.customer_account_task_price_cents',
    'platform.platform_account_task_price_cents',
    'platform.max_active_tasks_per_customer',
    'platform.max_scripts_per_task'
);
