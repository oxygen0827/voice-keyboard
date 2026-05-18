import unittest
from unittest.mock import MagicMock, patch

from pynput.keyboard import Key

from agent import typer


class TyperShortcutTests(unittest.TestCase):
    def test_init_loads_custom_shortcuts_from_config(self):
        with patch.object(typer, "register_shortcut") as register:
            typer.init({
                "shortcuts": {
                    "打开设置": "cmd+,",
                    "刷新": ["cmd", "r"],
                }
            })

        register.assert_any_call("打开设置", [Key.cmd, typer.KeyCode.from_char(",")])
        register.assert_any_call("刷新", [Key.cmd, typer.KeyCode.from_char("r")])

    def test_open_settings_is_global_system_action(self):
        with patch.object(typer, "_run_system_action", return_value=True) as run:
            self.assertTrue(typer.send_shortcut("打开系统设置"))

        run.assert_called_once_with("open_system_settings")

    def test_builtin_shortcuts_include_system_actions(self):
        self.assertIn("打开系统设置", typer.list_shortcuts())

    def test_macos_focus_probe_allows_insertion_when_accessibility_is_uncertain(self):
        class Workspace:
            @staticmethod
            def sharedWorkspace():
                return Workspace()

            def frontmostApplication(self):
                app = MagicMock()
                app.processIdentifier.return_value = 42
                return app

        class AX:
            @staticmethod
            def AXUIElementCreateApplication(pid):
                return object()

            @staticmethod
            def AXUIElementCopyAttributeValue(elem, attr, default):
                return 1, None

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "NSWorkspace", Workspace),
            patch.object(typer, "ApplicationServices", AX),
        ):
            self.assertTrue(typer.has_focused_text_input())


if __name__ == "__main__":
    unittest.main()
