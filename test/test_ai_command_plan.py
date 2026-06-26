import unittest
from unittest.mock import MagicMock

from agent.ai_command_plan import command_plan_from_operation
from agent.ai_risk_policy import apply_local_risk_policy
from agent.input_environment import TextTarget
from agent.text_io import ShortcutPolicyDecision
from agent.voice_text_operation import VoiceTextOperation


class AICommandPlanTests(unittest.TestCase):
    def test_plan_maps_operation_and_explicit_selection_target(self):
        plan = command_plan_from_operation(
            VoiceTextOperation("edit"),
            instruction="\u6539\u5f97\u66f4\u793c\u8c8c",
            target=TextTarget(selected="\u539f\u6587"),
        )

        self.assertEqual(plan.operation_kind, "edit")
        self.assertEqual(plan.target_source, "explicit_selection")
        self.assertEqual(plan.output_policy, "auto")

    def test_clipboard_target_requires_explicit_instruction(self):
        plan = command_plan_from_operation(
            VoiceTextOperation("write"),
            instruction="\u6839\u636e\u526a\u8d34\u677f\u5199\u4e00\u53e5",
            target=TextTarget(tracked_segment="\u521a\u624d"),
        )

        self.assertEqual(plan.target_source, "clipboard")


class AIRiskPolicyTests(unittest.TestCase):
    def test_delete_requires_confirmation(self):
        plan = command_plan_from_operation(VoiceTextOperation("delete"))

        planned = apply_local_risk_policy(plan, instruction="\u5220\u9664\u8fd9\u6bb5")

        self.assertEqual(planned.output_policy, "confirm")

    def test_auto_send_is_denied(self):
        plan = command_plan_from_operation(VoiceTextOperation("shortcut", name="\u53d1\u9001"))

        planned = apply_local_risk_policy(plan, instruction="\u5e2e\u6211\u53d1\u9001")

        self.assertEqual(planned.output_policy, "deny")

    def test_high_risk_shortcut_requires_confirmation(self):
        env = MagicMock()
        env.shortcut_policy_for_invocation.return_value = ShortcutPolicyDecision(
            name="\u53d1\u9001",
            found=True,
            allowed=True,
            risk="high",
        )
        plan = command_plan_from_operation(VoiceTextOperation("shortcut", name="\u53d1\u9001"))

        planned = apply_local_risk_policy(plan, instruction="\u53d1\u9001", input_environment=env)

        self.assertEqual(planned.output_policy, "confirm")

    def test_missing_shortcut_stays_auto_for_executor_feedback(self):
        env = MagicMock()
        env.shortcut_policy_for_invocation.return_value = ShortcutPolicyDecision.missing("missing")
        plan = command_plan_from_operation(VoiceTextOperation("shortcut", name="missing"))

        planned = apply_local_risk_policy(plan, instruction="missing", input_environment=env)

        self.assertEqual(planned.output_policy, "auto")

    def test_sensitive_memo_recall_requires_confirmation(self):
        memo = MagicMock()
        memo.metadata.return_value = {"sensitive": True}
        memo.get.return_value = "sk-test-only-dummy-key"
        plan = command_plan_from_operation(VoiceTextOperation("memo_recall", key="api key"))

        planned = apply_local_risk_policy(plan, memo_store=memo)

        self.assertEqual(planned.output_policy, "confirm")


if __name__ == "__main__":
    unittest.main()
