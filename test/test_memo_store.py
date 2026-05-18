import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.memo_store import MemoStore


class MemoStoreCompatibilityTests(unittest.TestCase):
    def test_memo_store_reads_existing_memos_json_shape(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memos.json"
            path.write_text(
                json.dumps({"邮箱": "me@example.com"}, ensure_ascii=False),
                encoding="utf-8",
            )

            store = MemoStore(path)

            self.assertEqual(store.get("邮箱"), "me@example.com")
            self.assertEqual(store.keys(), ["邮箱"])

    def test_memo_store_keeps_flat_json_format_when_saving(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memos.json"
            store = MemoStore(path)

            store.save("地址", "上海")

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"地址": "上海"},
            )


if __name__ == "__main__":
    unittest.main()
