import tempfile
import unittest
from pathlib import Path


class IntentSyncTests(unittest.TestCase):
    def test_sync_corrected_intents_appends_remote_rows_to_overrides(self):
        from agent.intent_overrides import find_override
        from agent.intent_sync import sync_corrected_intents

        with tempfile.TemporaryDirectory() as td:
            overrides = Path(td) / "overrides.jsonl"
            result = sync_corrected_intents(
                [
                    {
                        "text": "表格里查一下",
                        "corrected_intent": {"type": "shortcut", "name": "查找"},
                    },
                    {
                        "text": "没有修正",
                        "corrected_intent": {},
                    },
                    {
                        "text": "",
                        "corrected_intent": {"type": "delete"},
                    },
                ],
                override_path=overrides,
            )

            self.assertEqual(result["synced"], 1)
            self.assertEqual(result["skipped"], 2)
            self.assertEqual(
                find_override("表格里查一下", path=overrides),
                {"type": "shortcut", "name": "查找"},
            )

    def test_sync_corrected_intents_ignores_invalid_intents(self):
        from agent.intent_sync import sync_corrected_intents

        with tempfile.TemporaryDirectory() as td:
            overrides = Path(td) / "overrides.jsonl"
            result = sync_corrected_intents(
                [{"text": "表格里查一下", "corrected_intent": {"type": "shortcut"}}],
                override_path=overrides,
            )

            self.assertEqual(result["synced"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertFalse(overrides.exists())

    def test_sync_local_corrected_intents_reads_jsonl_samples(self):
        from agent.intent_overrides import find_override
        from agent.intent_sync import sync_local_corrected_intents

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            samples.write_text(
                '{"text": "表格里查一下", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n'
                '{"text": "没有修正", "corrected_intent": {}}\n'
                'not-json\n',
                encoding="utf-8",
            )

            result = sync_local_corrected_intents(samples, override_path=overrides)

            self.assertEqual(result["synced"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(
                find_override("表格里查一下", path=overrides),
                {"type": "shortcut", "name": "查找"},
            )


if __name__ == "__main__":
    unittest.main()
