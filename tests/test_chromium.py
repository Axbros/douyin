"""浏览器检测回归测试，不联网或启动真实浏览器。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
from src.core import LiveCompanionEngine


class ChromiumTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.executable = Path(self.temp.name) / "Chromium.app/Contents/MacOS/Chromium"
        self.engine = LiveCompanionEngine.__new__(LiveCompanionEngine)
        self.engine._emit_status = mock.Mock()
        self.engine._emit_error = mock.Mock()
        context = mock.MagicMock()
        context.__aenter__ = mock.AsyncMock(return_value=SimpleNamespace(
            chromium=SimpleNamespace(executable_path=str(self.executable))))
        context.__aexit__ = mock.AsyncMock(return_value=False)
        patcher = mock.patch("playwright.async_api.async_playwright", return_value=context)
        patcher.start()
        self.addCleanup(patcher.stop)

    def install(self, *args, **kwargs):
        self.executable.parent.mkdir(parents=True)
        self.executable.touch()
        return SimpleNamespace(returncode=0, stderr="")

    async def test_existing_macos_browser_skips_install(self):
        self.install()
        with mock.patch("src.core.subprocess.run") as run:
            self.assertTrue(await self.engine._ensure_chromium())
            run.assert_not_called()

    async def test_install_and_recheck(self):
        with mock.patch("src.core.subprocess.run", side_effect=self.install) as run:
            self.assertTrue(await self.engine._ensure_chromium())
            self.assertEqual(run.call_args.kwargs["creationflags"],
                             getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(run.call_args.args[0][-2:], ["install", "chromium"])
            self.assertTrue(await self.engine._ensure_chromium())
            self.assertEqual(run.call_count, 1)

    async def test_failed_install(self):
        with mock.patch("src.core.subprocess.run", return_value=SimpleNamespace(
                returncode=1, stderr="download failed")):
            self.assertFalse(await self.engine._ensure_chromium())
            self.engine._emit_error.assert_called_once()

    async def test_success_without_executable_is_not_accepted(self):
        with mock.patch("src.core.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stderr="")):
            self.assertFalse(await self.engine._ensure_chromium())


if __name__ == "__main__":
    unittest.main()
