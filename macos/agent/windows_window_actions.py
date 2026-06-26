"""Windows local window actions executed through Win32 APIs."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import ctypes.wintypes


WINDOW_ACTIONS = {
    "窗口左半屏": "left_half",
    "窗口右半屏": "right_half",
    "窗口左移": "left_half",
    "窗口右移": "right_half",
    "窗口最大化": "maximize",
    "窗口居中": "center",
}


@dataclass(frozen=True)
class WinWindowRect:
    x: int
    y: int
    width: int
    height: int


def run_window_action(action: str) -> bool:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        print("[typer] Windows window action skipped: no foreground window")
        return False

    current = window_rect(hwnd, user32)
    screen = work_area(user32)
    if current is None or screen is None:
        print("[typer] Windows window action skipped: cannot read window/screen frame")
        return False

    target = target_window_rect(action, current, screen)
    if target is None:
        return False

    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    ok = user32.MoveWindow(
        hwnd,
        int(target.x),
        int(target.y),
        int(target.width),
        int(target.height),
        True,
    )
    if not ok:
        print("[typer] Windows window action failed: MoveWindow returned false")
        return False
    return True


def window_rect(hwnd, user32) -> WinWindowRect | None:
    rect = ctypes.wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return WinWindowRect(
        int(rect.left),
        int(rect.top),
        int(rect.right - rect.left),
        int(rect.bottom - rect.top),
    )


def work_area(user32) -> WinWindowRect | None:
    SPI_GETWORKAREA = 0x0030
    rect = ctypes.wintypes.RECT()
    if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return None
    return WinWindowRect(
        int(rect.left),
        int(rect.top),
        int(rect.right - rect.left),
        int(rect.bottom - rect.top),
    )


def target_window_rect(
    action: str,
    current: WinWindowRect,
    screen: WinWindowRect,
) -> WinWindowRect | None:
    if action == "left_half":
        return WinWindowRect(screen.x, screen.y, screen.width // 2, screen.height)
    if action == "right_half":
        width = screen.width // 2
        return WinWindowRect(screen.x + width, screen.y, screen.width - width, screen.height)
    if action == "maximize":
        return WinWindowRect(screen.x, screen.y, screen.width, screen.height)
    if action == "center":
        width = min(max(current.width, 480), screen.width)
        height = min(max(current.height, 320), screen.height)
        return WinWindowRect(
            screen.x + (screen.width - width) // 2,
            screen.y + (screen.height - height) // 2,
            width,
            height,
        )
    return None
