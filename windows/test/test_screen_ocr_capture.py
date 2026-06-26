import unittest
from unittest.mock import patch

from agent import screen_ocr_capture
from agent.screen_ocr_capture import OcrTextLine


class ScreenOcrCaptureTests(unittest.TestCase):
    def test_voice_keyboard_ui_detection(self):
        self.assertTrue(
            screen_ocr_capture._looks_like_voice_keyboard_ui(
                "Voice Keyboard\n设置\n快捷键\n历史\n词典| 输入诊断"
            )
        )
        self.assertFalse(
            screen_ocr_capture._looks_like_voice_keyboard_ui(
                "Voice Keyboard typed in a normal editor"
            )
        )

    def test_fallback_visible_window_skips_excluded_pid(self):
        class Quartz:
            kCGWindowOwnerPID = "pid"
            kCGWindowNumber = "id"
            kCGWindowLayer = "layer"
            kCGWindowBounds = "bounds"

        rows = [
            {"pid": 10, "id": 1, "layer": 0, "bounds": {"Width": 500, "Height": 300}},
            {"pid": 20, "id": 2, "layer": 0, "bounds": {"Width": 500, "Height": 300}},
        ]
        with (
            patch.object(screen_ocr_capture, "Quartz", Quartz),
            patch.object(screen_ocr_capture, "_window_info_rows", return_value=rows),
        ):
            self.assertEqual(
                screen_ocr_capture._fallback_visible_window_id(excluded_pid=10),
                2,
            )

    def test_below_window_match_allows_repeated_short_cjk_correction_shape(self):
        self.assertTrue(
            screen_ocr_capture._ocr_text_matches_reference(
                "无人远，无人远，无人远",
                "胡任远，胡任远，胡任远",
                allow_repeated_correction_shape=True,
            )
        )
        self.assertFalse(
            screen_ocr_capture._ocr_text_matches_reference(
                "无人远，无人远，无人远",
                "Apple账户 蓝牙 网络 VPN",
                allow_repeated_correction_shape=True,
            )
        )

    def test_codex_text_mentioning_voice_keyboard_is_not_self_ui(self):
        with (
            patch.object(screen_ocr_capture, "_OS", "Darwin"),
            patch.object(screen_ocr_capture, "Quartz", object()),
            patch.object(screen_ocr_capture, "_frontmost_app_identity", return_value=("Codex", "com.openai.codex", 10)),
            patch.object(screen_ocr_capture, "_capture_frontmost_image", return_value=("front", "ocr_window", "window=1", 1)),
            patch.object(screen_ocr_capture, "_image_width", return_value=600),
            patch.object(screen_ocr_capture, "_image_height", return_value=400),
            patch.object(
                screen_ocr_capture,
                "_recognize_text",
                return_value=(
                    (
                        OcrTextLine("Voice Keyboard 设置 词典"),
                        OcrTextLine("王知行，王知行，王知行"),
                    ),
                    "lines=2",
                ),
            ),
        ):
            snapshot = screen_ocr_capture.capture_screen_text(reference_text="王之行，王之行，王之行")

        self.assertEqual(snapshot.text, "王知行，王知行，王知行")
        self.assertEqual(snapshot.source, "ocr_window")

    def test_repeated_cjk_selection_prefers_changed_line_over_exact_before_line(self):
        text = "\n".join(
            (
                "之前的内容",
                "王之行，王之行，王之行",
                "新的输入",
                "王知行，王知行，王知行",
            )
        )

        self.assertEqual(
            screen_ocr_capture._select_relevant_ocr_text(
                text,
                reference_text="王之行，王之行，王之行",
            ),
            "王知行，王知行，王知行",
        )

    def test_capture_screen_text_prefers_bottom_region_changed_line(self):
        def recognize(image):
            if image == "front":
                return ((OcrTextLine("王之行，王之行，王之行"),), "lines=1")
            return ((OcrTextLine("王知行，王知行，王知行"),), "lines=1")

        with (
            patch.object(screen_ocr_capture, "_OS", "Darwin"),
            patch.object(screen_ocr_capture, "Quartz", object()),
            patch.object(screen_ocr_capture, "_frontmost_app_identity", return_value=("Codex", "com.openai.codex", 10)),
            patch.object(screen_ocr_capture, "_capture_frontmost_image", return_value=("front", "ocr_window", "window=1", 1)),
            patch.object(screen_ocr_capture, "_capture_bottom_region_image", return_value="bottom"),
            patch.object(screen_ocr_capture, "_image_width", return_value=600),
            patch.object(screen_ocr_capture, "_image_height", return_value=400),
            patch.object(screen_ocr_capture, "_recognize_text", side_effect=recognize),
        ):
            snapshot = screen_ocr_capture.capture_screen_text(reference_text="王之行，王之行，王之行")

        self.assertEqual(snapshot.text, "王知行，王知行，王知行")
        self.assertEqual(snapshot.source, "ocr_window_bottom")
        self.assertIn("ScreenCaptureBottomRegion", [probe.name for probe in snapshot.probes])

    def test_capture_screen_text_uses_below_window_when_frontmost_is_own_ui(self):
        calls = []

        def recognize(image):
            calls.append(image)
            if image == "front":
                return (
                    (
                        OcrTextLine("Voice Keyboard"),
                        OcrTextLine("设置 快捷键 历史 词典 输入诊断"),
                    ),
                    "lines=2",
                )
            return ((OcrTextLine("胡任远，胡任远，胡任远"),), "lines=1")

        def visible_fallback(**_kwargs):
            raise AssertionError("visible fallback should not be used")

        with (
            patch.object(screen_ocr_capture, "_OS", "Darwin"),
            patch.object(screen_ocr_capture, "Quartz", object()),
            patch.object(screen_ocr_capture, "_frontmost_app_identity", return_value=("python", "", 10)),
            patch.object(screen_ocr_capture, "_capture_frontmost_image", return_value=("front", "ocr_window", "window=1", 1)),
            patch.object(screen_ocr_capture, "_capture_below_window_image", return_value="below"),
            patch.object(screen_ocr_capture, "_fallback_visible_ocr_text", side_effect=visible_fallback),
            patch.object(screen_ocr_capture, "_image_width", return_value=600),
            patch.object(screen_ocr_capture, "_image_height", return_value=400),
            patch.object(screen_ocr_capture, "_recognize_text", side_effect=recognize),
        ):
            snapshot = screen_ocr_capture.capture_screen_text(reference_text="胡人远")

        self.assertEqual(snapshot.text, "胡任远，胡任远，胡任远")
        self.assertEqual(snapshot.source, "ocr_screen_below_window")
        self.assertEqual(calls, ["front", "below"])
        self.assertIn("ScreenCaptureBelowWindow", [probe.name for probe in snapshot.probes])

    def test_capture_screen_text_skips_stacked_own_ui_below_windows(self):
        calls = []

        def capture_below(window_id):
            return f"below-{window_id}"

        def recognize(image):
            calls.append(image)
            if image in ("front", "below-1"):
                return (
                    (
                        OcrTextLine("Voice Keyboard"),
                        OcrTextLine("设置 快捷键 历史 词典 输入诊断"),
                    ),
                    "lines=2",
                )
            return ((OcrTextLine("王知行，王知行，王知行"),), "lines=1")

        with (
            patch.object(screen_ocr_capture, "_OS", "Darwin"),
            patch.object(screen_ocr_capture, "Quartz", object()),
            patch.object(screen_ocr_capture, "_frontmost_app_identity", return_value=("python", "", 10)),
            patch.object(screen_ocr_capture, "_capture_frontmost_image", return_value=("front", "ocr_window", "window=1", 1)),
            patch.object(screen_ocr_capture, "_window_ids_for_pid", return_value=(1, 4)),
            patch.object(screen_ocr_capture, "_capture_below_window_image", side_effect=capture_below),
            patch.object(screen_ocr_capture, "_image_width", return_value=600),
            patch.object(screen_ocr_capture, "_image_height", return_value=400),
            patch.object(screen_ocr_capture, "_recognize_text", side_effect=recognize),
        ):
            snapshot = screen_ocr_capture.capture_screen_text(reference_text="王之行，王之行，王之行")

        self.assertEqual(snapshot.text, "王知行，王知行，王知行")
        self.assertEqual(snapshot.source, "ocr_screen_below_window")
        self.assertEqual(calls, ["front", "below-1", "below-4"])

    def test_capture_screen_text_uses_below_window_for_repeated_cjk_shape(self):
        def recognize(image):
            if image == "front":
                return (
                    (
                        OcrTextLine("Voice Keyboard"),
                        OcrTextLine("设置 快捷键 历史 词典 输入诊断"),
                    ),
                    "lines=2",
                )
            return ((OcrTextLine("胡任远，胡任远，胡任远"),), "lines=1")

        with (
            patch.object(screen_ocr_capture, "_OS", "Darwin"),
            patch.object(screen_ocr_capture, "Quartz", object()),
            patch.object(screen_ocr_capture, "_frontmost_app_identity", return_value=("python", "", 10)),
            patch.object(screen_ocr_capture, "_capture_frontmost_image", return_value=("front", "ocr_window", "window=1", 1)),
            patch.object(screen_ocr_capture, "_capture_below_window_image", return_value="below"),
            patch.object(screen_ocr_capture, "_image_width", return_value=600),
            patch.object(screen_ocr_capture, "_image_height", return_value=400),
            patch.object(screen_ocr_capture, "_recognize_text", side_effect=recognize),
        ):
            snapshot = screen_ocr_capture.capture_screen_text(reference_text="无人远，无人远，无人远")

        self.assertEqual(snapshot.text, "胡任远，胡任远，胡任远")
        self.assertEqual(snapshot.source, "ocr_screen_below_window")

    def test_capture_screen_text_uses_fallback_when_frontmost_is_own_ui(self):
        calls = []

        def recognize(image):
            calls.append(image)
            if image == "front":
                return (
                    (
                        OcrTextLine("Voice Keyboard"),
                        OcrTextLine("设置 快捷键 历史 词典 输入诊断"),
                    ),
                    "lines=2",
                )
            return ((OcrTextLine("胡任远，胡任远，胡任远"),), "lines=1")

        with (
            patch.object(screen_ocr_capture, "_OS", "Darwin"),
            patch.object(screen_ocr_capture, "Quartz", object()),
            patch.object(screen_ocr_capture, "_frontmost_app_identity", return_value=("python", "", 10)),
            patch.object(screen_ocr_capture, "_capture_frontmost_image", return_value=("front", "ocr_window", "window=1", 1)),
            patch.object(screen_ocr_capture, "_capture_below_window_image", return_value=None),
            patch.object(screen_ocr_capture, "_fallback_visible_window_ids", return_value=[2]),
            patch.object(screen_ocr_capture, "_capture_window_image", return_value="fallback"),
            patch.object(screen_ocr_capture, "_image_width", return_value=600),
            patch.object(screen_ocr_capture, "_image_height", return_value=400),
            patch.object(screen_ocr_capture, "_recognize_text", side_effect=recognize),
        ):
            snapshot = screen_ocr_capture.capture_screen_text(reference_text="胡人远")

        self.assertEqual(snapshot.text, "胡任远，胡任远，胡任远")
        self.assertEqual(snapshot.source, "ocr_window_fallback")
        self.assertEqual(calls, ["front", "fallback"])
        self.assertIn("ScreenCaptureFallback", [probe.name for probe in snapshot.probes])

    def test_capture_screen_text_scans_until_relevant_fallback_window(self):
        calls = []

        def capture(window_id):
            return f"window-{window_id}"

        def recognize(image):
            calls.append(image)
            if image == "front":
                return (
                    (
                        OcrTextLine("Voice Keyboard"),
                        OcrTextLine("设置 快捷键 历史 词典 输入诊断"),
                    ),
                    "lines=2",
                )
            if image == "window-2":
                return ((OcrTextLine("Apple账户 蓝牙 网络 VPN"),), "lines=1")
            return ((OcrTextLine("胡任远，胡任远，胡任远"),), "lines=1")

        with (
            patch.object(screen_ocr_capture, "_OS", "Darwin"),
            patch.object(screen_ocr_capture, "Quartz", object()),
            patch.object(screen_ocr_capture, "_frontmost_app_identity", return_value=("python", "", 10)),
            patch.object(screen_ocr_capture, "_capture_frontmost_image", return_value=("front", "ocr_window", "window=1", 1)),
            patch.object(screen_ocr_capture, "_capture_below_window_image", return_value=None),
            patch.object(screen_ocr_capture, "_fallback_visible_window_ids", return_value=[2, 3]),
            patch.object(screen_ocr_capture, "_capture_window_image", side_effect=capture),
            patch.object(screen_ocr_capture, "_image_width", return_value=600),
            patch.object(screen_ocr_capture, "_image_height", return_value=400),
            patch.object(screen_ocr_capture, "_recognize_text", side_effect=recognize),
        ):
            snapshot = screen_ocr_capture.capture_screen_text(reference_text="胡人远")

        self.assertEqual(snapshot.text, "胡任远，胡任远，胡任远")
        self.assertEqual(snapshot.source, "ocr_window_fallback")
        self.assertEqual(calls, ["front", "window-2", "window-3"])


if __name__ == "__main__":
    unittest.main()
