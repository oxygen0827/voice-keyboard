"""Built-in Application Shortcut Catalog presets.

Voice Keyboard Engine keeps built-in Shortcut Invocation generic by default.
Application-specific shortcuts should be configured locally through
``typing.application_shortcuts`` once they are validated for that user's
Input Environment.
"""

MACOS_APP_SHORTCUT_PRESETS: dict[str, dict[str, str | list[str]]] = {}
