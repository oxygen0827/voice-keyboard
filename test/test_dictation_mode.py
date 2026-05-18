import unittest
from unittest.mock import MagicMock

from agent.dictation_mode import (
    DictationMode,
    clean_generated_text,
    clean_polished_text,
)


class DictationModeModuleTests(unittest.TestCase):
    def make_module(self, stt_text="hello"):
        stt = MagicMock(spec=["transcribe"])
        stt.transcribe.return_value = stt_text
        env = MagicMock()
        status = MagicMock()
        history = MagicMock()
        kbd = MagicMock()
        module = DictationMode(
            stt,
            env,
            kbd_monitor=kbd,
            status_window=status,
            history=history,
        )
        return module, stt, env, status, history, kbd

    def test_normal_dictation_inserts_text_and_records_history(self):
        module, stt, env, status, history, kbd = self.make_module("  ### hello  ")

        module.handle_utterance(b"pcm")

        stt.transcribe.assert_called_once_with(b"pcm")
        env.insert_dictation.assert_called_once_with("hello")
        history.append.assert_called_once_with("dictate", "hello", "ok", "")
        kbd.notify_voice_output.assert_called_once_with()
        status.set_state.assert_called_once_with("idle")

    def test_polish_stt_uses_dedicated_transcription_method_when_available(self):
        stt = MagicMock(spec=["transcribe", "transcribe_polished"])
        stt.transcribe.return_value = "base"
        stt.transcribe_polished.return_value = "polished by stt"
        env = MagicMock()
        history = MagicMock()
        module = DictationMode(stt, env, history=history)

        module.handle_utterance(b"pcm", polish=True)

        stt.transcribe_polished.assert_called_once_with(b"pcm")
        stt.transcribe.assert_not_called()
        env.insert_dictation.assert_called_once_with("polished by stt")
        history.append.assert_called_once_with("polish", "polished by stt", "ok", "")

    def test_polish_mode_can_apply_text_polisher_after_stt(self):
        module, _stt, env, status, history, _kbd = self.make_module("嗯 hello")
        editor = MagicMock()
        editor.chat.return_value = "润色结果：Hello."
        module.text_polisher = editor

        module.handle_utterance(b"pcm", polish=True)

        env.insert_dictation.assert_called_once_with("Hello.")
        self.assertEqual(status.set_state.call_args_list[0].args, ("polishing",))
        self.assertEqual(status.set_state.call_args_list[1].args, ("idle",))
        history.append.assert_called_once_with("polish", "Hello.", "ok", "")

    def test_polish_failure_keeps_original_text(self):
        module, _stt, env, _status, history, _kbd = self.make_module("original")
        editor = MagicMock()
        editor.chat.side_effect = RuntimeError("no llm")
        module.text_polisher = editor

        module.handle_utterance(b"pcm", polish=True)

        env.insert_dictation.assert_called_once_with("original")
        history.append.assert_called_once_with("polish", "original", "ok", "")

    def test_stt_error_records_error_without_insert(self):
        module, stt, env, status, history, _kbd = self.make_module()
        stt.transcribe.side_effect = RuntimeError("offline")

        module.handle_utterance(b"pcm")

        env.insert_dictation.assert_not_called()
        history.append.assert_called_once_with("dictate", "", "error", "STT: offline")
        status.set_state.assert_called_once_with("error_stt")

    def test_empty_stt_records_empty_without_insert(self):
        module, _stt, env, status, history, _kbd = self.make_module("  ###  ")

        module.handle_utterance(b"pcm")

        env.insert_dictation.assert_not_called()
        history.append.assert_called_once_with("dictate", "", "empty", "")
        status.set_state.assert_called_once_with("empty_stt")

    def test_typing_error_records_original_text_without_idle_status(self):
        module, _stt, env, status, history, kbd = self.make_module("hello")
        env.insert_dictation.side_effect = RuntimeError("blocked")

        module.handle_utterance(b"pcm")

        history.append.assert_called_once_with("dictate", "hello", "error", "typing: blocked")
        status.set_state.assert_called_once_with("error_typing")
        kbd.notify_voice_output.assert_not_called()

    def test_cancelled_no_focus_paste_is_not_recorded_as_typing_error(self):
        module, _stt, env, status, history, kbd = self.make_module("hello")
        env.insert_dictation.side_effect = RuntimeError("no_focused_input")

        module.handle_utterance(b"pcm")

        history.append.assert_called_once_with("dictate", "hello", "cancelled", "no_focused_input")
        status.show_message.assert_called_once_with("未点击到输入框，已取消输出", 5.0)
        status.set_state.assert_called_once_with("idle")
        kbd.notify_voice_output.assert_not_called()

    def test_status_flags_preserve_segment_behavior(self):
        module, _stt, env, status, _history, _kbd = self.make_module("hello")

        module.handle_utterance(b"pcm", clear_status=False, progress_status=False)

        env.insert_dictation.assert_called_once_with("hello")
        status.set_state.assert_not_called()

    def test_cleanup_helpers_match_common_model_markup(self):
        self.assertEqual(clean_generated_text("  ### 你好世界  "), "你好世界")
        self.assertEqual(clean_polished_text("```text\n润色结果：你好世界\n```"), "你好世界")


if __name__ == "__main__":
    unittest.main()
