import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.memo_store import MemoStore


class MemoStoreTests(unittest.TestCase):
    def test_reads_flat_json_shape(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memo.json"
            path.write_text(
                json.dumps({"email": "me@example.com"}, ensure_ascii=False),
                encoding="utf-8",
            )

            store = MemoStore(path)

            self.assertEqual(store.get("email"), "me@example.com")
            self.assertEqual(store.keys(), ["email"])

    def test_saves_structured_json_format(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memo.json"
            store = MemoStore(path)

            store.save("address", "Shanghai", value_type="address", aliases=["home"])

            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["address"]["value"], "Shanghai")
            self.assertEqual(raw["address"]["value_type"], "address")
            self.assertEqual(raw["address"]["aliases"], ["home"])

    def test_imports_legacy_memos_json_when_new_store_is_missing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_path = root / "memos.json"
            new_path = root / "memo.json"
            legacy_path.write_text(
                json.dumps({"email": "me@example.com"}, ensure_ascii=False),
                encoding="utf-8",
            )

            store = MemoStore(new_path, legacy_path=legacy_path)

            self.assertEqual(store.get("email"), "me@example.com")
            raw = json.loads(new_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["email"]["value"], "me@example.com")

    def test_reads_structured_metadata_records(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memo.json"
            path.write_text(
                json.dumps({
                    "api": {
                        "value": "sk-test-only-dummy-key",
                        "value_type": "api_key",
                        "aliases": ["token"],
                        "sensitive": True,
                        "updated_at": 1.0,
                    }
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            store = MemoStore(path)

            self.assertEqual(store.get("api"), "sk-test-only-dummy-key")
            self.assertEqual(store.metadata("api")["value_type"], "api_key")
            self.assertTrue(store.metadata("api")["sensitive"])
            self.assertEqual(store.records()[0]["aliases"], ("token",))


if __name__ == "__main__":
    unittest.main()
