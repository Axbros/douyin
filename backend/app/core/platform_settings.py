from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSetting


DEFAULT_PLATFORM_SETTINGS = {
    "comment_min_interval_seconds": 5,
    "comment_max_interval_seconds": 3600,
    "script_bulk_import_limit": 200,
    "qr_expire_minutes": 5,
    "worker_heartbeat_timeout_seconds": 20,
    "account_reclaim_seconds": 60,
}

SETTING_KEYS = {name: f"platform.{name}" for name in DEFAULT_PLATFORM_SETTINGS}


async def get_platform_settings(db: AsyncSession) -> dict[str, int]:
    values = DEFAULT_PLATFORM_SETTINGS.copy()
    reverse_keys = {setting_key: name for name, setting_key in SETTING_KEYS.items()}
    rows = await db.scalars(select(SystemSetting).where(
        SystemSetting.setting_key.in_(reverse_keys), SystemSetting.deleted_at.is_(None)
    ))
    for row in rows:
        name = reverse_keys[row.setting_key]
        raw_value = row.setting_value.get("value") if isinstance(row.setting_value, dict) else None
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            values[name] = raw_value
    return values


async def update_platform_settings(db: AsyncSession, values: dict[str, int], admin_id: int) -> dict[str, int]:
    rows = list(await db.scalars(select(SystemSetting).where(SystemSetting.setting_key.in_(SETTING_KEYS.values()))))
    existing = {row.setting_key: row for row in rows}
    for name, value in values.items():
        setting_key = SETTING_KEYS[name]
        row = existing.get(setting_key)
        if row:
            row.setting_value = {"value": value}
            row.updated_by = admin_id
            row.deleted_at = None
        else:
            db.add(SystemSetting(setting_key=setting_key, setting_value={"value": value}, updated_by=admin_id))
    await db.commit()
    return await get_platform_settings(db)
