import unittest

from agent.reusable_text_memory import (
    MemoryOperationResult,
    ReusableTextMemory,
    ReusableTextMemoryMatcher,
    fuzzy_match_memory_key,
)


class FakeMemoryStore:
    def __init__(self):
        self.data = {}

    def save(self, key: str, value: str) -> None:
        self.data[key] = value

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def delete(self, key: str) -> bool:
        if key in self.data:
            del self.data[key]
            return True
        return False

    def keys(self) -> list[str]:
        return list(self.data.keys())


class ReusableTextMemoryTests(unittest.TestCase):
    def test_save_uses_explicit_selection_before_classifier_value(self):
        store = FakeMemoryStore()
        memory = ReusableTextMemory(store)

        result = memory.save("邮箱", "wrong@example.com", selected="me@example.com")

        self.assertEqual(store.data, {"邮箱": "me@example.com"})
        self.assertEqual(result, MemoryOperationResult.show("已记住「邮箱」"))

    def test_recall_returns_insert_result(self):
        store = FakeMemoryStore()
        store.data["地址"] = "上海"
        memory = ReusableTextMemory(store)

        result = memory.recall("地址")

        self.assertEqual(result, MemoryOperationResult.insert("上海"))

    def test_missing_store_returns_disabled_message(self):
        memory = ReusableTextMemory(None)

        result = memory.list_all()

        self.assertEqual(result, MemoryOperationResult.show("可复用文本功能未启用"))

    def test_list_all_formats_saved_memory(self):
        store = FakeMemoryStore()
        store.data["邮箱"] = "me@example.com"
        store.data["地址"] = "上海"
        memory = ReusableTextMemory(store)

        result = memory.list_all()

        self.assertEqual(result, MemoryOperationResult.insert("邮箱: me@example.com\n地址: 上海"))

    def test_delete_reports_removed_memory(self):
        store = FakeMemoryStore()
        store.data["邮箱"] = "me@example.com"
        memory = ReusableTextMemory(store)

        result = memory.delete("邮箱")

        self.assertEqual(store.data, {})
        self.assertEqual(result, MemoryOperationResult.show("已忘掉「邮箱」"))

    def test_matcher_finds_saved_key_from_spoken_memory_request(self):
        matcher = ReusableTextMemoryMatcher()

        self.assertEqual(
            matcher.match_key("我的手机号是多少", ("手机号", "家庭地址")),
            "手机号",
        )

    def test_fuzzy_match_memory_key_keeps_matching_rule_in_memory_module(self):
        self.assertEqual(
            fuzzy_match_memory_key("白光宇说什么", ("白光宇最喜欢说的话",)),
            "白光宇最喜欢说的话",
        )


if __name__ == "__main__":
    unittest.main()
