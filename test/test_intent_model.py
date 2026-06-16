import tempfile
import unittest
from pathlib import Path


class IntentModelTests(unittest.TestCase):
    def test_train_and_load_exact_match_model(self):
        from agent.intent_model import load_intent_model, train_intent_model

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            model_path = Path(td) / "intent_model.json"
            samples.write_text(
                '{"text": "查找一下", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n'
                '{"text": "查找一下", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n'
                '{"text": "无修正"}\n',
                encoding="utf-8",
            )

            summary = train_intent_model(samples, model_path)
            model = load_intent_model(model_path)

            self.assertEqual(summary["examples"], 1)
            self.assertEqual(model.match("查找一下"), {"type": "shortcut", "name": "查找"})
            self.assertIsNone(model.match("查找一下别的"))
            self.assertIsNone(model.match("帮我查找一下", min_similarity=1.0))

    def test_model_can_match_high_similarity_variants_when_enabled(self):
        from agent.intent_model import load_intent_model, train_intent_model

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            model_path = Path(td) / "intent_model.json"
            samples.write_text(
                '{"text": "查找一下", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )
            train_intent_model(samples, model_path)
            model = load_intent_model(model_path)

            self.assertEqual(
                model.match("帮我查找一下", min_similarity=0.8),
                {"type": "shortcut", "name": "查找"},
            )
            self.assertIsNone(model.match("删除全文", min_similarity=0.8))

    def test_train_model_can_register_versioned_current_model(self):
        from agent.intent_model import list_intent_model_versions, load_intent_model, train_intent_model

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            registry = Path(td) / "models"
            samples.write_text(
                '{"text": "查找", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )

            summary = train_intent_model(samples, registry / "current.json", version="v1", registry_dir=registry)
            versions = list_intent_model_versions(registry)
            model = load_intent_model(registry / "current.json")

            self.assertEqual(summary["version"], "v1")
            self.assertEqual(summary["registered"], True)
            self.assertEqual(summary["current"], str(registry / "current.json"))
            self.assertEqual(versions, [{
                "version": "v1",
                "path": str(registry / "versions" / "v1.json"),
                "current": True,
                "examples": 1,
            }])
            self.assertEqual(model.version, "v1")
            self.assertEqual(model.match("查找"), {"type": "shortcut", "name": "查找"})

    def test_train_model_can_register_version_without_activation(self):
        from agent.intent_model import list_intent_model_versions, load_intent_model, train_intent_model

        with tempfile.TemporaryDirectory() as td:
            first = Path(td) / "first.jsonl"
            candidate = Path(td) / "candidate.jsonl"
            registry = Path(td) / "models"
            first.write_text(
                '{"text": "查找", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )
            candidate.write_text(
                '{"text": "保存", "corrected_intent": {"type": "shortcut", "name": "保存"}}\n',
                encoding="utf-8",
            )
            train_intent_model(first, registry / "current.json", version="v1", registry_dir=registry)

            summary = train_intent_model(
                candidate,
                registry / "candidate.json",
                version="v2",
                registry_dir=registry,
                activate=False,
            )
            current = load_intent_model(registry / "current.json")
            candidate_model = load_intent_model(registry / "versions" / "v2.json")

            self.assertEqual(summary["version"], "v2")
            self.assertEqual(summary["registered"], True)
            self.assertEqual(summary["current"], str(registry / "current.json"))
            self.assertEqual(summary["version_path"], str(registry / "versions" / "v2.json"))
            self.assertEqual(current.version, "v1")
            self.assertEqual(current.match("查找"), {"type": "shortcut", "name": "查找"})
            self.assertEqual(candidate_model.version, "v2")
            self.assertEqual(candidate_model.match("保存"), {"type": "shortcut", "name": "保存"})
            self.assertEqual(
                list_intent_model_versions(registry),
                [
                    {
                        "version": "v1",
                        "path": str(registry / "versions" / "v1.json"),
                        "current": True,
                        "examples": 1,
                    },
                    {
                        "version": "v2",
                        "path": str(registry / "versions" / "v2.json"),
                        "current": False,
                        "examples": 1,
                    },
                ],
            )

    def test_registered_model_can_rollback_to_previous_version(self):
        from agent.intent_model import load_intent_model, rollback_intent_model, train_intent_model

        with tempfile.TemporaryDirectory() as td:
            first = Path(td) / "first.jsonl"
            second = Path(td) / "second.jsonl"
            registry = Path(td) / "models"
            first.write_text(
                '{"text": "查找", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )
            second.write_text(
                '{"text": "保存", "corrected_intent": {"type": "shortcut", "name": "保存"}}\n',
                encoding="utf-8",
            )
            train_intent_model(first, registry / "current.json", version="v1", registry_dir=registry)
            train_intent_model(second, registry / "current.json", version="v2", registry_dir=registry)

            summary = rollback_intent_model(registry)
            model = load_intent_model(registry / "current.json")

            self.assertEqual(summary["version"], "v1")
            self.assertEqual(summary["previous_version"], "v2")
            self.assertEqual(model.version, "v1")
            self.assertEqual(model.match("查找"), {"type": "shortcut", "name": "查找"})
            self.assertIsNone(model.match("保存"))


if __name__ == "__main__":
    unittest.main()
