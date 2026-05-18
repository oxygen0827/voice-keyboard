import unittest
from unittest.mock import MagicMock

from agent.runtime_composition import RuntimeBackend, RuntimeOptions, options_from_args


class RuntimeCompositionTests(unittest.TestCase):
    def test_options_from_args_keeps_runtime_flags_only(self):
        class Args:
            no_serial = True
            port = "/dev/cu.test"
            headless = True

        self.assertEqual(
            options_from_args(Args()),
            RuntimeOptions(no_serial=True, port="/dev/cu.test"),
        )

    def test_runtime_backend_stop_stops_components_and_clears_slots(self):
        calls = []

        class Component:
            def __init__(self, name):
                self.name = name

            def stop(self):
                calls.append(self.name)

        backend = RuntimeBackend()
        backend.audio = Component("audio")
        backend.reader = Component("reader")
        backend.kbd_monitor = Component("keyboard")

        backend.stop()

        self.assertEqual(calls, ["audio", "reader", "keyboard"])
        self.assertIsNone(backend.audio)
        self.assertIsNone(backend.reader)
        self.assertIsNone(backend.mouse_monitor)
        self.assertIsNone(backend.kbd_monitor)


if __name__ == "__main__":
    unittest.main()
