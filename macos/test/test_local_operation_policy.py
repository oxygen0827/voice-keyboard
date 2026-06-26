from dataclasses import dataclass
import unittest

from agent.local_operation_policy import apply_local_operation_policy


@dataclass(frozen=True)
class FakeShortcutDecision:
    name: str
    found: bool
    allowed: bool
    risk: str = "normal"
    reason: str = ""
    source: str = ""
    application: str = ""
    kind: str = "shortcut"


class LocalOperationPolicyTests(unittest.TestCase):
    def test_normal_allowed_shortcut_remains_allowed_without_confirmation(self):
        decision = FakeShortcutDecision(
            name="保存",
            found=True,
            allowed=True,
            risk="normal",
            source="global",
            application="",
            kind="shortcut",
        )

        result = apply_local_operation_policy(decision)

        self.assertEqual(result.name, "保存")
        self.assertTrue(result.found)
        self.assertTrue(result.allowed)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(result.reason, "")
        self.assertEqual(result.source, "global")
        self.assertEqual(result.application, "")
        self.assertEqual(result.kind, "shortcut")

    def test_missing_shortcut_stays_missing_and_preserves_reason(self):
        decision = FakeShortcutDecision(
            name="不存在",
            found=False,
            allowed=False,
            reason="custom_missing_reason",
        )

        result = apply_local_operation_policy(decision)

        self.assertFalse(result.found)
        self.assertFalse(result.allowed)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(result.reason, "custom_missing_reason")

    def test_missing_shortcut_defaults_reason_to_not_in_shortcut_catalog(self):
        decision = FakeShortcutDecision(
            name="不存在",
            found=False,
            allowed=False,
        )

        result = apply_local_operation_policy(decision)

        self.assertFalse(result.found)
        self.assertFalse(result.allowed)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(result.reason, "not_in_shortcut_catalog")

    def test_high_risk_single_operation_requires_confirmation(self):
        decision = FakeShortcutDecision(
            name="发送",
            found=True,
            allowed=True,
            risk="high",
            source="application",
            application="Codex (com.openai.codex)",
        )

        result = apply_local_operation_policy(decision)

        self.assertTrue(result.found)
        self.assertFalse(result.allowed)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.reason, "high_risk_requires_confirmation")
        self.assertEqual(result.risk, "high")
        self.assertEqual(result.source, "application")
        self.assertEqual(result.application, "Codex (com.openai.codex)")

    def test_high_risk_operation_is_blocked_inside_atomic_stack(self):
        decision = FakeShortcutDecision(
            name="发送",
            found=True,
            allowed=True,
            risk="high",
            source="application",
        )

        result = apply_local_operation_policy(decision, in_atomic_stack=True)

        self.assertTrue(result.found)
        self.assertFalse(result.allowed)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(result.reason, "high_risk_blocked_in_atomic_stack")

    def test_existing_low_level_blocked_decision_stays_blocked_without_confirmation(self):
        decision = FakeShortcutDecision(
            name="保存",
            found=True,
            allowed=False,
            risk="normal",
            reason="blocked_by_local_config",
            source="global",
        )

        result = apply_local_operation_policy(decision)

        self.assertTrue(result.found)
        self.assertFalse(result.allowed)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(result.reason, "blocked_by_local_config")


if __name__ == "__main__":
    unittest.main()
