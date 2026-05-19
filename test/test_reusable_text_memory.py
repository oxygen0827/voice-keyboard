import unittest

from agent.reusable_text_memory import (
    ReusableTextMemoryResolver,
    ReusableTextOperationResult,
    ReusableTextMemoryRecord,
    ReusableTextMemory,
    ReusableTextMemoryMatcher,
    parse_memory_edit_command,
    redact_memory_value,
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
        self.assertEqual(result, ReusableTextOperationResult.show("已记住「邮箱」"))

    def test_recall_returns_insert_result(self):
        store = FakeMemoryStore()
        store.data["地址"] = "上海"
        memory = ReusableTextMemory(store)

        result = memory.recall("地址")

        self.assertEqual(result, ReusableTextOperationResult.insert("上海"))

    def test_missing_store_returns_disabled_message(self):
        memory = ReusableTextMemory(None)

        result = memory.list_all()

        self.assertEqual(result, ReusableTextOperationResult.show("可复用文本功能未启用"))

    def test_list_all_formats_saved_memory(self):
        store = FakeMemoryStore()
        store.data["邮箱"] = "me@example.com"
        store.data["地址"] = "上海"
        memory = ReusableTextMemory(store)

        result = memory.list_all()

        self.assertEqual(result, ReusableTextOperationResult.insert("邮箱: me@example.com\n地址: 上海"))

    def test_list_all_redacts_sensitive_memory_values(self):
        store = FakeMemoryStore()
        store.data["小米的api密钥"] = "sk-testonlydummyvalue000000000000000000"
        store.data["访问我家服务器的地址"] = "ssh -p 10281 wq@5.tcp.cpolar.cn"
        memory = ReusableTextMemory(store)

        result = memory.list_all()

        self.assertEqual(result, ReusableTextOperationResult.insert(
            "小米的api密钥: [已隐藏]\n访问我家服务器的地址: [已隐藏]"
        ))
        self.assertNotIn("sk-", result.text)
        self.assertNotIn("ssh -p", result.text)

    def test_delete_reports_removed_memory(self):
        store = FakeMemoryStore()
        store.data["邮箱"] = "me@example.com"
        memory = ReusableTextMemory(store)

        result = memory.delete("邮箱")

        self.assertEqual(store.data, {})
        self.assertEqual(result, ReusableTextOperationResult.show("已忘掉「邮箱」"))

    def test_edit_text_renames_key_and_updates_value(self):
        store = FakeMemoryStore()
        store.data["mac的密码"] = "mac password"
        memory = ReusableTextMemory(store)

        result = memory.edit_text("mac的密码", "mac", "macOS")

        self.assertEqual(result, ReusableTextOperationResult.show("已更新「macOS的密码」"))
        self.assertEqual(store.data, {"macOS的密码": "macOS password"})

    def test_edit_text_reports_ambiguous_memory(self):
        store = FakeMemoryStore()
        store.data["mac的密码"] = "one"
        store.data["mac的账号"] = "two"
        memory = ReusableTextMemory(store)

        result = memory.edit_text("", "mac", "macOS")

        self.assertEqual(
            result,
            ReusableTextOperationResult.show("找到多个可复用文本：mac的密码、mac的账号，请说得更具体"),
        )

    def test_matcher_finds_saved_key_from_spoken_memory_request(self):
        matcher = ReusableTextMemoryMatcher()

        self.assertEqual(
            matcher.match_key("我的手机号是多少", ("手机号", "家庭地址")),
            "手机号",
        )

    def test_matcher_treats_phone_number_as_phone_key(self):
        matcher = ReusableTextMemoryMatcher()

        self.assertEqual(
            matcher.match_key("我的手机号码是多少", ("手机号", "家庭地址")),
            "手机号",
        )

    def test_matcher_does_not_match_unrelated_saved_key(self):
        matcher = ReusableTextMemoryMatcher()

        self.assertIsNone(matcher.match_key("我的手机号码是多少", ("儿子",)))

    def test_fuzzy_match_memory_key_keeps_matching_rule_in_memory_module(self):
        self.assertEqual(
            fuzzy_match_memory_key("白光宇说什么", ("白光宇最喜欢说的话",)),
            "白光宇最喜欢说的话",
        )

    def test_redact_memory_value_leaves_normal_text_visible(self):
        self.assertEqual(redact_memory_value("爱吃的雪糕", "伊利雪糕"), "伊利雪糕")

    def test_parse_recent_memory_edit_command(self):
        command = parse_memory_edit_command("刚刚说的mac的密码，那个mac实际上是macOS")

        self.assertIsNotNone(command)
        self.assertEqual(command.target, "mac的密码")
        self.assertEqual(command.old, "mac")
        self.assertEqual(command.new, "macOS")


class ReusableTextMemoryResolverTests(unittest.TestCase):
    def resolve(self, text: str, *records: ReusableTextMemoryRecord):
        return ReusableTextMemoryResolver().resolve(text, records)

    def test_single_email_type_query_resolves_unique_memory(self):
        result = self.resolve(
            "我的邮箱地址是什么",
            ReusableTextMemoryRecord("工作邮箱", "me@example.com"),
        )

        self.assertEqual(result.status, "unique")
        self.assertEqual(result.key, "工作邮箱")

    def test_multiple_email_type_query_is_ambiguous(self):
        result = self.resolve(
            "我的邮箱是什么",
            ReusableTextMemoryRecord("个人邮箱", "me@example.com"),
            ReusableTextMemoryRecord("工作邮箱", "work@example.com"),
        )

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.candidates, ("个人邮箱", "工作邮箱"))

    def test_specific_email_alias_selects_one_of_multiple_email_memories(self):
        result = self.resolve(
            "我的工作邮箱是什么",
            ReusableTextMemoryRecord("个人邮箱", "me@example.com"),
            ReusableTextMemoryRecord("工作邮箱", "work@example.com"),
        )

        self.assertTrue(result.can_recall)
        self.assertEqual(result.key, "工作邮箱")

    def test_address_type_does_not_hide_more_specific_repo_address(self):
        result = self.resolve(
            "量化项目仓库地址是什么",
            ReusableTextMemoryRecord("家庭地址", "上海"),
            ReusableTextMemoryRecord("量化项目仓库地址", "https://github.com/example/repo.git"),
        )

        self.assertTrue(result.can_recall)
        self.assertEqual(result.key, "量化项目仓库地址")

    def test_unrelated_query_returns_none(self):
        result = self.resolve(
            "我的手机号码是多少",
            ReusableTextMemoryRecord("儿子", "白光宇"),
        )

        self.assertEqual(result.status, "none")

    def test_personal_alias_resolves_memory_key(self):
        result = self.resolve(
            "小白说什么",
            ReusableTextMemoryRecord("白光宇最喜欢说的话", "大美女", aliases=("小白",)),
        )

        self.assertTrue(result.can_recall)
        self.assertEqual(result.key, "白光宇最喜欢说的话")


if __name__ == "__main__":
    unittest.main()
