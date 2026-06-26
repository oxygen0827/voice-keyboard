import unittest
from unittest.mock import MagicMock

from agent.operation_confirmation import (
    WindowsOperationConfirmation,
    _confirmation_message,
    make_operation_confirmation,
)


class OperationConfirmationTests(unittest.TestCase):
    def test_non_windows_platform_has_no_confirmation_adapter(self):
        self.assertIsNone(make_operation_confirmation(platform="darwin"))

    def test_windows_platform_without_windll_has_no_confirmation_adapter(self):
        adapter = make_operation_confirmation(platform="win32")

        self.assertIsNone(adapter)

    def test_confirmation_message_names_action_and_reason(self):
        message = _confirmation_message("发送", "high_risk_requires_confirmation")

        self.assertIn("发送", message)
        self.assertIn("高风险操作", message)
        self.assertIn("确认执行吗", message)

    def test_windows_confirmation_returns_true_only_for_yes(self):
        user32 = MagicMock()
        user32.MessageBoxW.return_value = 6
        status = MagicMock()
        adapter = WindowsOperationConfirmation(status_window=status, user32=user32)

        self.assertTrue(adapter("发送", "high_risk_requires_confirmation"))
        status.show_message.assert_called_once_with("需要确认：发送", 4.0)
        self.assertIn("发送", user32.MessageBoxW.call_args.args[1])

    def test_windows_confirmation_returns_false_for_no(self):
        user32 = MagicMock()
        user32.MessageBoxW.return_value = 7
        adapter = WindowsOperationConfirmation(user32=user32)

        self.assertFalse(adapter("发送", "high_risk_requires_confirmation"))


if __name__ == "__main__":
    unittest.main()
