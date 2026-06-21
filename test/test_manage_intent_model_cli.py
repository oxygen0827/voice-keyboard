import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


class ManageIntentModelCliTests(unittest.TestCase):
    def test_pull_published_command_prints_json_summary(self):
        import tools.manage_intent_model as cli

        with patch("sys.argv", [
            "manage_intent_model.py",
            "--registry-dir",
            "/tmp/models",
            "--json",
            "pull-published",
            "--server",
            "http://training.local",
            "--token",
            "secret",
        ]), patch.object(cli, "pull_published_intent_model", return_value={
            "version": "server-v2",
            "previous_version": "local-v1",
            "current": "/tmp/models/current.json",
            "examples": 3,
        }) as pull:
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main()

        pull.assert_called_once_with(
            "http://training.local",
            "/tmp/models",
            token="secret",
        )
        self.assertIn('"version": "server-v2"', out.getvalue())
        self.assertIn('"examples": 3', out.getvalue())


if __name__ == "__main__":
    unittest.main()
