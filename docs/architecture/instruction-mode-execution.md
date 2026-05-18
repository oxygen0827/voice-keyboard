# Instruction Mode Execution

This design expands ADR-0003 into an implementation plan for deepening Instruction Mode.

## Current Friction

`AIHandler` is now narrower, but still owns runtime orchestration responsibilities:

- transcribing Instruction Mode speech
- gathering Explicit Selection and Tracked Segment context
- calling intent classification
- recording history and status/error states
- coordinating temporary feedback cleanup

`InstructionModeExecutor` owns Voice Text Operation execution. The remaining friction is deciding which feedback and orchestration policy belongs with runtime handling and which belongs with Voice Text Operation execution.

## Target Modules

Instruction Mode execution now lives across a small module set:

```text
agent/voice_text_operation.py
agent/instruction_executor.py
agent/operation_history.py
agent/reusable_text_memory.py
```

`agent/operation_history.py` models reversible text effects:

- replacing existing text with new text
- inserting new text
- deleting existing text

The history module should not call `typer`, `TextBuffer`, or providers. It describes what happened and keeps a bounded history. Execution now lives in `InstructionModeExecutor`; `AIHandler` remains the runtime orchestrator for transcription, context gathering, classification, status, and feedback cleanup.

## Migration Slices

1. Done: add `OperationEffect` and `OperationHistory`.
2. Done: replace `_undo_stack` tuples in `AIHandler` with `OperationHistory`.
3. Done: keep a compatibility `_undo_stack` view during migration.
4. Done: move Operation Reversal logic to consume `OperationEffect`.
5. Done: convert classifier dictionaries into typed Voice Text Operation objects.
6. Done: move Voice Text Operation execution into `InstructionModeExecutor`.
7. Done: move Memory Operation rules into `ReusableTextMemory`.
8. Next: reduce `AIHandler` to runtime orchestration by moving any remaining Instruction Mode execution branching and feedback policy that belongs with Voice Text Operation handling into the executor.

## Test Surface

- History keeps at most the configured limit.
- Text Revision records old and new text.
- Text Generation records inserted text.
- Text Removal records deleted text.
- Operation Reversal consumes the latest effect first.
