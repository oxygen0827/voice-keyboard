import tempfile
import unittest
from pathlib import Path


class _Response:
    def __init__(self, payload: dict, *, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")

    def json(self):
        return self._payload


class _HTTPClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    def get(self, url: str, *, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "timeout": timeout})
        return _Response(self.payload)


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

    def test_pull_published_model_registers_and_activates_server_version(self):
        from agent.intent_model import load_intent_model, pull_published_intent_model, rollback_intent_model, train_intent_model

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            registry = Path(td) / "models"
            samples.write_text(
                '{"text": "查找", "corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )
            train_intent_model(samples, registry / "current.json", version="local-v1", registry_dir=registry)
            http = _HTTPClient({
                "version": "server-v2",
                "created_at": 123.0,
                "examples": {
                    "保存": {"type": "shortcut", "name": "保存"},
                },
            })

            summary = pull_published_intent_model(
                "http://training.local",
                registry,
                token="secret",
                http=http,
            )
            current = load_intent_model(registry / "current.json")
            rollback = rollback_intent_model(registry)
            rolled_back = load_intent_model(registry / "current.json")

            self.assertEqual(http.calls[0]["url"], "http://training.local/v1/intent-models/published/download")
            self.assertEqual(http.calls[0]["headers"], {"Authorization": "Bearer secret"})
            self.assertEqual(summary["version"], "server-v2")
            self.assertEqual(summary["previous_version"], "local-v1")
            self.assertEqual(summary["examples"], 1)
            self.assertEqual(current.version, "server-v2")
            self.assertEqual(current.match("保存"), {"type": "shortcut", "name": "保存"})
            self.assertEqual(rollback["version"], "local-v1")
            self.assertEqual(rolled_back.match("查找"), {"type": "shortcut", "name": "查找"})


if __name__ == "__main__":
    unittest.main()
