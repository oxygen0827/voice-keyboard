import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _HTTPClient:
    def __init__(self, corrections=None):
        self.posts = []
        self.gets = []
        self.corrections = corrections

    def post(self, url, *, params=None, data=None, headers=None, timeout=None):
        self.posts.append({
            "url": url,
            "params": params,
            "data": data,
            "headers": headers,
            "timeout": timeout,
        })
        return _Response({"inserted": 1})

    def get(self, url, *, params=None, headers=None, timeout=None):
        self.gets.append({
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout,
        })
        return _Response({
            "items": self.corrections if self.corrections is not None else [
                {
                    "text": "表格里查一下",
                    "corrected_intent": {"type": "shortcut", "name": "查找"},
                }
            ]
        })


class IntentLoopTests(unittest.TestCase):
    def test_run_training_loop_marks_regressed_model_activation_unsafe(self):
        from agent.intent_loop import _model_activation_decision

        decision = _model_activation_decision(
            baseline={"accuracy": 0.9, "correct": 9, "wrong": 1, "mismatches": []},
            candidate={"accuracy": 0.8, "correct": 8, "wrong": 2, "mismatches": [{"text": "bad"}]},
        )

        self.assertFalse(decision["should_activate"])
        self.assertEqual(decision["reason"], "candidate_regressed")
    def test_run_training_loop_uploads_syncs_and_evaluates(self):
        from agent.intent_loop import run_training_loop
        from agent.intent_overrides import find_override

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            samples.write_text(
                '{"text": "表格里查一下", "shortcut_names": ["查找"], '
                '"corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )
            http = _HTTPClient()

            report = run_training_loop(
                sample_path=samples,
                server="http://training.local",
                token="secret",
                override_path=overrides,
                http=http,
            )

            self.assertEqual(http.posts[0]["url"], "http://training.local/v1/intent-samples/batches")
            self.assertEqual(http.gets[0]["url"], "http://training.local/v1/intent-samples/corrections")
            self.assertEqual(http.posts[0]["headers"]["Authorization"], "Bearer secret")
            self.assertEqual(report["upload"]["inserted"], 1)
            self.assertEqual(report["sync"], {"synced": 1, "skipped": 0, "compacted": 0})
            self.assertEqual(report["evaluation"]["accuracy_label"], "100.0%")
            self.assertEqual(
                find_override("表格里查一下", path=overrides),
                {"type": "shortcut", "name": "查找"},
            )

    def test_run_training_loop_can_train_versioned_model_and_report_it(self):
        from agent.intent_loop import run_training_loop
        from agent.intent_model import load_intent_model

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            registry = Path(td) / "models"
            reports = Path(td) / "reports"
            samples.write_text(
                '{"text": "表格里查一下", "shortcut_names": ["查找"], '
                '"corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )
            http = _HTTPClient()

            report = run_training_loop(
                sample_path=samples,
                server="http://training.local",
                override_path=overrides,
                http=http,
                model_registry_dir=registry,
                model_version="loop-v1",
                model_report_dir=reports,
                model_min_similarity=0.8,
            )
            model = load_intent_model(registry / "current.json")

            self.assertEqual(report["model"]["version"], "loop-v1")
            self.assertEqual(report["model"]["registered"], True)
            self.assertEqual(report["model_evaluation"]["report"]["intent_model_min_similarity"], 0.8)
            self.assertTrue(report["model_activation"]["should_activate"])
            self.assertEqual(report["model_activation"]["reason"], "candidate_ok")
            self.assertTrue(Path(report["model_evaluation"]["path"]).exists())
            self.assertEqual(model.version, "loop-v1")
            self.assertEqual(model.match("表格里查一下"), {"type": "shortcut", "name": "查找"})

    def test_run_training_loop_evaluates_candidate_version_path_before_activation(self):
        from agent.intent_loop import run_training_loop

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            registry = Path(td) / "models"
            reports = Path(td) / "reports"
            samples.write_text(
                '{"text": "表格里查一下", "shortcut_names": ["查找"], '
                '"corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )

            report = run_training_loop(
                sample_path=samples,
                server="http://training.local",
                override_path=overrides,
                http=_HTTPClient(),
                model_registry_dir=registry,
                model_version="loop-v2",
                model_report_dir=reports,
            )

            self.assertEqual(report["model"]["version_path"], str(registry / "versions" / "loop-v2.json"))
            self.assertEqual(
                report["model_evaluation"]["report"]["intent_model_path"],
                str(registry / "versions" / "loop-v2.json"),
            )
            self.assertEqual(report["model_activation"]["activated"], True)

    def test_run_training_loop_does_not_activate_model_without_evaluation_report(self):
        from agent.intent_loop import run_training_loop

        with tempfile.TemporaryDirectory() as td:
            samples = Path(td) / "samples.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            registry = Path(td) / "models"
            samples.write_text(
                '{"text": "表格里查一下", "shortcut_names": ["查找"], '
                '"corrected_intent": {"type": "shortcut", "name": "查找"}}\n',
                encoding="utf-8",
            )

            report = run_training_loop(
                sample_path=samples,
                server="http://training.local",
                override_path=overrides,
                http=_HTTPClient(),
                model_registry_dir=registry,
                model_version="loop-v2",
            )

            self.assertEqual(report["model_activation"]["reason"], "not_evaluated")
            self.assertFalse(report["model_activation"]["should_activate"])
            self.assertFalse(report["model_activation"]["activated"])
            self.assertFalse((registry / "current.json").exists())
            self.assertTrue((registry / "versions" / "loop-v2.json").exists())

    def test_run_training_loop_keeps_current_model_when_candidate_regresses(self):
        from agent.intent_loop import run_training_loop
        from agent.intent_model import load_intent_model, train_intent_model

        with tempfile.TemporaryDirectory() as td:
            baseline_samples = Path(td) / "baseline.jsonl"
            candidate_samples = Path(td) / "candidate.jsonl"
            overrides = Path(td) / "overrides.jsonl"
            registry = Path(td) / "models"
            reports = Path(td) / "reports"
            baseline_samples.write_text(
                '{"text": "调出我的暗号", '
                '"corrected_intent": {"type": "memo_recall", "key": "暗号"}}\n',
                encoding="utf-8",
            )
            candidate_samples.write_text(
                '{"text": "调出我的暗号", '
                '"corrected_intent": {"type": "memo_recall", "key": "暗号"}}\n'
                '{"text": "调出我的地址", '
                '"corrected_intent": {"type": "memo_recall", "key": "地址"}}\n',
                encoding="utf-8",
            )
            train_intent_model(
                baseline_samples,
                registry / "current.json",
                version="baseline",
                registry_dir=registry,
            )

            with patch(
                "agent.intent_loop._model_activation_decision",
                return_value={
                    "should_activate": False,
                    "reason": "candidate_regressed",
                    "comparison": {"regressed": True},
                },
            ):
                report = run_training_loop(
                    sample_path=candidate_samples,
                    server="http://training.local",
                    override_path=overrides,
                    http=_HTTPClient(corrections=[]),
                    model_registry_dir=registry,
                    model_version="candidate",
                    model_report_dir=reports,
                    model_min_similarity=0.8,
                )
            current = load_intent_model(registry / "current.json")
            candidate = load_intent_model(registry / "versions" / "candidate.json")

            self.assertFalse(report["model_activation"]["should_activate"])
            self.assertFalse(report["model_activation"]["activated"])
            self.assertEqual(report["model_activation"]["reason"], "candidate_regressed")
            self.assertEqual(current.version, "baseline")
            self.assertIsNone(current.match("调出我的地址"))
            self.assertEqual(candidate.version, "candidate")
            self.assertEqual(candidate.match("调出我的地址"), {"type": "memo_recall", "key": "地址"})


if __name__ == "__main__":
    unittest.main()
