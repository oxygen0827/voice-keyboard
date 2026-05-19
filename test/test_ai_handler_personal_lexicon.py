import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from agent.ai_handler import AIHandler
from agent.input_environment import TextInsertionResult, TextTarget
from agent.personal_lexicon import PersonalLexicon
from agent.text_buffer import TextBuffer


class FakeReusableTextMemoryStore:
    def __init__(self):
        self.data = {}

    def save(self, key: str, value: str) -> None:
        self.data[key] = value

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def delete(self, key: str) -> bool:
        if key not in self.data:
            return False
        del self.data[key]
        return True

    def keys(self) -> list[str]:
        return list(self.data.keys())


class FakeInputEnvironment:
    def __init__(self, selected: str = ""):
        self.inserted = []
        self.selected = selected

    def target_for_instruction(self):
        return TextTarget(selected=self.selected, tracked_segment="")

    def active_application(self):
        return "Codex (com.openai.codex)"

    def shortcuts(self):
        return ()

    def insert_generated_text(self, text: str):
        self.inserted.append(text)
        return TextInsertionResult(inserted_text=text)


class AIHandlerPersonalLexiconTests(unittest.TestCase):
    def test_learning_alias_command_updates_lexicon_without_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt = MagicMock()
            stt.transcribe.return_value = "以后我说小白就是白光宇"
            llm = MagicMock()
            status = MagicMock()
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            handler = AIHandler(
                stt,
                llm,
                TextBuffer(),
                reusable_text_memory_store=FakeReusableTextMemoryStore(),
                status_window=status,
                input_environment=FakeInputEnvironment(),
                personal_lexicon=lexicon,
            )

            keep_status = handler._run_inner(b"pcm")

            self.assertTrue(keep_status)
            self.assertEqual(lexicon.aliases_for("白光宇"), ("小白",))
            llm.chat.assert_not_called()
            status.show_typing_message.assert_called_once()

    def test_personal_lexicon_normalization_feeds_reusable_text_resolver(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt = MagicMock()
            stt.transcribe.return_value = "我的白光雨说什么"
            llm = MagicMock()
            llm.chat.return_value = '{"type":"chat","reply":"不知道"}'
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            lexicon.remember("白光雨", "白光宇")
            reusable_text_memory = FakeReusableTextMemoryStore()
            reusable_text_memory.save("白光宇最喜欢说的话", "大美女")
            env = FakeInputEnvironment()
            handler = AIHandler(
                stt,
                llm,
                TextBuffer(),
                reusable_text_memory_store=reusable_text_memory,
                input_environment=env,
                personal_lexicon=lexicon,
            )

            handler._run_inner(b"pcm")

            self.assertEqual(env.inserted, ["大美女"])

    def test_forget_alias_command_updates_lexicon_without_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt = MagicMock()
            stt.transcribe.return_value = "忘记我说小白这个说法"
            llm = MagicMock()
            status = MagicMock()
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            lexicon.remember("小白", "白光宇", "alias")
            handler = AIHandler(
                stt,
                llm,
                TextBuffer(),
                reusable_text_memory_store=FakeReusableTextMemoryStore(),
                status_window=status,
                input_environment=FakeInputEnvironment(),
                personal_lexicon=lexicon,
            )

            keep_status = handler._run_inner(b"pcm")

            self.assertTrue(keep_status)
            self.assertEqual(lexicon.aliases_for("白光宇"), ())
            llm.chat.assert_not_called()

    def test_list_lexicon_command_does_not_call_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt = MagicMock()
            stt.transcribe.return_value = "看一下个人词库"
            llm = MagicMock()
            status = MagicMock()
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            lexicon.remember("小白", "白光宇", "alias")
            handler = AIHandler(
                stt,
                llm,
                TextBuffer(),
                reusable_text_memory_store=FakeReusableTextMemoryStore(),
                status_window=status,
                input_environment=FakeInputEnvironment(),
                personal_lexicon=lexicon,
            )

            keep_status = handler._run_inner(b"pcm")

            self.assertTrue(keep_status)
            llm.chat.assert_not_called()
            status.show_typing_message.assert_called_once()
            self.assertIn("小白 -> 白光宇", status.show_typing_message.call_args.args[0])

    def test_recent_memory_edit_updates_reusable_text_without_learning_global_lexicon(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt = MagicMock()
            stt.transcribe.return_value = "刚刚说的mac的密码，那个mac实际上是macOS"
            llm = MagicMock()
            status = MagicMock()
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            reusable_text_memory = FakeReusableTextMemoryStore()
            reusable_text_memory.save("mac的密码", "mac password")
            handler = AIHandler(
                stt,
                llm,
                TextBuffer(),
                reusable_text_memory_store=reusable_text_memory,
                status_window=status,
                input_environment=FakeInputEnvironment(),
                personal_lexicon=lexicon,
            )

            keep_status = handler._run_inner(b"pcm")

            self.assertTrue(keep_status)
            self.assertEqual(reusable_text_memory.data, {"macOS的密码": "macOS password"})
            self.assertEqual(lexicon.rules(), ())
            llm.chat.assert_not_called()

    def test_selection_learning_uses_selected_text_as_written_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt = MagicMock()
            stt.transcribe.return_value = "以后我说的伽马斯就是这个词"
            llm = MagicMock()
            status = MagicMock()
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            handler = AIHandler(
                stt,
                llm,
                TextBuffer(),
                reusable_text_memory_store=FakeReusableTextMemoryStore(),
                status_window=status,
                input_environment=FakeInputEnvironment(selected="gemma4"),
                personal_lexicon=lexicon,
            )

            keep_status = handler._run_inner(b"pcm")

            self.assertTrue(keep_status)
            signatures = {
                "伽马斯": "gamasi",
                "伽马四": "gamasi",
                "干妈四": "ganmasi",
                "嘎玛寺": "gamasi",
            }
            with patch(
                "agent.personal_lexicon._phonetic_signature",
                side_effect=lambda text: signatures.get(text, text),
            ):
                self.assertEqual(lexicon.normalize("谷歌的伽马四模型"), "谷歌的gemma4模型")
                self.assertEqual(lexicon.normalize("我正在打的比赛是干妈四"), "我正在打的比赛是gemma4")
                self.assertEqual(lexicon.normalize("嘎玛寺"), "gemma4")
            self.assertIn("伽马斯", lexicon.aliases_for("gemma4"))
            self.assertNotIn("干妈四", lexicon.aliases_for("gemma4"))
            self.assertEqual(len(lexicon.rules()), 1)
            llm.chat.assert_not_called()

    def test_selection_learning_requires_selected_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt = MagicMock()
            stt.transcribe.return_value = "以后我说伽马四就是这个词"
            llm = MagicMock()
            status = MagicMock()
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            handler = AIHandler(
                stt,
                llm,
                TextBuffer(),
                reusable_text_memory_store=FakeReusableTextMemoryStore(),
                status_window=status,
                input_environment=FakeInputEnvironment(),
                personal_lexicon=lexicon,
            )

            keep_status = handler._run_inner(b"pcm")

            self.assertTrue(keep_status)
            self.assertEqual(lexicon.rules(), ())
            status.show_typing_message.assert_called_once()
            self.assertIn("请先选中正确写法", status.show_typing_message.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
