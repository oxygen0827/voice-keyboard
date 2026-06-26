# Focus checks and correction memory boundaries

The Voice Keyboard Engine should not pretend it can reliably detect every missing focused input field through generic text injection alone. The current Input Environment can insert text, read an Explicit Selection, and discover platform-supported current text windows, but reliable focus detection is platform-specific and often application-specific. A future "ask whether to paste" behavior must be implemented behind the Input Environment seam using platform accessibility APIs or desktop host cooperation, and should report best-effort confidence rather than a universal guarantee.

The Voice Keyboard Engine should also keep Dictation Correction Memory separate from Memo. Memo stores short user-provided snippets for later insertion into the Input Environment. Dictation Correction Memory is a different rule set: it stores local wrong-to-correct pairs learned from repeated manual fixes after Dictation insertion.

Current implementation:

- `agent/correction_memory.py` owns persistence, inference, candidates, promotion, and observation scheduling.
- `agent/dictation_mode.py` applies the confirmed Correction Dictionary before insertion and remembers inserted Dictation text for learning.
- `agent/runtime_composition.py` wires correction tracking to PushToTalk key events and macOS IME committed-text events.
- `agent/input_environment.py`, `agent/text_io.py`, `agent/typer.py`, and `agent/screen_ocr_capture.py` provide focused-text and OCR snapshots behind the Input Environment/TextIO seams.
- `agent/ui/main_window.py` exposes a `词典` tab for confirmed entries and candidates.

Future hotword or provider-prompt behavior should still stay separate from Memo and should not let a Speech Interpretation Provider bypass local application of the confirmed Correction Dictionary.
