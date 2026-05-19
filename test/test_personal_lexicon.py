import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.personal_lexicon import (
    PersonalLexicon,
    is_lexicon_list_request,
    parse_lexicon_forget,
    parse_lexicon_learning,
    parse_selection_lexicon_learning,
)


class PersonalLexiconTests(unittest.TestCase):
    def test_remember_normalizes_future_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")

            self.assertTrue(lexicon.remember("白光雨", "白光宇"))

            self.assertEqual(lexicon.normalize("我的白光雨最喜欢说什么"), "我的白光宇最喜欢说什么")

    def test_rules_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lexicon.json"
            PersonalLexicon(path).remember("小白", "白光宇", "alias")

            lexicon = PersonalLexicon(path)

            self.assertEqual(lexicon.aliases_for("白光宇"), ("小白",))

    def test_parse_alias_learning(self):
        rule = parse_lexicon_learning("以后我说小白就是白光宇")

        self.assertIsNotNone(rule)
        self.assertEqual(rule.spoken, "小白")
        self.assertEqual(rule.written, "白光宇")
        self.assertEqual(rule.kind, "alias")

    def test_parse_correction_learning(self):
        rule = parse_lexicon_learning("不是白光雨，是白光宇")

        self.assertIsNotNone(rule)
        self.assertEqual(rule.spoken, "白光雨")
        self.assertEqual(rule.written, "白光宇")
        self.assertEqual(rule.kind, "correction")

    def test_forget_removes_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            lexicon.remember("小白", "白光宇", "alias")

            self.assertTrue(lexicon.forget("小白"))

            self.assertEqual(lexicon.aliases_for("白光宇"), ())

    def test_list_text_formats_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")
            lexicon.remember("小白", "白光宇", "alias")

            self.assertEqual(lexicon.list_text(), "小白 -> 白光宇 (alias)")

    def test_parse_forget_and_list_requests(self):
        self.assertEqual(parse_lexicon_forget("忘记我说小白这个说法"), "小白")
        self.assertTrue(is_lexicon_list_request("看一下个人词库"))

    def test_parse_selection_learning(self):
        rule = parse_selection_lexicon_learning("以后我说伽马四就是这个词")

        self.assertIsNotNone(rule)
        self.assertEqual(rule.spoken, "伽马四")
        self.assertEqual(rule.kind, "alias")

    def test_parse_selection_learning_ignores_colloquial_de_particle(self):
        rule = parse_selection_lexicon_learning("以后我说的伽马斯就是这个词")

        self.assertIsNotNone(rule)
        self.assertEqual(rule.spoken, "伽马斯")

    def test_phonetic_alias_uses_signature_without_storing_each_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            lexicon = PersonalLexicon(Path(tmp) / "lexicon.json")

            remembered = lexicon.remember_with_variants("伽马斯", "gemma4", "alias")

            self.assertEqual(remembered, ("伽马斯",))
            self.assertEqual(len(lexicon.rules()), 1)
            signatures = {
                "伽马斯": "gamasi",
                "干妈四": "ganmasi",
                "嘎玛寺": "gamasi",
            }
            with patch(
                "agent.personal_lexicon._phonetic_signature",
                side_effect=lambda text: signatures.get(text, text),
            ):
                self.assertEqual(lexicon.normalize("我正在打的比赛是干妈四"), "我正在打的比赛是gemma4")
                self.assertEqual(lexicon.normalize("嘎玛寺"), "gemma4")
            self.assertEqual(lexicon.aliases_for("gemma4"), ("伽马斯",))


if __name__ == "__main__":
    unittest.main()
