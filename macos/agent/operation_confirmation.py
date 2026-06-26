"""User confirmation adapters for local high-risk operations."""

from __future__ import annotations

import ctypes
import sys
from typing import Callable

_MB_YESNO = 0x00000004
_MB_ICONWARNING = 0x00000030
_MB_TOPMOST = 0x00040000
_IDYES = 6


class WindowsOperationConfirmation:
    def __init__(self, *, status_window=None, user32=None):
        self._status = status_window
        self._user32 = user32 or ctypes.windll.user32

    def __call__(self, name: str, reason: str = "") -> bool:
        message = _confirmation_message(name, reason)
        if self._status is not None and hasattr(self._status, "show_message"):
            try:
                self._status.show_message(f"需要确认：{name}", 4.0)
            except Exception:
                pass
        result = self._user32.MessageBoxW(
            None,
            message,
            "Voice Keyboard",
            _MB_YESNO | _MB_ICONWARNING | _MB_TOPMOST,
        )
        return result == _IDYES


def make_operation_confirmation(
    *,
    status_window=None,
    platform: str | None = None,
) -> Callable[[str, str], bool] | None:
    platform = platform or sys.platform
    if platform == "win32":
        if not hasattr(ctypes, "windll"):
            return None
        return WindowsOperationConfirmation(status_window=status_window)
    return None


def _confirmation_message(name: str, reason: str = "") -> str:
    action = str(name or "").strip() or "这个操作"
    reason_text = _reason_label(reason)
    return (
        f"Voice Keyboard 准备执行高风险操作：{action}\n\n"
        f"原因：{reason_text}\n\n"
        "确认执行吗？"
    )


def _reason_label(reason: str = "") -> str:
    labels = {
        "high_risk_requires_confirmation": "该操作可能发送、提交、关闭、删除或影响当前应用状态",
        "high_risk_blocked_in_atomic_stack": "高风险操作不能在组合指令中直接执行",
    }
    return labels.get(str(reason or ""), "需要你手动确认")
