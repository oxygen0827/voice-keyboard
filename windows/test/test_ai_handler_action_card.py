import unittest
from unittest.mock import MagicMock

from agent.ai_command_plan import AICommandPlan
from agent.ai_handler import AIHandler
from agent.input_environment import TextTarget
from agent.voice_text_operation import VoiceTextOperation


class FakeSTT:
    def transcribe(self, _pcm: bytes) -> str:
        return ""


class FakeStatus:
    def __init__(self):
        self.messages = []
        self.action_cards = []

    def show_message(self, text: str, seconds: float = 6.0):
        self.messages.append((text, seconds))

    def show_action_card(self, **kwargs):
        self.action_cards.append(kwargs)
        return True


class AIHandlerActionCardTests(unittest.TestCase):
    def test_auto_command_uses_short_status_not_action_card(self):
        status = FakeStatus()
        handler = AIHandler(
            FakeSTT(),
            MagicMock(),
            MagicMock(),
            status_window=status,
            input_environment=MagicMock(),
        )
        handler._executor = MagicMock()
        handler._executor.execute_plan.return_value = False
        plan = AICommandPlan(
            VoiceTextOperation("memo_recall", key="手机号码"),
            operation_kind="memo_recall",
            target_source="memo",
            output_policy="auto",
            preview_text="手机号码",
        )

        handler._execute_command_plan(plan, "输入我的手机号码", "", TextTarget())

        self.assertEqual(status.action_cards, [])
        self.assertEqual(status.messages, [
            ("[AI]: 已执行：输入我的手机号码", 2.2),
        ])

    def test_auto_command_keeps_existing_visible_feedback(self):
        status = FakeStatus()
        handler = AIHandler(
            FakeSTT(),
            MagicMock(),
            MagicMock(),
            status_window=status,
            input_environment=MagicMock(),
        )
        handler._executor = MagicMock()
        handler._executor.execute_plan.return_value = True
        plan = AICommandPlan(
            VoiceTextOperation("chat", reply="hello"),
            operation_kind="chat",
            output_policy="auto",
            preview_text="hello",
        )

        handler._execute_command_plan(plan, "question", "", TextTarget())

        self.assertEqual(status.action_cards, [])
        self.assertEqual(status.messages, [])

    def test_confirm_command_still_uses_action_card(self):
        status = FakeStatus()
        handler = AIHandler(
            FakeSTT(),
            MagicMock(),
            MagicMock(),
            status_window=status,
            input_environment=MagicMock(),
        )
        handler._executor = MagicMock()
        plan = AICommandPlan(
            VoiceTextOperation("delete"),
            operation_kind="delete",
            output_policy="confirm",
            preview_text="删除内容",
        )

        handler._execute_command_plan(plan, "删除全部", "", TextTarget())

        handler._executor.execute_plan.assert_not_called()
        self.assertEqual(len(status.action_cards), 1)
        self.assertEqual(status.action_cards[0]["operation_kind"], "delete")


if __name__ == "__main__":
    unittest.main()
