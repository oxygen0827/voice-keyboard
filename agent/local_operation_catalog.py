"""Local operation catalog for voice-triggered keyboard-style actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LocalOperationKind = Literal[
    "shortcut",
    "app_launch",
    "system_action",
    "system_window_action",
]


@dataclass(frozen=True)
class LocalOperationCandidate:
    name: str
    source: str
    kind: LocalOperationKind = "shortcut"
    application: str = ""
    key_signature: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShortcutCatalogEntry:
    name: str
    source: str
    risk: str = "normal"
    application: str = ""
    kind: LocalOperationKind = "shortcut"


@dataclass(frozen=True)
class ShortcutPolicyDecision:
    name: str
    found: bool
    allowed: bool
    risk: str = "normal"
    source: str = ""
    application: str = ""
    reason: str = ""
    kind: LocalOperationKind = "shortcut"

    @classmethod
    def missing(cls, name: str) -> "ShortcutPolicyDecision":
        return cls(
            name=name,
            found=False,
            allowed=False,
            reason="not_in_shortcut_catalog",
        )


def build_shortcut_catalog(
    candidates: list[LocalOperationCandidate],
    *,
    blocked_names: set[str] | None = None,
    blocked_key_signatures: set[tuple[str, ...]] | None = None,
    high_risk_names: set[str] | None = None,
) -> list[ShortcutCatalogEntry]:
    blocked_names = blocked_names or set()
    blocked_key_signatures = blocked_key_signatures or set()
    high_risk_names = high_risk_names or set()
    names: set[str] = set()
    entries: list[ShortcutCatalogEntry] = []

    for candidate in candidates:
        name = candidate.name.strip()
        if not name or name in names:
            continue
        if name in blocked_names:
            continue
        if candidate.key_signature and candidate.key_signature in blocked_key_signatures:
            continue
        names.add(name)
        entries.append(ShortcutCatalogEntry(
            name=name,
            source=candidate.source,
            risk=_operation_risk(name, high_risk_names),
            application=candidate.application,
            kind=candidate.kind,
        ))
    return entries


def shortcut_policy_for_invocation(
    catalog: list[ShortcutCatalogEntry],
    name: str,
    *,
    in_atomic_stack: bool = False,
) -> ShortcutPolicyDecision:
    for entry in catalog:
        if entry.name != name:
            continue
        if in_atomic_stack and entry.risk == "high":
            return ShortcutPolicyDecision(
                name=name,
                found=True,
                allowed=False,
                risk=entry.risk,
                source=entry.source,
                application=entry.application,
                reason="high_risk_requires_confirmation",
                kind=entry.kind,
            )
        return ShortcutPolicyDecision(
            name=name,
            found=True,
            allowed=True,
            risk=entry.risk,
            source=entry.source,
            application=entry.application,
            kind=entry.kind,
        )
    return ShortcutPolicyDecision.missing(name)


def _operation_risk(name: str, high_risk_names: set[str]) -> str:
    return "high" if name in high_risk_names else "normal"
