from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SubscriptionPlan, User


async def get_customer_plan(db: AsyncSession, customer: User) -> SubscriptionPlan:
    plan = None
    if customer.subscription_plan_id:
        plan = await db.scalar(select(SubscriptionPlan).where(
            SubscriptionPlan.id == customer.subscription_plan_id,
            SubscriptionPlan.enabled.is_(True),
            SubscriptionPlan.deleted_at.is_(None),
        ))
    if not plan:
        plan = await db.scalar(select(SubscriptionPlan).where(
            SubscriptionPlan.code == "standard",
            SubscriptionPlan.enabled.is_(True),
            SubscriptionPlan.deleted_at.is_(None),
        ))
    if not plan:
        raise RuntimeError("未配置可用的标准套餐")
    return plan
