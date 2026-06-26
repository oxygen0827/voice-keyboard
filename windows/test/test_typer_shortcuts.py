import unittest
import plistlib
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from pynput.keyboard import Key

from agent import app_launcher
from agent import macos_window_actions
from agent import typer
from agent.windows import window_actions as windows_window_actions


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

    def test_init_loads_app_shortcuts_from_config(self):
        with patch.dict(typer._APP_SHORTCUTS, {}, clear=True):
            typer.init({
                "application_shortcuts": {
                    "com.openai.codex": {
                        "发送": "cmd+enter",
                    },
                },
            })

            self.assertEqual(
                typer._APP_SHORTCUTS["com.openai.codex"]["发送"],
                [Key.cmd, Key.enter],
            )

    def test_init_loads_legacy_experimental_app_shortcuts_from_config(self):
        with patch.dict(typer._APP_SHORTCUTS, {}, clear=True):
            typer.init({
                "experimental_app_shortcuts": {
                    "com.openai.codex": {
                        "发送": "cmd+enter",
                    },
                },
            })

            self.assertEqual(
                typer._APP_SHORTCUTS["com.openai.codex"]["发送"],
                [Key.cmd, Key.enter],
            )

    def test_init_merges_legacy_and_current_app_shortcut_fields_by_action(self):
        with patch.dict(typer._APP_SHORTCUTS, {}, clear=True):
            typer.init({
                "experimental_app_shortcuts": {
                    "com.openai.codex": {
                        "发送": "cmd+enter",
                    },
                },
                "application_shortcuts": {
                    "com.openai.codex": {
                        "新建会话": "cmd+n",
                    },
                },
            })

            self.assertEqual(
                typer._APP_SHORTCUTS["com.openai.codex"],
                {
                    "发送": [Key.cmd, Key.enter],
                    "新建会话": [Key.cmd, typer.KeyCode.from_char("n")],
                },
            )

    def test_send_shortcut_prefers_active_application_shortcut(self):
        app = typer.ActiveApplication("Codex", "com.openai.codex", 42)
        with (
            patch.dict(typer._APP_SHORTCUTS, {
                "com.openai.codex": {"发送": [Key.cmd, Key.enter]},
            }, clear=True),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_press_keys") as press_keys,
        ):
            self.assertTrue(typer.send_shortcut("发送"))

        press_keys.assert_called_once_with([Key.cmd, Key.enter])

    def test_send_shortcut_does_not_use_builtin_app_preset(self):
        app = typer.ActiveApplication("Feishu", "com.bytedance.macos.feishu", 42)
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.dict(typer._APP_SHORTCUTS, {}, clear=True),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_press_keys") as press_keys,
        ):
            self.assertFalse(typer.send_shortcut("发送"))

        press_keys.assert_not_called()

    def test_custom_app_shortcut_overrides_builtin_preset(self):
        app = typer.ActiveApplication("Feishu", "com.bytedance.macos.feishu", 42)
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.dict(typer._APP_SHORTCUTS, {
                "com.bytedance.macos.feishu": {"发送": [Key.cmd, Key.enter]},
            }, clear=True),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_press_keys") as press_keys,
        ):
            self.assertTrue(typer.send_shortcut("发送"))

        press_keys.assert_called_once_with([Key.cmd, Key.enter])

    def test_list_shortcuts_includes_active_application_shortcuts(self):
        app = typer.ActiveApplication("Codex", "com.openai.codex", 42)
        with (
            patch.dict(typer._APP_SHORTCUTS, {
                "com.openai.codex": {"发送": [Key.cmd, Key.enter]},
            }, clear=True),
            patch.object(typer, "current_application", return_value=app),
        ):
            self.assertIn("发送", typer.list_shortcuts())

    def test_shortcut_catalog_prefers_application_entries_and_keeps_metadata(self):
        app = typer.ActiveApplication("Codex", "com.openai.codex", 42)
        with (
            patch.dict(typer._APP_SHORTCUTS, {
                "com.openai.codex": {"保存": [Key.cmd, Key.shift, typer.KeyCode.from_char("s")]},
            }, clear=True),
            patch.object(typer, "current_application", return_value=app),
        ):
            catalog = typer.shortcut_catalog()

        save = next(entry for entry in catalog if entry.name == "保存")
        self.assertEqual(save.source, "application")
        self.assertEqual(save.kind, "shortcut")
        self.assertEqual(save.application, "Codex (com.openai.codex)")
        self.assertEqual(save.risk, "normal")
        self.assertEqual([entry.name for entry in catalog].count("保存"), 1)

    def test_shortcut_catalog_marks_high_risk_named_actions(self):
        app = typer.ActiveApplication("Codex", "com.openai.codex", 42)
        with (
            patch.dict(typer._APP_SHORTCUTS, {
                "com.openai.codex": {"发送": [Key.cmd, Key.enter]},
            }, clear=True),
            patch.object(typer, "current_application", return_value=app),
        ):
            catalog = typer.shortcut_catalog()

        send = next(entry for entry in catalog if entry.name == "发送")
        self.assertEqual(send.source, "application")
        self.assertEqual(send.risk, "high")

    def test_universal_core_shortcuts_are_global_without_application_presets(self):
        app = typer.ActiveApplication("Microsoft Word", "com.microsoft.Word", 42)
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.dict(typer._APP_SHORTCUTS, {}, clear=True),
            patch.object(typer, "current_application", return_value=app),
        ):
            catalog = typer.shortcut_catalog()

        bold = next(entry for entry in catalog if entry.name == "加粗")
        self.assertEqual(bold.source, "global")
        self.assertEqual(bold.application, "")
        self.assertNotIn("插入批注", [entry.name for entry in catalog])

    def test_macos_builtin_presets_are_empty_by_default(self):
        cases = [
            typer.ActiveApplication("Chrome", "com.google.Chrome", 42),
            typer.ActiveApplication("Codex", "com.openai.codex", 42),
            typer.ActiveApplication("微信", "com.tencent.xinwechat", 42),
            typer.ActiveApplication("Microsoft Word", "com.microsoft.Word", 42),
            typer.ActiveApplication("Microsoft Excel", "com.microsoft.Excel", 42),
            typer.ActiveApplication("Microsoft PowerPoint", "com.microsoft.Powerpoint", 42),
            typer.ActiveApplication("WPS Office", "com.kingsoft.wpsoffice.mac", 42),
            typer.ActiveApplication("飞书", "com.bytedance.macos.feishu", 42),
        ]
        for app in cases:
            with self.subTest(app=app.label):
                with (
                    patch.object(typer, "_OS", "Darwin"),
                    patch.dict(typer._APP_SHORTCUTS, {}, clear=True),
                    patch.object(typer, "current_application", return_value=app),
                ):
                    catalog = typer.shortcut_catalog()

                self.assertFalse([
                    entry for entry in catalog
                    if entry.source == "application"
                ])

    def test_send_shortcut_uses_global_formatting_in_feishu(self):
        app = typer.ActiveApplication("飞书", "com.bytedance.macos.feishu", 42)
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.dict(typer._APP_SHORTCUTS, {}, clear=True),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_press_keys") as press_keys,
        ):
            self.assertTrue(typer.send_shortcut("加粗"))

        press_keys.assert_called_once_with([Key.cmd, typer.KeyCode.from_char("b")])

    def test_blocked_shortcut_name_is_removed_from_catalog_and_execution(self):
        app = typer.ActiveApplication("飞书", "com.bytedance.macos.feishu", 42)
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_BLOCKED_SHORTCUT_NAMES", set()),
            patch.object(typer, "_BLOCKED_SHORTCUT_KEY_SEQUENCES", set()),
            patch.object(typer, "_press_keys") as press_keys,
        ):
            typer.init({"blocked_shortcuts": ["加粗"]})
            self.assertNotIn("加粗", typer.list_shortcuts())
            self.assertFalse(typer.send_shortcut("加粗"))

        press_keys.assert_not_called()

    def test_blocked_shortcut_keys_are_removed_from_catalog_and_execution(self):
        app = typer.ActiveApplication("飞书", "com.bytedance.macos.feishu", 42)
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_BLOCKED_SHORTCUT_NAMES", set()),
            patch.object(typer, "_BLOCKED_SHORTCUT_KEY_SEQUENCES", set()),
            patch.object(typer, "_press_keys") as press_keys,
        ):
            typer.init({"blocked_shortcut_keys": ["cmd+shift+z"]})
            self.assertNotIn("重做", typer.list_shortcuts())
            self.assertFalse(typer.send_shortcut("重做"))

        press_keys.assert_not_called()

    def test_macos_builtin_app_preset_is_not_used_on_other_platforms(self):
        app = typer.ActiveApplication("Microsoft Word", "com.microsoft.Word", 42)
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.dict(typer._APP_SHORTCUTS, {}, clear=True),
            patch.object(typer, "current_application", return_value=app),
        ):
            application_names = {
                entry.name for entry in typer.shortcut_catalog()
                if entry.source == "application"
            }
            self.assertNotIn("加粗", application_names)

    def test_shortcut_policy_blocks_missing_shortcut_before_adapter_execution(self):
        app = typer.ActiveApplication("Codex", "com.openai.codex", 42)
        with (
            patch.dict(typer._APP_SHORTCUTS, {}, clear=True),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_press_keys") as press_keys,
        ):
            decision = typer.shortcut_policy_for_invocation("provider invented")
            result = typer.send_shortcut("provider invented")

        self.assertEqual(
            decision,
            typer.ShortcutPolicyDecision.missing("provider invented"),
        )
        self.assertFalse(result)
        press_keys.assert_not_called()

    def test_shortcut_policy_blocks_high_risk_shortcut_in_atomic_stack(self):
        app = typer.ActiveApplication("Codex", "com.openai.codex", 42)
        with (
            patch.dict(typer._APP_SHORTCUTS, {
                "com.openai.codex": {"发送": [Key.cmd, Key.enter]},
            }, clear=True),
            patch.object(typer, "current_application", return_value=app),
        ):
            decision = typer.shortcut_policy_for_invocation("发送", in_atomic_stack=True)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "high_risk_requires_confirmation")
        self.assertEqual(decision.risk, "high")

    def test_open_settings_is_global_system_action(self):
        with patch.object(typer, "_run_system_action", return_value=True) as run:
            self.assertTrue(typer.send_shortcut("打开系统设置"))

        run.assert_called_once_with("open_system_settings")

    def test_macos_window_actions_are_system_actions_without_key_chords(self):
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            patch.object(typer, "_run_system_action", return_value=True) as run,
            patch.object(typer, "_press_keys") as press_keys,
        ):
            names = set(typer.list_shortcuts())
            self.assertIn("窗口左半屏", names)
            self.assertIn("窗口右半屏", names)
            self.assertIn("窗口最大化", names)
            self.assertIn("窗口居中", names)
            left_half = next(entry for entry in typer.shortcut_catalog() if entry.name == "窗口左半屏")
            self.assertEqual(left_half.kind, "system_window_action")
            self.assertTrue(typer.send_shortcut("窗口左半屏"))

        run.assert_called_once_with("macos_window_left_half")
        press_keys.assert_not_called()

    def test_windows_window_actions_are_system_actions_without_key_chords(self):
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            patch.object(typer, "_run_system_action", return_value=True) as run,
            patch.object(typer, "_press_keys") as press_keys,
        ):
            names = set(typer.list_shortcuts())
            self.assertIn("窗口左半屏", names)
            self.assertIn("窗口右半屏", names)
            self.assertIn("窗口最大化", names)
            self.assertIn("窗口居中", names)
            left_half = next(entry for entry in typer.shortcut_catalog() if entry.name == "窗口左半屏")
            self.assertEqual(left_half.kind, "system_window_action")
            self.assertTrue(typer.send_shortcut("窗口左半屏"))

        run.assert_called_once_with("windows_window_left_half")
        press_keys.assert_not_called()

    def test_window_actions_are_not_exposed_on_linux(self):
        with (
            patch.object(typer, "_OS", "Linux"),
            patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
        ):
            self.assertNotIn("窗口左半屏", typer.list_shortcuts())

    def test_macos_window_target_rects_keep_slice_small_and_predictable(self):
        screen = macos_window_actions.MacWindowRect(0, 24, 1440, 876)
        current = macos_window_actions.MacWindowRect(200, 120, 800, 600)

        self.assertEqual(
            macos_window_actions.target_window_rect("left_half", current, screen),
            macos_window_actions.MacWindowRect(0, 24, 720, 876),
        )
        self.assertEqual(
            macos_window_actions.target_window_rect("right_half", current, screen),
            macos_window_actions.MacWindowRect(720, 24, 720, 876),
        )
        self.assertEqual(
            macos_window_actions.target_window_rect("maximize", current, screen),
            macos_window_actions.MacWindowRect(0, 24, 1440, 876),
        )
        self.assertEqual(
            macos_window_actions.target_window_rect("center", current, screen),
            macos_window_actions.MacWindowRect(320, 162, 800, 600),
        )

    def test_windows_window_target_rects_keep_slice_small_and_predictable(self):
        screen = windows_window_actions.WinWindowRect(0, 0, 1440, 900)
        current = windows_window_actions.WinWindowRect(200, 120, 800, 600)

        self.assertEqual(
            windows_window_actions.target_window_rect("left_half", current, screen),
            windows_window_actions.WinWindowRect(0, 0, 720, 900),
        )
        self.assertEqual(
            windows_window_actions.target_window_rect("right_half", current, screen),
            windows_window_actions.WinWindowRect(720, 0, 720, 900),
        )
        self.assertEqual(
            windows_window_actions.target_window_rect("maximize", current, screen),
            windows_window_actions.WinWindowRect(0, 0, 1440, 900),
        )
        self.assertEqual(
            windows_window_actions.target_window_rect("center", current, screen),
            windows_window_actions.WinWindowRect(320, 150, 800, 600),
        )

    def test_windows_replace_selection_types_directly_without_clipboard(self):
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "_replace_accessibility_selection", return_value=False),
            patch.object(typer, "type_text") as type_text,
            patch.object(typer, "_set_clipboard") as set_clipboard,
        ):
            typer.replace_selection("earth", original="world")

        type_text.assert_called_once_with("earth")
        set_clipboard.assert_not_called()

    def test_windows_delete_selection_sends_backspace_without_clipboard(self):
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "_replace_accessibility_selection", return_value=False),
            patch.object(typer, "_press_key") as press_key,
            patch.object(typer, "_set_clipboard") as set_clipboard,
        ):
            typer.delete_selection(original="world")

        press_key.assert_called_once_with(Key.backspace)
        set_clipboard.assert_not_called()

    def test_macos_window_action_sets_accessibility_frame(self):
        window = object()
        current = macos_window_actions.MacWindowRect(200, 120, 800, 600)
        screen = macos_window_actions.MacWindowRect(0, 24, 1440, 876)
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(macos_window_actions, "frontmost_window", return_value=window),
            patch.object(macos_window_actions, "is_fullscreen_window", return_value=False),
            patch.object(macos_window_actions, "window_rect", return_value=current),
            patch.object(macos_window_actions, "screen_for_window", return_value=screen),
            patch.object(macos_window_actions, "set_window_rect", return_value=True) as set_rect,
        ):
            self.assertTrue(typer._run_macos_window_action("right_half"))

        set_rect.assert_called_once_with(
            window,
            macos_window_actions.MacWindowRect(720, 24, 720, 876),
            typer.ApplicationServices,
            current_rect=current,
        )

    def test_macos_window_action_exits_fullscreen_before_setting_frame(self):
        window = object()
        current = macos_window_actions.MacWindowRect(200, 120, 800, 600)
        screen = macos_window_actions.MacWindowRect(0, 24, 1440, 876)
        fullscreen_checks = [True, False]

        class AX:
            @staticmethod
            def AXUIElementSetAttributeValue(_window, _attr, _value):
                return 0

        with (
            patch.object(macos_window_actions, "frontmost_window", return_value=window),
            patch.object(
                macos_window_actions,
                "is_fullscreen_window",
                side_effect=lambda *_args: fullscreen_checks.pop(0) if fullscreen_checks else False,
            ),
            patch.object(macos_window_actions, "window_rect", return_value=current),
            patch.object(macos_window_actions, "screen_for_window", return_value=screen),
            patch.object(macos_window_actions, "set_window_rect", return_value=True) as set_rect,
        ):
            self.assertTrue(
                macos_window_actions.run_window_action(
                    "left_half",
                    typer.ActiveApplication("Notes", "com.apple.Notes", 42),
                    AX,
                    MagicMock(),
                )
            )

        set_rect.assert_called_once_with(
            window,
            macos_window_actions.MacWindowRect(0, 24, 720, 876),
            AX,
            current_rect=current,
        )

    def test_macos_window_action_reacquires_window_after_fullscreen_exit(self):
        fullscreen_window = object()
        regular_window = object()
        current = macos_window_actions.MacWindowRect(200, 120, 800, 600)
        screen = macos_window_actions.MacWindowRect(0, 24, 1440, 876)

        class AX:
            @staticmethod
            def AXUIElementSetAttributeValue(_window, _attr, _value):
                return 0

        with (
            patch.object(
                macos_window_actions,
                "frontmost_window",
                side_effect=[fullscreen_window, regular_window],
            ) as frontmost,
            patch.object(
                macos_window_actions,
                "is_fullscreen_window",
                side_effect=lambda window, _ax: window is fullscreen_window,
            ),
            patch.object(macos_window_actions, "window_rect", return_value=current) as window_rect,
            patch.object(macos_window_actions, "screen_for_window", return_value=screen),
            patch.object(macos_window_actions, "set_window_rect", return_value=True) as set_rect,
        ):
            self.assertTrue(
                macos_window_actions.run_window_action(
                    "left_half",
                    typer.ActiveApplication("Notes", "com.apple.Notes", 42),
                    AX,
                    MagicMock(),
                )
            )

        self.assertEqual(frontmost.call_count, 2)
        window_rect.assert_called_once_with(regular_window, AX)
        set_rect.assert_called_once_with(
            regular_window,
            macos_window_actions.MacWindowRect(0, 24, 720, 876),
            AX,
            current_rect=current,
        )

    def test_macos_window_action_stops_when_fullscreen_exit_fails(self):
        window = object()

        class AX:
            @staticmethod
            def AXUIElementSetAttributeValue(_window, _attr, _value):
                return -25200

        with (
            patch.object(macos_window_actions, "frontmost_window", return_value=window),
            patch.object(macos_window_actions, "is_fullscreen_window", return_value=True),
            patch.object(macos_window_actions, "window_rect") as window_rect,
            patch.object(macos_window_actions, "set_window_rect") as set_rect,
        ):
            self.assertFalse(
                macos_window_actions.run_window_action(
                    "left_half",
                    typer.ActiveApplication("Notes", "com.apple.Notes", 42),
                    AX,
                    MagicMock(),
                )
            )

        window_rect.assert_not_called()
        set_rect.assert_not_called()

    def test_macos_window_frame_sets_size_before_position(self):
        window = object()
        rect = macos_window_actions.MacWindowRect(0, 24, 720, 876)
        calls = []

        class AX:
            kAXValueCGSizeType = "size"
            kAXValueCGPointType = "point"

            @staticmethod
            def CGSizeMake(width, height):
                return ("size", width, height)

            @staticmethod
            def CGPointMake(x, y):
                return ("point", x, y)

            @staticmethod
            def AXValueCreate(value_type, value):
                return (value_type, value)

            @staticmethod
            def AXValueGetValue(_value, _value_type, _default):
                return False, None

            @staticmethod
            def AXUIElementCopyAttributeValue(_window, _attr, _default):
                return 1, None

            @staticmethod
            def AXUIElementSetAttributeValue(_window, attr, _value):
                calls.append(attr)
                return 0

        with patch.object(macos_window_actions.time, "sleep"):
            self.assertTrue(
                macos_window_actions.set_window_rect(
                    window,
                    rect,
                    AX,
                    current_rect=macos_window_actions.MacWindowRect(200, 120, 900, 900),
                )
            )
        self.assertEqual(calls[:2], ["AXSize", "AXPosition"])

    def test_macos_window_frame_moves_small_window_then_expands_and_realigned(self):
        window = object()
        rect = macos_window_actions.MacWindowRect(0, 24, 720, 876)
        calls = []

        class AX:
            kAXValueCGSizeType = "size"
            kAXValueCGPointType = "point"

            @staticmethod
            def CGSizeMake(width, height):
                return ("size", width, height)

            @staticmethod
            def CGPointMake(x, y):
                return ("point", x, y)

            @staticmethod
            def AXValueCreate(value_type, value):
                return (value_type, value)

            @staticmethod
            def AXValueGetValue(_value, _value_type, _default):
                return False, None

            @staticmethod
            def AXUIElementCopyAttributeValue(_window, _attr, _default):
                return 1, None

            @staticmethod
            def AXUIElementSetAttributeValue(_window, attr, _value):
                calls.append(attr)
                return 0

        with patch.object(macos_window_actions.time, "sleep"):
            self.assertTrue(
                macos_window_actions.set_window_rect(
                    window,
                    rect,
                    AX,
                    current_rect=macos_window_actions.MacWindowRect(200, 120, 500, 400),
                )
            )

        self.assertEqual(calls[:3], ["AXPosition", "AXSize", "AXPosition"])

    def test_macos_window_frame_shrinks_before_moving_left_edge(self):
        window = object()
        current = macos_window_actions.MacWindowRect(500, 80, 1800, 900)
        screen = macos_window_actions.MacWindowRect(0, 24, 1440, 876)
        calls = []

        class AX:
            kAXValueCGSizeType = "size"
            kAXValueCGPointType = "point"

            @staticmethod
            def CGSizeMake(width, height):
                return ("size", width, height)

            @staticmethod
            def CGPointMake(x, y):
                return ("point", x, y)

            @staticmethod
            def AXValueCreate(value_type, value):
                return (value_type, value)

            @staticmethod
            def AXValueGetValue(_value, _value_type, _default):
                return False, None

            @staticmethod
            def AXUIElementCopyAttributeValue(_window, _attr, _default):
                return 1, None

            @staticmethod
            def AXUIElementSetAttributeValue(_window, attr, value):
                calls.append((attr, value))
                return 0

        def window_rect_probe(*_args):
            if calls:
                return macos_window_actions.MacWindowRect(0, 24, 720, 876)
            return current

        with (
            patch.object(macos_window_actions, "frontmost_window", return_value=window),
            patch.object(macos_window_actions, "is_fullscreen_window", return_value=False),
            patch.object(macos_window_actions, "window_rect", side_effect=window_rect_probe),
            patch.object(macos_window_actions, "screen_for_window", return_value=screen),
            patch.object(macos_window_actions.time, "sleep"),
        ):
            self.assertTrue(
                macos_window_actions.run_window_action(
                    "left_half",
                    typer.ActiveApplication("Notes", "com.apple.Notes", 42),
                    AX,
                    MagicMock(),
                )
            )

        self.assertEqual(calls[:2], [
            ("AXSize", ("size", ("size", 720, 876))),
            ("AXPosition", ("point", ("point", 0, 24))),
        ])

    def test_macos_window_frame_keeps_size_before_position_when_position_fails(self):
        window = object()
        rect = macos_window_actions.MacWindowRect(0, 24, 720, 876)
        calls = []

        class AX:
            kAXValueCGSizeType = "size"
            kAXValueCGPointType = "point"

            @staticmethod
            def CGSizeMake(width, height):
                return ("size", width, height)

            @staticmethod
            def CGPointMake(x, y):
                return ("point", x, y)

            @staticmethod
            def AXValueCreate(value_type, value):
                return (value_type, value)

            @staticmethod
            def AXValueGetValue(_value, _value_type, _default):
                return False, None

            @staticmethod
            def AXUIElementCopyAttributeValue(_window, _attr, _default):
                return 1, None

            @staticmethod
            def AXUIElementSetAttributeValue(_window, attr, _value):
                calls.append(attr)
                if calls == ["AXSize", "AXPosition"]:
                    return -25200
                return 0

        with patch.object(macos_window_actions.time, "sleep"):
            self.assertTrue(
                macos_window_actions.set_window_rect(
                    window,
                    rect,
                    AX,
                    current_rect=macos_window_actions.MacWindowRect(200, 120, 900, 900),
                )
            )
        self.assertEqual(calls[:2], ["AXSize", "AXPosition"])

    def test_macos_window_frame_reapplies_when_readback_is_not_target(self):
        window = object()
        rect = macos_window_actions.MacWindowRect(0, 24, 720, 876)
        reads = [
            macos_window_actions.MacWindowRect(-1200, 24, 1800, 876),
            macos_window_actions.MacWindowRect(0, 24, 720, 876),
        ]
        calls = []

        class AX:
            kAXValueCGSizeType = "size"
            kAXValueCGPointType = "point"

            @staticmethod
            def CGSizeMake(width, height):
                return ("size", width, height)

            @staticmethod
            def CGPointMake(x, y):
                return ("point", x, y)

            @staticmethod
            def AXValueCreate(value_type, value):
                return (value_type, value)

            @staticmethod
            def AXUIElementSetAttributeValue(_window, attr, _value):
                calls.append(attr)
                return 0

        with (
            patch.object(macos_window_actions, "window_rect", side_effect=lambda *_args: reads.pop(0)),
            patch.object(macos_window_actions.time, "sleep"),
        ):
            self.assertTrue(
                macos_window_actions.set_window_rect(
                    window,
                    rect,
                    AX,
                    current_rect=macos_window_actions.MacWindowRect(200, 120, 900, 900),
                )
            )

        self.assertEqual(calls, ["AXSize", "AXPosition", "AXSize", "AXPosition"])

    def test_macos_window_frame_accepts_app_constrained_half_screen(self):
        target = macos_window_actions.MacWindowRect(745, -1440, 1280, 1440)
        current = macos_window_actions.MacWindowRect(745, -1410, 1280, 1296)

        self.assertTrue(macos_window_actions.rect_satisfies_window_action(current, target))

    def test_macos_window_rect_reads_pyobjc_axvalue_return_tuple(self):
        position = typer.ApplicationServices.AXValueCreate(
            typer.ApplicationServices.kAXValueCGPointType,
            typer.ApplicationServices.CGPointMake(12, 34),
        )
        size = typer.ApplicationServices.AXValueCreate(
            typer.ApplicationServices.kAXValueCGSizeType,
            typer.ApplicationServices.CGSizeMake(640, 480),
        )

        def copy_attr(_window, attr, _default):
            if attr == "AXPosition":
                return 0, position
            if attr == "AXSize":
                return 0, size
            return 1, None

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(
                typer.ApplicationServices,
                "AXUIElementCopyAttributeValue",
                side_effect=copy_attr,
            ),
        ):
            rect = macos_window_actions.window_rect(object(), typer.ApplicationServices)

        self.assertEqual(rect, macos_window_actions.MacWindowRect(12, 34, 640, 480))

    def test_macos_visible_screens_convert_from_main_screen_top(self):
        class Point:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class Size:
            def __init__(self, width, height):
                self.width = width
                self.height = height

        class Rect:
            def __init__(self, x, y, width, height):
                self.origin = Point(x, y)
                self.size = Size(width, height)

        class Screen:
            def __init__(self, frame, visible):
                self._frame = frame
                self._visible = visible

            def frame(self):
                return self._frame

            def visibleFrame(self):
                return self._visible

        main = Screen(Rect(0, 0, 1512, 982), Rect(0, 53, 1512, 896))
        above = Screen(Rect(745, 982, 2560, 1440), Rect(745, 982, 2560, 1440))
        left_above = Screen(Rect(-1815, 982, 2560, 1440), Rect(-1815, 982, 2560, 1440))

        class Screens:
            @staticmethod
            def screens():
                return [main, above, left_above]

            @staticmethod
            def mainScreen():
                return main

        self.assertEqual(
            macos_window_actions.visible_screens(Screens),
            [
                macos_window_actions.MacWindowRect(0, 33, 1512, 896),
                macos_window_actions.MacWindowRect(745, -1440, 2560, 1440),
                macos_window_actions.MacWindowRect(-1815, -1440, 2560, 1440),
            ],
        )

    def test_macos_visible_screens_ignore_dynamic_main_screen_when_converting(self):
        class Point:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class Size:
            def __init__(self, width, height):
                self.width = width
                self.height = height

        class Rect:
            def __init__(self, x, y, width, height):
                self.origin = Point(x, y)
                self.size = Size(width, height)

        class Screen:
            def __init__(self, frame, visible):
                self._frame = frame
                self._visible = visible

            def frame(self):
                return self._frame

            def visibleFrame(self):
                return self._visible

        primary = Screen(Rect(0, 0, 1512, 982), Rect(0, 53, 1512, 896))
        upper = Screen(Rect(745, 982, 2560, 1440), Rect(745, 982, 2560, 1440))

        class Screens:
            @staticmethod
            def screens():
                return [primary, upper]

            @staticmethod
            def mainScreen():
                return upper

        self.assertEqual(
            macos_window_actions.visible_screens(Screens)[0],
            macos_window_actions.MacWindowRect(0, 33, 1512, 896),
        )

    def test_builtin_open_app_actions_cover_current_launch_slice(self):
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
        ):
            names = set(typer.list_shortcuts())

        self.assertIn("打开飞书", names)
        self.assertIn("打开Word", names)
        self.assertIn("打开Excel", names)
        self.assertIn("打开PowerPoint", names)
        self.assertIn("打开WPS", names)
        self.assertIn("打开谷歌浏览器", names)
        self.assertIn("打开Chrome", names)
        feishu = next(entry for entry in typer.shortcut_catalog() if entry.name == "打开飞书")
        self.assertEqual(feishu.kind, "app_launch")

    def test_macos_discovers_installed_app_launch_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Obsidian.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "md.obsidian",
                "CFBundleName": "Obsidian",
            }))

            with (
                patch.object(typer, "_OS", "Darwin"),
                patch.object(app_launcher, "MACOS_APP_SEARCH_DIRS", (tmp,)),
                patch.object(app_launcher, "DYNAMIC_APP_LAUNCH_CACHE", None),
                patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            ):
                self.assertIn("打开Obsidian", typer.list_shortcuts())

    def test_macos_discovered_app_launches_can_use_common_chinese_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "NeteaseMusic.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "com.netease.163music",
                "CFBundleName": "NeteaseMusic",
            }))

            with (
                patch.object(typer, "_OS", "Darwin"),
                patch.object(app_launcher, "MACOS_APP_SEARCH_DIRS", (tmp,)),
                patch.object(app_launcher, "DYNAMIC_APP_LAUNCH_CACHE", None),
                patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            ):
                names = set(typer.list_shortcuts())

        self.assertIn("打开网易云音乐", names)
        self.assertIn("打开网易云", names)

    def test_macos_discovered_terminal_can_use_chinese_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Terminal.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "com.apple.Terminal",
                "CFBundleName": "Terminal",
            }))

            with (
                patch.object(typer, "_OS", "Darwin"),
                patch.object(app_launcher, "MACOS_APP_SEARCH_DIRS", (tmp,)),
                patch.object(app_launcher, "DYNAMIC_APP_LAUNCH_CACHE", None),
                patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            ):
                self.assertIn("打开终端", typer.list_shortcuts())

    def test_macos_discovered_stocks_app_has_chinese_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Stocks.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "com.apple.stocks",
                "CFBundleName": "Stocks",
            }))

            with (
                patch.object(typer, "_OS", "Darwin"),
                patch.object(app_launcher, "MACOS_APP_SEARCH_DIRS", (tmp,)),
                patch.object(app_launcher, "DYNAMIC_APP_LAUNCH_CACHE", None),
                patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            ):
                names = set(typer.list_shortcuts())

        self.assertIn("打开股市", names)
        self.assertIn("打开股票", names)

    def test_send_shortcut_opens_builtin_macos_application_by_bundle_id(self):
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            patch.object(app_launcher.subprocess, "Popen") as popen,
        ):
            self.assertTrue(typer.send_shortcut("打开飞书"))

        popen.assert_called_once_with(["open", "-b", "com.bytedance.macos.feishu"])

    def test_send_shortcut_opens_builtin_chrome_application_by_bundle_id(self):
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            patch.object(app_launcher.subprocess, "Popen") as popen,
        ):
            self.assertTrue(typer.send_shortcut("打开谷歌浏览器"))

        popen.assert_called_once_with(["open", "-b", "com.google.Chrome"])

    def test_send_shortcut_opens_discovered_macos_application_by_bundle_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Obsidian.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "md.obsidian",
                "CFBundleName": "Obsidian",
            }))

            with (
                patch.object(typer, "_OS", "Darwin"),
                patch.object(app_launcher, "MACOS_APP_SEARCH_DIRS", (tmp,)),
                patch.object(app_launcher, "DYNAMIC_APP_LAUNCH_CACHE", None),
                patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
                patch.object(app_launcher.subprocess, "Popen") as popen,
            ):
                self.assertTrue(typer.send_shortcut("打开Obsidian"))

        popen.assert_called_once_with(["open", "-b", "md.obsidian"])

    def test_send_shortcut_opens_discovered_app_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Stocks.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "com.apple.stocks",
                "CFBundleName": "Stocks",
            }))

            with (
                patch.object(typer, "_OS", "Darwin"),
                patch.object(app_launcher, "MACOS_APP_SEARCH_DIRS", (tmp,)),
                patch.object(app_launcher, "DYNAMIC_APP_LAUNCH_CACHE", None),
                patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
                patch.object(app_launcher.subprocess, "Popen") as popen,
            ):
                self.assertTrue(typer.send_shortcut("打开stocks"))

        popen.assert_called_once_with(["open", "-b", "com.apple.stocks"])

    def test_init_loads_custom_app_launch_actions_from_config(self):
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.dict(app_launcher.CUSTOM_APP_LAUNCHES, {}, clear=True),
            patch.object(typer, "current_application", return_value=typer.ActiveApplication()),
            patch.object(app_launcher.subprocess, "Popen") as popen,
        ):
            typer.init({
                "app_launches": {
                    "打开Obsidian": {
                        "macos_bundle_id": "md.obsidian",
                        "macos_name": "Obsidian",
                    },
                },
            })

            self.assertIn("打开Obsidian", typer.list_shortcuts())
            self.assertTrue(typer.send_shortcut("打开Obsidian"))

        popen.assert_called_once_with(["open", "-b", "md.obsidian"])

    def test_builtin_shortcuts_include_system_actions(self):
        self.assertIn("打开系统设置", typer.list_shortcuts())
        self.assertNotIn("打开设置", typer.list_shortcuts())

    def test_global_shortcuts_are_limited_to_common_keyboard_actions(self):
        with patch.object(typer, "current_application", return_value=typer.ActiveApplication()):
            names = set(typer.list_shortcuts())

        self.assertIn("保存", names)
        self.assertIn("重做", names)
        self.assertIn("加粗", names)
        self.assertIn("斜体", names)
        self.assertIn("下划线", names)
        self.assertIn("查找", names)
        self.assertNotIn("居中", names)
        self.assertNotIn("替换", names)
        self.assertNotIn("截图", names)
        self.assertNotIn("新标签", names)
        self.assertNotIn("关闭标签", names)

    def test_macos_clip_method_pastes_text(self):
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_use_clipboard_mode", True),
            patch.object(typer, "paste_text") as paste_text,
            patch.object(typer, "_type_via_quartz") as type_via_quartz,
        ):
            typer.type_text("hello")

        paste_text.assert_called_once_with("hello")
        type_via_quartz.assert_not_called()

    def test_windows_clip_method_still_types_directly(self):
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "_use_clipboard_mode", True),
            patch.object(typer, "_type_via_clipboard_win") as type_via_clipboard_win,
            patch.object(typer, "_type_via_sendinput") as type_via_sendinput,
        ):
            typer.type_text("hello")

        type_via_sendinput.assert_called_once_with("hello")
        type_via_clipboard_win.assert_not_called()

    def test_windows_type_text_marks_sendinput_as_simulated(self):
        states = []

        def sendinput(_text):
            states.append(typer.is_simulating())

        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "_remember_focused_text_target_windows"),
            patch.object(typer, "_type_via_sendinput", side_effect=sendinput),
            patch.object(typer.time, "sleep"),
        ):
            typer.type_text("文静")

        self.assertEqual(states, [True])
        self.assertFalse(typer.is_simulating())

    def test_windows_clipboard_typing_marks_paste_as_simulated(self):
        states = []
        pressed = []

        class Keyboard:
            def press(self, key):
                pressed.append(("press", key, typer.is_simulating()))

            def release(self, key):
                pressed.append(("release", key, typer.is_simulating()))

        def press_key(_key):
            states.append(typer.is_simulating())

        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "_set_clipboard_win"),
            patch.object(typer, "_kb", Keyboard()),
            patch.object(typer, "_press_key", side_effect=press_key),
            patch.object(typer.time, "sleep"),
        ):
            typer._type_via_clipboard_win("文静")

        self.assertEqual(states, [True])
        self.assertEqual([item[2] for item in pressed], [True, True])
        self.assertFalse(typer.is_simulating())

    def test_focus_probe_is_disabled_before_typing(self):
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "NSWorkspace") as workspace,
            patch.object(typer, "ApplicationServices") as ax,
        ):
            self.assertTrue(typer.has_focused_text_input())

        workspace.sharedWorkspace.assert_not_called()
        ax.AXUIElementCreateApplication.assert_not_called()

    def test_get_selection_prefers_accessibility_selection(self):
        with (
            patch.object(typer, "_get_accessibility_selection", return_value="选中的文字"),
            patch.object(typer, "_copy_selection") as copy_selection,
        ):
            self.assertEqual(typer.get_selection(), "选中的文字")

        copy_selection.assert_not_called()

    def test_slice_caret_text_window_prefers_current_text_when_small(self):
        text = "第一句。第二句需要修改。第三句。"

        window = typer._slice_caret_text_window(text, text.index("需要"))

        self.assertIsNotNone(window)
        self.assertEqual(window.text, text)
        self.assertEqual(window.source, "text_field")

    def test_slice_caret_text_window_limits_long_sentence(self):
        text = "a" * 20

        window = typer._slice_caret_text_window(text, 10, max_chars=8)

        self.assertIsNotNone(window)
        self.assertEqual(window.text, "aaaaaaaa")

    def test_get_caret_text_window_reads_accessibility_value_and_range(self):
        focused = object()
        text = "第一句。第二句需要修改。第三句。"

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=(8, 0)),
            patch.object(typer, "ApplicationServices") as ax,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, text)

            window = typer.get_caret_text_window()

        self.assertIsNotNone(window)
        self.assertEqual(window.text, text)
        self.assertEqual(window.source, "text_field")

    def test_accessibility_selected_range_reads_pyobjc_return_tuple(self):
        app_services = typer.ApplicationServices
        selected_range = app_services.AXValueCreate(
            app_services.kAXValueCFRangeType,
            app_services.CFRangeMake(3, 4),
        )
        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "ApplicationServices") as ax,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, selected_range)
            ax.kAXValueCFRangeType = app_services.kAXValueCFRangeType
            ax.AXValueGetValue = app_services.AXValueGetValue

            self.assertEqual(typer._get_accessibility_selected_range(object()), (3, 4))

    def test_accessibility_replacement_uses_value_range(self):
        focused = object()
        state = {
            "value": "hello world",
            "range": (6, 5),
            "set_range": None,
        }

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_frontmost_app_is_codex", return_value=True),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=state["range"]),
            patch.object(typer, "_set_accessibility_selected_range") as set_range,
            patch.object(typer, "ApplicationServices") as ax,
            patch.object(typer, "_set_clipboard") as set_clipboard,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])

            def set_attr(element, attr, value):
                state[attr] = value
                return 0

            ax.AXUIElementSetAttributeValue.side_effect = set_attr

            typer.replace_selection("earth")

        self.assertEqual(state["AXValue"], "hello earth")
        set_range.assert_called_once_with(focused, 11, 0)
        set_clipboard.assert_not_called()

    def test_accessibility_delete_uses_value_range(self):
        focused = object()
        state = {"value": "hello world"}

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_frontmost_app_is_codex", return_value=True),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=(6, 5)),
            patch.object(typer, "_set_accessibility_selected_range"),
            patch.object(typer, "ApplicationServices") as ax,
            patch.object(typer, "_press_key") as press_key,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])

            def set_attr(element, attr, value):
                state[attr] = value
                return 0

            ax.AXUIElementSetAttributeValue.side_effect = set_attr

            typer.delete_selection()

        self.assertEqual(state["AXValue"], "hello ")
        press_key.assert_not_called()

    def test_accessibility_replacement_falls_back_to_original_when_selection_range_is_lost(self):
        focused = object()
        state = {"value": "hello world"}

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_frontmost_app_is_codex", return_value=True),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=(11, 0)),
            patch.object(typer, "_set_accessibility_selected_range") as set_range,
            patch.object(typer, "ApplicationServices") as ax,
            patch.object(typer, "_set_clipboard") as set_clipboard,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])

            def set_attr(element, attr, value):
                state[attr] = value
                return 0

            ax.AXUIElementSetAttributeValue.side_effect = set_attr

            typer.replace_selection("earth", original="world")

        self.assertEqual(state["AXValue"], "hello earth")
        set_range.assert_called_once_with(focused, 11, 0)
        set_clipboard.assert_not_called()

    def test_replace_text_window_requires_original_adjacent_to_caret(self):
        focused = object()
        state = {"value": "same text. other words. same text.", "range": (18, 0)}

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=state["range"]),
            patch.object(typer, "ApplicationServices") as ax,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])

            result = typer.replace_text_window("same text.", "changed.")

        self.assertFalse(result)
        ax.AXUIElementSetAttributeValue.assert_not_called()

    def test_replace_text_window_applies_when_original_contains_caret(self):
        focused = object()
        state = {"value": "First sentence. Second sentence here.", "range": (23, 0)}

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=state["range"]),
            patch.object(typer, "_set_accessibility_selected_range") as set_range,
            patch.object(typer, "ApplicationServices") as ax,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])

            def set_attr(element, attr, value):
                state[attr] = value
                return 0

            ax.AXUIElementSetAttributeValue.side_effect = set_attr

            result = typer.replace_text_window("Second sentence here.", "Changed sentence.")

        self.assertTrue(result)
        self.assertEqual(state["AXValue"], "First sentence. Changed sentence.")
        set_range.assert_called_once_with(focused, 33, 0)

    def test_replace_text_window_applies_when_original_starts_at_caret(self):
        focused = object()
        state = {"value": "same text. other words. same text.", "range": (24, 0)}

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=state["range"]),
            patch.object(typer, "_set_accessibility_selected_range") as set_range,
            patch.object(typer, "ApplicationServices") as ax,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])

            def set_attr(element, attr, value):
                state[attr] = value
                return 0

            ax.AXUIElementSetAttributeValue.side_effect = set_attr

            result = typer.replace_text_window("same text.", "changed.")

        self.assertTrue(result)
        self.assertEqual(state["AXValue"], "same text. other words. changed.")
        set_range.assert_called_once_with(focused, 32, 0)

    def test_replace_text_window_has_no_clipboard_fallback(self):
        with (
            patch.object(typer, "_replace_accessibility_selection", return_value=False),
            patch.object(typer, "_set_clipboard") as set_clipboard,
        ):
            result = typer.replace_text_window("world", "earth")

        self.assertFalse(result)
        set_clipboard.assert_not_called()

    def test_accessibility_delete_falls_back_to_original_when_selection_range_is_lost(self):
        focused = object()
        state = {"value": "hello world"}

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_frontmost_app_is_codex", return_value=True),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=(11, 0)),
            patch.object(typer, "_set_accessibility_selected_range") as set_range,
            patch.object(typer, "ApplicationServices") as ax,
            patch.object(typer, "_press_key") as press_key,
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])

            def set_attr(element, attr, value):
                state[attr] = value
                return 0

            ax.AXUIElementSetAttributeValue.side_effect = set_attr

            typer.delete_selection(original="world")

        self.assertEqual(state["AXValue"], "hello ")
        set_range.assert_called_once_with(focused, 6, 0)
        press_key.assert_not_called()

    def test_accessibility_value_failure_restores_selection_before_clipboard_fallback(self):
        focused = object()
        state = {"value": "hello world"}

        with (
            patch.object(typer, "_OS", "Darwin"),
            patch.object(typer, "_focused_accessibility_element", return_value=focused),
            patch.object(typer, "_get_accessibility_selected_range", return_value=(11, 0)),
            patch.object(typer, "_set_accessibility_selected_range", return_value=True) as set_range,
            patch.object(typer, "ApplicationServices") as ax,
            patch.object(typer, "_set_clipboard") as set_clipboard,
            patch.object(typer, "_kb"),
            patch.object(typer, "_press_key"),
        ):
            ax.AXUIElementCopyAttributeValue.return_value = (0, state["value"])
            ax.AXUIElementSetAttributeValue.return_value = 1

            typer.replace_selection("earth", original="world")

        set_range.assert_called_once_with(focused, 6, 5)
        set_clipboard.assert_called_once_with("earth")

    def test_windows_inspect_focused_text_reads_focused_control_without_typing(self):
        text = "\u6587\u51c0\uff0c\u6587\u51c0\uff0c\u6587\u51c0"
        app = typer.ActiveApplication("Notepad", "", 4242)
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=1001, create=True),
            patch.object(typer, "_read_window_text_windows", return_value=text, create=True),
            patch.object(typer, "_window_class_name_windows", return_value="Edit", create=True),
            patch.object(typer, "_type_via_sendinput") as sendinput,
            patch.object(typer, "_type_via_clipboard_win") as clipboard_type,
            patch.object(typer, "_set_clipboard_win") as set_clipboard,
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, text)
        self.assertEqual(snapshot.source, "Win32:WM_GETTEXT")
        self.assertEqual(snapshot.confidence, "medium")
        self.assertEqual(snapshot.role, "Edit")
        sendinput.assert_not_called()
        clipboard_type.assert_not_called()
        set_clipboard.assert_not_called()

    def test_windows_inspect_focused_text_prefers_uiautomation_when_available(self):
        text = "\u6587\u51c0\uff0c\u6587\u51c0\uff0c\u6587\u51c0"
        app = typer.ActiveApplication("WeChat", "", 4242)
        pattern = types.SimpleNamespace(Value=text)
        control = types.SimpleNamespace(
            ControlTypeName="EditControl",
            Name="message",
            ClassName="Edit",
            GetValuePattern=lambda: pattern,
        )
        fake_uia = types.SimpleNamespace(
            GetFocusedControl=lambda: control,
            WalkControl=lambda control, includeTop=False, maxDepth=5: iter(()),
        )

        with (
            patch.dict(sys.modules, {"uiautomation": fake_uia}),
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=1001, create=True) as hwnd,
            patch.object(typer, "_read_window_text_windows", return_value="", create=True) as win32_read,
            patch.object(typer, "_type_via_sendinput") as sendinput,
            patch.object(typer, "_set_clipboard_win") as set_clipboard,
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, text)
        self.assertEqual(snapshot.source, "UIAutomation:ValuePattern")
        self.assertEqual(snapshot.confidence, "medium")
        self.assertEqual(snapshot.role, "EditControl")
        hwnd.assert_not_called()
        win32_read.assert_not_called()
        sendinput.assert_not_called()
        set_clipboard.assert_not_called()

    def test_windows_inspect_focused_text_finds_uia_child_edit_control(self):
        text = "\u6587\u51c0\uff0c\u6587\u51c0\uff0c\u6587\u51c0"
        app = typer.ActiveApplication("WeChat", "", 4242)
        pattern = types.SimpleNamespace(Value=text)
        outer = types.SimpleNamespace(
            ControlTypeName="PaneControl",
            Name="\u5fae\u4fe1",
            ClassName="Qt51514QWindowIcon",
        )
        edit = types.SimpleNamespace(
            ControlTypeName="EditControl",
            Name="message",
            ClassName="Edit",
            GetValuePattern=lambda: pattern,
        )
        fake_uia = types.SimpleNamespace(
            GetFocusedControl=lambda: outer,
            WalkControl=lambda control, includeTop=False, maxDepth=5: iter(((edit, 1),)),
        )

        with (
            patch.dict(sys.modules, {"uiautomation": fake_uia}),
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=1001, create=True) as hwnd,
            patch.object(typer, "_read_window_text_windows", return_value="\u5fae\u4fe1", create=True) as win32_read,
            patch.object(typer, "_type_via_sendinput") as sendinput,
            patch.object(typer, "_set_clipboard_win") as set_clipboard,
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, text)
        self.assertEqual(snapshot.source, "UIAutomation:ValuePattern")
        self.assertEqual(snapshot.role, "EditControl")
        hwnd.assert_not_called()
        win32_read.assert_not_called()
        sendinput.assert_not_called()
        set_clipboard.assert_not_called()

    def test_windows_inspect_focused_text_skips_document_url_and_uses_child_edit(self):
        text = "\u738b\u77e5\u884c\uff0c\u738b\u77e5\u884c\uff0c\u738b\u77e5\u884c"
        app = typer.ActiveApplication("Codex", "", 4242)
        document_pattern = types.SimpleNamespace(Value="app://-/index.html")
        edit_pattern = types.SimpleNamespace(Value=text)
        document = types.SimpleNamespace(
            ControlTypeName="DocumentControl",
            Name="Codex",
            ClassName="Chrome_WidgetWin_1",
            GetValuePattern=lambda: document_pattern,
        )
        edit = types.SimpleNamespace(
            ControlTypeName="EditControl",
            Name="message",
            ClassName="",
            GetValuePattern=lambda: edit_pattern,
        )
        fake_uia = types.SimpleNamespace(
            GetFocusedControl=lambda: document,
            WalkControl=lambda control, includeTop=False, maxDepth=5: iter(((edit, 1),)),
        )

        with (
            patch.dict(sys.modules, {"uiautomation": fake_uia}),
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=1001, create=True) as hwnd,
            patch.object(typer, "_read_window_text_windows", return_value="", create=True) as win32_read,
            patch.object(typer, "_type_via_sendinput") as sendinput,
            patch.object(typer, "_set_clipboard_win") as set_clipboard,
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, text)
        self.assertEqual(snapshot.source, "UIAutomation:ValuePattern")
        self.assertEqual(snapshot.role, "EditControl")
        hwnd.assert_not_called()
        win32_read.assert_not_called()
        sendinput.assert_not_called()
        set_clipboard.assert_not_called()

    def test_windows_inspect_focused_text_reads_prosemirror_child_text(self):
        text = "\u738b\u77e5\u884c\uff0c\u738b\u77e5\u884c\uff0c\u738b\u77e5\u884c"
        app = typer.ActiveApplication("Codex", "", 4242)
        editor = types.SimpleNamespace(
            ControlTypeName="GroupControl",
            Name="",
            ClassName="ProseMirror ProseMirror-focused",
            GetTextPattern=lambda: types.SimpleNamespace(
                DocumentRange=types.SimpleNamespace(GetText=lambda max_chars: "\n\u8981\u6c42\u540e\u7eed\u53d8\u66f4"),
                GetSelection=lambda: [],
            ),
        )
        trailing_break = types.SimpleNamespace(
            ControlTypeName="TextControl",
            Name="\n",
            ClassName="ProseMirror-trailingBreak",
        )
        paragraph = types.SimpleNamespace(
            ControlTypeName="TextControl",
            Name=text,
            ClassName="",
        )

        def walk(control, includeTop=False, maxDepth=5):
            if control is editor:
                return iter(((trailing_break, 1), (paragraph, 2)))
            return iter(())

        fake_uia = types.SimpleNamespace(
            GetFocusedControl=lambda: editor,
            WalkControl=walk,
        )

        with (
            patch.dict(sys.modules, {"uiautomation": fake_uia}),
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=1001, create=True) as hwnd,
            patch.object(typer, "_read_window_text_windows", return_value="", create=True) as win32_read,
            patch.object(typer, "_type_via_sendinput") as sendinput,
            patch.object(typer, "_set_clipboard_win") as set_clipboard,
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, text)
        self.assertEqual(snapshot.source, "UIAutomation:DescendantText")
        self.assertEqual(snapshot.role, "GroupControl")
        hwnd.assert_not_called()
        win32_read.assert_not_called()
        sendinput.assert_not_called()
        set_clipboard.assert_not_called()

    def test_windows_inspect_focused_text_skips_prosemirror_placeholder_and_page_dump(self):
        app = typer.ActiveApplication("Codex", "", 4242)
        editor = types.SimpleNamespace(
            ControlTypeName="GroupControl",
            Name="",
            ClassName="ProseMirror ProseMirror-focused",
            GetTextPattern=lambda: types.SimpleNamespace(
                DocumentRange=types.SimpleNamespace(GetText=lambda max_chars: "\n\u8981\u6c42\u540e\u7eed\u53d8\u66f4"),
                GetSelection=lambda: [],
            ),
        )
        placeholder = types.SimpleNamespace(
            ControlTypeName="TextControl",
            Name="\u8981\u6c42\u540e\u7eed\u53d8\u66f4",
            ClassName="placeholder",
        )
        page_text = "\ufffc\n\u66f4\u65b0\n\u6587\u4ef6\n\u7f16\u8f91\n\u89c6\u56fe\n\u5e2e\u52a9\n\ufffc\nvoice-keyboard\n\ufffc\n"
        document = types.SimpleNamespace(
            ControlTypeName="DocumentControl",
            Name="Codex",
            ClassName="Chrome_WidgetWin_1",
            GetTextPattern=lambda: types.SimpleNamespace(
                DocumentRange=types.SimpleNamespace(GetText=lambda max_chars: page_text),
                GetSelection=lambda: [],
            ),
        )

        def walk(control, includeTop=False, maxDepth=5):
            if control is editor:
                return iter(((placeholder, 1),))
            return iter(())

        fake_uia = types.SimpleNamespace(
            GetFocusedControl=lambda: editor,
            ControlFromHandle=lambda hwnd: document,
            GetForegroundControl=lambda: document,
            WalkControl=walk,
        )

        with (
            patch.dict(sys.modules, {"uiautomation": fake_uia}),
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=1001, create=True),
            patch.object(typer, "_read_window_text_windows", return_value="", create=True),
            patch.object(typer, "_window_class_name_windows", return_value="Chrome_WidgetWin_1", create=True),
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, "")
        self.assertEqual(snapshot.source, "unsupported")

    def test_windows_inspect_focused_text_skips_document_page_navigation_dump(self):
        app = typer.ActiveApplication("Steam", "", 4242)
        page_text = (
            "Steam 查看 好友 游戏 帮助 oxygen 商店 库 社区 OXYGEN 主页 "
            "游戏 库筛选条件 游戏模式 单人 多人 合作 本地多人 游戏状态 "
            "准备就绪 已本地安装 已玩过 未玩过 私密 硬件支持 手柄支持 "
            "Steam Deck 支持 建议使用控制器 完全支持控制器 VR 非 VR 游戏 "
            "特色 集换式卡牌 创意工坊 成就 远程同乐 家庭共享 语言 任意语言 "
            "类型 动作 冒险 休闲 独立 大型多人在线 竞速 角色扮演 模拟 体育 策略"
        )
        document = types.SimpleNamespace(
            ControlTypeName="DocumentControl",
            Name="Steam",
            ClassName="Chrome_RenderWidgetHostHWND",
            GetTextPattern=lambda: types.SimpleNamespace(
                DocumentRange=types.SimpleNamespace(GetText=lambda max_chars: page_text),
                GetSelection=lambda: [],
            ),
        )
        fake_uia = types.SimpleNamespace(
            GetFocusedControl=lambda: document,
            WalkControl=lambda control, includeTop=False, maxDepth=5: iter(()),
        )

        with (
            patch.dict(sys.modules, {"uiautomation": fake_uia}),
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=0, create=True),
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, "")
        self.assertEqual(snapshot.source, "unsupported")

    def test_windows_type_text_remembers_uia_target_for_later_correction_capture(self):
        text = "\u6587\u51c0\uff0c\u6587\u51c0\uff0c\u6587\u51c0"
        app = typer.ActiveApplication("WeChat", "", 4242)
        pattern = types.SimpleNamespace(Value="")
        edit = types.SimpleNamespace(
            ControlTypeName="EditControl",
            Name="message",
            ClassName="Edit",
            GetValuePattern=lambda: pattern,
        )
        outer = types.SimpleNamespace(
            ControlTypeName="PaneControl",
            Name="\u5fae\u4fe1",
            ClassName="Qt51514QWindowIcon",
        )
        focused = {"control": edit}
        fake_uia = types.SimpleNamespace(
            GetFocusedControl=lambda: focused["control"],
            WalkControl=lambda control, includeTop=False, maxDepth=5: iter(()),
        )

        with (
            patch.dict(sys.modules, {"uiautomation": fake_uia}),
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=0, create=True),
            patch.object(typer, "_type_via_sendinput") as sendinput,
        ):
            self.assertTrue(typer.type_text("x") is None)
            pattern.Value = text
            focused["control"] = outer
            snapshot = typer.inspect_focused_text(max_chars=2000)

        sendinput.assert_called_once_with("x")
        self.assertEqual(snapshot.text, text)
        self.assertEqual(snapshot.source, "UIAutomation:ValuePattern")
        self.assertEqual(snapshot.role, "EditControl")
        self.assertTrue(
            any(probe.name == "UIAutomationRememberedTarget" and probe.ok for probe in snapshot.probes)
        )

    def test_windows_inspect_focused_text_skips_non_edit_window_title(self):
        app = typer.ActiveApplication("WeChat", "", 4242)
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "current_application", return_value=app),
            patch.object(typer, "_inspect_focused_text_uia_windows", return_value=None),
            patch.object(typer, "_focused_text_window_handle_windows", return_value=1001, create=True),
            patch.object(typer, "_read_window_text_windows", return_value="\u5fae\u4fe1", create=True),
            patch.object(typer, "_window_class_name_windows", return_value="Qt51514QWindowIcon", create=True),
            patch.object(typer, "_type_via_sendinput") as sendinput,
            patch.object(typer, "_set_clipboard_win") as set_clipboard,
        ):
            snapshot = typer.inspect_focused_text(max_chars=2000)

        self.assertEqual(snapshot.text, "")
        self.assertEqual(snapshot.source, "unsupported")
        self.assertEqual(snapshot.confidence, "unsupported")
        self.assertEqual(snapshot.role, "Qt51514QWindowIcon")
        sendinput.assert_not_called()
        set_clipboard.assert_not_called()

    def test_windows_clipboard_probe_reads_full_text_and_restores_clipboard(self):
        clipboard = {"value": "old"}
        calls = []

        def set_clip(text):
            calls.append(("set", text))
            clipboard["value"] = text

        def get_clip():
            calls.append(("get", clipboard["value"]))
            return clipboard["value"]

        def copy_selection():
            calls.append(("copy",))
            clipboard["value"] = "胡任远，王知行，王知行王知行"

        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "_foreground_window_is_console", return_value=False),
            patch.object(typer, "_get_clipboard", side_effect=get_clip),
            patch.object(typer, "_set_clipboard", side_effect=set_clip),
            patch.object(typer, "_press_select_all") as select_all,
            patch.object(typer, "_copy_selection", side_effect=copy_selection),
            patch.object(typer, "_collapse_selection_to_end") as collapse,
            patch.object(typer.time, "sleep"),
        ):
            snapshot = typer.probe_full_text_via_clipboard()

        self.assertEqual(snapshot.text, "胡任远，王知行，王知行王知行")
        self.assertEqual(snapshot.source, "clipboard_probe")
        select_all.assert_called_once()
        collapse.assert_called_once()
        self.assertEqual(calls[-1], ("set", "old"))

    def test_windows_clipboard_probe_skips_console(self):
        with (
            patch.object(typer, "_OS", "Windows"),
            patch.object(typer, "_foreground_window_is_console", return_value=True),
            patch.object(typer, "_get_clipboard") as get_clip,
        ):
            snapshot = typer.probe_full_text_via_clipboard()

        self.assertEqual(snapshot.text, "")
        self.assertEqual(snapshot.source, "clipboard_probe_skipped")
        get_clip.assert_not_called()


if __name__ == "__main__":
    unittest.main()
