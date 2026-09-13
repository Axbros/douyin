# 抖音多账号直播评论平台：第一版系统设计

## 1. 产品边界

第一版服务端以当前仓库的 Playwright 浏览器控制和评论发送能力为核心，暂时关闭 SenseVoice、主播语音转录和自动弹幕分析。系统只处理：账号登录、账号分配、进入指定直播间、审核通过的话术随机选择、评论发送、任务控制和审计日志。

客户端不配置抖音账号。抖音账号由管理员添加并登录，平台将可用账号分配给客户任务。客户只能管理自己提交的话术和直播任务。

## 2. 部署拓扑

```text
客户 H5 / 管理员 PC Web
             |
          Nginx / HTTPS
             |
        FastAPI API 服务
        |        |        |
 PostgreSQL  Redis   对象存储/加密状态
                         |
                  Playwright Worker 集群
                  |       |       |
                worker-1 worker-2 ...
```

- FastAPI 负责认证、权限、CRUD、审核、任务控制和 WebSocket/SSE 状态推送。
- PostgreSQL 是业务数据唯一来源，YAML 只保留开发环境默认配置。
- Redis 用于任务队列、分布式锁、心跳、短期状态和限流。
- Worker 负责启动 Playwright、恢复账号登录状态、进入直播间和发送评论。
- 第一版可以在一台服务器运行多个 worker 进程，后续再扩展到多台服务器。

## 3. 客户 H5

### 登录

- 手机号/邮箱 + 密码登录。
- JWT 短期 access token + refresh token。
- 支持退出登录和修改密码。

### 话术

- 新建、编辑、删除、启用/停用话术。
- 支持文本粘贴和 TXT 导入。
- 每条话术单独保存，可选权重。
- 状态：`draft`、`pending_review`、`approved`、`rejected`、`disabled`。
- 只有审核通过的话术才能用于新建任务。
- 被拒绝时展示管理员填写的原因。

### 任务

- 新建任务：直播间 ID、选择已审核话术、发送间隔、目标账号数量。
- 默认分配数量由后台配置，初始值为 3。
- 查看任务状态：`pending`、`running`、`paused`、`stopped`、`failed`。
- 暂停、恢复、停止任务。
- 查看任务日志：时间、直播间 ID、执行账号、评论内容、结果和失败原因。
- 客户只能看到自己的任务、话术和日志，不能看到账号 Cookie 或其他客户数据。

## 4. 管理端 PC Web

### 抖音账号

- 添加账号：创建登录会话，后端返回二维码图片或二维码数据，管理员界面展示二维码。
- 扫码成功后，Worker 捕获完整 Playwright `storage_state`，加密后保存。
- 增删改查、启用/禁用账号。
- 查看账号状态：`unlogged`、`available`、`assigned`、`running`、`risk_controlled`、`error`、`disabled`。
- 查看登录时间、最近心跳、当前任务、当前直播间、最近错误。
- 查看账号日志：登录、风控提示、评论成功、评论失败、浏览器异常和人工操作。
- 禁用账号后不再分配新任务，正在运行的任务按策略停止或替换账号。

### 浏览器/Worker 监控

- 查看 Worker 在线状态、PID、版本、账号数、CPU、内存和最近心跳。
- 查看每个账号对应 Browser Context/Page 是否正常。
- 当前实现优先使用 Redis 心跳；管理端通过 WebSocket 或 SSE 接收状态更新。
- 若 Playwright WebSocket 用于浏览器控制，则展示控制连接状态和最后心跳；不把浏览器调试端口暴露到公网。

### 任务和账号分配

- 查看全部客户任务、来源客户、直播间 ID、任务状态和分配账号。
- 客户创建任务后，事务内锁定并随机选择 N 个闲置账号，N 默认 3，可后台配置。
- 管理员可以手动添加、移除任务执行账号。
- 账号必须满足：启用、登录有效、未被其他互斥任务占用、所属平台正确。
- 账号分配使用 PostgreSQL 行锁或 Redis 分布式锁，避免多个任务抢到同一个账号。
- 闲置账号不足时任务保持 `pending`，明确显示缺少数量。

### 审核和敏感词

- 审核客户话术：通过、拒绝、填写原因。
- 维护敏感词：新增、编辑、删除、启用/停用、批量导入。
- 评论发送前进行敏感词匹配；命中则不发送，记录 `blocked_by_sensitive_word` 日志。
- 敏感词匹配在 Worker 发送前执行，服务端也可在任务入队前预检，避免绕过。

## 5. 数据库模型

核心表：

```text
users
- id, role(customer/admin), login, password_hash, status, created_at

douyin_accounts
- id, display_name, status, encrypted_storage_state
- assigned_customer_id(nullable), last_login_at, last_heartbeat_at
- current_worker_id, risk_code, risk_message, created_at, updated_at

workers
- id, hostname, process_id, status, version
- last_heartbeat_at, cpu_percent, memory_bytes, created_at

scripts
- id, customer_id, title, content, weight, status
- review_reason, reviewed_by, reviewed_at, created_at, updated_at

tasks
- id, customer_id, room_id, status
- target_account_count, min_interval, max_interval
- started_at, paused_at, stopped_at, created_at, updated_at

task_scripts
- task_id, script_id

task_accounts
- task_id, account_id, status, assigned_at, removed_at

comment_logs
- id, task_id, account_id, room_id, content
- result, failure_code, sensitive_word, sent_at, created_at

account_logs
- id, account_id, worker_id, event_type, detail, created_at

sensitive_words
- id, word, match_type, enabled, created_by, created_at, updated_at

system_settings
- key, value_json, updated_by, updated_at
```

账号 `encrypted_storage_state` 必须使用服务端密钥加密，数据库备份不能直接恢复登录状态。密码只保存 Argon2id/bcrypt 哈希，日志禁止写入 Cookie、二维码 token 或完整请求参数。

## 6. 登录和二维码流程

1. 管理员点击“添加抖音账号”。
2. FastAPI 创建 `account_login_sessions` 记录并投递登录任务到 Redis。
3. Worker 启动隔离的 Playwright Context，打开抖音登录页。
4. Worker 捕获二维码，上传短期有效图片或返回受保护的二维码数据。
5. 管理端通过 WebSocket/SSE 收到二维码和状态。
6. 管理员扫码后，Worker 检查登录状态并保存完整 `storage_state`。
7. 服务端将账号状态改为 `available`，记录登录日志。
8. 二维码会话超时、重复使用或登录失败时立即失效。

二维码接口只返回短期会话引用，不把抖音 Cookie 返回给前端。

## 7. 任务执行流程

1. 客户提交直播间 ID和话术列表。
2. API 校验话术全部为 `approved`，否则拒绝创建任务。
3. PostgreSQL 事务创建任务并锁定 N 个可用账号；不足则任务进入 `pending`。
4. 调度器为每个任务账号投递 Worker 作业。
5. Worker 解密并恢复账号状态，进入 `https://live.douyin.com/{room_id}`。
6. 按任务的随机间隔从话术池选取一条，进行敏感词检查。
7. 未命中敏感词才发送；无论成功、失败或拦截都写 `comment_logs`。
8. 暂停时停止发送并保留账号分配；停止时关闭页面、释放账号并结束作业。
9. 账号异常或风控时暂停该账号，记录原因；任务按配置等待替换账号或进入人工处理。

## 8. Worker 设计

Worker 不直接读取客户 YAML。它从 Redis 获取任务，从 API/数据库获取任务快照和加密账号状态。

每个账号使用独立 Browser Context；账号之间不共享 Cookie、localStorage、页面和任务状态。Worker 必须实现：

- 启动、停止、暂停、恢复。
- 每 5～10 秒上报心跳。
- 账号登录失效检测。
- 评论发送结果回传。
- 页面崩溃和浏览器崩溃自动重试。
- 优雅退出，释放账号锁。
- 单账号任务超时和最大重试次数。

第一版不加载 SenseVoice，也不启动音频转录任务。当前仓库中的评论发送器和抖音页面控制逻辑可迁移为 Worker 核心模块。

## 9. API 分组

```text
POST   /api/auth/login
POST   /api/auth/refresh

GET    /api/customer/scripts
POST   /api/customer/scripts
PATCH  /api/customer/scripts/{id}
POST   /api/customer/scripts/import

GET    /api/customer/tasks
POST   /api/customer/tasks
POST   /api/customer/tasks/{id}/pause
POST   /api/customer/tasks/{id}/resume
POST   /api/customer/tasks/{id}/stop
GET    /api/customer/tasks/{id}/logs

POST   /api/admin/douyin-accounts/login-session
GET    /api/admin/douyin-accounts/login-session/{id}/events
GET    /api/admin/douyin-accounts
PATCH  /api/admin/douyin-accounts/{id}
DELETE /api/admin/douyin-accounts/{id}
GET    /api/admin/douyin-accounts/{id}/logs

GET    /api/admin/workers
GET    /api/admin/tasks
POST   /api/admin/tasks/{id}/accounts
DELETE /api/admin/tasks/{id}/accounts/{account_id}

GET    /api/admin/scripts/review-queue
POST   /api/admin/scripts/{id}/approve
POST   /api/admin/scripts/{id}/reject
GET    /api/admin/sensitive-words
POST   /api/admin/sensitive-words
PATCH  /api/admin/sensitive-words/{id}
DELETE /api/admin/sensitive-words/{id}
```

## 10. 第一版交付拆分

### 服务端

- FastAPI 项目、JWT 认证、RBAC。
- PostgreSQL migrations 和 SQLAlchemy/SQLModel 模型。
- Redis 队列、任务锁、账号锁和心跳。
- 账号登录会话、二维码事件流和加密 storage state。
- 客户话术、审核、任务、账号分配和日志 API。
- 敏感词预检和 Worker 发送前拦截。

### Worker

- 从队列领取任务。
- 恢复账号浏览器状态并进入直播间。
- 随机选择话术并发送。
- 上报心跳、状态、发送结果和异常日志。
- 优雅暂停、停止、重试和账号释放。

### 管理端 PC Web

- 管理员登录。
- 抖音账号扫码添加和状态页。
- 账号启停、编辑、删除和日志。
- Worker/浏览器监控。
- 任务列表和手动账号分配。
- 话术审核和敏感词管理。

### 客户 H5

- 客户登录。
- 话术导入、编辑和审核状态。
- 直播任务创建、暂停、恢复和停止。
- 任务日志和评论结果查询。

### 运维交付

- Docker Compose：API、PostgreSQL、Redis、Worker、Nginx。
- Alembic 数据库迁移。
- `.env.example`、密钥生成说明和备份恢复说明。
- 基础监控、结构化日志和错误告警。
- 5/10/20 个账号的压力测试报告。

## 11. 建议开发顺序

先完成单管理员、单客户、单 Worker 的完整闭环：扫码登录、保存账号、提交审核话术、创建一个直播任务、进入直播间、发送评论、记录日志。闭环稳定后，再加入 3 个账号随机分配、手动调度、账号替换和多 Worker 扩展。这样可以优先验证最容易出问题的登录状态恢复、抖音页面稳定性和评论结果回执。
