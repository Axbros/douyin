ALTER TABLE users
    ADD COLUMN expires_at DATETIME(3) NULL COMMENT '客户服务到期时间，管理员为空' AFTER last_login_at;
