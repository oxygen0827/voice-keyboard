import tempfile
import unittest
from pathlib import Path


class IntentDiagnosticsTests(unittest.TestCase):
    def test_load_diagnostics_rows_returns_newest_first_with_source_index(self):
        from agent.intent_diagnostics import load_diagnostics_rows

        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "samples.jsonl"
            source.write_text(
                '{"ts": 100, "text": "one", "intent_type": "chat"}\n'
                '{"ts": 200, "text": "two", "intent_type": "shortcut"}\n',
                encoding="utf-8",
            )

            rows = load_diagnostics_rows(source, limit=10)

            self.assertEqual([row["text"] for row in rows], ["two", "one"])
            self.assertEqual([row["source_index"] for row in rows], [1, 0])

    def test_load_diagnostics_rows_filters_by_intent_type(self):
        from agent.intent_diagnostics import load_diagnostics_rows

        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "samples.jsonl"
            source.write_text(
                '{"ts": 100, "text": "one", "intent_type": "chat"}\n'
                '{"ts": 200, "text": "two", "intent_type": "shortcut"}\n'
                '{"ts": 300, "text": "three", "intent_type": "chat"}\n',
                encoding="utf-8",
            )

            rows = load_diagnostics_rows(source, limit=10, intent_type="chat")

            self.assertEqual([row["text"] for row in rows], ["three", "one"])
            self.assertEqual([row["source_index"] for row in rows], [2, 0])

    def test_load_diagnostics_rows_filters_by_review_state(self):
        from agent.intent_diagnostics import load_diagnostics_rows

        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "samples.jsonl"
            source.write_text(
                '{"ts": 100, "text": "one", "review_label": ""}\n'
                '{"ts": 200, "text": "two", "review_label": "correct"}\n'
                '{"ts": 300, "text": "three"}\n',
                encoding="utf-8",
            )

            reviewed = load_diagnostics_rows(source, limit=10, review_state="reviewed")
            unreviewed = load_diagnostics_rows(source, limit=10, review_state="unreviewed")

            self.assertEqual([row["text"] for row in reviewed], ["two"])
            self.assertEqual([row["text"] for row in unreviewed], ["three", "one"])

    def test_save_review_updates_underlying_sample(self):
        from agent.intent_diagnostics import load_diagnostics_rows, save_diagnostics_review
        from agent.intent_training import load_samples

        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "samples.jsonl"
            source.write_text(
                '{"ts": 100, "text": "one", "intent_type": "chat"}\n'
                '{"ts": 200, "text": "two", "intent_type": "shortcut"}\n',
                encoding="utf-8",
            )
            newest = load_diagnostics_rows(source, limit=10)[0]

            updated = save_diagnostics_review(
                source,
                newest,
                label="wrong_target",
                note="target should be current input",
            )

            self.assertEqual(updated["review_label"], "wrong_target")
            rows = load_samples(source, limit=0)
            self.assertEqual(rows[1]["review_label"], "wrong_target")
            self.assertEqual(rows[1]["review_note"], "target should be current input")

    def test_save_review_with_corrected_intent_appends_override(self):
        from agent.intent_diagnostics import load_diagnostics_rows, save_diagnostics_review
        from agent.intent_overrides import find_override
        from agent.intent_training import load_samples

        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "samples.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            source.write_text(
                '{"ts": 100, "text": "one", "intent_type": "chat"}\n'
                '{"ts": 200, "text": "表格里查一下", "intent_type": "chat"}\n',
                encoding="utf-8",
            )
            newest = load_diagnostics_rows(source, limit=10)[0]

            updated = save_diagnostics_review(
                source,
                newest,
                label="wrong_intent",
                note="should use local shortcut",
                corrected_intent={"type": "shortcut", "name": "查找"},
                override_path=overrides,
            )

            self.assertEqual(updated["corrected_intent"], {"type": "shortcut", "name": "查找"})
            rows = load_samples(source, limit=0)
            self.assertEqual(rows[1]["corrected_intent"], {"type": "shortcut", "name": "查找"})
            self.assertEqual(
                find_override("表格里查一下", path=overrides),
                {"type": "shortcut", "name": "查找"},
            )

    def test_summarize_diagnostics_counts_review_quality_and_override_coverage(self):
        from agent.intent_diagnostics import summarize_diagnostics
        from agent.intent_overrides import append_override

        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "samples.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            source.write_text(
                '{"text": "发送", "intent_type": "shortcut", "review_label": "correct"}\n'
                '{"text": "表格里查一下", "intent_type": "chat", "review_label": "wrong_intent", '
                '"corrected_intent": {"type": "shortcut", "name": "查找"}}\n'
                '{"text": "删一下", "intent_type": "delete", "review_label": "wrong_target"}\n'
                '{"text": "你好", "intent_type": "chat", "review_label": ""}\n',
                encoding="utf-8",
            )
            append_override(
                "表格里查一下",
                {"type": "shortcut", "name": "查找"},
                path=overrides,
            )

            summary = summarize_diagnostics(source, override_path=overrides)

            self.assertEqual(summary["total"], 4)
            self.assertEqual(summary["reviewed"], 3)
            self.assertEqual(summary["unreviewed"], 1)
            self.assertEqual(summary["correct"], 1)
            self.assertEqual(summary["wrong"], 2)
            self.assertEqual(summary["corrected"], 1)
            self.assertEqual(summary["override_covered"], 1)
            self.assertEqual(summary["wrong_by_intent"], {"chat": 1, "delete": 1})
            self.assertEqual(summary["accuracy_label"], "已标注正确率 33.3%")
            self.assertEqual(summary["evaluation"]["total"], 1)
            self.assertEqual(summary["evaluation"]["correct"], 1)
            self.assertEqual(summary["evaluation"]["accuracy_label"], "100.0%")


if __name__ == "__main__":
    unittest.main()
