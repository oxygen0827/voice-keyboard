import unittest
from unittest.mock import MagicMock

from pynput import keyboard as kb

from agent.macos_keyboard_listener import (
    MacOSKeyboardListener,
    _event_mask,
    _key_from_cg_event,
)


class _FakeQuartz:
    kCGEventKeyDown = 10
    kCGEventKeyUp = 11
    kCGEventFlagsChanged = 12
    kCGKeyboardEventKeycode = 100
    kCGEventFlagMaskShift = 1 << 17
    kCGEventFlagMaskControl = 1 << 18
    kCGEventFlagMaskAlternate = 1 << 19
    kCGEventFlagMaskCommand = 1 << 20

    @staticmethod
    def CGEventMaskBit(value):
        return 1 << value

    @staticmethod
    def CGEventGetIntegerValueField(event, _field):
        return event["vk"]

    @staticmethod
    def CGEventGetFlags(event):
        return event.get("flags", 0)

    @staticmethod
    def CGEventKeyboardGetUnicodeString(event, _max_len, _actual, _buffer):
        return len(event.get("text", "")), event.get("text", "")


class MacOSKeyboardListenerTests(unittest.TestCase):
    def test_event_mask_excludes_system_defined_media_events(self):
        self.assertEqual(
            _event_mask(_FakeQuartz),
            (1 << _FakeQuartz.kCGEventKeyDown)
            | (1 << _FakeQuartz.kCGEventKeyUp)
            | (1 << _FakeQuartz.kCGEventFlagsChanged),
        )

    def test_maps_caps_lock_without_appkit_event_conversion(self):
        self.assertEqual(
            _key_from_cg_event(_FakeQuartz, {"vk": 0x39}),
            kb.Key.caps_lock,
        )

    def test_maps_printable_character_from_core_graphics_unicode(self):
        key = _key_from_cg_event(_FakeQuartz, {"vk": 0, "text": "a"})

        self.assertEqual(key.char, "a")
        self.assertEqual(key.vk, 0)

    def test_caps_lock_flags_changed_emits_press_and_release_together(self):
        on_press = MagicMock()
        on_release = MagicMock()
        listener = MacOSKeyboardListener(on_press, on_release)
        event = {"vk": 0x39}

        listener._handle_event(_FakeQuartz, _FakeQuartz.kCGEventFlagsChanged, event)

        on_press.assert_called_once_with(kb.Key.caps_lock)
        on_release.assert_called_once_with(kb.Key.caps_lock)

    def test_flags_changed_toggles_modifier_press_and_release(self):
        on_press = MagicMock()
        on_release = MagicMock()
        listener = MacOSKeyboardListener(on_press, on_release)
        down = {"vk": 0x3C, "flags": _FakeQuartz.kCGEventFlagMaskShift}
        up = {"vk": 0x3C, "flags": 0}

        listener._handle_event(_FakeQuartz, _FakeQuartz.kCGEventFlagsChanged, down)
        listener._handle_event(_FakeQuartz, _FakeQuartz.kCGEventFlagsChanged, up)

        on_press.assert_called_once_with(kb.Key.shift_r)
        on_release.assert_called_once_with(kb.Key.shift_r)

    def test_repeated_modifier_flags_changed_does_not_emit_release_until_flag_clears(self):
        on_press = MagicMock()
        on_release = MagicMock()
        listener = MacOSKeyboardListener(on_press, on_release)
        down = {"vk": 0x3C, "flags": _FakeQuartz.kCGEventFlagMaskShift}
        up = {"vk": 0x3C, "flags": 0}

        listener._handle_event(_FakeQuartz, _FakeQuartz.kCGEventFlagsChanged, down)
        listener._handle_event(_FakeQuartz, _FakeQuartz.kCGEventFlagsChanged, down)
        listener._handle_event(_FakeQuartz, _FakeQuartz.kCGEventFlagsChanged, up)

        on_press.assert_called_once_with(kb.Key.shift_r)
        on_release.assert_called_once_with(kb.Key.shift_r)


if __name__ == "__main__":
    unittest.main()
