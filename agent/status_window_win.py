"""Windows floating status HUD implemented with Win32 APIs via ctypes."""

from __future__ import annotations

import ctypes
import queue
from ctypes import wintypes


_STATES: dict[str, tuple[str, int]] = {
    "recording": ("录音中", 0x5252F0),
    "polish_recording": ("录音中 · 微润色", 0x78C931),
    "ai_recording": ("AI 指令录音中", 0xF755A8),
    "recognizing": ("识别中", 0x0B9EF5),
    "polishing": ("润色中", 0xD4B606),
    "ai_processing": ("AI 处理中", 0xF6823B),
    "error_stt": ("识别失败", 0x4444EF),
    "error_typing": ("打字失败", 0x4444EF),
    "error_llm": ("LLM 失败", 0x4444EF),
    "error_perm": ("权限未授予", 0x4444EF),
}

_ERROR_STATES = {"error_stt", "error_typing", "error_llm", "error_perm"}
_WM_APP_STATE = 0x8001
_WM_APP_STOP = 0x8002
_TIMER_POLL = 1
_TIMER_HIDE = 2
_SPI_GETWORKAREA = 0x0030
_HWND_TOPMOST = wintypes.HWND(-1)
_SWP_NOACTIVATE = 0x0010
_BOTTOM_MARGIN = 48
_CORNER_RADIUS = 18

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
_user32.SystemParametersInfoW.restype = wintypes.BOOL
_user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
_user32.SetWindowRgn.restype = ctypes.c_int
_gdi32.CreateRoundRectRgn.argtypes = [
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
]
_gdi32.CreateRoundRectRgn.restype = wintypes.HRGN


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


_user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
_user32.FillRect.restype = ctypes.c_int


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class StatusWindow:
    def __init__(self):
        self._q: queue.Queue[str] = queue.Queue()
        self._extra_setup = []
        self._hwnd = None
        self._state = "idle"
        self._text = ""
        self._color = 0xFFFFFF
        self._wndproc = WNDPROC(self._handle_message)
        self._hinst = _kernel32.GetModuleHandleW(None)
        self._class_name = "VoiceKeyboardStatusWindow"

    def set_state(self, state: str) -> None:
        self._q.put(state)
        if self._hwnd:
            _user32.PostMessageW(self._hwnd, _WM_APP_STATE, 0, 0)

    def add_main_thread_setup(self, fn) -> None:
        self._extra_setup.append(fn)

    def stop(self) -> None:
        if self._hwnd:
            _user32.PostMessageW(self._hwnd, _WM_APP_STOP, 0, 0)

    def run(self) -> None:
        self._register_class()
        ex_style = 0x00000008 | 0x00000080 | 0x00080000 | 0x00000020
        style = 0x80000000
        self._hwnd = _user32.CreateWindowExW(
            ex_style,
            self._class_name,
            "Voice Keyboard",
            style,
            0,
            0,
            260,
            44,
            None,
            None,
            self._hinst,
            None,
        )
        if not self._hwnd:
            raise ctypes.WinError()

        _user32.SetLayeredWindowAttributes(self._hwnd, 0, 235, 0x00000002)
        _user32.SetTimer(self._hwnd, _TIMER_POLL, 40, None)

        for fn in self._extra_setup:
            try:
                fn()
            except Exception as e:
                print(f"[status] 主线程初始化失败: {e}")

        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _register_class(self) -> None:
        wc = WNDCLASS()
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
        wc.hInstance = self._hinst
        wc.lpszClassName = self._class_name
        wc.hbrBackground = _gdi32.CreateSolidBrush(0x272322)
        _user32.RegisterClassW(ctypes.byref(wc))

    def _handle_message(self, hwnd, msg, wparam, lparam):
        if msg == 0x000F:
            self._paint(hwnd)
            return 0
        if msg == 0x0113:
            if wparam == _TIMER_POLL:
                self._poll()
            elif wparam == _TIMER_HIDE:
                _user32.KillTimer(hwnd, _TIMER_HIDE)
                _user32.ShowWindow(hwnd, 0)
            return 0
        if msg == _WM_APP_STATE:
            self._poll()
            return 0
        if msg == _WM_APP_STOP:
            _user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:
            _user32.PostQuitMessage(0)
            return 0
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _poll(self) -> None:
        try:
            while True:
                self._apply(self._q.get_nowait())
        except queue.Empty:
            pass

    def _apply(self, state: str) -> None:
        if not self._hwnd:
            return
        info = _STATES.get(state)
        if info is None or state == "idle":
            _user32.ShowWindow(self._hwnd, 0)
            return
        self._state = state
        self._text, self._color = info
        _user32.KillTimer(self._hwnd, _TIMER_HIDE)
        self._position()
        _user32.ShowWindow(self._hwnd, 8)
        _user32.InvalidateRect(self._hwnd, None, True)
        if state in _ERROR_STATES:
            _user32.SetTimer(self._hwnd, _TIMER_HIDE, 1500, None)

    def _position(self) -> None:
        hdc = _user32.GetDC(self._hwnd)
        font = self._font()
        old_font = _gdi32.SelectObject(hdc, font)
        size = SIZE()
        _gdi32.GetTextExtentPoint32W(hdc, self._text, len(self._text), ctypes.byref(size))
        _gdi32.SelectObject(hdc, old_font)
        _gdi32.DeleteObject(font)
        _user32.ReleaseDC(self._hwnd, hdc)

        width = max(130, size.cx + 54)
        height = 40
        work = RECT()
        if _user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(work), 0):
            x = int(work.left + ((work.right - work.left - width) / 2))
            y = int(work.bottom - height - _BOTTOM_MARGIN)
        else:
            screen_w = _user32.GetSystemMetrics(0)
            screen_h = _user32.GetSystemMetrics(1)
            x = int((screen_w - width) / 2)
            y = int(screen_h - height - _BOTTOM_MARGIN)
        if not _user32.SetWindowPos(self._hwnd, _HWND_TOPMOST, x, y, width, height, _SWP_NOACTIVATE):
            raise ctypes.WinError()
        region = _gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, _CORNER_RADIUS, _CORNER_RADIUS)
        if region:
            _user32.SetWindowRgn(self._hwnd, region, True)

    def _paint(self, hwnd) -> None:
        ps = PAINTSTRUCT()
        hdc = _user32.BeginPaint(hwnd, ctypes.byref(ps))
        rect = RECT()
        _user32.GetClientRect(hwnd, ctypes.byref(rect))

        bg = _gdi32.CreateSolidBrush(0x272322)
        _user32.FillRect(hdc, ctypes.byref(rect), bg)
        _gdi32.DeleteObject(bg)

        dot = _gdi32.CreateSolidBrush(self._color)
        _gdi32.SelectObject(hdc, dot)
        _gdi32.Ellipse(hdc, 16, 15, 26, 25)
        _gdi32.DeleteObject(dot)

        font = self._font()
        old_font = _gdi32.SelectObject(hdc, font)
        _gdi32.SetBkMode(hdc, 1)
        _gdi32.SetTextColor(hdc, 0xFAFAF9)
        text_rect = RECT(36, 10, rect.right - 12, rect.bottom)
        _user32.DrawTextW(hdc, self._text, -1, ctypes.byref(text_rect), 0)
        _gdi32.SelectObject(hdc, old_font)
        _gdi32.DeleteObject(font)

        _user32.EndPaint(hwnd, ctypes.byref(ps))

    def _font(self):
        return _gdi32.CreateFontW(
            -15,
            0,
            0,
            0,
            500,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
            0,
            "Microsoft YaHei UI",
        )
