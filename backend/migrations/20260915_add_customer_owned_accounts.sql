ALTER TABLE users
  ADD COLUMN extra_douyin_account_quota INT NOT NULL DEFAULT 0 AFTER expires_at;

ALTER TABLE douyin_accounts
  ADD COLUMN ownership_type VARCHAR(20) NOT NULL DEFAULT 'platform' AFTER assigned_customer_id,
  ADD COLUMN owner_customer_id BIGINT UNSIGNED NULL AFTER ownership_type,
  ADD INDEX idx_douyin_accounts_owner (owner_customer_id, ownership_type, deleted_at),
  ADD CONSTRAINT fk_douyin_accounts_owner FOREIGN KEY (owner_customer_id) REFERENCES users(id);

ALTER TABLE tasks
  ADD COLUMN account_source VARCHAR(20) NOT NULL DEFAULT 'platform' AFTER target_account_count,
  ADD COLUMN billing_amount_cents INT UNSIGNED NOT NULL DEFAULT 0 AFTER account_source,
  ADD INDEX idx_tasks_account_source (account_source);

INSERT INTO system_settings (setting_key, setting_value, created_at, updated_at)
VALUES
  ('platform.default_customer_account_quota', JSON_OBJECT('value', 3), CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3)),
  ('platform.customer_account_task_price_cents', JSON_OBJECT('value', 1000), CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3)),
  ('platform.platform_account_task_price_cents', JSON_OBJECT('value', 3000), CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3))
ON DUPLICATE KEY UPDATE setting_value = setting_value;
