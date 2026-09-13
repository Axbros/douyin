import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
from src.audio import AudioTranscriber
from src.core import LiveCompanionEngine


class ModelLoadingTest(unittest.TestCase):
    def test_complete_local_quantized_model_needs_no_download(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("model_quant.onnx", "config.yaml", "am.mvn",
                         "chn_jpn_yue_eng_ko_spectok.bpe.model"):
                (Path(directory) / name).touch()
            audio = AudioTranscriber({})
            with (mock.patch("src.audio._get_model_dir", return_value=directory),
                  mock.patch("src.audio.SenseVoiceSmall") as model,
                  mock.patch("modelscope.hub.snapshot_download.snapshot_download") as download):
                audio._load_model()
                model.assert_called_once_with(directory, quantize=True)
                download.assert_not_called()

    def test_download_failure_preserves_real_cause(self):
        audio = AudioTranscriber({})
        with (mock.patch("src.audio._get_model_dir", return_value="iic/SenseVoiceSmall-onnx"),
              mock.patch("modelscope.hub.snapshot_download.snapshot_download",
                         side_effect=OSError("network unavailable"))):
            with self.assertRaisesRegex(RuntimeError, "模型下载失败: OSError: network unavailable") as error:
                audio._load_model()
            self.assertIsInstance(error.exception.__cause__, OSError)

    def test_incomplete_model_does_not_trigger_implicit_export(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "model.onnx").touch()
            with (mock.patch("src.audio._get_model_dir", return_value=directory),
                  mock.patch("src.audio.SenseVoiceSmall") as model):
                with self.assertRaisesRegex(RuntimeError, "模型文件不完整"):
                    AudioTranscriber({})._load_model()
                model.assert_not_called()


class AudioIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_transcription_does_not_stop_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("{}")
            engine = LiveCompanionEngine(str(config))
            engine.is_running = True
            engine._stream_url = "https://example.invalid/live.flv"
            engine._transcriber = mock.Mock(
                start=mock.AsyncMock(side_effect=RuntimeError("model unavailable")))
            engine.on_error = mock.Mock()
            with mock.patch("traceback.print_exc"):
                await engine._run_audio()
            self.assertTrue(engine.is_running)
            self.assertTrue(any("弹幕和评论继续运行" in call.args[0]
                                for call in engine.on_error.call_args_list))
            engine._transcriber.stop.assert_called_once()
            self.assertFalse(engine._tasks)


if __name__ == "__main__":
    unittest.main()
