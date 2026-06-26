"""Local-only learning events for AI key corrections."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from agent.memo import is_sensitive_memo
from agent.personal_dictionary import DEFAULT_DICTIONARY_PATH, PersonalDictionaryStore


_DEFAULT_EVENTS_PATH = Path.home() / ".voice-keyboard" / "learning_events.jsonl"


@dataclass(frozen=True)
class CorrectionCommand:
    old: str = ""
    new: str = ""
    action: str = ""


@dataclass(frozen=True)
class RecentOutput:
    text: str = ""
    mode: str = ""
    operation_kind: str = ""
    ts: float = 0.0


def parse_correction_command(text: str) -> CorrectionCommand | None:
    cleaned = str(text or "").strip().strip("\u3002\uff01\uff1f!? ")
    pair = _parse_not_x_but_y(cleaned)
    if pair is not None:
        old, new = pair
        return CorrectionCommand(old=old, new=new, action="replace")
    compact = "".join(cleaned.split())
    if compact in {"\u6700\u540e\u4e00\u53e5\u5220\u6389", "\u5220\u6389\u6700\u540e\u4e00\u53e5"}:
        return CorrectionCommand(action="delete_last_sentence")
    if any(marker in compact for marker in ("\u518d\u77ed\u4e00\u70b9", "\u7b80\u77ed\u4e00\u70b9", "\u77ed\u4e00\u70b9")):
        return CorrectionCommand(action="shorten_recent")
    return None


class LocalLearningRecorder:
    def __init__(
        self,
        *,
        events_path: Path | None = None,
        dictionary_path: Path | None = None,
        dictionary_store: PersonalDictionaryStore | None = None,
    ):
        self._events_path = events_path or _DEFAULT_EVENTS_PATH
        self._dictionary_path = dictionary_path or DEFAULT_DICTIONARY_PATH
        self._dictionary_store = dictionary_store
        self._recent = RecentOutput()

    @property
    def recent(self) -> RecentOutput:
        return self._recent

    def remember_output(self, text: str, *, mode: str = "ai", operation_kind: str = "") -> None:
        if text:
            self._recent = RecentOutput(
                text=str(text),
                mode=mode,
                operation_kind=operation_kind,
                ts=time.time(),
            )

    def record_correction(
        self,
        command: CorrectionCommand,
        *,
        source_text: str = "",
        status: str = "ok",
    ) -> None:
        original = source_text or self._recent.text
        event = {
            "ts": time.time(),
            "scope": "recent_output",
            "original_text": _sanitize(original),
            "old": _sanitize(command.old),
            "new": _sanitize(command.new),
            "action": command.action,
            "diff_type": _diff_type(command, original),
            "status": status,
        }
        try:
            self._events_path.parent.mkdir(parents=True, exist_ok=True)
            with self._events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[learning] write failed: {e}")
        self._maybe_add_dictionary_candidate(command)

    def _maybe_add_dictionary_candidate(self, command: CorrectionCommand) -> None:
        if command.action != "replace" or not command.new:
            return
        if is_sensitive_memo(command.old, command.new):
            return
        if len(command.old) > 24 or len(command.new) > 24:
            return
        try:
            store = self._dictionary_store or PersonalDictionaryStore(self._dictionary_path)
            store.save(command.new, source="correction", confidence=0.6)
        except Exception as e:
            print(f"[learning] dictionary write failed: {e}")


def apply_correction_to_text(text: str, command: CorrectionCommand) -> str:
    value = str(text or "")
    if command.action == "replace" and command.old:
        return value.replace(command.old, command.new, 1)
    if command.action == "delete_last_sentence":
        return _delete_last_sentence(value)
    return value


def _parse_not_x_but_y(text: str) -> tuple[str, str] | None:
    patterns = (
        r"^\u4e0d\u662f(.+?)\uff0c?\u662f(.+)$",
        r"^\u4e0d\u662f(.+?)\s+\u662f(.+)$",
        r"^\u521a\u624d\u90a3\u4e2a(.+?)\uff0c?\u662f(.+)$",
        r"^(?:\u628a|\u5c06)(.+?)(?:\u4fee\u6539\u6210|\u6539\u6210|\u6539\u4e3a|\u4fee\u6b63\u4e3a|\u7ea0\u6b63\u4e3a|\u6362\u6210)(.+)$",
        r"^\u7528(.+?)(?:\u4fee\u6539\u6210|\u6539\u6210|\u6539\u4e3a|\u66ff\u6362\u6210)(.+)$",
        r"^(.+?)(?:\u4fee\u6539\u6210|\u6539\u6210|\u6539\u4e3a|\u4fee\u6b63\u4e3a|\u7ea0\u6b63\u4e3a|\u6362\u6210)(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        old, new = (_clean_correction_part(part) for part in match.groups())
        if old and new and old != new:
            return old, new
    return None


def _clean_correction_part(text: str) -> str:
    value = str(text or "").strip().strip("\u3002\uff01\uff1f!? ,\uff0c")
    for prefix in ("\u90a3\u4e2a", "\u8fd9\u4e2a"):
        if value.startswith(prefix) and len(value) > len(prefix):
            value = value[len(prefix):].strip()
    return value


def _delete_last_sentence(text: str) -> str:
    value = str(text or "").rstrip()
    if not value:
        return value
    for index in range(len(value) - 2, -1, -1):
        if value[index] in "\u3002\uff01\uff1f.!?":
            return value[: index + 1].rstrip()
    return ""


def _diff_type(command: CorrectionCommand, original: str) -> str:
    if command.action == "replace" and command.old and command.old in original:
        return "small_correction"
    return command.action or "unknown"


def _sanitize(text: str, limit: int = 240) -> str:
    value = " ".join(str(text or "").split())
    if len(value) > limit:
        return value[:limit] + "..."
    return value
