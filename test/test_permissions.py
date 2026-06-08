import unittest
from unittest.mock import patch


class PermissionRequestTests(unittest.TestCase):
    def test_request_helpers_are_noop_off_macos(self):
        from agent import permissions

        with patch.object(permissions, "_DARWIN", False):
            self.assertEqual(permissions.request_accessibility(), "granted")
            self.assertEqual(permissions.request_input_monitoring(), "granted")
            self.assertEqual(permissions.request_microphone_sync(timeout=0.01), "granted")

    def test_input_monitoring_request_maps_iokit_status(self):
        from agent import permissions

        def fake_request(_request_type):
            return 0

        with (
            patch.object(permissions, "_DARWIN", True),
            patch.object(permissions, "activate_app_for_permission_prompt"),
            patch.object(permissions, "_load_iokit_request", return_value=fake_request),
            patch.object(permissions, "input_monitoring", return_value="granted"),
        ):
            self.assertEqual(permissions.request_input_monitoring(), "granted")

    def test_input_monitoring_request_returns_actual_post_request_status(self):
        from agent import permissions

        def fake_request(_request_type):
            return 0

        with (
            patch.object(permissions, "_DARWIN", True),
            patch.object(permissions, "activate_app_for_permission_prompt"),
            patch.object(permissions, "_load_iokit_request", return_value=fake_request),
            patch.object(permissions, "input_monitoring", return_value="denied"),
        ):
            self.assertEqual(permissions.request_input_monitoring(), "denied")

    def test_microphone_capture_prompt_uses_raw_input_stream(self):
        from agent import permissions

        class FakeSoundDevice:
            def __init__(self):
                self.raw_opened = False
                self.input_opened = False

            def RawInputStream(self, **kwargs):
                self.raw_opened = True
                return self

            def InputStream(self, **kwargs):
                self.input_opened = True
                return self

            def sleep(self, _ms):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_sd = FakeSoundDevice()
        with (
            patch.object(permissions, "_DARWIN", True),
            patch.dict("sys.modules", {"sounddevice": fake_sd}),
        ):
            permissions.request_microphone_by_capture()
        self.assertTrue(fake_sd.raw_opened)
        self.assertFalse(fake_sd.input_opened)

    def test_source_runtime_does_not_activate_appkit_for_permission_prompt(self):
        from agent import permissions

        imports = []

        def fail_import(name, *args, **kwargs):
            imports.append(name)
            if name == "AppKit":
                raise AssertionError("source runtime should not import AppKit for prompt activation")
            return original_import(name, *args, **kwargs)

        original_import = __import__
        with (
            patch.object(permissions, "_DARWIN", True),
            patch("builtins.__import__", side_effect=fail_import),
        ):
            permissions.activate_app_for_permission_prompt()
        self.assertNotIn("AppKit", imports)


if __name__ == "__main__":
    unittest.main()
