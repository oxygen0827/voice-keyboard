"""Compatibility entry point for the Windows tray app.

Prefer ``python -m agent.windows.tray`` for new Windows packaging and scripts.
"""

from agent.windows.tray import WindowsTrayApp, main

__all__ = ["WindowsTrayApp", "main"]


if __name__ == "__main__":
    main()
