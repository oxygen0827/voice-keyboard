import unittest
from unittest.mock import MagicMock, patch


class WindowsTraySafetyTests(unittest.TestCase):
    def test_legacy_tray_entry_reexports_new_windows_package(self):
        from agent.windows.tray import WindowsTrayApp as NewWindowsTrayApp
        from agent.windows_tray import WindowsTrayApp as LegacyWindowsTrayApp

        self.assertIs(LegacyWindowsTrayApp, NewWindowsTrayApp)

    def test_run_starts_keyboard_backend_by_default(self):
        backend = MagicMock()
        with (
            patch("agent.windows.tray.StatusWindow") as status_cls,
            patch("agent.windows.tray.WindowsMainWindow"),
            patch("agent.windows.tray.ensure_user_config"),
            patch("agent.windows.tray.threading.Thread") as thread_cls,
            patch("agent.windows.tray.pystray.Icon") as icon_cls,
            patch("agent.windows.tray.build_runtime_backend", return_value=backend) as build_backend,
        ):
            status_cls.return_value.run = MagicMock()
            icon_cls.return_value.run.return_value = None

            from agent.windows.tray import WindowsTrayApp

            app = WindowsTrayApp()
            app._read_config = MagicMock(return_value={})
            app.run()

        build_backend.assert_called_once()
        thread_cls.assert_called_once()
        icon_cls.return_value.run.assert_called_once_with()

    def test_run_can_start_in_standby_from_config(self):
        with (
            patch("agent.windows.tray.StatusWindow") as status_cls,
            patch("agent.windows.tray.WindowsMainWindow"),
            patch("agent.windows.tray.ensure_user_config"),
            patch("agent.windows.tray.threading.Thread") as thread_cls,
            patch("agent.windows.tray.pystray.Icon") as icon_cls,
            patch("agent.windows.tray.build_runtime_backend") as build_backend,
        ):
            status_cls.return_value.run = MagicMock()
            icon_cls.return_value.run.return_value = None

            from agent.windows.tray import WindowsTrayApp

            app = WindowsTrayApp()
            app._read_config = MagicMock(return_value={"ui": {"start_enabled": False}})
            app.run()

        build_backend.assert_not_called()
        thread_cls.assert_called_once()
        icon_cls.return_value.run.assert_called_once_with()

    def test_enable_and_disable_voice_keyboard_controls_backend_explicitly(self):
        backend = MagicMock()
        with (
            patch("agent.windows.tray.StatusWindow"),
            patch("agent.windows.tray.WindowsMainWindow"),
            patch("agent.windows.tray.build_runtime_backend", return_value=backend) as build_backend,
        ):
            from agent.windows.tray import WindowsTrayApp

            app = WindowsTrayApp()
            app._notify = MagicMock()
            app._refresh_menu = MagicMock()
            app._enable_voice_keyboard()
            app._disable_voice_keyboard()

        build_backend.assert_called_once()
        backend.stop.assert_called_once_with()

    def test_standby_insert_is_blocked_without_keyboard_fallback(self):
        with (
            patch("agent.windows.tray.StatusWindow"),
            patch("agent.windows.tray.WindowsMainWindow"),
            patch("agent.windows.tray.threading.Thread") as thread_cls,
            patch("agent.typer.type_text") as type_text,
        ):
            from agent.windows.tray import WindowsTrayApp

            app = WindowsTrayApp()
            app._notify = MagicMock()
            app._buf.push = MagicMock()

            thread_cls.side_effect = lambda target, **_kwargs: MagicMock(start=target)
            app._insert_text_after_menu_closes("secret", "Memo inserted")

        type_text.assert_not_called()
        app._buf.push.assert_not_called()
        app._notify.assert_called_once_with("insert_blocked_standby")

    def test_enabled_insert_uses_backend_input_environment(self):
        backend = MagicMock()
        backend.input_environment.insert_output_text.return_value = MagicMock(ok=True)
        with (
            patch("agent.windows.tray.StatusWindow"),
            patch("agent.windows.tray.WindowsMainWindow"),
            patch("agent.windows.tray.threading.Thread") as thread_cls,
        ):
            from agent.windows.tray import WindowsTrayApp

            app = WindowsTrayApp()
            app._backend_enabled = True
            app._backend = backend
            app._notify = MagicMock()

            thread_cls.side_effect = lambda target, **_kwargs: MagicMock(start=target)
            app._insert_text_after_menu_closes("hello", "History inserted")

        backend.input_environment.insert_output_text.assert_called_once_with("hello")
        app._notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
