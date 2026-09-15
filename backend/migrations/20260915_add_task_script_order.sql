ALTER TABLE tasks
    ADD COLUMN script_order_mode VARCHAR(20) NOT NULL DEFAULT 'random'
        COMMENT 'random/sequential' AFTER billing_amount_cents;

ALTER TABLE task_scripts
    ADD COLUMN sort_order INT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '任务内话术顺序，从0开始' AFTER script_id;
