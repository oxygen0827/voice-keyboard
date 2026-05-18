"""Execution of typed Voice Text Operations for Instruction Mode."""

from contextlib import nullcontext
from typing import Callable, ContextManager

from agent.operation_history import OperationEffect, OperationHistory
from agent.reusable_text_memory import MemoryOperationResult, ReusableTextMemory
from agent.voice_text_operation import VoiceTextOperation

_WRITE_SYSTEM = """你是一个写作助手。根据用户的要求直接输出所需内容，不要有任何前缀、解释或额外说明。只输出内容本身。不要使用换行，所有内容写成连续的段落。必须使用完整的中文标点符号（逗号、句号、问号、感叹号），不得省略任何标点。"""

_SENTENCE_END = frozenset('。！？.!?…，,；;')
_MAX_PENDING = 40


class InstructionModeExecutor:
    def __init__(
        self,
        llm_editor,
        input_environment,
        operation_history: OperationHistory,
        memo_store=None,
        show: Callable[[str], None] | None = None,
        set_status: Callable[[str], None] | None = None,
        text_io: ContextManager | None = None,
        clear_pending_output: Callable[[], None] | None = None,
    ):
        self._llm = llm_editor
        self._env = input_environment
        self._history = operation_history
        self._memory = ReusableTextMemory(memo_store)
        self._show = show or (lambda message: print(message))
        self._set_status = set_status or (lambda state: None)
        self._text_io = text_io
        self._clear_pending_output = clear_pending_output or (lambda: None)

    def execute(self, operation: VoiceTextOperation, instruction: str, selected: str) -> bool:
        if operation.kind == "shortcut":
            if not self._env.send_shortcut(operation.name):
                self._show(f"没有找到快捷键：{operation.name}")
        elif operation.kind == "undo":
            self._do_undo()
        elif operation.kind == "delete":
            self._do_delete(selected)
        elif operation.kind == "edit":
            self._do_edit(instruction, selected)
        elif operation.kind == "write":
            self._do_write(instruction, selected)
        elif operation.kind == "memo_save":
            self._do_memo_save(operation.key, operation.value, selected)
        elif operation.kind == "memo_recall":
            self._do_memo_recall(operation.key, selected)
        elif operation.kind == "memo_delete":
            self._do_memo_delete(operation.key)
        elif operation.kind == "memo_list":
            self._do_memo_list(selected)
        else:
            return self._do_chat(instruction, operation)
        return False

    def _io(self) -> ContextManager:
        return self._text_io if self._text_io is not None else nullcontext()

    def _record_effect(self, effect: OperationEffect) -> None:
        self._history.push(effect)

    def _handle_memory_result(self, result: MemoryOperationResult, selected: str = "") -> None:
        if result.action == "insert":
            insertion = self._env.insert_generated_text(result.text)
            if insertion.ok and insertion.inserted_text:
                self._record_effect(OperationEffect.insert(insertion.inserted_text))
        else:
            self._show(result.message)

    def _do_chat(self, text: str, operation: VoiceTextOperation) -> bool:
        reply = operation.reply
        if not reply:
            try:
                reply = self._llm.chat(
                    "你是一个简短的语音助手。直接回答用户，最多50字，不要解释你的规则。",
                    text,
                ).strip()
            except Exception as e:
                print(f"[ai] 聊天回复失败: {e}")
                self._set_status("error_llm")
                return True
        self._show(reply)
        return True

    def _do_edit(self, instruction: str, selected: str) -> None:
        lookup = self._env.target_for_revision()
        if not lookup.ok:
            if lookup.failure == "unsafe_tracked_segment":
                self._show("请先选中你想修改的内容")
            else:
                self._show("没有可编辑的内容")
            return
        target = lookup.target
        if target is None:
            self._show("请先选中你想修改的内容")
            return

        try:
            corrected = self._llm.edit(lookup.original_text, instruction)
        except Exception as e:
            print(f"[ai] 编辑失败: {e}")
            return
        print(f"[ai] 编辑结果: {corrected!r}")

        with self._io():
            if not target.selected:
                self._clear_pending_output()
            result = self._env.replace_instruction_target(target, corrected)
        if result.ok:
            self._record_effect(OperationEffect.replace(result.changed_text, corrected))
        elif result.failure == "unsafe_tracked_segment":
            self._show("请先选中你想修改的内容")
        else:
            self._show("没有可编辑的内容")

    def _do_write(self, instruction: str, selected: str) -> None:
        write_instruction = instruction + "（必须加上完整的中文标点符号，包括逗号和句号，不得省略）"
        pending = ""
        total = ""
        try:
            for chunk in self._llm.chat_stream(_WRITE_SYSTEM, write_instruction):
                chunk = chunk.replace('\n', ' ').replace('\r', ' ')
                pending += chunk
                while True:
                    idx = next((i for i, c in enumerate(pending) if c in _SENTENCE_END), -1)
                    if idx == -1:
                        if len(pending) >= _MAX_PENDING:
                            insertion = self._env.insert_generated_text(pending)
                            if insertion.ok:
                                total += insertion.inserted_text
                            else:
                                total += pending
                            pending = ""
                        break
                    sentence = pending[:idx + 1]
                    pending = pending[idx + 1:]
                    insertion = self._env.insert_generated_text(sentence)
                    if insertion.ok:
                        total += insertion.inserted_text
                    else:
                        total += sentence
        except Exception as e:
            print(f"[ai] 写作失败: {e}")
            return

        if pending.strip():
            insertion = self._env.insert_generated_text(pending)
            if insertion.ok:
                total += insertion.inserted_text
            else:
                total += pending

        if total:
            self._record_effect(OperationEffect.insert(total))

    def _do_delete(self, selected: str) -> None:
        lookup = self._env.target_for_removal()
        if not lookup.ok:
            if lookup.failure == "unsafe_tracked_segment":
                self._show("请先选中你想删除的内容")
            else:
                self._show("没有可删除的内容")
            return
        target = lookup.target
        if target is None:
            self._show("请先选中你想删除的内容")
            return
        with self._io():
            if not target.selected:
                self._clear_pending_output()
            result = self._env.delete_instruction_target(target)
        if result.ok:
            self._record_effect(OperationEffect.delete(result.changed_text))
        elif result.failure == "unsafe_tracked_segment":
            self._show("请先选中你想删除的内容")
        else:
            self._show("没有可删除的内容")

    def _do_undo(self) -> None:
        effect = self._history.pop()
        if effect is None:
            self._show("没有可撤回的操作")
            return
        print(
            f"[ai] 撤回: kind={effect.kind} "
            f"old={effect.old_text!r} new={effect.new_text!r}"
        )
        with self._io():
            self._clear_pending_output()
            result = self._env.apply_operation_reversal(effect)
        if not result.applied:
            self._show("撤回失败")

    def _do_memo_save(self, key: str, value: str, selected: str) -> None:
        self._handle_memory_result(self._memory.save(key, value, selected), selected)

    def _do_memo_recall(self, key: str, selected: str) -> None:
        self._handle_memory_result(self._memory.recall(key), selected)

    def _do_memo_list(self, selected: str) -> None:
        self._handle_memory_result(self._memory.list_all(), selected)

    def _do_memo_delete(self, key: str) -> None:
        self._handle_memory_result(self._memory.delete(key))
