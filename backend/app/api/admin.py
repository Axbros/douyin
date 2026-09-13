from typing import Annotated

from datetime import datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.database import redis_client
from app.dependencies import admin_user
from app.models import AccountLoginSession, AccountLog, DouyinAccount, Script, User
from app.schemas import AccountResponse, LoginSessionResponse, ScriptResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/douyin-accounts", response_model=list[AccountResponse])
async def list_accounts(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(DouyinAccount).where(DouyinAccount.deleted_at.is_(None)).order_by(DouyinAccount.id.desc()))
    return list(result)


@router.post("/douyin-accounts", response_model=AccountResponse, status_code=201)
async def create_account(display_name: str, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = DouyinAccount(display_name=display_name.strip() or "未命名账号", status="unlogged", enabled=True)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.patch("/douyin-accounts/{account_id}/disable", response_model=AccountResponse)
async def disable_account(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await db.scalar(select(DouyinAccount).where(DouyinAccount.id == account_id, DouyinAccount.deleted_at.is_(None)))
    if not account:
        raise HTTPException(404, "抖音账号不存在")
    account.enabled = False
    account.status = "disabled"
    await db.commit()
    await db.refresh(account)
    return account


@router.patch("/douyin-accounts/{account_id}/enable", response_model=AccountResponse)
async def enable_account(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await db.scalar(select(DouyinAccount).where(DouyinAccount.id == account_id, DouyinAccount.deleted_at.is_(None)))
    if not account:
        raise HTTPException(404, "抖音账号不存在")
    account.enabled = True
    account.status = "available" if account.encrypted_storage_state else "unlogged"
    await db.commit()
    await db.refresh(account)
    return account


@router.delete("/douyin-accounts/{account_id}", status_code=204)
async def delete_account(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await db.scalar(select(DouyinAccount).where(DouyinAccount.id == account_id, DouyinAccount.deleted_at.is_(None)))
    if not account:
        raise HTTPException(404, "抖音账号不存在")
    account.deleted_at = datetime.now()
    account.enabled = False
    account.status = "disabled"
    await db.commit()


@router.post("/douyin-accounts/{account_id}/login-session", response_model=LoginSessionResponse, status_code=201)
async def create_login_session(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await db.scalar(select(DouyinAccount).where(DouyinAccount.id == account_id, DouyinAccount.deleted_at.is_(None)))
    if not account:
        raise HTTPException(404, "抖音账号不存在")
    raw_token = token_urlsafe(32)
    session = AccountLoginSession(
        account_id=account.id, created_by=user.id,
        session_token_hash=sha256(raw_token.encode()).hexdigest(),
        # MySQL DATETIME 不带时区；项目统一按服务器本地时间写入。
        status="waiting", expires_at=datetime.now() + timedelta(minutes=5),
    )
    db.add(session)
    db.add(AccountLog(account_id=account.id, event_type="login_session_created", detail={"session_id": session.id}))
    await db.commit()
    await db.refresh(session)
    # Worker 只拿到会话 ID；二维码和登录状态通过 Redis 事件流传递。
    await redis_client.rpush("douyin:login:sessions", str(session.id))
    return session


@router.get("/douyin-login-sessions/{session_id}", response_model=LoginSessionResponse)
async def login_session_status(session_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    session = await db.scalar(select(AccountLoginSession).where(AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None)))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    return session


@router.post("/douyin-login-sessions/{session_id}/close", response_model=LoginSessionResponse)
async def close_login_session(session_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    session = await db.scalar(select(AccountLoginSession).where(AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None)))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    # 使用会话专属队列，避免关闭已结束会话的指令影响其他登录会话。
    await redis_client.rpush(f"douyin:login:close:{session.id}", "close")
    session.status = "cancelled"
    session.completed_at = datetime.now()
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/douyin-accounts/{account_id}/logs")
async def account_logs(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(AccountLog).where(AccountLog.account_id == account_id, AccountLog.deleted_at.is_(None)).order_by(AccountLog.id.desc()).limit(200))
    return list(result)


@router.get("/scripts/review-queue", response_model=list[ScriptResponse])
async def review_queue(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(Script).where(Script.status == "pending_review", Script.deleted_at.is_(None)).order_by(Script.created_at))
    return list(result)


async def _review(script_id: int, status: str, reason: str | None, user: User, db: AsyncSession):
    script = await db.scalar(select(Script).where(Script.id == script_id, Script.deleted_at.is_(None)))
    if not script:
        raise HTTPException(404, "话术不存在")
    if script.status != "pending_review":
        raise HTTPException(409, "话术不在待审核状态")
    script.status = status
    script.review_reason = reason
    script.reviewed_by = user.id
    await db.commit()
    await db.refresh(script)
    return script


@router.post("/scripts/{script_id}/approve", response_model=ScriptResponse)
async def approve_script(script_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _review(script_id, "approved", None, user, db)


@router.post("/scripts/{script_id}/reject", response_model=ScriptResponse)
async def reject_script(script_id: int, reason: str = "管理员拒绝", user: Annotated[User, Depends(admin_user)] = None, db: Annotated[AsyncSession, Depends(get_db)] = None):
    return await _review(script_id, "rejected", reason, user, db)
