"""Local execution policy for high-risk voice operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalOperationPolicyDecision:
    name: str
    found: bool
    allowed: bool
    risk: str = "normal"
    reason: str = ""
    source: str = ""
    application: str = ""
    kind: str = "shortcut"
    requires_confirmation: bool = False


def apply_local_operation_policy(
    decision: object,
    *,
    in_atomic_stack: bool = False,
) -> LocalOperationPolicyDecision:
    """Apply local high-risk policy to a shortcut policy decision-like object."""
    name = _field(decision, "name")
    found = bool(_field(decision, "found", False))
    allowed = bool(_field(decision, "allowed", False))
    risk = _field(decision, "risk", "normal") or "normal"
    reason = _field(decision, "reason")
    source = _field(decision, "source")
    application = _field(decision, "application")
    kind = _field(decision, "kind", "shortcut") or "shortcut"

    if not found:
        return LocalOperationPolicyDecision(
            name=name,
            found=False,
            allowed=False,
            risk=risk,
            reason=reason or "not_in_shortcut_catalog",
            source=source,
            application=application,
            kind=kind,
        )

    if not allowed:
        return LocalOperationPolicyDecision(
            name=name,
            found=True,
            allowed=False,
            risk=risk,
            reason=reason,
            source=source,
            application=application,
            kind=kind,
        )

    if risk == "high":
        if in_atomic_stack:
            return LocalOperationPolicyDecision(
                name=name,
                found=True,
                allowed=False,
                risk=risk,
                reason="high_risk_blocked_in_atomic_stack",
                source=source,
                application=application,
                kind=kind,
            )
        return LocalOperationPolicyDecision(
            name=name,
            found=True,
            allowed=False,
            risk=risk,
            reason="high_risk_requires_confirmation",
            source=source,
            application=application,
            kind=kind,
            requires_confirmation=True,
        )

    return LocalOperationPolicyDecision(
        name=name,
        found=True,
        allowed=True,
        risk=risk,
        reason=reason,
        source=source,
        application=application,
        kind=kind,
    )


def _field(decision: object, name: str, default: object = "") -> object:
    return getattr(decision, name, default)
