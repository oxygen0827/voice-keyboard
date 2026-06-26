import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


    def test_windows_listener_emits_only_committed_cjk_text(self):
        values = []
        started = []
        stopped = []
        captured = {}

        class Listener:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def start(self):
                started.append(True)

            def stop(self):
                stopped.append(True)

        with (
            patch("agent.ime_commit_monitor.sys.platform", "win32"),
            patch("agent.ime_commit_monitor._windows_keyboard_listener_class", return_value=Listener),
            patch("agent.typer.is_simulating", return_value=False),
        ):
            monitor = ImeCommitMonitor(values.append)
            monitor.start()
            captured["on_press"](SimpleNamespace(char="j"))
            captured["on_press"](SimpleNamespace(char="\u51c0"))
            monitor.stop()

        self.assertEqual(values, ["\u51c0"])
        self.assertEqual(started, [True])
        self.assertEqual(stopped, [True])


if __name__ == "__main__":
    unittest.main()
