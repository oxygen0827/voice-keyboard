"""Quartz-only keyboard listener for macOS hotkeys and edit tracking."""

from __future__ import annotations

import threading
from typing import Callable

from pynput import keyboard as kb


_SPECIAL_KEYS_BY_VK = {
    0x24: kb.Key.enter,
    0x30: kb.Key.tab,
    0x31: kb.Key.space,
    0x33: kb.Key.backspace,
    0x35: kb.Key.esc,
    0x36: kb.Key.cmd_r,
    0x37: kb.Key.cmd_l,
    0x38: kb.Key.shift_l,
    0x39: kb.Key.caps_lock,
    0x3A: kb.Key.alt_l,
    0x3B: kb.Key.ctrl_l,
    0x3C: kb.Key.shift_r,
    0x3D: kb.Key.alt_r,
    0x3E: kb.Key.ctrl_r,
    0x7A: kb.Key.f1,
    0x78: kb.Key.f2,
    0x63: kb.Key.f3,
    0x76: kb.Key.f4,
    0x60: kb.Key.f5,
    0x61: kb.Key.f6,
    0x62: kb.Key.f7,
    0x64: kb.Key.f8,
    0x65: kb.Key.f9,
    0x6D: kb.Key.f10,
    0x67: kb.Key.f11,
    0x6F: kb.Key.f12,
    0x69: kb.Key.f13,
    0x6B: kb.Key.f14,
    0x71: kb.Key.f15,
    0x6A: kb.Key.f16,
    0x40: kb.Key.f17,
    0x4F: kb.Key.f18,
    0x50: kb.Key.f19,
    0x5A: kb.Key.f20,
    0x73: kb.Key.home,
    0x74: kb.Key.page_up,
    0x75: kb.Key.delete,
    0x77: kb.Key.end,
    0x79: kb.Key.page_down,
    0x7B: kb.Key.left,
    0x7C: kb.Key.right,
    0x7D: kb.Key.down,
    0x7E: kb.Key.up,
}

_MODIFIER_VKS = {
    0x36,
    0x37,
    0x38,
    0x39,
    0x3A,
    0x3B,
    0x3C,
    0x3D,
    0x3E,
}


class MacOSKeyboardListener:
    """Listen to keyboard events without converting them through AppKit NSEvent."""

    def __init__(
        self,
        on_press: Callable[[object], None],
        on_release: Callable[[object], None],
    ):
        self._on_press = on_press
        self._on_release = on_release
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._loop = None
        self._event_tap = None
        self._callback = None
        self._modifier_down: set[int] = set()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="voice-keyboard-macos-keyboard",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._loop is not None:
            try:
                from CoreFoundation import CFRunLoopStop

                CFRunLoopStop(self._loop)
            except Exception:
                pass
        if self._event_tap is not None:
            try:
                import Quartz

                Quartz.CGEventTapEnable(self._event_tap, False)
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None
        self._loop = None
        self._event_tap = None
        self._callback = None

    def _run(self) -> None:
        try:
            import Quartz
            from CoreFoundation import (
                CFRunLoopAddSource,
                CFRunLoopGetCurrent,
                CFRunLoopRunInMode,
                kCFRunLoopDefaultMode,
            )
        except Exception as e:
            print(f"[keyboard] macOS Quartz listener unavailable: {e}")
            return

        def callback(_proxy, event_type, event, _refcon):
            try:
                self._handle_event(Quartz, event_type, event)
            except Exception as e:
                print(f"[keyboard] macOS event ignored: {e}")
            return event

        self._callback = callback
        try:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                _event_mask(Quartz),
                callback,
                None,
            )
            if tap is None:
                print("[keyboard] macOS Quartz listener unavailable: event tap denied")
                return
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            loop = CFRunLoopGetCurrent()
            self._loop = loop
            self._event_tap = tap
            CFRunLoopAddSource(loop, source, kCFRunLoopDefaultMode)
            Quartz.CGEventTapEnable(tap, True)
            print("[keyboard] macOS Quartz listener enabled")
            while not self._stopped.is_set():
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.25, False)
        except Exception as e:
            print(f"[keyboard] macOS Quartz listener stopped: {e}")
        finally:
            self._loop = None
            self._event_tap = None

    def _handle_event(self, quartz, event_type: int, event) -> None:
        key = _key_from_cg_event(quartz, event)
        if key is None:
            return
        if event_type == quartz.kCGEventKeyDown:
            self._on_press(key)
            return
        if event_type == quartz.kCGEventKeyUp:
            self._on_release(key)
            return
        if event_type == quartz.kCGEventFlagsChanged:
            vk = _vk_from_cg_event(quartz, event)
            if vk == 0x39:
                self._on_press(key)
                self._on_release(key)
                return
            if vk in self._modifier_down:
                self._modifier_down.discard(vk)
                self._on_release(key)
            else:
                self._modifier_down.add(vk)
                self._on_press(key)


def _event_mask(quartz) -> int:
    return (
        quartz.CGEventMaskBit(quartz.kCGEventKeyDown)
        | quartz.CGEventMaskBit(quartz.kCGEventKeyUp)
        | quartz.CGEventMaskBit(quartz.kCGEventFlagsChanged)
    )


def _key_from_cg_event(quartz, event):
    vk = _vk_from_cg_event(quartz, event)
    if vk in _SPECIAL_KEYS_BY_VK:
        return _SPECIAL_KEYS_BY_VK[vk]
    text = _unicode_from_cg_event(quartz, event)
    if text:
        return kb.KeyCode.from_char(text, vk=vk)
    return kb.KeyCode.from_vk(vk)


def _vk_from_cg_event(quartz, event) -> int:
    return int(
        quartz.CGEventGetIntegerValueField(
            event,
            quartz.kCGKeyboardEventKeycode,
        )
    )


def _unicode_from_cg_event(quartz, event) -> str:
    try:
        result = quartz.CGEventKeyboardGetUnicodeString(event, 64, None, None)
    except Exception:
        return ""
    if not isinstance(result, tuple) or len(result) < 2:
        return ""
    length = int(result[0] or 0)
    chars = result[1]
    if length <= 0 or chars is None:
        return ""
    if isinstance(chars, str):
        return chars[:length]
    try:
        return "".join(chars[:length])
    except Exception:
        return str(chars)
