"""引擎任务和 GUI 工作线程的退出回归测试。"""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
from src.core import LiveCompanionEngine
from src.gui import EngineWorker


class EngineCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = Path(self.temp.name) / "config.yaml"
        config.write_text("{}")
        self.engine = LiveCompanionEngine(str(config))

    async def test_stop_cancels_and_awaits_background_tasks_once(self):
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def background():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        task = self.engine._create_task(background())
        await started.wait()
        self.engine._context = mock.Mock(close=mock.AsyncMock())
        await asyncio.gather(self.engine.stop(), self.engine.stop())
        self.assertTrue(task.cancelled())
        self.assertTrue(cleaned.is_set())
        self.assertFalse(self.engine._tasks)
        self.engine._context.close.assert_awaited_once()

    async def test_start_cancellation_still_closes_resources(self):
        entered = asyncio.Event()

        async def ensure():
            entered.set()
            await asyncio.Event().wait()

        self.engine._ensure_chromium = ensure
        self.engine._context = mock.Mock(close=mock.AsyncMock())
        task = asyncio.create_task(self.engine.start())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.engine._context.close.assert_awaited_once()
        self.assertFalse(self.engine.is_running)

    async def test_failed_sibling_cleanup(self):
        async def fail():
            raise RuntimeError("audio failed")

        sibling = self.engine._create_task(asyncio.sleep(3600))
        failed = self.engine._create_task(fail())
        with self.assertRaisesRegex(RuntimeError, "audio failed"):
            await asyncio.gather(sibling, failed)
        await self.engine.stop()
        self.assertTrue(sibling.cancelled())
        self.assertFalse(self.engine._tasks)


class WorkerCleanupTest(unittest.TestCase):
    def test_stop_request_cancels_main_task_and_cleans_up(self):
        events = []
        worker = EngineWorker("unused-config.yaml")

        async def start():
            asyncio.get_running_loop().call_soon(worker.stop_engine)
            try:
                await asyncio.Event().wait()
            finally:
                events.append("main cleaned")

        engine = mock.Mock(start=start, stop=mock.AsyncMock())
        worker.stopped.connect(lambda: events.append("stopped"))
        with mock.patch("src.gui.LiveCompanionEngine", return_value=engine):
            worker.run()
        self.assertEqual(events, ["main cleaned", "stopped"])
        self.assertTrue(worker._main_task.cancelled())
        self.assertTrue(worker._loop.is_closed())
        engine.stop.assert_awaited_once()

    def test_stopped_signal_follows_pending_task_cleanup_and_loop_close(self):
        events = []
        tasks = []

        async def background():
            try:
                await asyncio.Event().wait()
            finally:
                events.append("cleaned")

        async def start():
            tasks.append(asyncio.create_task(background()))
            await asyncio.sleep(0)
            # 模拟主流程异常返回后，gather 的其它任务仍未完成。

        engine = mock.Mock(start=start, stop=mock.AsyncMock())
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("{}")
            worker = EngineWorker(str(config))
            worker.stopped.connect(lambda: events.append(
                "closed" if worker._loop.is_closed() else "still open"))
            with mock.patch("src.gui.LiveCompanionEngine", return_value=engine):
                worker.run()
        self.assertEqual(events, ["cleaned", "closed"])
        self.assertTrue(tasks[0].cancelled())
        engine.stop.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
