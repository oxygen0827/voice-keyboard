# Local shortcut catalog

Shortcut Invocation should target a named action from a local Shortcut Catalog. A Speech Interpretation Provider may choose among named shortcut actions that the engine provides in context, but it must not invent shortcut actions, key sequences, or app-specific macros.

In this context, "shortcut" means a low-conflict keyboard-style action for ordinary repeated work. The goal is to remove the common redundant keyboard operations that most users repeat every day, not to expose an exhaustive power-user automation or macro system.

The catalog may be composed from a Global Shortcut Catalog and an Application Shortcut Catalog. Global actions cover common system or broadly reusable shortcuts. Application actions cover the current application context and take precedence when names conflict.

Universal editing actions should live in the Global Shortcut Catalog when their key sequence is stable across the target applications. Application presets should not repeat those actions just to name the same key sequence again; they should be reserved for application-specific actions and true overrides.

The built-in catalog should stay curated and narrow. Default application presets cover only the current product slice and only actions that are low-ambiguity, low-conflict, and useful to ordinary users in that context. Broader app shortcuts, exhaustive menu coverage, and uncertain surface-specific actions belong in local config or a later surface-aware adapter, not in the default catalog.

Application launch actions may be broader than application shortcuts because launching an installed app does not depend on the active Input Environment surface. The engine may expose launch actions discovered from local installed applications, plus configured aliases, but a Speech Interpretation Provider still must choose a discovered or configured action instead of inventing an executable app name.

macOS window management actions should be treated as System Actions instead of keyboard shortcut aliases when the engine can execute them through Accessibility. This keeps actions such as left half, right half, maximize, and center independent from application menus and global hotkey collisions.

The local engine keeps shortcut metadata, including source and risk signals. This keeps Shortcut Invocation aligned with voice-driven keyboard efficiency instead of provider-generated automation.
