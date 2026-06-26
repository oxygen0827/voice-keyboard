# Windows Runtime Package

This package contains the Windows-specific desktop surface for Voice Keyboard Engine.

## Entry Points

- `tray.py`: preferred Windows tray runtime.
- `main_window.py`: Tkinter control center.
- `status_window.py`: compact capsule HUD for status feedback.
- `action_card.py`: optional action confirmation/feedback card.
- `window_actions.py`: Win32 window-management operations.

Compatibility wrappers remain at the older module paths:

- `agent.windows_tray`
- `agent.windows_main_window`
- `agent.status_window_win`
- `agent.windows_window_actions`

New Windows code and packaging should import from `agent.windows.*`.

## Runtime Behavior

The tray runtime starts in safe standby. In standby it does not register global Dictation/Instruction hotkeys, send keyboard input, or insert history/memo snippets. The backend starts only after the user enables Voice Keyboard from the tray menu.

The status HUD intentionally stays small and low-friction:

- capsule-shaped overlay
- filled dark background
- no drawn outer border
- antialiased state dot
- localized state/message text

## Platform Boundaries

Windows-specific UI and Win32 APIs live here. macOS-specific UI/runtime files remain outside this package, such as:

- `agent/ui/`
- `agent/status_window.py`
- `packaging/macos/`

Keep headless modules such as `agent.cli` free of Windows tray, Tkinter, pystray, and global-hotkey assumptions.
