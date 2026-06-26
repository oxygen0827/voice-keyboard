# Voice Keyboard Stage Development Plan

Updated: 2026-06-25

This document summarizes the current development stage of Voice Keyboard Engine, the usable runtime surfaces, and the next implementation priorities. Domain language comes from [CONTEXT.md](../CONTEXT.md).

## Current Stage Summary

The current repository has a usable Windows desktop runtime and a growing local engine architecture behind it.

The Windows client now covers the main local workflow:

- Safe-standby tray runtime.
- Main window for status, history, intent diagnostics, personal dictionary, memo library, hotkeys, config, and checks.
- Compact capsule HUD for feedback.
- Dictation Mode and micro-polish.
- Instruction Mode for text operations and keyboard-style operations.
- Local shortcut catalog and application/window operation seams.
- Personal dictionary hints for provider adapters.
- Memo operations.
- Intent diagnostics, local learning hooks, and sample collection.

The intent training loop infrastructure exists, but a production local model is not the current source of truth. The useful loop is still:

1. Collect sanitized real usage samples.
2. Upload/export samples.
3. Review and label samples.
4. Mine rules and aliases.
5. Train/evaluate a lightweight classifier only after enough reviewed samples exist.
6. Feed improvements back into the client behind local safety policy.

## Completed Capabilities

### Windows Client

- Tray entry point: `python -m agent.windows.tray`.
- `agent.main` and `agent.main --no-serial` route into the safe-standby tray experience on Windows.
- Manual enable/disable of the backend from the tray menu.
- Chinese/English tray labels.
- Runtime config reload.
- Dictation and Instruction hotkey configuration.
- History and memo insertion while the backend is enabled.
- Start-on-login registration and removal.
- Capsule HUD feedback with no drawn outer border and an antialiased state dot.
- Main window tabs for overview, history, intent diagnostics, dictionary, memo, hotkeys, config, and runtime checks.

### Dictation Mode

- Software Capture Path through the computer microphone.
- Push-to-talk utterance capture.
- Raw Dictation Mode.
- Micro-polish flow.
- Text insertion through the current input environment.
- Clipboard insertion fallback for applications that reject Unicode key injection.

### Instruction Mode

- Local deterministic handling before provider fallback where possible.
- Structured operation execution seam for text-side effects.
- Text revision and removal through replacement plans.
- Memo save, recall, delete, and list.
- Shortcut invocation from local catalogs.
- Application launch and system window action seams.
- Local high-risk operation policy.
- Action card/feedback hooks for operation confirmation and feedback.

### Data And Learning

- Intent diagnostics for later analysis.
- Local intent sample collection.
- Local learning and override modules under active development.
- Personal dictionary file and UI.
- Correction memory and observation modules under active development.
- Training server for upload, listing, review labels, and stats.

### Training Server

- FastAPI API.
- SQLite storage for development and small deployments.
- Token-protected JSONL batch ingestion.
- Sample listing and filtering.
- Review label updates.
- Basic stats.
- Client upload CLI.
- Review page module under development.

## Current Runtime Commands

Windows tray:

```powershell
.\.venv\Scripts\python.exe -u -m agent.windows.tray
```

Windows desktop runtime:

```powershell
.\.venv\Scripts\python.exe -m agent.main --no-serial
```

Headless backend debugging:

```powershell
.\.venv\Scripts\python.exe -u -m agent.main --no-serial --no-ui --headless --enable-backend
```

Headless dictation CLI:

```powershell
.\.venv\Scripts\python.exe -m agent.cli --once --seconds 5
```

Training server:

```powershell
$env:INTENT_TRAINING_DATABASE_URL = "sqlite:///./intent_training.db"
$env:INTENT_TRAINING_UPLOAD_TOKEN = "change-me"
uvicorn training_server.api:app --host 0.0.0.0 --port 8000
```

## Verification

Routine fast checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test
.\.venv\Scripts\python.exe -m compileall -q agent training_server tools test
```

Focused Windows checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test -p test_windows_status_window.py
.\.venv\Scripts\python.exe -m unittest discover -s test -p test_windows_tray.py
.\.venv\Scripts\python.exe -m unittest discover -s test -p test_windows_main_window.py
```

Some global hotkey, typing, tray, and desktop-permission behavior still requires manual verification in a real desktop session.

## Priorities

### P0: Stabilize Windows Runtime

- Keep tray safe standby reliable.
- Keep backend lifecycle idempotent when enabling, disabling, reloading config, or quitting.
- Keep HUD feedback visually clean and non-intrusive.
- Continue testing history, memo, dictionary, hotkey, and config tabs.
- Avoid requiring unsigned exe usage on enterprise machines during development.

### P1: Harden Input Environment Behavior

- Broaden focused text capture where platform adapters allow it.
- Preserve the rule that Explicit Selection takes precedence.
- Preserve fail-closed behavior for local partial removal when no safe target exists.
- Keep platform text IO behind adapters so headless use stays clean.

### P2: Improve Instruction Mode Reliability

- Continue moving behavior from raw classifier dictionaries into structured operation objects.
- Keep local shortcut names catalog-driven.
- Keep Speech Interpretation Providers from inventing arbitrary key sequences.
- Expand high-risk confirmation coverage for submit, send, broad delete, cross-application, and hard-to-reverse operations.

### P3: Complete Review And Training Loop

- Finish the review page workflow.
- Add export/evaluation scripts where useful.
- Use reviewed samples to improve local rules and aliases first.
- Train a lightweight local classifier only after reviewed samples are large enough to evaluate honestly.
- Keep model outputs behind local risk policy.

### P4: Packaging And Distribution

- Continue source-first development for enterprise-restricted machines.
- Use PyInstaller onedir packaging for Windows.
- Add code signing and allowlist workflow for formal enterprise distribution.
- Keep package docs current with runtime entry points and security behavior.

## Key Risks

### Enterprise Security

Unsigned background tray apps with hotkey and input APIs are often blocked. This is expected for PyInstaller development builds. Formal distribution should use code signing and enterprise allowlisting.

### API Key Safety

Real provider credentials must not be committed. Use local config, environment variables, or organization secret management.

### Sample Quality

Training data without review labels is weak. The most valuable next step is reviewed real usage samples, not immediate model complexity.

### High-Risk Operations

Faster local interpretation must not bypass safety policy. Send, submit, delete, broad overwrite, close-window, and cross-application actions need confirmation or conservative handling.

## Recommended Next Order

1. Keep Windows runtime and HUD stable.
2. Finish review page and label workflow.
3. Expand sample export and evaluation tooling.
4. Mine reviewed samples for local aliases and missing shortcut catalog entries.
5. Train and evaluate a first lightweight local intent classifier.
6. Connect the classifier as an optional local layer behind risk policy.
7. Prepare signed Windows distribution only after runtime behavior is stable.
