"""Structured AI key command plans for Instruction Mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent.input_environment import ReplacementPlan, TextTarget
from agent.voice_text_operation import VoiceTextOperation


TargetSource = Literal[
    "explicit_selection",
    "tracked_segment",
    "clipboard",
    "memo",
    "none",
]
OutputPolicy = Literal["auto", "confirm", "deny"]


@dataclass(frozen=True)
class AICommandPlan:
    operation: VoiceTextOperation
    operation_kind: str
    target_source: TargetSource = "none"
    output_policy: OutputPolicy = "auto"
    preview_text: str = ""
    generated_text: str = ""
    replacement_plan: ReplacementPlan | None = None
    risk_reason: str = ""

    def with_policy(self, policy: OutputPolicy, reason: str = "") -> "AICommandPlan":
        return AICommandPlan(
            operation=self.operation,
            operation_kind=self.operation_kind,
            target_source=self.target_source,
            output_policy=policy,
            preview_text=self.preview_text,
            generated_text=self.generated_text,
            replacement_plan=self.replacement_plan,
            risk_reason=reason or self.risk_reason,
        )

    def with_preview(self, preview_text: str) -> "AICommandPlan":
        return AICommandPlan(
            operation=self.operation,
            operation_kind=self.operation_kind,
            target_source=self.target_source,
            output_policy=self.output_policy,
            preview_text=preview_text,
            generated_text=self.generated_text,
            replacement_plan=self.replacement_plan,
            risk_reason=self.risk_reason,
        )


def command_plan_from_operation(
    operation: VoiceTextOperation,
    *,
    instruction: str = "",
    target: TextTarget | None = None,
) -> AICommandPlan:
    return AICommandPlan(
        operation=operation,
        operation_kind=operation.kind,
        target_source=_target_source(operation, instruction, target),
        preview_text=_preview_for_operation(operation),
    )


def _target_source(
    operation: VoiceTextOperation,
    instruction: str,
    target: TextTarget | None,
) -> TargetSource:
    if _explicit_clipboard_requested(instruction):
        return "clipboard"
    if operation.kind in {"memo_recall", "memo_save", "memo_delete", "memo_list"}:
        return "memo"
    if target is not None and target.selected:
        return "explicit_selection"
    if target is not None and target.tracked_segment:
        return "tracked_segment"
    return "none"


def _explicit_clipboard_requested(text: str) -> bool:
    compact = "".join(str(text or "").split()).lower()
    return any(marker in compact for marker in (
        "\u6839\u636e\u526a\u8d34\u677f",
        "\u7528\u526a\u8d34\u677f",
        "\u526a\u8d34\u677f\u91cc",
        "clipboard",
    ))


def _preview_for_operation(operation: VoiceTextOperation) -> str:
    if operation.kind == "shortcut":
        return operation.name
    if operation.kind.startswith("memo_"):
        return operation.key or operation.value
    if operation.kind == "chat":
        return operation.reply
    return operation.kind
