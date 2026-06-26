# Voice Keyboard Repository Guide

This root repository is intentionally split into two platform subprojects:

- `windows/` contains the active Windows Voice Keyboard Engine codebase.
- `macos/` contains the macOS-oriented upstream snapshot.

Work inside the platform folder that matches the task. Read that folder's `AGENTS.md`, `CONTEXT.md`, and docs before changing code.

Do not mix platform-specific runtime code across `windows/` and `macos/` unless the user explicitly asks for a cross-platform consolidation.

Keep root-level files limited to repository coordination, shared ignore rules, and high-level navigation.
