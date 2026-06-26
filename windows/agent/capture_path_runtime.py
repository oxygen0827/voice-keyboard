"""Runtime state helpers for the Voice Keyboard Engine Capture Path."""

from dataclasses import dataclass
from typing import Literal, Optional


CaptureSessionMode = Literal["dictate", "edit", "ai"]


@dataclass(frozen=True)
class CaptureStart:
    mode: CaptureSessionMode
    polish: bool = False


@dataclass(frozen=True)
class PolishToggle:
    polish: bool


@dataclass
class CapturePathRuntime:
    """Small state machine for hotkey-enabled Capture Path recording."""

    double_tap_window: float = 0.4
    enabled: bool = True
    active_mode: Optional[CaptureSessionMode] = None
    active_trigger: object = None
    polish_mode: bool = False
    last_ptt_press_time: float = 0.0

    @property
    def is_capturing(self) -> bool:
        return self.active_mode is not None

    def toggle_enabled(self) -> bool:
        self.enabled = not self.enabled
        if not self.enabled:
            self.clear_capture()
        return self.enabled

    def press_dictation(self, trigger: object, now: float) -> Optional[CaptureStart | PolishToggle]:
        if not self._can_start():
            return None
        if (now - self.last_ptt_press_time) < self.double_tap_window:
            self.polish_mode = not self.polish_mode
            self.last_ptt_press_time = 0.0
            return PolishToggle(polish=self.polish_mode)
        self.last_ptt_press_time = now
        self._start("dictate", trigger)
        return CaptureStart(mode="dictate", polish=self.polish_mode)

    def press_instruction_edit(self, trigger: object) -> Optional[CaptureStart]:
        if not self._can_start():
            return None
        self._start("edit", trigger)
        return CaptureStart(mode="edit")

    def press_instruction(self, trigger: object) -> Optional[CaptureStart]:
        if not self._can_start():
            return None
        self._start("ai", trigger)
        return CaptureStart(mode="ai")

    def release(self, trigger: object) -> Optional[CaptureSessionMode]:
        if trigger != self.active_trigger:
            return None
        mode = self.active_mode
        self.clear_capture()
        return mode

    def clear_capture(self) -> None:
        self.active_mode = None
        self.active_trigger = None

    def _can_start(self) -> bool:
        return self.enabled and self.active_mode is None

    def _start(self, mode: CaptureSessionMode, trigger: object) -> None:
        self.active_mode = mode
        self.active_trigger = trigger
