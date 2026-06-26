# Windows Packaging

The current Windows build is a tray-resident Voice Keyboard Engine runtime. The packaged entry point is `agent.windows.tray`, built with PyInstaller onedir mode:

```
dist/VoiceKeyboard/VoiceKeyboard.exe
```

After launch, the app shows a Voice Keyboard tray icon and starts in safe standby. In standby it does not register Dictation/Instruction global hotkeys, send keyboard input, or allow history/memo insertion into the current input environment. Use the tray menu to enable Voice Keyboard before the backend starts.

The tray menu provides:

- Open main window
- Enable or disable Voice Keyboard
- Switch Chinese or English labels
- Configure Dictation and Instruction hotkeys
- View recent history and memo snippets
- Reload config
- Register or remove start-on-login
- Quit

The Windows status HUD is rendered by `agent.windows.status_window`: it is a compact capsule overlay with no drawn outer border, a filled dark background, and an antialiased state dot.

## Build

Run from the repository root:

```bat
build_windows_app.bat
```

Or manually:

```bat
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\pyinstaller.exe --clean --noconfirm packaging\windows\voice-keyboard-tray.spec
```

## Run

```bat
dist\VoiceKeyboard\VoiceKeyboard.exe
```

User config remains at:

```text
%USERPROFILE%\.voice-keyboard\config.yaml
```

## Notes

- Python 3.13+ is supported by compatibility shims for several Win32 handle aliases removed from `ctypes.wintypes`.
- WeChat, DingTalk, and some Electron apps may reject Unicode key injection; use `typing.method: clip` when needed.
- Correction dictionary learning on Windows observes manual edits through read-only UI Automation text snapshots, with a read-only `WM_GETTEXT` fallback for classic controls.
- The correction observation listener is passive: it does not suppress keys, send replacement keys, paste text, or modify the clipboard while watching for manual edits.
- On some Chinese or international keyboard layouts, right Alt behaves as AltGr and may not be reliable as a global hotkey.
- `python -m agent.main`, `python -m agent.main --no-serial`, and `python -m agent.windows.tray` enter the same safe-standby tray runtime.
- `--no-ui --headless --no-serial --enable-backend` is a debugging entry point that starts the backend directly.

## Enterprise Security Software

Unsigned PyInstaller tray apps are commonly blocked by enterprise security software. Typical reasons:

- The exe is unsigned.
- The app runs in the background.
- After Voice Keyboard is enabled, the backend uses global hotkey listeners.
- After Voice Keyboard is enabled, the backend uses input-related Win32 APIs.
- PyInstaller artifact patterns can trigger static rules.

This does not mean the program is malicious; it means the behavior profile can match security rules. For enterprise computers:

1. Prefer source + virtual environment during development:

   ```bat
   start_tray_windows.bat
   ```

2. If an exe is required, submit this file and its SHA256 to IT for allowlisting:

   ```text
   dist\VoiceKeyboard\VoiceKeyboard.exe
   ```

3. For formal distribution, sign the exe with an organization code-signing certificate before allowlisting.

Generate SHA256:

```powershell
Get-FileHash -Algorithm SHA256 dist\VoiceKeyboard\VoiceKeyboard.exe
```
