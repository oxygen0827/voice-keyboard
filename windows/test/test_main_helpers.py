import unittest
import os
import sys
from unittest.mock import MagicMock, patch


class MainHelperTests(unittest.TestCase):
    def test_generated_text_cleanup_removes_common_model_markup(self):
        typer = MagicMock()
        typer.list_shortcuts.return_value = []
        with patch.dict("sys.modules", {"sounddevice": MagicMock(), "agent.typer": typer}):
            from agent.main import _clean_generated_text, _clean_polished_text

        self.assertEqual(_clean_generated_text("  ### 你好世界  "), "你好世界")
        self.assertEqual(_clean_polished_text("```text\n润色结果：你好世界\n```"), "你好世界")

    def test_llm_configured_accepts_typeup_backend_tokens(self):
        typer = MagicMock()
        typer.list_shortcuts.return_value = []
        with patch.dict("sys.modules", {"sounddevice": MagicMock(), "agent.typer": typer}):
            from agent.main import _llm_configured

        self.assertTrue(_llm_configured({
            "provider": "typeup_backend",
            "api_base_url": "http://localhost:8000",
            "access_token": "token",
        }))
        self.assertFalse(_llm_configured({
            "provider": "typeup_backend",
            "api_base_url": "http://localhost:8000",
            "access_token": "",
        }))
        self.assertTrue(_llm_configured({
            "provider": "openai",
            "api_key": "test-api-key",
        }))

    def test_configure_ssl_cert_file_sets_certifi_when_env_is_missing(self):
        typer = MagicMock()
        typer.list_shortcuts.return_value = []
        with (
            patch.dict("sys.modules", {"sounddevice": MagicMock(), "agent.typer": typer}),
            patch.dict(os.environ, {"USERPROFILE": os.path.dirname(__file__)}, clear=True),
        ):
            from agent.main import _configure_ssl_cert_file

            _configure_ssl_cert_file()

            self.assertIn("certifi", os.environ["SSL_CERT_FILE"])
            self.assertEqual(os.environ["SSL_CERT_FILE"], os.environ["REQUESTS_CA_BUNDLE"])

    def test_configure_ssl_cert_file_preserves_existing_valid_env(self):
        typer = MagicMock()
        typer.list_shortcuts.return_value = []
        existing = __file__
        with (
            patch.dict("sys.modules", {"sounddevice": MagicMock(), "agent.typer": typer}),
            patch.dict(os.environ, {
                "USERPROFILE": os.path.dirname(__file__),
                "SSL_CERT_FILE": existing,
                "REQUESTS_CA_BUNDLE": existing,
            }, clear=True),
        ):
            from agent.main import _configure_ssl_cert_file

            _configure_ssl_cert_file()

            self.assertEqual(os.environ["SSL_CERT_FILE"], existing)
            self.assertEqual(os.environ["REQUESTS_CA_BUNDLE"], existing)

    def test_windows_default_ui_routes_to_tray_without_starting_backend(self):
        typer = MagicMock()
        typer.list_shortcuts.return_value = []
        with patch.dict("sys.modules", {"sounddevice": MagicMock(), "agent.typer": typer}):
            import agent.main as main_mod

        with (
            patch.object(sys, "argv", ["agent.main"]),
            patch("sys.platform", "win32"),
            patch.object(main_mod, "_acquire_runtime_lock", return_value=True),
            patch("agent.config.ensure_user_config"),
            patch("agent.windows.tray.WindowsTrayApp") as tray_cls,
            patch.object(main_mod, "build_backend") as build_backend,
        ):
            main_mod.main()

        build_backend.assert_not_called()
        tray_cls.return_value.run.assert_called_once_with()

    def test_windows_no_ui_requires_explicit_backend_enable(self):
        typer = MagicMock()
        typer.list_shortcuts.return_value = []
        with patch.dict("sys.modules", {"sounddevice": MagicMock(), "agent.typer": typer}):
            import agent.main as main_mod

        with (
            patch.object(sys, "argv", ["agent.main", "--no-ui", "--headless", "--no-serial"]),
            patch("sys.platform", "win32"),
            patch.object(main_mod, "_acquire_runtime_lock", return_value=True),
            patch("agent.config.ensure_user_config"),
            patch.object(main_mod, "build_backend") as build_backend,
        ):
            main_mod.main()

        build_backend.assert_not_called()

    def test_windows_no_ui_enable_backend_keeps_explicit_debug_path(self):
        typer = MagicMock()
        typer.list_shortcuts.return_value = []
        backend = MagicMock()
        with patch.dict("sys.modules", {"sounddevice": MagicMock(), "agent.typer": typer}):
            import agent.main as main_mod

        with (
            patch.object(sys, "argv", ["agent.main", "--no-ui", "--headless", "--no-serial", "--enable-backend"]),
            patch("sys.platform", "win32"),
            patch.object(main_mod, "_acquire_runtime_lock", return_value=True),
            patch("agent.config.ensure_user_config"),
            patch("agent.permissions.summary_log", return_value="ok"),
            patch.object(main_mod, "TextBuffer"),
            patch.object(main_mod, "History") as history_cls,
            patch.object(main_mod, "build_backend", return_value=backend) as build_backend,
            patch.object(main_mod.time, "sleep", side_effect=KeyboardInterrupt),
        ):
            history_cls.return_value.compact = MagicMock()
            with self.assertRaises(KeyboardInterrupt):
                main_mod.main()

        build_backend.assert_called_once()


if __name__ == "__main__":
    unittest.main()
