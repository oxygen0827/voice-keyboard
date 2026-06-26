# Voice Keyboard Engine Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the next development-plan hardening slice for guarded model activation, Memo metadata, and local high-risk operation policy.

**Architecture:** Keep existing public interfaces compatible while deepening the current modules. The one-command training loop gets guarded activation; Memo Store becomes record-aware while preserving `save/get/delete/keys`; high-risk shortcut execution gets a small local policy and executor-level confirmation orchestration.

**Tech Stack:** Python 3, unittest, JSON files, existing Voice Keyboard Engine modules.

---

## File Structure

- `agent/intent_model.py`: add non-activating model registration support while keeping default activation behavior.
- `agent/intent_loop.py`: train/evaluate candidate model and activate only when guard passes.
- `tools/run_intent_training_loop.py`: update help text and non-JSON summary output.
- `test/test_intent_model.py`: cover non-activating registration.
- `test/test_intent_loop.py`: cover safe activation and regression blocking.
- `agent/memo_store.py`: support canonical record JSON and expose `records()`.
- `agent/memo.py`: extend `MemoRecord` metadata and prefer explicit value type/sensitivity.
- `agent/ai_intent.py`: use store records when available for memo resolution.
- `test/test_memo_store.py`: cover flat compatibility, record shape, metadata preservation.
- `test/test_memo.py`: cover resolver behavior with explicit metadata.
- `agent/local_operation_policy.py`: new policy module for allow/confirm/block decisions.
- `agent/instruction_executor.py`: inject confirmation callback and apply policy before high-risk shortcut execution.
- `agent/intent_training.py`: record explicit risk/confirmation sample fields.
- `agent/ai_handler.py`: pass executor confirmation metadata into training recorder.
- `test/test_local_operation_policy.py`: new focused tests for risk policy.
- `test/test_instruction_executor.py`: cover high-risk confirm/cancel execution behavior.
- `test/test_intent_training.py`: cover sample schema fields.

## Task 1: Guard Intent Model Activation

**Files:**
- Modify: `agent/intent_model.py`
- Modify: `agent/intent_loop.py`
- Modify: `tools/run_intent_training_loop.py`
- Test: `test/test_intent_model.py`
- Test: `test/test_intent_loop.py`

- [ ] **Step 1: Write failing tests for non-activating model registration**

Add tests that prove `train_intent_model(..., registry_dir=..., activate=False)` writes the version file but leaves `current.json` unchanged.

Run:

```bash
python3 -m unittest test.test_intent_model -v
```

Expected before implementation: failure because `activate` is not accepted.

- [ ] **Step 2: Implement optional activation control**

In `agent/intent_model.py`, add `activate: bool = True` to `train_intent_model`. When `registry_dir` is supplied, keep registering `versions/<version>.json`; call `activate_intent_model_version()` only when `activate` is true. Preserve all existing return fields and add fields only if useful, such as `activated`.

- [ ] **Step 3: Write failing loop regression guard test**

Add a test in `test/test_intent_loop.py` that starts with an existing `registry/current.json` version and then runs `run_training_loop()` with a candidate that regresses. Assert:

- `report["model_activation"]["should_activate"] is False`
- `report["model_activation"]["reason"] == "candidate_regressed"`
- `registry/current.json` still loads as the previous version
- `registry/versions/<candidate>.json` exists

- [ ] **Step 4: Implement guarded candidate flow**

In `agent/intent_loop.py`, when `model_registry_dir` is set:

- train with `activate=False`
- evaluate using the candidate version path
- compute `_model_activation_decision`
- activate only when `should_activate`
- report whether activation happened and which model path was evaluated

- [ ] **Step 5: Update CLI text output**

In `tools/run_intent_training_loop.py`, change help text from “trains and activates” to “trains, evaluates, and activates only if safe”. Include activation reason in non-JSON output.

- [ ] **Step 6: Verify focused tests**

Run:

```bash
python3 -m unittest discover -s test -p 'test_intent_model.py' -v
python3 -m unittest discover -s test -p 'test_intent_loop.py' -v
```

Expected: all pass.

## Task 2: Add Memo Store Metadata Records

**Files:**
- Modify: `agent/memo.py`
- Modify: `agent/memo_store.py`
- Modify: `agent/ai_intent.py`
- Test: `test/test_memo_store.py`
- Test: `test/test_memo.py`
- Optional Test: focused `test/test_ai_intent.py` memo record bridge case

- [ ] **Step 1: Write failing store compatibility tests**

Add tests for:

- reading flat JSON shape
- reading record JSON shape
- `get()` returning only the value for record shape
- `records()` returning `MemoRecord` with aliases/value_type/sensitive
- saving existing records preserving aliases and explicit metadata
- saving new memos writing canonical record shape

Run:

```bash
python3 -m unittest discover -s test -p 'test_memo_store.py' -v
```

Expected before implementation: failures for record shape and `records()`.

- [ ] **Step 2: Implement canonical Memo Store records**

Change `agent/memo_store.py` internals to load flat values and record objects into one normalized representation. Keep `save/get/delete/keys` compatible. Add `records()` returning `tuple[MemoRecord, ...]`. Write canonical record JSON on save.

- [ ] **Step 3: Extend MemoRecord metadata usage**

In `agent/memo.py`, extend `MemoRecord` with `value_type: str = ""` and `sensitive: bool | None = None`. In `MemoResolver._score_record`, prefer `record.value_type` before detecting from key/value.

- [ ] **Step 4: Bridge ai_intent to record-aware stores**

In `agent/ai_intent.py`, update memo record creation so stores with `records()` are used directly. Fall back to existing `keys()/get()` behavior for compatibility.

- [ ] **Step 5: Verify focused tests**

Run:

```bash
python3 -m unittest discover -s test -p 'test_memo_store.py' -v
python3 -m unittest discover -s test -p 'test_memo.py' -v
python3 -m unittest discover -s test -p 'test_ai_intent.py' -v
```

Expected: all pass.

## Task 3: Add Local High-Risk Operation Policy

**Files:**
- Create: `agent/local_operation_policy.py`
- Modify: `agent/instruction_executor.py`
- Modify: `agent/intent_training.py`
- Modify: `agent/ai_handler.py`
- Test: `test/test_local_operation_policy.py`
- Test: `test/test_instruction_executor.py`
- Test: `test/test_intent_training.py`

- [ ] **Step 1: Write policy tests**

Create `test/test_local_operation_policy.py` covering:

- normal shortcut is allowed without confirmation
- single high-risk shortcut requires confirmation
- high-risk shortcut inside atomic stack is blocked
- missing shortcut is blocked

Run:

```bash
python3 -m unittest discover -s test -p 'test_local_operation_policy.py' -v
```

Expected before implementation: import failure.

- [ ] **Step 2: Implement policy module**

Create `agent/local_operation_policy.py` with a dataclass result such as:

```python
LocalOperationPolicyDecision(
    name: str,
    found: bool,
    allowed: bool,
    requires_confirmation: bool = False,
    risk: str = "normal",
    reason: str = "",
)
```

Provide a function that accepts the existing shortcut policy decision plus `in_atomic_stack`.

- [ ] **Step 3: Write executor confirm/cancel tests**

In `test/test_instruction_executor.py`, add fakes proving:

- high-risk confirm callback returning true calls `send_shortcut`
- high-risk confirm callback returning false does not call `send_shortcut`
- `last_status` records confirm/cancel detail

- [ ] **Step 4: Wire executor confirmation**

In `InstructionModeExecutor.__init__`, accept `confirm_operation: Callable[[str, str], bool] | None = None`. Default should be conservative for high-risk operations when no UI confirmation exists. Apply local policy before `send_shortcut`.

- [ ] **Step 5: Record confirmation fields in training samples**

Extend `IntentTrainingRecorder.record()` to accept optional `operation_risk`, `confirmation_triggered`, and `user_cancelled`. Include these fields only when not `None`. Update `AIHandler` to pass structured metadata from the executor after Instruction Mode runs.

- [ ] **Step 6: Verify focused tests**

Run:

```bash
python3 -m unittest discover -s test -p 'test_local_operation_policy.py' -v
python3 -m unittest discover -s test -p 'test_instruction_executor.py' -v
python3 -m unittest discover -s test -p 'test_intent_training.py' -v
```

Expected: all pass.

## Integration Verification

- [ ] Run focused suites:

```bash
python3 -m unittest discover -s test -p 'test_intent_model.py' -v
python3 -m unittest discover -s test -p 'test_intent_loop.py' -v
python3 -m unittest discover -s test -p 'test_memo_store.py' -v
python3 -m unittest discover -s test -p 'test_memo.py' -v
python3 -m unittest discover -s test -p 'test_ai_intent.py' -v
python3 -m unittest discover -s test -p 'test_local_operation_policy.py' -v
python3 -m unittest discover -s test -p 'test_instruction_executor.py' -v
python3 -m unittest discover -s test -p 'test_intent_training.py' -v
```

- [ ] Run compile check:

```bash
python3 -m compileall -q agent training_server tools test
```

- [ ] Check diff:

```bash
git diff --check
git status --short
```

## Self-Review Notes

This plan intentionally skips editable Memo aliases in the UI and full Atomic Operation Stack. Those are separate product/UI changes. This wave only adds the core data and policy surfaces needed by the existing development plan.
