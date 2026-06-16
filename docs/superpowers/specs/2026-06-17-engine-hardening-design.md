# Voice Keyboard Engine Hardening Design

## Goal

Harden the current Voice Keyboard Engine according to the existing development plan without expanding product scope. This work improves three areas that are already documented as incomplete: guarded intent model activation, metadata-aware Memo storage, and local high-risk operation policy.

## Scope

The first implementation wave covers:

- Intent model activation guard for the one-command training loop.
- Memo Store record metadata and alias preservation with flat JSON backward compatibility.
- A small local high-risk operation policy module plus executor hooks.

Out of scope for this wave:

- Server-side semantic classifier training.
- Server model publishing and client pull.
- Editable Memo alias UI.
- Full Atomic Operation Stack execution.
- New platform-specific focus detection.

## Architecture

### Intent Model Activation Guard

`train_intent_model()` keeps its current default behavior for direct CLI and UI callers: when a registry is supplied, it registers and activates the model. The one-command training loop becomes stricter. It trains a candidate version without activating it, evaluates the candidate, compares it with the baseline, and activates only when the guard passes. Regressed candidates remain available under `versions/` for inspection, while `current.json` stays unchanged.

### Memo Metadata

`MemoStore` accepts both legacy flat JSON and canonical record JSON. Public `save/get/delete/keys` behavior remains compatible with current UI callers. New record access exposes `MemoRecord` values with `aliases`, `value_type`, and `sensitive` metadata. Saving an existing memo preserves metadata unless the value changes enough that computed metadata should be refreshed. The Windows Memo tab can continue editing only key and value.

### High-Risk Operation Policy

Shortcut catalog risk remains local metadata. A new execution policy module translates catalog decisions into allow, confirm, or block outcomes. `InstructionModeExecutor` owns confirmation orchestration so non-UI paths cannot bypass policy accidentally. The adapter still owns physical shortcut execution. Intent training records explicit `operation_risk`, `confirmation_triggered`, and `user_cancelled` fields when available.

## Testing

Use focused unittest suites:

- `python3 -m unittest discover -s test -p 'test_intent_model.py' -v`
- `python3 -m unittest discover -s test -p 'test_intent_loop.py' -v`
- `python3 -m unittest discover -s test -p 'test_memo_store.py' -v`
- `python3 -m unittest discover -s test -p 'test_memo.py' -v`
- `python3 -m unittest discover -s test -p 'test_local_operation_policy.py' -v`
- `python3 -m unittest discover -s test -p 'test_instruction_executor.py' -v`
- `python3 -m compileall -q agent training_server tools test`

`test_typer_shortcuts.py` currently requires `pynput`; in this local worktree the baseline import fails because `pynput` is not installed in the active Python environment. Avoid depending on that file for the high-risk policy unit tests unless dependencies are installed.

## Risks

The model guard must preserve direct training CLI compatibility. The Memo migration must not corrupt existing flat memo files or destroy metadata after UI saves. The high-risk policy must not put confirmation inside low-level typing adapters, because then the executor and training recorder cannot reliably observe whether confirmation was triggered or cancelled.
