ALTER TABLE subscription_plans DROP COLUMN extra_account_price_cents;

INSERT INTO system_settings (setting_key, setting_value, created_at, updated_at)
VALUES ('platform.extra_account_quota_price_cents', JSON_OBJECT('value', 0), CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3))
ON DUPLICATE KEY UPDATE deleted_at = NULL;

UPDATE purchase_orders SET status = 'pending_payment' WHERE status = 'pending';

ALTER TABLE purchase_orders
    DROP FOREIGN KEY fk_purchase_orders_reviewer,
    DROP COLUMN reviewed_by,
    DROP COLUMN reviewed_at,
    DROP COLUMN note;
