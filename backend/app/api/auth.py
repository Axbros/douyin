from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies import current_user
from app.models import User
from app.schemas import ChangePasswordRequest, LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    user = await db.scalar(select(User).where(User.login == payload.login, User.deleted_at.is_(None)))
    if not user or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if user.role == "customer" and (user.expires_at is None or user.expires_at <= datetime.now()):
        user.status = "disabled"
        await db.commit()
        raise HTTPException(status_code=401, detail="客户服务已到期，请联系管理员续签")
    user.last_login_at = datetime.now()
    await db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.role), user=user)


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(current_user)]):
    return user


@router.post("/change-password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    user.password_hash = hash_password(payload.new_password)
    await db.commit()
