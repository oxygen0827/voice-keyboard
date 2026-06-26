# Voice Keyboard Marketing Brief

This document is raw material for marketing, product positioning, landing pages, demos, and outreach. It should stay aligned with the current repository: this repo owns the local Voice Keyboard Engine, not account, payment, subscription, entitlement, or provider billing flows.

## One-Line Positioning

Voice Keyboard turns speech into typing, editing, shortcuts, and recall in the input field you are already using.

## Short Product Description

Voice Keyboard Engine is a local desktop layer between the user and the current input environment. The user speaks; the engine inserts text, revises existing text, invokes named shortcuts, recalls saved snippets, or performs local window/application actions.

The important shift is that voice is not limited to one app. The same engine can work in chat apps, editors, browsers, documents, internal tools, terminals, and ordinary text fields because it acts at the desktop input layer.

## Core Message

Most voice tools stop at transcription. Voice Keyboard goes further:

- Dictate directly into the focused input field.
- Ask for text changes without manually selecting every character when the engine has a safe target.
- Invoke common local shortcuts by name.
- Recall saved snippets by voice.
- Keep the workflow local-first and keyboard-oriented rather than chat-first.

## Current Product Reality

The current repository is strongest on the Windows desktop runtime:

- System tray app with safe standby by default.
- Main window for configuration, history, diagnostics, personal dictionary, memo library, hotkeys, and runtime checks.
- Compact capsule HUD for state feedback.
- Dictation Mode for speech-to-text insertion.
- Instruction Mode for voice-driven operations.
- Personal dictionary and memo features.
- Intent diagnostics and training-data loop infrastructure.
- Windows packaging through PyInstaller onedir.

macOS, Linux, and headless CLI entry points remain present, but the current product focus is Windows desktop validation.

## Audience

| Audience | Need | Voice Keyboard Value |
| --- | --- | --- |
| Writers and knowledge workers | Capture thoughts faster than typing | Speak into the current editor without switching tools |
| Support and operations teams | Reply quickly with repeated phrases | Memo recall and voice-driven insertion |
| Developers | Reduce friction around notes, comments, docs, and local commands | Dictation plus named shortcut/application operations |
| Users with typing strain | Reduce keyboard load | Voice replaces repeated text entry and common shortcuts |
| Older or slower typists | Lower the barrier to writing | Speak naturally and insert text into existing apps |

## Demo Flow

1. Launch the Windows tray app.
2. Show that the app starts in safe standby.
3. Enable Voice Keyboard from the tray menu.
4. Hold the Dictation hotkey and dictate into Notepad or a browser text box.
5. Hold the Instruction hotkey and say a simple revision such as "make this more polite" or "delete the last sentence".
6. Recall a memo by voice.
7. Open the main window and show history, memo, dictionary, and hotkey tabs.
8. Show the small capsule HUD during recognition and feedback.

## Differentiators

### Works At The Input Layer

The engine targets the current input environment rather than one special editor. This makes the same workflow available across ordinary desktop software.

### Voice Keyboard Operations, Not Chat

The product is not a chat assistant. It turns speech into keyboard-style operations: insert, revise, remove, recall, invoke a shortcut, launch an app, or move a window.

### Safe Local Control

The Windows tray starts in safe standby. The backend and global hotkeys are enabled only when the user explicitly turns Voice Keyboard on.

### Personal Vocabulary And Memos

The personal dictionary helps provider adapters favor user-specific names and phrases. The memo library stores short snippets for later insertion.

### Training Loop For Real Usage

Intent diagnostics and sample collection make it possible to improve local rules and future lightweight classifiers from reviewed real-world data instead of guessing.

## Suggested Copy

### Headlines

1. "Voice Keyboard: speak into any input field."
2. "Dictation, editing, shortcuts, and snippets by voice."
3. "A local voice layer for everyday desktop work."
4. "Less typing. More flow."

### Short Blurbs

- "Hold a hotkey, speak, and the text appears where your cursor already is."
- "Use voice for more than transcription: revise text, recall snippets, and trigger common shortcuts."
- "Voice Keyboard starts safely, stays local-first, and only acts when you enable it."
- "Your personal dictionary and memos make repeated work faster over time."

## Current Capability Matrix

| Capability | Current Status |
| --- | --- |
| Windows tray runtime | Implemented |
| Safe standby | Implemented |
| Windows main window | Implemented |
| Capsule HUD | Implemented |
| Dictation Mode | Implemented |
| Instruction Mode | Implemented and evolving |
| Personal dictionary | Implemented |
| Memo library | Implemented |
| Local shortcut catalog | Implemented and evolving |
| Application/window operations | Implemented through platform adapters where available |
| Intent diagnostics | Implemented |
| Intent training server | Implemented for development and small deployments |
| Local trained intent model | Future work |
| Signed Windows installer | Future distribution work |
| Hardware Capture Path | Product direction and partial repo support; not the main current desktop validation path |

## Technical Talking Points

- Python desktop runtime.
- Windows tray app with `pystray`.
- Tkinter main window.
- Win32 status HUD and window operations.
- Speech Interpretation Provider adapters for STT and LLM flows.
- Input Environment seam for text insertion, replacement, and deletion.
- Local risk policy for high-risk operations.
- Intent sample collection and FastAPI training server.
- PyInstaller onedir packaging for Windows.

## Messaging Guardrails

- Do not present the product as a general chat assistant.
- Do not imply account, billing, subscription, or entitlement handling lives in this repository.
- Do not promise that every desktop app behaves identically; some apps require clipboard insertion.
- Do not present a trained local intent model as production-ready until reviewed data and evaluation support it.
- Treat hardware-mode stories as product direction unless the specific hardware flow is being demonstrated.

## Roadmap Narrative

Near-term work should emphasize reliability and trust:

1. Stabilize Windows runtime and HUD.
2. Improve Input Environment targeting.
3. Expand local shortcut catalogs and safe operation policy.
4. Complete the review workflow for intent samples.
5. Mine real reviewed samples for local rule improvements.
6. Train and evaluate a lightweight local classifier only after enough reviewed data exists.
7. Prepare signed Windows distribution for enterprise environments.

## Project Facts

| Item | Value |
| --- | --- |
| Repository | `wangqioo/voice-keyboard` |
| License | MIT |
| Main language | Python |
| Primary current platform | Windows desktop |
| Main Windows entry point | `python -m agent.windows.tray` |
| Headless entry point | `python -m agent.cli` |
| Packaging | PyInstaller onedir |
| User config | `~/.voice-keyboard/config.yaml` |
