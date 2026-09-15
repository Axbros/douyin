# Linux 部署与进程管理

## 浏览器是否需要桌面 UI

服务器无需安装桌面环境。登录 Worker、账号浏览器 Worker 和任务 Worker 都通过 `xvfb-run` 启动。Xvfb 会为 Chromium 提供一块虚拟屏幕，Playwright 仍以 `headless=false` 的有界面模式运行，因此可以正常：

- 打开抖音页面、点击登录和评论控件；
- 从 DOM 读取二维码图片并返回管理后台；
- 保存 Cookie、localStorage 和 Playwright storage state；
- 使用已保存的账号状态进入指定直播间。

账号登录数据经过 Fernet 加密后保存在 MySQL，不依赖真实显示器。服务器重启后，Worker 会从数据库恢复账号状态。VNC 只适合排查网页改版或风控页面，不是正常运行的依赖。

## 进程划分

| 服务 | 数量 | 作用 |
| --- | ---: | --- |
| FastAPI | 1 | 接口、鉴权、任务和账号管理 |
| 扫码登录 Worker | 1 | 创建浏览器、提取二维码、保存登录状态 |
| 账号浏览器 Worker | 1 | 管理员临时唤醒或关闭账号浏览器 |
| 任务 Worker | 可配置 | 领取任务，控制账号进入直播间并评论 |
| Nginx | 1 | 托管前端并反向代理 `/api` |

每个任务 Worker 会在 `workers` 表登记稳定的服务器和实例编号，持续上报心跳。Worker 异常退出后，API 会释放它占用的抖音账号，避免账号一直显示忙碌。

## 首次部署

推荐 Ubuntu 22.04/24.04。先安装 Node.js 20.19+ 或 22.12+、MySQL 8 和 Redis 7。MySQL、Redis 可以运行在同一台服务器，也可以使用独立服务。

1. 将仓库放到服务器，例如 `/root/douyin-source`。
2. 在仓库的 `backend/.env` 写入生产数据库、Redis、JWT 和 Fernet 密钥。该文件不会进入 Git。
3. 将 [schema.mysql.sql](../docs/schema.mysql.sql) 导入生产 MySQL。已有数据库按 `backend/migrations` 中尚未执行的迁移升级。
4. 执行安装：

   ```bash
   cd /root/douyin-source
   sudo bash deploy/install_linux.sh
   ```

安装脚本会把程序同步到 `/opt/douyin`，安装 Python 和 Chromium 依赖，构建前端，安装 systemd/Nginx/logrotate 配置并启动服务。

`backend/.env` 中的任务 Worker 数量示例：

```dotenv
TASK_WORKER_PROCESSES=2
PLAYWRIGHT_HEADLESS=false
```

修改数量后，启用新增实例：

```bash
sudo systemctl enable --now douyin-task-worker@3.service
```

减少数量时关闭多余实例：

```bash
sudo systemctl disable --now douyin-task-worker@3.service
```

## 健康检查与日志

- `/healthz`：只检查 API 进程是否存活。
- `/readyz`：同时检查 MySQL 和 Redis，任一不可用时返回 HTTP 503。
- 管理后台“服务器监控”：显示主机资源、MySQL、Redis、登录 Worker、浏览器 Worker 和在线任务 Worker 数量。

常用命令：

```bash
curl http://127.0.0.1/readyz
sudo systemctl status douyin-api douyin-login-worker douyin-browser-worker 'douyin-task-worker@*'
sudo tail -f /var/log/douyin/api.log
sudo tail -f /var/log/douyin/task-worker-1.log
```

日志每天轮转，单个文件达到 100MB 也会提前轮转，保留 14 份并压缩。

## 更新版本

停止服务后重新运行安装脚本即可同步代码、更新依赖、重新构建并启动。生产环境变更数据库前先备份 MySQL。

## 本机开发

macOS 不需要 Xvfb，浏览器会直接显示。项目根目录可使用：

```bash
./scripts/services.sh start
./scripts/services.sh status
./scripts/services.sh stop
```

日志保存在 `.runtime/logs`，PID 保存在 `.runtime/pids`，两者都已加入 `.gitignore`。`start` 会启动真实任务 Worker；数据库存在待执行任务时，它会开始进入直播间并评论。
