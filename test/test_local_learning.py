import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.local_learning import (
    LocalLearningRecorder,
    apply_correction_to_text,
    parse_correction_command,
)


class LocalLearningTests(unittest.TestCase):
    def test_parse_not_x_is_y_correction(self):
        command = parse_correction_command("\u4e0d\u662f\u5c0f\u738b\uff0c\u662f\u5c0f\u6c6a")

        self.assertIsNotNone(command)
        self.assertEqual(command.old, "\u5c0f\u738b")
        self.assertEqual(command.new, "\u5c0f\u6c6a")
        self.assertEqual(command.action, "replace")

    def test_parse_change_x_to_y_correction(self):
        command = parse_correction_command("\u628a\u6587\u9759\u6539\u6210\u6587\u51c0")

        self.assertIsNotNone(command)
        self.assertEqual(command.old, "\u6587\u9759")
        self.assertEqual(command.new, "\u6587\u51c0")
        self.assertEqual(command.action, "replace")

    def test_parse_using_x_change_to_y_correction(self):
        command = parse_correction_command("\u7528\u6587\u9759\u4fee\u6539\u6210\u6587\u51c0")

        self.assertIsNotNone(command)
        self.assertEqual(command.old, "\u6587\u9759")
        self.assertEqual(command.new, "\u6587\u51c0")
        self.assertEqual(command.action, "replace")

    def test_apply_correction_to_recent_text(self):
        command = parse_correction_command("\u4e0d\u662f\u5c0f\u738b\uff0c\u662f\u5c0f\u6c6a")

        self.assertEqual(
            apply_correction_to_text("\u4f60\u597d\u5c0f\u738b", command),
            "\u4f60\u597d\u5c0f\u6c6a",
        )

    def test_record_correction_writes_local_event_and_dictionary_candidate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = LocalLearningRecorder(
                events_path=root / "events.jsonl",
                dictionary_path=root / "dictionary.json",
            )
            command = parse_correction_command("\u4e0d\u662f\u5c0f\u738b\uff0c\u662f\u5c0f\u6c6a")

            recorder.remember_output("\u4f60\u597d\u5c0f\u738b")
            recorder.record_correction(command)

            event = json.loads((root / "events.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual(event["scope"], "recent_output")
            dictionary = json.loads((root / "dictionary.json").read_text(encoding="utf-8"))
            self.assertIn("\u5c0f\u6c6a", dictionary)


if __name__ == "__main__":
    unittest.main()
