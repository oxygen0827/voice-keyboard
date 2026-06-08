import time
import unittest
from unittest.mock import MagicMock

from agent.ai_handler import AIHandler
from agent.input_environment import TextTarget


class FakeSTT:
    def __init__(self, text: str):
        self.text = text

    def transcribe(self, pcm: bytes) -> str:
        return self.text


class FakeEnv:
    def target_for_instruction(self):
        return TextTarget()

    def active_application(self):
        return "Test App"

    def shortcuts(self):
        return ()

    def shortcut_catalog(self):
        return ()


class FakeHistory:
    def __init__(self):
        self.entries = []

    def append(self, mode: str, text: str, status: str = "ok", detail: str = ""):
        self.entries.append((mode, text, status, detail))


class FakeStatus:
    def __init__(self):
        self.messages = []
        self.states = []

    def show_message(self, text: str, seconds: float = 6.0):
        self.messages.append((text, seconds))

    def set_state(self, state: str):
        self.states.append(state)


class AIHandlerRuntimeTests(unittest.TestCase):
    def test_records_executor_failure_status_after_execution(self):
        llm = MagicMock()
        llm.chat.return_value = '{"type":"shortcut","name":"missing"}'
        history = FakeHistory()
        handler = AIHandler(
            FakeSTT("save it"),
            llm,
            MagicMock(),
            history=history,
            input_environment=FakeEnv(),
        )
        handler._executor = MagicMock()
        handler._executor.execute.return_value = True
        handler._executor.last_status = ("error", "shortcut_missing:missing")

        handler._run_inner(b"pcm")

        self.assertEqual(len(history.entries), 1)
        self.assertEqual(history.entries[0][:3], ("ai", "save it", "error"))
        self.assertIn("shortcut_missing:missing", history.entries[0][3])
        self.assertIn("intent_source=llm", history.entries[0][3])

    def test_records_intent_source_in_history_detail(self):
        llm = MagicMock()
        llm.chat.return_value = '{"type":"chat","reply":"x"}'
        history = FakeHistory()
        handler = AIHandler(
            FakeSTT("question"),
            llm,
            MagicMock(),
            history=history,
            input_environment=FakeEnv(),
        )
        handler._executor = MagicMock()
        handler._executor.execute.return_value = True
        handler._executor.last_status = ("ok", "chat")

        handler._run_inner(b"pcm")

        self.assertEqual(len(history.entries), 1)
        self.assertIn("intent_source=llm", history.entries[0][3])
        self.assertIn("intent_confidence=high", history.entries[0][3])

    def test_intent_timeout_keeps_feedback_visible_and_records_error(self):
        class SlowLLM:
            def chat(self, _system, _user):
                time.sleep(0.05)
                return '{"type":"chat","reply":"late"}'

        history = FakeHistory()
        handler = AIHandler(
            FakeSTT("question"),
            SlowLLM(),
            MagicMock(),
            history=history,
            input_environment=FakeEnv(),
        )
        import agent.ai_handler as ai_handler_module
        original_timeout = ai_handler_module._INTENT_TIMEOUT_SECONDS
        ai_handler_module._INTENT_TIMEOUT_SECONDS = 0.001
        try:
            keep_status = handler._run_inner(b"pcm")
        finally:
            ai_handler_module._INTENT_TIMEOUT_SECONDS = original_timeout

        self.assertTrue(keep_status)
        self.assertEqual(history.entries, [
            ("ai", "question", "error", "intent_timeout"),
        ])

    def test_shows_ai_progress_stages(self):
        llm = MagicMock()
        llm.chat.return_value = '{"type":"write"}'
        status = FakeStatus()
        handler = AIHandler(
            FakeSTT("write a note"),
            llm,
            MagicMock(),
            status_window=status,
            input_environment=FakeEnv(),
        )
        handler._executor = MagicMock()
        handler._executor.execute.return_value = False
        handler._executor.last_status = ("ok", "write")

        handler._run_inner(b"pcm")

        messages = [text for text, _seconds in status.messages]
        self.assertEqual(messages, [
            "[AI]: 已识别：write a note",
            "[AI]: 正在理解指令",
            "[AI]: 准备生成文字",
        ])


if __name__ == "__main__":
    unittest.main()
