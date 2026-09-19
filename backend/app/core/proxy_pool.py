"""Account-bound SOCKS5 proxy selection and browser configuration."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_transient_secret
from app.models import DouyinAccount, Proxy


async def choose_proxy_for_new_account(db: AsyncSession) -> int | None:
    """Reserve a slot under a proxy row lock; caller inserts account before commit."""
    now = datetime.now()
    proxies = list(await db.scalars(
        select(Proxy).where(Proxy.deleted_at.is_(None), Proxy.expires_at > now)
        .order_by(Proxy.id).with_for_update()
    ))
    for proxy in proxies:
        # Locking read sees the latest committed assignments under MySQL's
        # REPEATABLE READ, even if the request read other rows earlier.
        bound_ids = list(await db.scalars(select(DouyinAccount.id).where(
            DouyinAccount.proxy_id == proxy.id,
            DouyinAccount.deleted_at.is_(None),
        ).with_for_update()))
        if len(bound_ids) < proxy.max_accounts:
            return proxy.id
    return None


async def browser_proxy_for_account(db: AsyncSession, account: DouyinAccount) -> dict | None:
    if account.proxy_id is None:
        return None
    proxy = await db.get(Proxy, account.proxy_id)
    if not proxy or proxy.deleted_at is not None or proxy.expires_at <= datetime.now():
        raise RuntimeError("绑定的代理已删除或过期，请管理员重新分配代理")
    return {
        "host": proxy.domain,
        "port": proxy.port,
        "username": proxy.username,
        "password": decrypt_transient_secret(proxy.encrypted_password.decode()),
    }
