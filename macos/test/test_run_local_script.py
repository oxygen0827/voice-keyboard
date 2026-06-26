import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RunLocalScriptTests(unittest.TestCase):
    def test_kill_only_matcher_searches_agent_main_processes(self):
        script = ROOT / "scripts" / "run-local.sh"
        command = [str(script), "--kill-only"]
        if sys.platform == "win32":
            bash = shutil.which("bash")
            if bash is None:
                self.skipTest("bash is required to run scripts/run-local.sh on Windows")
            command = [bash, str(script), "--kill-only"]

        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            log_path = Path(tmp) / "pgrep.log"
            fake_pgrep = bin_dir / "pgrep"
            fake_pgrep.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    printf '%s\\n' "$*" >> "{log_path}"
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            fake_pgrep.chmod(fake_pgrep.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            matcher = log_path.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("agent\\.main|agent/main\\.py", matcher)

    def test_status_reports_not_running_without_pid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_pgrep = bin_dir / "pgrep"
            fake_pgrep.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            fake_pgrep.chmod(fake_pgrep.stat().st_mode | stat.S_IXUSR)
            fake_launchctl = bin_dir / "launchctl"
            fake_launchctl.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            fake_launchctl.chmod(fake_launchctl.stat().st_mode | stat.S_IXUSR)

            pid_file = ROOT / ".local" / "run" / "voice-keyboard-local.pid"
            old_pid_file = pid_file.read_text(encoding="utf-8") if pid_file.exists() else None
            pid_file.unlink(missing_ok=True)
            try:
                env = os.environ.copy()
                env["PATH"] = f"{bin_dir}:{env['PATH']}"
                result = subprocess.run(
                    [str(ROOT / "scripts" / "run-local.sh"), "--status"],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            finally:
                if old_pid_file is not None:
                    pid_file.parent.mkdir(parents=True, exist_ok=True)
                    pid_file.write_text(old_pid_file, encoding="utf-8")

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("[run-local] Status: not running", result.stdout)

    def test_status_reports_launch_agent_when_pid_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_pgrep = bin_dir / "pgrep"
            fake_pgrep.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            fake_pgrep.chmod(fake_pgrep.stat().st_mode | stat.S_IXUSR)
            fake_launchctl = bin_dir / "launchctl"
            fake_launchctl.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    cat <<'EOF'
                    gui/501/com.voicekeyboard.agent = {{
                        state = running
                        arguments = {{
                            {ROOT}/.venv/bin/python
                            -u
                            -m
                            agent.main
                            --no-serial
                            --headless
                        }}
                        working directory = {ROOT}
                        pid = 12345
                    }}
                    EOF
                    """
                ),
                encoding="utf-8",
            )
            fake_launchctl.chmod(fake_launchctl.stat().st_mode | stat.S_IXUSR)

            pid_file = ROOT / ".local" / "run" / "voice-keyboard-local.pid"
            old_pid_file = pid_file.read_text(encoding="utf-8") if pid_file.exists() else None
            pid_file.unlink(missing_ok=True)
            try:
                env = os.environ.copy()
                env["PATH"] = f"{bin_dir}:{env['PATH']}"
                result = subprocess.run(
                    [str(ROOT / "scripts" / "run-local.sh"), "--status"],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            finally:
                if old_pid_file is not None:
                    pid_file.parent.mkdir(parents=True, exist_ok=True)
                    pid_file.write_text(old_pid_file, encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[run-local] Status: running", result.stdout)
        self.assertIn("[run-local] PID: 12345", result.stdout)
        self.assertIn("[run-local] LaunchAgent: com.voicekeyboard.agent", result.stdout)

    def test_background_start_writes_pid_and_log_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_python = bin_dir / "python"
            fake_python.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    sleep 30
                    """
                ),
                encoding="utf-8",
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PYTHON"] = str(fake_python)
            result = subprocess.run(
                [
                    str(ROOT / "scripts" / "run-local.sh"),
                    "--no-kill",
                    "--background",
                    "--",
                    "--no-ui",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            pid_file = ROOT / ".local" / "run" / "voice-keyboard-local.pid"
            try:
                pid_text = pid_file.read_text(encoding="utf-8").strip()
                self.assertTrue(pid_text.isdigit(), result.stdout)
                self.assertIn(f"[run-local] PID file: {pid_file}", result.stdout)
                self.assertIn("[run-local] Log:", result.stdout)
            finally:
                if pid_file.exists():
                    pid = pid_file.read_text(encoding="utf-8").strip()
                    if pid.isdigit():
                        subprocess.run(["kill", pid], check=False)
                    pid_file.unlink(missing_ok=True)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_permissions_command_is_advertised_for_macos_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_python = bin_dir / "python"
            fake_python.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    sleep 30
                    """
                ),
                encoding="utf-8",
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PYTHON"] = str(fake_python)
            result = subprocess.run(
                [str(ROOT / "scripts" / "run-local.sh"), "--no-kill", "--background"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            pid_file = ROOT / ".local" / "run" / "voice-keyboard-local.pid"
            try:
                self.assertIn(
                    "scripts/run-local.sh --permissions",
                    result.stdout,
                )
                self.assertIn("System Settings grants apply to the launching app", result.stdout)
            finally:
                if pid_file.exists():
                    pid = pid_file.read_text(encoding="utf-8").strip()
                    if pid.isdigit():
                        subprocess.run(["kill", pid], check=False)
                    pid_file.unlink(missing_ok=True)

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
