-- Run once on existing installations before restarting the API and workers.
CREATE TABLE proxies (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    port INT NOT NULL,
    username VARCHAR(255) NOT NULL,
    encrypted_password MEDIUMBLOB NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    max_accounts INT NOT NULL DEFAULT 3,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at DATETIME(3) NULL,
    KEY idx_proxies_available (deleted_at, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

ALTER TABLE douyin_accounts
    ADD COLUMN proxy_id BIGINT UNSIGNED NULL AFTER owner_customer_id,
    ADD KEY idx_douyin_accounts_proxy (proxy_id),
    ADD CONSTRAINT fk_douyin_accounts_proxy FOREIGN KEY (proxy_id) REFERENCES proxies(id);
