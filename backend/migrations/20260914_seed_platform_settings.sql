INSERT INTO system_settings (setting_key, setting_value)
VALUES
    ('task.default_target_account_count', JSON_OBJECT('value', 3)),
    ('platform.max_active_tasks_per_customer', JSON_OBJECT('value', 1)),
    ('platform.comment_min_interval_seconds', JSON_OBJECT('value', 5)),
    ('platform.comment_max_interval_seconds', JSON_OBJECT('value', 3600)),
    ('platform.max_scripts_per_task', JSON_OBJECT('value', 100)),
    ('platform.script_bulk_import_limit', JSON_OBJECT('value', 200)),
    ('platform.qr_expire_minutes', JSON_OBJECT('value', 5)),
    ('platform.worker_heartbeat_timeout_seconds', JSON_OBJECT('value', 20)),
    ('platform.account_reclaim_seconds', JSON_OBJECT('value', 60))
ON DUPLICATE KEY UPDATE setting_key = setting_key;
