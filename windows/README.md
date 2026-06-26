# Voice Keyboard Engine

Voice Keyboard Engine is a local, voice-driven keyboard efficiency layer. It turns speech into text insertion, text revision, shortcut invocation, window operations, application launch, and memo recall in the current input environment.

The project is not a chat assistant and it is not an account, payment, subscription, or entitlement system. Those product flows belong outside this repository. This repository owns the local engine and desktop runtime.

## Current Status

The repository is currently focused on the Windows desktop experience while keeping macOS, Linux, and headless entry points available.

The Windows runtime includes:

- A system tray app that can start the backend automatically or stay in standby with `ui.start_enabled: false`.
- A Tkinter main window for overview, history, intent diagnostics, personal dictionary, memos, hotkeys, config, and runtime checks.
- A compact capsule HUD for local status feedback.
- Dictation Mode for speech-to-text insertion.
- Instruction Mode for voice-driven text operations and keyboard-style actions.
- Dictation correction memory with confirmed entries, candidates, and batch deletion from the Windows main window.
- Personal dictionary hints for Speech Interpretation Provider adapters.
- Memo save, recall, delete, and list operations.
- Local intent diagnostics and sample collection for later review and training.
- A separate intent training server for JSONL sample ingestion, review labels, and basic statistics.

Important safety behavior:

- Standby is available from the tray menu or with `ui.start_enabled: false`.
- In standby, PTT/AI global hotkeys are not active and the engine does not send keyboard input.
- History and memo insertion from the tray are blocked while standby is active.
- High-risk Instruction Mode operations require local policy checks and may require confirmation.

## Domain Language

Use the domain language in [CONTEXT.md](CONTEXT.md). In short:

- **Voice Keyboard Engine**: the local engine in this repository.
- **Dictation Mode**: speech is treated as content to insert.
- **Instruction Mode**: speech is treated as a Voice Keyboard Operation.
- **Input Environment**: the current app, field, cursor position, and selected text.
- **Tracked Segment**: recently inserted text that is still safe to revise.
- **Explicit Selection**: text deliberately selected by the user.
- **Speech Interpretation Provider**: external STT or LLM capability used by the engine.

## Main Features

### Dictation Mode

- Hold the configured Dictation hotkey, speak, release, and insert recognized text.
- Supports raw dictation and micro-polish flows.
- Uses the current typing backend to insert text into the focused input environment.
- Supports clipboard insertion for applications that reject Unicode key injection.
- Applies confirmed correction-memory entries before text is inserted.

### Dictation Correction Memory

Correction memory learns small `wrong -> correct` pairs from manual edits made shortly after Dictation Mode inserts text.

Default location:

```text
~/.voice-keyboard/correction_memory.json
```

Behavior:

- The engine remembers the most recent Tracked Segment inserted by Dictation Mode.
- It observes the focused input field for a short window after insertion.
- If the user edits the inserted text, the engine compares `before` and `after` and infers correction pairs.
- A single changed occurrence counts once.
- A batch edit of three occurrences counts three times.
- The default confirmation threshold is `3`, meaning "more than twice".
- Confirmed entries are applied to future dictation output before typing.
- Candidate entries remain visible until they collect enough evidence or are deleted.

Example:

```text
before: 王之行，王之行，王之行
after:  王知行，王知行，王知行
learns: 王之行 -> 王知行, count 3
```

Windows capture paths for correction learning:

- UIAutomation `ValuePattern`, `TextPattern`, and rich-text descendant scanning.
- Win32 `WM_GETTEXT` for classic controls.
- Local keyboard edit tracking and Windows IME committed-text events.
- Optional clipboard probe fallback, disabled by default because it can disturb selection.
- Optional screen OCR fallback where supported.

### Instruction Mode

- Hold the configured Instruction hotkey and speak an operation request.
- Supports text revision, text generation, text removal, shortcut invocation, application launch, window actions, and memo operations.
- Uses local deterministic handling where possible before falling back to a Speech Interpretation Provider.
- Applies local risk policy for operations that may submit, delete, overwrite broad content, or cross application boundaries.

### Windows Tray And Main Window

The Windows tray app is the preferred Windows runtime surface.

Tray menu capabilities:

- Open the main window.
- Enable or disable Voice Keyboard.
- Switch Chinese or English UI labels.
- Configure Dictation and Instruction hotkeys.
- Insert recent history or memo snippets when the backend is enabled.
- Reload config.
- Register or remove start-on-login.
- Quit the runtime.

Main window areas:

- Overview
- History
- Intent diagnostics
- Correction dictionary with added entries, candidate entries, checkboxes, and batch deletion
- Memo library
- Hotkeys
- Config
- Runtime check

### Personal Dictionary

The personal dictionary is separate from correction memory. It stores proper nouns, contacts, brand terms, and phrases that should be offered to Speech Interpretation Provider adapters as prompt hints or, when explicitly enabled, hotwords.

Default location:

```text
~/.voice-keyboard/personal_dictionary.json
```

By default, entries are used as conservative prompt hints. Set `personal_dictionary_hotwords: true` in the STT config only when the provider's hotword behavior is known to be safe for your audio environment.

### Memo Library

Memos are short user-provided snippets for later insertion, such as emails, addresses, signatures, or common replies.

Memo is intentionally narrow:

- It is not chat memory.
- It is not a user profile.
- It is not a personal knowledge base.

### Intent Training Loop

The desktop client can collect sanitized intent samples for later review and training. The server side lives in `training_server/` and supports:

- FastAPI API
- SQLite store for development and small deployments
- Token-protected JSONL upload
- Sample listing
- Review labels
- Basic stats
- Client upload CLI

See:

- [docs/intent-training.md](docs/intent-training.md)
- [docs/intent-training-server.md](docs/intent-training-server.md)

## Installation

Python 3.11 or newer is recommended.

Windows:

```powershell
git clone https://github.com/oxygen0827/voice-keyboard.git
cd voice-keyboard\windows
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy config.yaml.example config.yaml
```

macOS or Linux:

```bash
git clone https://github.com/oxygen0827/voice-keyboard.git
cd voice-keyboard/windows
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.yaml.example config.yaml
```

Configure `config.yaml` or the user config:

```text
~/.voice-keyboard/config.yaml
```

When the user config exists, it takes priority over the repository config.

## Runtime Entry Points

Windows tray app:

```powershell
.\.venv\Scripts\python.exe -u -m agent.windows.tray
```

In a split checkout, the helper batch files also accept the repository root virtual environment as a fallback. For example, `start_tray_windows.bat` first looks for `windows\.venv`, then for `..\.venv`.

Windows desktop runtime:

```powershell
.\.venv\Scripts\python.exe -m agent.main --no-serial
```

Headless backend debugging on Windows:

```powershell
.\.venv\Scripts\python.exe -u -m agent.main --no-serial --no-ui --headless --enable-backend
```

List devices:

```powershell
.\.venv\Scripts\python.exe -m agent.main --list-devices
```

Headless CLI:

```powershell
.\.venv\Scripts\python.exe -m agent.cli --list-devices
.\.venv\Scripts\python.exe -m agent.cli --once --seconds 5
.\.venv\Scripts\python.exe -m agent.cli --loop
```

macOS or Linux:

```bash
.venv/bin/python -m agent.main --no-serial
.venv/bin/python -m agent.main --list-devices
.venv/bin/python -m agent.cli --once --seconds 5
```

macOS may need microphone, Accessibility, and input-monitoring permissions.

## Configuration

Main config sections:

- `stt`: Dictation Mode speech recognition provider.
- `ai_stt`: optional Instruction Mode speech recognition provider.
- `polish_stt`: optional micro-polish recognition provider.
- `llm`: text interpretation, revision, and generation provider.
- `audio`: capture mode, hotkeys, device, and VAD settings.
- `typing`: text insertion backend.
- `correction_memory`: local Dictation Mode correction learning and dictionary storage.
- `instruction_mode`: Instruction Mode diagnostics, local learning, and training sample options.

Example hotkey config:

```yaml
audio:
  mode: ptt
  ptt_key: ctrl_r
  ai_key: shift_r
  device: auto
```

Windows note: on some Chinese or international keyboard layouts, right Alt may behave as AltGr and may not be reliable as a global hotkey. Prefer `ctrl_r`, `shift_r`, or function keys if that happens.

Use clipboard insertion for applications that reject Unicode key injection:

```yaml
typing:
  method: clip
```

Correction memory config:

```yaml
correction_memory:
  enabled: true
  path: ~/.voice-keyboard/correction_memory.json
  confirm_threshold: 3
  observe_window_seconds: 30
  clipboard_probe_fallback: false
  screen_ocr_fallback: false
```

Instruction Mode local learning options:

```yaml
instruction_mode:
  learning:
    intent_overrides: true
    intent_overrides_path: ~/.voice-keyboard/intent_overrides.jsonl
    intent_model: false
    intent_model_path: ~/.voice-keyboard/intent_models/current.json
```

Never commit real API keys. Use local config, environment variables, or your organization secret-management system.

## Local Data Files

User data is stored under:

```text
~/.voice-keyboard/
```

Common files:

- `config.yaml`: user-level runtime config.
- `history.jsonl`: local history rows.
- `correction_memory.json`: Dictation Mode confirmed and candidate correction pairs.
- `personal_dictionary.json`: provider hint terms and phrases.
- `memo.json`: local memo snippets.
- `intent_samples.jsonl`: optional intent diagnostic samples.
- `intent_overrides.jsonl`: local corrected-intent overrides.
- `intent_models/current.json`: optional trained local intent model.

## Windows Packaging

Windows packaging files live in [packaging/windows](packaging/windows).

Build:

```bat
build_windows_app.bat
```

Output:

```text
dist/VoiceKeyboard/VoiceKeyboard.exe
```

Unsigned PyInstaller executables are often blocked by enterprise security software. For formal distribution, use code signing and an enterprise allowlist process.

## Training Server

Install server dependencies:

```powershell
pip install -r requirements-server.txt
```

Run:

```powershell
$env:INTENT_TRAINING_DATABASE_URL = "sqlite:///./intent_training.db"
$env:INTENT_TRAINING_UPLOAD_TOKEN = "change-me"
uvicorn training_server.api:app --host 0.0.0.0 --port 8000
```

Upload samples:

```powershell
python tools/upload_intent_samples.py --server http://SERVER:8000 --token change-me --source laptop-a
python tools/upload_intent_samples.py --dry-run
```

## Development And Verification

Fast checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test
.\.venv\Scripts\python.exe -m compileall -q agent training_server tools test
git diff --check
```

Focused Windows checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test -p test_windows_status_window.py
.\.venv\Scripts\python.exe -m unittest discover -s test -p test_windows_tray.py
.\.venv\Scripts\python.exe -m unittest discover -s test -p test_windows_main_window.py
```

Some typing, global hotkey, tray, and OS-permission behavior requires a real desktop session and cannot be fully covered by automated tests.

## Documentation Map

- [CONTEXT.md](CONTEXT.md): domain glossary.
- [docs/adr](docs/adr): architectural decisions.
- [docs/architecture/roadmap.md](docs/architecture/roadmap.md): architecture roadmap.
- [docs/architecture/dictation-correction-memory.md](docs/architecture/dictation-correction-memory.md): correction memory architecture.
- [docs/stage-development-plan.md](docs/stage-development-plan.md): current development stage.
- [docs/intent-training.md](docs/intent-training.md): local training data loop.
- [docs/intent-training-server.md](docs/intent-training-server.md): server-side sample review loop.
- [packaging/windows/README.md](packaging/windows/README.md): Windows packaging notes.

## License

MIT
