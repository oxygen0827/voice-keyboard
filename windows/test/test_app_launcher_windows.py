import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import app_launcher


class WindowsAppLauncherTests(unittest.TestCase):
    def test_windows_discovers_start_menu_shortcuts(self):
        prefix = next(iter(app_launcher.MACOS_APP_LAUNCH_PRESETS))[:2]
        with tempfile.TemporaryDirectory() as tmp:
            shortcut = Path(tmp) / "Obsidian.lnk"
            shortcut.write_text("", encoding="utf-8")

            with patch.object(app_launcher, "WINDOWS_APP_SEARCH_DIRS", (tmp,)):
                launches = app_launcher.discover_windows_app_launches()

        self.assertEqual(launches[f"{prefix}Obsidian"].windows, str(shortcut))

    def test_windows_builtin_launch_prefers_discovered_shortcut(self):
        chrome_action = next(
            name
            for name, spec in app_launcher.MACOS_APP_LAUNCH_PRESETS.items()
            if spec.get("app_name") == "Google Chrome"
        )
        shortcut = app_launcher.ApplicationLaunchSpec(
            app_name="Chrome",
            windows=r"C:\Start Menu\Chrome.lnk",
        )

        with (
            patch.object(app_launcher, "discover_windows_app_launches", return_value={chrome_action: shortcut}),
            patch.object(app_launcher, "windows_app_path", return_value=""),
        ):
            launches = app_launcher.app_launches_for_system("Windows")

        self.assertEqual(launches[chrome_action].windows, shortcut.windows)
        self.assertEqual(launches[chrome_action].bundle_id, "")

    def test_windows_wechat_launch_prefers_wechat_shortcut(self):
        shortcut = app_launcher.ApplicationLaunchSpec(
            app_name="微信",
            windows=r"C:\Start Menu\微信\微信.lnk",
        )
        uninstall = app_launcher.ApplicationLaunchSpec(
            app_name="卸载微信",
            windows=r"C:\Start Menu\微信\卸载微信.lnk",
        )

        with patch.object(
            app_launcher,
            "discover_windows_app_launches",
            return_value={"打开微信": shortcut, "打开卸载微信": uninstall},
        ):
            launches = app_launcher.app_launches_for_system("Windows")

        self.assertEqual(launches["打开微信"].windows, shortcut.windows)

    def test_windows_app_launches_include_switch_aliases_for_builtin_apps(self):
        action_name = "\u6253\u5f00\u5fae\u4fe1"
        switch_name = "\u5207\u6362\u5230\u5fae\u4fe1"
        shortcut = app_launcher.ApplicationLaunchSpec(
            app_name="WeChat",
            windows=r"C:\Start Menu\WeChat.lnk",
        )

        with patch.object(
            app_launcher,
            "discover_windows_app_launches",
            return_value={action_name: shortcut},
        ):
            launches = app_launcher.app_launches_for_system("Windows")

        self.assertIs(launches[switch_name], launches[action_name])

    def test_windows_app_launches_do_not_expose_every_discovered_shortcut(self):
        discovered_only = app_launcher.ApplicationLaunchSpec(
            app_name="Random Tool",
            windows=r"C:\Start Menu\Random Tool.lnk",
        )

        with patch.object(
            app_launcher,
            "discover_windows_app_launches",
            return_value={"打开Random Tool": discovered_only},
        ):
            launches = app_launcher.app_launches_for_system("Windows")

        self.assertNotIn("打开Random Tool", launches)

    def test_windows_launch_uses_startfile_for_existing_target(self):
        if not hasattr(app_launcher.os, "startfile"):
            self.skipTest("os.startfile is only available on Windows")
        with tempfile.TemporaryDirectory() as tmp:
            shortcut = Path(tmp) / "Obsidian.lnk"
            shortcut.write_text("", encoding="utf-8")
            spec = app_launcher.ApplicationLaunchSpec(windows=str(shortcut))

            with patch.object(app_launcher.os, "startfile") as startfile:
                self.assertTrue(app_launcher.launch_application(spec, "Windows"))

        startfile.assert_called_once_with(str(shortcut))

    def test_windows_wechat_does_not_relaunch_when_process_is_running(self):
        spec = app_launcher.ApplicationLaunchSpec(
            app_name="WeChat",
            windows=r"C:\Start Menu\微信\微信.lnk",
        )

        with (
            patch.object(app_launcher, "activate_running_windows_application", return_value=False),
            patch.object(app_launcher, "windows_process_running", return_value=True),
            patch.object(app_launcher.os.path, "exists", return_value=True),
            patch.object(app_launcher.subprocess, "Popen") as popen,
        ):
            self.assertTrue(app_launcher.launch_application(spec, "Windows"))

        popen.assert_not_called()

    def test_linux_launch_splits_command_without_shell(self):
        spec = app_launcher.ApplicationLaunchSpec(linux='xdg-open "file name.txt"')

        with patch.object(app_launcher.subprocess, "Popen") as popen:
            self.assertTrue(app_launcher.launch_application(spec, "Linux"))

        popen.assert_called_once_with(["xdg-open", "file name.txt"])

    def test_windows_app_path_returns_empty_without_winreg(self):
        with patch.object(app_launcher, "winreg", None):
            self.assertEqual(app_launcher.windows_app_path("chrome.exe"), "")


if __name__ == "__main__":
    unittest.main()
