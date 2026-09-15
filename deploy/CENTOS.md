# 抖无忧 CentOS 全新服务器部署教程

本文适用于 **CentOS Stream 9 x86_64**。前端、FastAPI、MySQL、Redis、Playwright Chromium，以及扫码登录、账号浏览器和任务 Worker 全部使用 Docker Compose 运行。CentOS 宿主机无需安装 Python、Node.js、MySQL、Redis、Nginx 或桌面环境。

## 1. 服务器要求

测试环境建议至少使用 4 核 CPU、8 GB 内存和 50 GB SSD，安全组开放 TCP 22、80；配置 HTTPS 后再开放 443。正式运行多个账号时建议从 8 核、16 GB 内存起步，部署后根据同时工作的浏览器数量观察内存占用。

```bash
cat /etc/centos-release
uname -m
```

本文不适用于已经停止维护的 CentOS 7。

## 2. 安装基础工具和 Docker

```bash
ssh root@你的服务器IP
dnf update -y
dnf install -y git curl ca-certificates dnf-plugins-core openssl python3
timedatectl set-timezone Asia/Shanghai
```

清理冲突包并安装 Docker 官方版本：

```bash
dnf remove -y docker docker-client docker-client-latest docker-common \
  docker-latest docker-latest-logrotate docker-logrotate docker-engine || true
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version
docker compose version
```

## 3. 下载项目

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/Axbros/douyin.git douyin
cd /opt/douyin
```

私有仓库需要先给服务器配置 GitHub Deploy Key，再使用 `git@github.com:Axbros/douyin.git`。

## 4. 生成生产配置

```bash
cd /opt/douyin/deploy/centos
python3 - <<'PY'
from base64 import urlsafe_b64encode
from pathlib import Path
from secrets import token_bytes, token_hex

mysql_root_password = token_hex(24)
mysql_password = token_hex(24)
jwt_secret = token_hex(32)
fernet_key = urlsafe_b64encode(token_bytes(32)).decode()

Path('.env').write_text(f'''COMPOSE_PROJECT_NAME=douyin
PUBLIC_PORT=80
TZ=Asia/Shanghai

MYSQL_DATABASE=douyin
MYSQL_USER=douyin_app
MYSQL_ROOT_PASSWORD={mysql_root_password}
MYSQL_PASSWORD={mysql_password}
DATABASE_URL=mysql+asyncmy://douyin_app:{mysql_password}@mysql:3306/douyin?charset=utf8mb4

REDIS_URL=redis://redis:6379/0
JWT_SECRET={jwt_secret}
JWT_EXPIRE_MINUTES=60
STORAGE_STATE_ENCRYPTION_KEY={fernet_key}

PLAYWRIGHT_HEADLESS=false
TASK_WORKER_PROCESSES=2
''', encoding='utf-8')
PY
chmod 600 .env
```

真实密码只保存在 `.env`，该文件已被 Git 忽略。不要在后续更新中更换 `STORAGE_STATE_ENCRYPTION_KEY`，否则已保存的抖音登录状态将无法解密。

编辑 `.env` 可调整 `TASK_WORKER_PROCESSES`。它控制任务 Worker 进程数，一个 Worker 本身仍能并发处理多个任务账号。

## 5. 启动全部服务

```bash
cd /opt/douyin/deploy/centos
./manage.sh start
```

第一次构建会下载 Python 包、前端依赖和 Chromium，通常需要几分钟。随后检查：

```bash
./manage.sh status
curl http://127.0.0.1/readyz
```

正常结果应包含：

```json
{"status":"ok","database":"ok","redis":"ok"}
```

MySQL 数据卷首次创建时会自动执行 `docs/schema.mysql.sql`，无需再次手工导入。

## 6. 创建第一个管理员

```bash
cd /opt/douyin/deploy/centos
docker compose --env-file .env -f compose.yaml exec api python scripts/create_admin.py
```

按提示输入管理员登录名、显示名称和至少 8 位密码，然后访问 `http://你的服务器IP/`。管理员和客户使用同一个登录入口，系统根据角色进入对应后台。

云服务器还需在安全组放行 TCP 80。CentOS 启用了 firewalld 时执行：

```bash
firewall-cmd --permanent --add-service=http
firewall-cmd --reload
```

## 7. 验证浏览器 Worker

```bash
./manage.sh logs login-worker
./manage.sh logs browser-worker
./manage.sh logs task-worker
```

后台新增抖音账号并发起扫码登录后，`login-worker` 日志应出现 Chromium 启动、二维码已保存和检测到登录成功等信息。

Chromium 以 `headless=false` 运行，画面由 Xvfb 虚拟屏幕承载，因此服务器不需要桌面：

- 二维码和二次验证在管理后台操作；
- 评论、账号唤醒和登录检测仍然操作真实页面；
- 点击“调试浏览器”会在服务器虚拟屏幕运行，不会在管理员电脑弹出窗口。

若确实需要远程看到服务器浏览器，需要另行部署带密码和防火墙保护的 VNC/noVNC，日常业务运行不依赖它。

## 8. 日常命令

在 `/opt/douyin/deploy/centos` 执行：

```bash
./manage.sh status                 # 查看所有服务
./manage.sh logs                   # 全部实时日志
./manage.sh logs api               # API 日志
./manage.sh logs login-worker      # 扫码登录日志
./manage.sh logs browser-worker    # 账号浏览器日志
./manage.sh logs task-worker       # 评论任务日志
./manage.sh restart                # 重启全部服务
./manage.sh stop                   # 停止并保留数据
./manage.sh update                 # 拉取 main 并重新构建
```

Docker 和容器均已配置自动重启。不要执行 `docker compose down -v`，其中 `-v` 会删除 MySQL 和 Redis 数据卷。

## 9. 更新数据库

全新部署直接使用完整 schema。以后更新代码若包含新的 SQL 文件，应先备份，再按文件名时间顺序执行尚未执行的迁移：

```bash
cd /opt/douyin/deploy/centos
docker compose --env-file .env -f compose.yaml exec -T mysql \
  sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" douyin' \
  < ../../backend/migrations/迁移文件.sql
```

每个迁移只能执行一次。当前项目还没有数据库迁移版本表，请在发布记录中记下服务器执行到哪个 SQL 文件。

## 10. 数据库备份与恢复

备份：

```bash
cd /opt/douyin/deploy/centos
mkdir -p backups
docker compose --env-file .env -f compose.yaml exec -T mysql \
  sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers douyin' \
  | gzip > "backups/douyin-$(date +%F-%H%M%S).sql.gz"
ls -lh backups
```

恢复：

```bash
gunzip -c backups/你的备份文件.sql.gz | \
docker compose --env-file .env -f compose.yaml exec -T mysql \
  sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" douyin'
```

`backups/` 已被 Git 忽略。正式环境还应把备份同步到另一台机器或对象存储。

## 11. HTTPS

当前配置监听 HTTP 80，适合首次测试。正式开放客户登录前，应在云负载均衡、CDN 或独立反向代理上绑定域名和 HTTPS 证书，并转发到服务器 80 端口。保持 `/api/`、`/healthz` 和 `/readyz` 路径不变。

## 12. 常见问题

无法访问时检查：

```bash
./manage.sh status
ss -lntp | grep ':80'
curl -v http://127.0.0.1/healthz
```

页面出现 502 时检查 API、MySQL 和 Redis：

```bash
./manage.sh logs api
./manage.sh logs mysql
./manage.sh logs redis
```

Chromium 启动失败时检查并重新安装浏览器：

```bash
./manage.sh logs login-worker
docker compose --env-file .env -f compose.yaml run --rm login-worker \
  python -m playwright install chromium
```

修改 `.env` 后需要重新创建容器：

```bash
docker compose --env-file .env -f compose.yaml up -d --force-recreate
```

首次启动数据库没有表时先看 `./manage.sh logs mysql`。初始化 SQL 只在数据卷为空时运行。只有确认没有任何数据需要保留时，才能执行以下命令重建：

```bash
docker compose --env-file .env -f compose.yaml down -v
./manage.sh start
```

上述命令会永久删除当前 MySQL 和 Redis 数据。

## 13. 服务结构

| 服务 | 作用 | 公网端口 |
| --- | --- | --- |
| `web` | Nginx、前端静态文件和 API 反向代理 | 80 |
| `api` | FastAPI 接口 | 无 |
| `mysql` | 业务数据和加密后的登录状态 | 无 |
| `redis` | 队列、浏览器指令和 Worker 心跳 | 无 |
| `login-worker` | 扫码登录和二次认证 | 无 |
| `browser-worker` | 唤醒、关闭账号浏览器 | 无 |
| `task-worker` | 进入直播链接并执行评论任务 | 无 |

MySQL 和 Redis 使用 Docker 命名卷持久化，只有 `web` 容器占用宿主机 80 端口。
