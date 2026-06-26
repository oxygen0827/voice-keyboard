import ctypes
import unittest
from unittest.mock import MagicMock, patch

from agent.windows import status_window as module


class WindowsStatusWindowPaintTests(unittest.TestCase):
    def test_paint_fills_whole_client_area_without_outer_border(self):
        window = module.StatusWindow()
        window._text = "Recording"
        window._measured_text_width = 72
        window._color = 0x5252F0

        hdc = object()
        bg_brush = object()
        font = object()
        old_font = object()

        user32 = MagicMock()
        gdi32 = MagicMock()
        user32.BeginPaint.return_value = hdc

        def get_client_rect(_hwnd, rect_ptr):
            rect = ctypes.cast(rect_ptr, ctypes.POINTER(module.RECT)).contents
            rect.left = 0
            rect.top = 0
            rect.right = 180
            rect.bottom = 44
            return 1

        user32.GetClientRect.side_effect = get_client_rect
        gdi32.CreateSolidBrush.return_value = bg_brush
        gdi32.SelectObject.side_effect = [
            old_font,
            None,
        ]
        gdi32.CreateFontW.return_value = font

        previous_user32 = module._user32
        previous_gdi32 = module._gdi32
        try:
            module._user32 = user32
            module._gdi32 = gdi32
            with patch.object(module, "_draw_smooth_dot", return_value=True) as draw_dot:
                window._paint(123)
        finally:
            module._user32 = previous_user32
            module._gdi32 = previous_gdi32

        user32.FillRect.assert_called_once()
        self.assertIs(user32.FillRect.call_args.args[0], hdc)
        self.assertIs(user32.FillRect.call_args.args[2], bg_brush)
        gdi32.RoundRect.assert_not_called()
        gdi32.CreatePen.assert_not_called()
        draw_dot.assert_called_once_with(hdc, 44, 17, module._HUD_DOT_SIZE, 0x5252F0)


if __name__ == "__main__":
    unittest.main()
