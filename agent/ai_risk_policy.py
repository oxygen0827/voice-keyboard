"""Local execution policy for AI key command plans."""

from __future__ import annotations

from agent.ai_command_plan import AICommandPlan
from agent.memo import is_sensitive_memo


_DENY_MARKERS = (
    "\u81ea\u52a8\u53d1\u9001",
    "\u5e2e\u6211\u53d1\u9001",
    "\u53d1\u51fa\u53bb",
    "\u76f4\u63a5\u53d1",
    "\u81ea\u52a8\u63d0\u4ea4",
    "\u5e2e\u6211\u63d0\u4ea4",
    "\u76f4\u63a5\u63d0\u4ea4",
    "\u81ea\u52a8\u4ed8\u6b3e",
    "\u5e2e\u6211\u4ed8\u6b3e",
    "\u76f4\u63a5\u4ed8\u6b3e",
)
_WHOLE_SCOPE_MARKERS = (
    "\u5168\u6587",
    "\u5168\u90e8",
    "\u6e05\u7a7a",
    "\u6574\u4e2a\u8f93\u5165\u6846",
    "\u6240\u6709\u5185\u5bb9",
)


def apply_local_risk_policy(
    plan: AICommandPlan,
    *,
    instruction: str = "",
    input_environment=None,
    memo_store=None,
) -> AICommandPlan:
    """Return a plan whose output_policy is decided locally."""

    text = str(instruction or "")
    operation = plan.operation
    if _looks_denied(text):
        return plan.with_policy("deny", "denied_high_risk_automation")

    if operation.kind == "shortcut":
        if _shortcut_requires_confirmation(operation.name, input_environment):
            return plan.with_policy("confirm", f"high_risk_shortcut:{operation.name}")
        return plan.with_policy("auto")

    if operation.kind == "delete":
        return plan.with_policy("confirm", "delete_requires_confirmation")

    if operation.kind == "edit" and _looks_whole_scope(text):
        return plan.with_policy("confirm", "whole_scope_replacement")

    if operation.kind == "memo_recall" and _memo_is_sensitive(operation.key, memo_store):
        return plan.with_policy("confirm", f"sensitive_memo:{operation.key}")

    return plan.with_policy("auto")


def deny_feedback() -> str:
    return "\u6211\u53ef\u4ee5\u5e2e\u4f60\u5199\u597d\uff0c\u53d1\u9001\u8bf7\u624b\u52a8\u786e\u8ba4"


def _looks_denied(text: str) -> bool:
    compact = "".join(text.split())
    return any(marker in compact for marker in _DENY_MARKERS)


def _looks_whole_scope(text: str) -> bool:
    compact = "".join(text.split())
    return any(marker in compact for marker in _WHOLE_SCOPE_MARKERS)


def _shortcut_requires_confirmation(name: str, input_environment) -> bool:
    if input_environment is None:
        return False
    try:
        decision = input_environment.shortcut_policy_for_invocation(name)
    except Exception:
        return True
    if not decision.found:
        return False
    return (not decision.allowed) or decision.risk == "high"


def _memo_is_sensitive(key: str, memo_store) -> bool:
    if memo_store is None or not key:
        return False
    try:
        if hasattr(memo_store, "metadata"):
            metadata = memo_store.metadata(key)
            if metadata.get("sensitive"):
                return True
        value = memo_store.get(key) or ""
    except Exception:
        return False
    return is_sensitive_memo(key, value)
