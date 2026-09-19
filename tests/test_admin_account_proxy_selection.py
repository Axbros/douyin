"""Admin account proxy selection must respect capacity and explicit direct mode."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.api import admin


class AdminAccountProxySelectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_proxy_rejected(self):
        db = SimpleNamespace(scalar=AsyncMock(), scalars=AsyncMock())
        db.scalar.return_value = SimpleNamespace(id=7, expires_at=datetime.now() + timedelta(days=1), max_accounts=3)
        db.scalars.return_value = [1, 2, 3]
        with self.assertRaises(HTTPException) as error:
            await admin._get_available_proxy(7, db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("上限", error.exception.detail)

    async def test_direct_create_does_not_auto_assign_proxy(self):
        db = SimpleNamespace(add=lambda _: None, flush=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock())
        with patch.object(admin, "choose_proxy_for_new_account", new_callable=AsyncMock) as auto_assign:
            account = await admin.create_account("测试", SimpleNamespace(id=1), db, proxy_mode="direct")
        self.assertIsNone(account.proxy_id)
        auto_assign.assert_not_awaited()

    async def test_explicit_proxy_create_checks_availability(self):
        db = SimpleNamespace(add=lambda _: None, flush=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock())
        with patch.object(admin, "_get_available_proxy", new_callable=AsyncMock) as check:
            account = await admin.create_account("测试", SimpleNamespace(id=1), db, proxy_mode="proxy", proxy_id=7)
        self.assertEqual(account.proxy_id, 7)
        check.assert_awaited_once_with(7, db)


if __name__ == "__main__":
    unittest.main()
