"""Focused text capture diagnostics for the Voice Keyboard Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CaptureConfidence = Literal["high", "medium", "low", "unsupported"]


@dataclass(frozen=True)
class FocusedTextProbe:
    name: str
    ok: bool
    value: str = ""
    detail: str = ""


@dataclass(frozen=True)
class FocusedTextSnapshot:
    text: str = ""
    source: str = "unsupported"
    confidence: CaptureConfidence = "unsupported"
    app_name: str = ""
    bundle_id: str = ""
    pid: int | None = None
    role: str = ""
    subrole: str = ""
    selected_range: tuple[int, int] | None = None
    probes: tuple[FocusedTextProbe, ...] = ()

    @property
    def app_label(self) -> str:
        if self.app_name and self.bundle_id:
            return f"{self.app_name} ({self.bundle_id})"
        return self.app_name or self.bundle_id or "未知活动应用"

    @property
    def has_real_text(self) -> bool:
        return bool(self.text and self.confidence in ("high", "medium"))

    def text_for_log(self, limit: int = 160) -> str:
        value = self.text.replace("\n", "\\n")
        suffix = "..." if len(value) > limit else ""
        return value[:limit] + suffix


def classify_text_capture(
    *,
    source: str,
    text: str,
    selected_range: tuple[int, int] | None = None,
) -> CaptureConfidence:
    if not text:
        return "unsupported"
    if source == "AXValue":
        return "high"
    if source == "AXStringForRange":
        return "high"
    if source.startswith("child:"):
        return "medium"
    if source.startswith("caret:"):
        return "medium" if selected_range is not None else "low"
    return "low"


def format_focused_text_snapshot(snapshot: FocusedTextSnapshot) -> str:
    probes = ", ".join(
        _format_probe_for_log(probe)
        for probe in snapshot.probes
    )
    probes_part = f" probes=[{probes}]" if probes else ""
    return (
        "[capture-diagnostics] "
        f"app={snapshot.app_label!r} "
        f"source={snapshot.source} "
        f"confidence={snapshot.confidence} "
        f"role={snapshot.role or '-'} "
        f"subrole={snapshot.subrole or '-'} "
        f"range={snapshot.selected_range or '-'} "
        f"text={snapshot.text_for_log(180)!r}"
        f"{probes_part}"
    )


def _format_probe_for_log(probe: FocusedTextProbe) -> str:
    state = "ok" if probe.ok else "no"
    detail = f"({probe.detail})" if probe.detail else ""
    return f"{probe.name}:{state}{detail}"
