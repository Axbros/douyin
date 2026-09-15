ALTER TABLE tasks
    DROP INDEX idx_tasks_room_status,
    CHANGE COLUMN room_id live_url VARCHAR(500) NOT NULL,
    ADD KEY idx_tasks_live_url_status (live_url(191), status);

ALTER TABLE comment_logs
    CHANGE COLUMN room_id live_url VARCHAR(500) NOT NULL;

UPDATE tasks
SET live_url = CONCAT('https://live.douyin.com/', live_url)
WHERE live_url NOT LIKE 'http%';

UPDATE comment_logs
SET live_url = CONCAT('https://live.douyin.com/', live_url)
WHERE live_url NOT LIKE 'http%';
