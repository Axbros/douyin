ALTER TABLE comment_logs
    ADD COLUMN failure_reason VARCHAR(500) NULL AFTER failure_code;

UPDATE comment_logs
SET failure_reason = CASE
    WHEN result = 'blocked_sensitive' THEN '评论包含敏感内容，已被系统拦截'
    WHEN result <> 'sent' THEN COALESCE(failure_code, '评论发送失败')
    ELSE NULL
END
WHERE result <> 'sent' AND failure_reason IS NULL;
