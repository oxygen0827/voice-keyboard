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
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShortcutCatalogEntry:
    name: str
    source: str
    risk: str = "normal"
    application: str = ""
    kind: LocalOperationKind = "shortcut"
    aliases: tuple[str, ...] = ()


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
            aliases=_operation_aliases(name, candidate.aliases),
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



def _operation_aliases(name: str, configured: tuple[str, ...] = ()) -> tuple[str, ...]:
    aliases = []
    for alias in configured:
        if alias and alias not in aliases and alias != name:
            aliases.append(alias)
    for alias in _COMMON_OPERATION_ALIASES.get(name, ()):
        if alias and alias not in aliases and alias != name:
            aliases.append(alias)
    return tuple(aliases)


_COMMON_OPERATION_ALIASES = {
    "\u4fdd\u5b58": ("\u4fdd\u5b58\u4e00\u4e0b", "\u5e2e\u6211\u4fdd\u5b58", "\u4fdd\u5b58\u5f53\u524d", "\u5b58\u4e00\u4e0b"),
    "\u53d1\u9001": ("\u53d1\u9001\u4e00\u4e0b", "\u53d1\u51fa\u53bb", "\u5e2e\u6211\u53d1\u9001", "\u53d1\u4e00\u4e0b", "\u63d0\u4ea4\u53d1\u9001"),
    "\u5168\u9009": ("\u5168\u90e8\u9009\u4e2d", "\u9009\u4e2d\u5168\u90e8", "\u5168\u90fd\u9009\u4e2d"),
    "\u590d\u5236": ("\u590d\u5236\u4e00\u4e0b", "\u5e2e\u6211\u590d\u5236"),
    "\u7c98\u8d34": ("\u8d34\u4e0a", "\u8d34\u4e00\u4e0b", "\u5e2e\u6211\u7c98\u8d34"),
    "\u56de\u8f66": ("\u6309\u56de\u8f66", "\u6572\u56de\u8f66", "\u786e\u8ba4\u4e00\u4e0b"),
    "\u786e\u8ba4": ("\u786e\u8ba4\u4e00\u4e0b", "\u786e\u5b9a", "\u786e\u5b9a\u4e00\u4e0b"),
    "\u63d0\u4ea4": ("\u63d0\u4ea4\u4e00\u4e0b", "\u5e2e\u6211\u63d0\u4ea4"),
    "\u5173\u95ed": ("\u5173\u95ed\u4e00\u4e0b", "\u5173\u6389", "\u5173\u4e00\u4e0b"),
}
def _operation_risk(name: str, high_risk_names: set[str]) -> str:
    return "high" if name in high_risk_names else "normal"
