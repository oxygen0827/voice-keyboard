import unittest

from agent.ime_commit_monitor import ImeCommitMonitor


class ImeCommitMonitorTests(unittest.TestCase):
    def test_emit_deduplicates_same_text_in_short_window(self):
        values = []
        now = {"value": 10.0}
        monitor = ImeCommitMonitor(values.append, clock=lambda: now["value"])

        self.assertTrue(monitor._emit_text("净"))
        now["value"] += 0.03
        self.assertFalse(monitor._emit_text("净"))
        now["value"] += 0.30
        self.assertTrue(monitor._emit_text("净"))

        self.assertEqual(values, ["净", "净"])

    def test_emit_does_not_filter_different_text(self):
        values = []
        now = {"value": 10.0}
        monitor = ImeCommitMonitor(values.append, clock=lambda: now["value"])

        self.assertTrue(monitor._emit_text("净"))
        now["value"] += 0.03
        self.assertTrue(monitor._emit_text("文"))

        self.assertEqual(values, ["净", "文"])


if __name__ == "__main__":
    unittest.main()
