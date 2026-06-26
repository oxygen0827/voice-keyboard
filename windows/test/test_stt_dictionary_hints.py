import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent import stt


class OpenAITranscriptionHintTests(unittest.TestCase):
    def test_openai_transcription_receives_prompt_hint(self):
        created = {}

        class FakeOpenAI:
            def __init__(self, **_kwargs):
                self.audio = SimpleNamespace(
                    transcriptions=SimpleNamespace(create=self._create)
                )

            def _create(self, **kwargs):
                created.update(kwargs)
                return SimpleNamespace(text="ok")

        with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}):
            client = stt.STTClient({
                "provider": "openai",
                "api_key": "test-api-key",
                "prompt": "个人词典热词：小汪",
            })

        self.assertEqual(client.transcribe(b"\0\0"), "ok")
        self.assertEqual(created["prompt"], "个人词典热词：小汪")


class ZhipuTranscriptionHintTests(unittest.TestCase):
    def test_zhipu_voice_prompt_includes_personal_dictionary_hints(self):
        captured = {}

        class FakeZhipuAI:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            def _create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="小汪")
                        )
                    ]
                )

        with patch.dict("sys.modules", {"zhipuai": SimpleNamespace(ZhipuAI=FakeZhipuAI)}):
            client = stt.STTClient({
                "provider": "zhipuai",
                "api_key": "test-api-key",
                "prompt": "个人词典热词，优先准确转写：小汪（客户联系人）",
                "hotwords": ["小汪"],
            })

        self.assertEqual(client.transcribe(b"\0\0"), "小汪")
        prompt = captured["messages"][0]["content"][1]["text"]
        self.assertIn("个人词典热词", prompt)
        self.assertIn("小汪", prompt)
        self.assertIn("Hotwords / personal dictionary", prompt)


class GLMASRTranscriptionHintTests(unittest.TestCase):
    def test_glm_asr_request_receives_prompt_and_hotwords(self):
        post = MagicMock()
        post.return_value.ok = True
        post.return_value.json.return_value = {"text": "小汪"}

        with patch.object(stt.requests, "post", post):
            client = stt.STTClient({
                "provider": "glm_asr_2512",
                "api_key": "test-api-key",
                "prompt": "个人词典热词：小汪",
                "hotwords": ["小汪", "Voice Keyboard"],
            })

            self.assertEqual(client.transcribe(b"\0\0"), "小汪")

        data = post.call_args.kwargs["data"]
        self.assertEqual(data["prompt"], "个人词典热词：小汪")
        self.assertEqual(data["hotwords[0]"], "小汪")
        self.assertEqual(data["hotwords[1]"], "Voice Keyboard")


if __name__ == "__main__":
    unittest.main()
