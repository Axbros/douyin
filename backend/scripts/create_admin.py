import asyncio
import getpass
import sys

from sqlalchemy import select

sys.path.insert(0, ".")
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User


async def main():
    login = input("管理员登录名: ").strip()
    display_name = input("显示名称: ").strip() or login
    password = getpass.getpass("密码（至少8位）: ")
    async with SessionLocal() as db:
        exists = await db.scalar(select(User).where(User.login == login, User.deleted_at.is_(None)))
        if exists:
            raise SystemExit("该登录名已存在")
        db.add(User(role="admin", login=login, display_name=display_name, password_hash=hash_password(password)))
        await db.commit()
    print("管理员创建成功")


if __name__ == "__main__":
    asyncio.run(main())
