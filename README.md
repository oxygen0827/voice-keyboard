# Voice Keyboard

This repository now keeps the two platform codebases side by side.

## Layout

| Path | Purpose |
| --- | --- |
| `windows/` | Windows Voice Keyboard Engine. This is the active Windows build that contains the tray runtime, main window, correction memory, dictionary UI, and Windows validation tests. |
| `macos/` | macOS-oriented upstream snapshot from `origin/main`. Keep macOS-specific runtime, packaging, and docs here. |

Each subfolder is intended to be self-contained. Run setup, tests, and packaging commands from inside the platform folder you are working on.

## Windows

```powershell
cd windows
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s test
.\.venv\Scripts\python.exe -m agent.windows.tray
```

If you want to reuse the root virtual environment during local development, run commands from `windows/` with `..\.venv\Scripts\python.exe`.

## macOS

```bash
cd macos
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m agent.main --no-serial
```

Before moving behavior between platforms, check the relevant `AGENTS.md`, `CONTEXT.md`, and ADR files inside that platform folder.
