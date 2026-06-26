import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.personal_dictionary import PersonalDictionaryStore


class PersonalDictionaryStoreTests(unittest.TestCase):
    def test_saves_and_reads_dictionary_entries(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "dictionary.json"
            store = PersonalDictionaryStore(path)

            store.save("小汪", phrase="客户联系人", source="manual", confidence=0.9)

            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["小汪"]["term"], "小汪")
            self.assertEqual(raw["小汪"]["phrase"], "客户联系人")

            loaded = PersonalDictionaryStore(path)
            entry = loaded.get("小汪")
            self.assertIsNotNone(entry)
            self.assertEqual(entry.term, "小汪")
            self.assertEqual(entry.source, "manual")
            self.assertEqual(loaded.terms(), ["小汪"])

    def test_reads_legacy_flat_dictionary(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "dictionary.json"
            path.write_text(
                json.dumps({"小汪": "小汪"}, ensure_ascii=False),
                encoding="utf-8",
            )

            store = PersonalDictionaryStore(path)

            self.assertEqual(store.get("小汪").term, "小汪")
            self.assertEqual(store.get("小汪").source, "legacy")

    def test_refuses_sensitive_values(self):
        with TemporaryDirectory() as tmp:
            store = PersonalDictionaryStore(Path(tmp) / "dictionary.json")

            with self.assertRaises(ValueError):
                store.save("api key", phrase="sk-test-only-dummy-key-1234567890")

    def test_allows_ordinary_technical_terms(self):
        with TemporaryDirectory() as tmp:
            store = PersonalDictionaryStore(Path(tmp) / "dictionary.json")

            store.save("API", phrase="application programming interface")

            self.assertEqual(store.get("API").term, "API")

    def test_exports_hotwords_and_prompt_hint(self):
        with TemporaryDirectory() as tmp:
            store = PersonalDictionaryStore(Path(tmp) / "dictionary.json")

            store.save("小汪", phrase="客户联系人", confidence=0.9)
            store.save("Voice Keyboard")

            self.assertEqual(store.hotwords(), ["Voice Keyboard", "小汪"])
            self.assertIn("Voice Keyboard", store.prompt_hint())
            self.assertIn("小汪（客户联系人）", store.prompt_hint())


if __name__ == "__main__":
    unittest.main()
