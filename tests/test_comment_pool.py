import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', 'python')
from src.comment_pool import choose_comment, parse_comments, read_comments
from src.core import LiveCompanionEngine


class CommentPoolTest(unittest.TestCase):
    def test_parse_removes_blanks_and_duplicates(self):
        self.assertEqual(parse_comments(' 第一条 \n\n第二条\r\n第一条'), ['第一条', '第二条'])

    def test_import_supported_encodings(self):
        with tempfile.TemporaryDirectory() as directory:
            for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
                path = Path(directory) / (encoding + '.txt')
                path.write_bytes('你好\n欢迎'.encode(encoding))
                self.assertEqual(read_comments(path), ['你好', '欢迎'])

    def test_small_pool_keeps_sending_without_consecutive_duplicates(self):
        recent = []
        for _ in range(25):
            comment = choose_comment(['甲', '乙'], recent, 20)
            if recent:
                self.assertNotEqual(comment, recent[-1])
            recent.append(comment)
        self.assertEqual(choose_comment(['甲'], ['甲'] * 15, 20), '甲')
        self.assertEqual(choose_comment([], [], 20), '')

    def test_deduplicates_truncated_comments(self):
        self.assertEqual(choose_comment(['前缀一', '前缀二', '其他'], ['前缀'], 2), '其他')


class TextCommentLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_text_mode_starts_without_waiting_for_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.yaml'
            config.write_text('sender:\n  comment_source: text\n  text_comments: [你好]\n  like_enabled: false\n')
            engine = LiveCompanionEngine(str(config))
            page = mock.Mock(url='https://live.example.com/123')
            page.goto = mock.AsyncMock()
            page.add_init_script = mock.AsyncMock()
            context = mock.Mock(pages=[page], new_page=mock.AsyncMock(return_value=page),
                                close=mock.AsyncMock())
            browser = mock.Mock(new_context=mock.AsyncMock(return_value=context))
            engine.platform = mock.Mock(home_url='https://live.example.com',
                                        room_url_pattern=r'live\.example\.com/\d+',
                                        check_logged_in=mock.AsyncMock(return_value=True))
            engine._ensure_chromium = mock.AsyncMock(return_value=True)
            engine._load_saved_cookies = mock.AsyncMock(return_value=[])
            engine._save_cookies = mock.AsyncMock()
            engine._probe_current_stream_url = mock.AsyncMock()
            engine._run_audio = mock.AsyncMock()
            engine._run_danmu = mock.AsyncMock()
            engine._run_comment_loop = mock.AsyncMock()
            with (mock.patch('src.core.asyncio.sleep', new=mock.AsyncMock()),
                  mock.patch('src.core.DanmuReader'), mock.patch('src.core.CommentSender')):
                await engine.start(shared_browser=browser)
            engine._probe_current_stream_url.assert_not_awaited()
            engine._run_comment_loop.assert_awaited_once()
            self.assertIsNone(engine._stream_url)

    async def test_text_mode_sends_without_context_or_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.yaml'
            config.write_text('sender:\n  comment_source: text\n  text_comments: [你好, 欢迎]\n')
            engine = LiveCompanionEngine(str(config))
            engine.is_running = True

            async def send(text):
                engine.is_running = False
                return True

            engine._sender = mock.Mock(send_comment=mock.AsyncMock(side_effect=send))
            with (mock.patch('src.core.asyncio.sleep', new=mock.AsyncMock()) as sleep,
                  mock.patch('src.core.LLMClient') as llm):
                await engine._run_comment_loop()
                llm.assert_not_called()
                sleep.assert_awaited_once()
                self.assertGreaterEqual(sleep.call_args.args[0], 20)
                self.assertLessEqual(sleep.call_args.args[0], 50)
            engine._sender.send_comment.assert_awaited_once()
            self.assertIn(engine._sender.send_comment.call_args.args[0], ['你好', '欢迎'])


if __name__ == '__main__':
    unittest.main()
