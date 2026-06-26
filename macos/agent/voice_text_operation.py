"""Typed Voice Text Operations produced by Instruction Mode classification."""

from dataclasses import dataclass
from typing import Literal


OperationKind = Literal[
    "shortcut",
    "undo",
    "delete",
    "edit",
    "write",
    "memo_save",
    "memo_recall",
    "memo_delete",
    "memo_list",
    "chat",
]


@dataclass(frozen=True)
class VoiceTextOperation:
    kind: OperationKind
    name: str = ""
    key: str = ""
    value: str = ""
    reply: str = ""


def operation_from_intent(result: dict) -> VoiceTextOperation:
    kind = _normalize_kind(result.get("type"))
    return VoiceTextOperation(
        kind=kind,
        name=_string_field(result, "name"),
        key=_string_field(result, "key"),
        value=_string_field(result, "value"),
        reply=_string_field(result, "reply"),
    )


def _normalize_kind(raw: object) -> OperationKind:
    if raw in {
        "shortcut",
        "undo",
        "delete",
        "edit",
        "write",
        "memo_save",
        "memo_recall",
        "memo_delete",
        "memo_list",
        "chat",
    }:
        return raw
    return "chat"


def _string_field(result: dict, key: str) -> str:
    value = result.get(key, "")
    return value.strip() if isinstance(value, str) else ""
