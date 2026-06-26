"""Committed text monitor for IME-backed manual corrections on macOS."""

from __future__ import annotations

import sys
import time
from typing import Callable


class ImeCommitMonitor:
    def __init__(
        self,
        on_text: Callable[[str], None],
        *,
        clock: Callable[[], float] = time.monotonic,
        dedupe_window_seconds: float = 0.08,
    ):
        self._on_text = on_text
        self._clock = clock
        self._dedupe_window_seconds = max(0.0, float(dedupe_window_seconds))
        self._last_text = ""
        self._last_text_at = 0.0
        self._monitor = None
        self._event_tap = None
        self._event_source = None
        self._keyboard_listener = None

    def start(self) -> None:
        if (
            self._monitor is not None
            or self._event_tap is not None
            or self._keyboard_listener is not None
        ):
            return
        if sys.platform == "win32":
            self._start_windows_keyboard_listener()
            return
        if sys.platform != "darwin":
            return
        started = False
        try:
            from AppKit import NSEvent, NSKeyDownMask

            def handler(event):
                from agent import typer

                if typer.is_simulating():
                    return None
                text = str(event.characters() or "")
                self._emit_text(text)
                return None

            self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSKeyDownMask,
                handler,
            )
            started = True
            print("[ime] AppKit committed text monitor enabled")
        except Exception as e:
            print(f"[ime] AppKit committed text monitor unavailable: {e}")
            self._monitor = None
        if self._start_cg_event_tap():
            started = True
        if started:
            print("[ime] macOS committed text monitor enabled")

    def _start_windows_keyboard_listener(self) -> bool:
        try:
            Listener = _windows_keyboard_listener_class()

            def on_press(key):
                from agent import typer

                if typer.is_simulating():
                    return None
                text = _windows_key_text(key)
                if not _contains_cjk(text):
                    return None
                self._emit_text(text)
                return None

            self._keyboard_listener = Listener(on_press=on_press)
            self._keyboard_listener.start()
            print("[ime] Windows committed text monitor enabled")
            return True
        except Exception as e:
            print(f"[ime] Windows committed text monitor unavailable: {e}")
            self._keyboard_listener = None
            return False

    def _start_cg_event_tap(self) -> bool:
        try:
            import Quartz
            from CoreFoundation import (
                CFRunLoopAddSource,
                CFRunLoopGetCurrent,
                kCFRunLoopCommonModes,
            )

            mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)

            def callback(_proxy, event_type, event, _refcon):
                if event_type != Quartz.kCGEventKeyDown:
                    return event
                from agent import typer

                if typer.is_simulating():
                    return event
                text = _unicode_from_cg_event(Quartz, event)
                self._emit_text(text)
                return event

            tap = Quartz.CGEventTapCreate(
                Quartz.kCGAnnotatedSessionEventTap,
                Quartz.kCGTailAppendEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                mask,
                callback,
                None,
            )
            if tap is None:
                print("[ime] CGEvent committed text monitor unavailable: event tap denied")
                return False
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
            self._event_tap = tap
            self._event_source = source
            print("[ime] CGEvent committed text monitor enabled")
            return True
        except Exception as e:
            print(f"[ime] CGEvent committed text monitor unavailable: {e}")
            self._event_tap = None
            self._event_source = None
            return False

    def _emit_text(self, text: str) -> bool:
        value = str(text or "")
        if not value:
            return False
        now = self._clock()
        if (
            value == self._last_text
            and now - self._last_text_at <= self._dedupe_window_seconds
        ):
            return False
        self._last_text = value
        self._last_text_at = now
        self._on_text(value)
        return True

    def stop(self) -> None:
        if self._monitor is not None:
            try:
                from AppKit import NSEvent

                NSEvent.removeMonitor_(self._monitor)
            except Exception:
                pass
            self._monitor = None
        if self._event_tap is not None:
            try:
                import Quartz

                Quartz.CGEventTapEnable(self._event_tap, False)
            except Exception:
                pass
            self._event_tap = None
            self._event_source = None
        if self._keyboard_listener is not None:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
            self._keyboard_listener = None


def _unicode_from_cg_event(quartz, event) -> str:
    try:
        result = quartz.CGEventKeyboardGetUnicodeString(event, 64, None, None)
    except Exception:
        return ""
    if not isinstance(result, tuple) or len(result) < 2:
        return ""
    length = result[0]
    chars = result[1]
    if not length or chars is None:
        return ""
    if isinstance(chars, str):
        return chars[: int(length)]
    try:
        return "".join(chars[: int(length)])
    except Exception:
        return str(chars)


def _windows_keyboard_listener_class():
    from pynput import keyboard

    return keyboard.Listener


def _windows_key_text(key) -> str:
    return str(getattr(key, "char", "") or "")


def _contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff"
        for char in str(text or "")
    )
