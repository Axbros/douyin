# FastAPI 后端（第一阶段）

## 本地启动

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填写 MySQL 密码、JWT_SECRET 和加密密钥
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

创建第一个管理员：

```bash
cd backend
PYTHONPATH=. python scripts/create_admin.py
```

健康检查：`GET http://127.0.0.1:8000/healthz`

Swagger：`http://127.0.0.1:8000/docs`

数据库密码只允许写入 `backend/.env`，该文件已加入 `.gitignore`。不要把密码写入 YAML、源码或提交记录。

当前已实现认证、客户话术创建/提交审核、管理员审核、客户任务创建/列表/暂停/停止。任务账号分配、二维码登录会话、Worker 和实时日志将在下一阶段接入。

登录 Worker 创建的浏览器不会因登录成功、超时或页面异常自动关闭。管理员调用 `POST /api/admin/douyin-login-sessions/{id}/close` 后才会关闭对应浏览器。
