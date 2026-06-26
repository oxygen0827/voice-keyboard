import unittest

from agent.voice_text_operation import VoiceTextOperation, operation_from_intent


class VoiceTextOperationTests(unittest.TestCase):
    def test_converts_structured_shortcut_intent(self):
        operation = operation_from_intent({"type": "shortcut", "name": " 保存 "})

        self.assertEqual(operation, VoiceTextOperation(kind="shortcut", name="保存"))

    def test_unknown_intent_becomes_chat_operation(self):
        operation = operation_from_intent({"type": "unknown", "reply": " 稍后再试 "})

        self.assertEqual(operation, VoiceTextOperation(kind="chat", reply="稍后再试"))

    def test_non_string_payload_fields_become_empty_strings(self):
        operation = operation_from_intent({"type": "memo_save", "key": 123, "value": None})

        self.assertEqual(operation, VoiceTextOperation(kind="memo_save"))

    def test_keeps_memo_operation_kinds(self):
        self.assertEqual(
            operation_from_intent({
                "type": "memo_save",
                "key": "邮箱",
                "value": "me@example.com",
            }),
            VoiceTextOperation(
                kind="memo_save",
                key="邮箱",
                value="me@example.com",
            ),
        )
        self.assertEqual(
            operation_from_intent({"type": "memo_recall", "key": "邮箱"}),
            VoiceTextOperation(kind="memo_recall", key="邮箱"),
        )
        self.assertEqual(
            operation_from_intent({"type": "memo_delete", "key": "邮箱"}),
            VoiceTextOperation(kind="memo_delete", key="邮箱"),
        )
        self.assertEqual(
            operation_from_intent({"type": "memo_list"}),
            VoiceTextOperation(kind="memo_list"),
        )

if __name__ == "__main__":
    unittest.main()
