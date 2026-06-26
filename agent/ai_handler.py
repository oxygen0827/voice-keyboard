"""
Instruction Mode orchestration：speech recognition → intent classification → Voice Text Operation execution

意图分类规则：
  shortcut — 明确的快捷键操作，直接执行
  edit     — 修改/润色/编辑 Explicit Selection 或 Tracked Segment
  write    — 给主题/要求让 AI 生成新内容，直接打入，不自动删除
  undo     — 触发当前输入环境的撤销快捷键
  chat     — 其他（问题、聊天、不确定），只在状态框显示简短 feedback
"""

import queue
import threading

from agent.ai_intent import (
    IntentContext,
    IntentFallbackOptions,
    classify_intent_details,
    memo_records,
    shortcut_intent_entries,
)
from agent.ai_command_plan import command_plan_from_operation
from agent.ai_risk_policy import apply_local_risk_policy
from agent.input_environment import TyperInputEnvironment
from agent.instruction_executor import InstructionModeExecutor
from agent.intent_training import IntentTrainingRecorder
from agent.local_learning import (
    LocalLearningRecorder,
    apply_correction_to_text,
    parse_correction_command,
)
from agent.memo import Memo, parse_memo_edit_command
from agent.voice_text_operation import operation_from_intent

_AI_PREFIX = " [AI]: "
_INTENT_TIMEOUT_SECONDS = 12.0
_PROGRESS_SECONDS = 2.2


class AIHandler:
    def __init__(self, stt_client, llm_editor, buf, memo_store=None,
                 status_window=None, history=None, input_environment=None,
                 intent_fallbacks=None, intent_training=None, learning=None,
                 confirm_operation=None):
        self._stt             = stt_client
        self._llm             = llm_editor
        self._env             = input_environment or TyperInputEnvironment(buf)
        self._memo_store = memo_store
        self._status          = status_window
        self._history         = history
        self._intent_fallbacks = intent_fallbacks or IntentFallbackOptions()
        self._intent_training = intent_training or IntentTrainingRecorder()
        self._learning = learning or LocalLearningRecorder()
        self._io_lock         = threading.Lock()   # 串行化所有输入框 IO（删+打）
        self._executor = InstructionModeExecutor(
            self._llm,
            self._env,
            memo_store=self._memo_store,
            show=self._show,
            set_status=self._set_status,
            text_io=self._io_lock,
            confirm_operation=confirm_operation,
        )

    def _record(self, mode: str, text: str = "", status: str = "ok", detail: str = ""):
        if self._history is not None:
            try:
                self._history.append(mode, text, status, detail)
            except Exception as e:
                print(f"[ai] history 写入失败: {e}")

    def handle(self, pcm: bytes) -> None:
        """AI 键松开后调用，在后台线程执行。"""
        threading.Thread(target=self._run, args=(pcm,), daemon=True, name="AIHandler").start()

    # ── 内部流程 ──────────────────────────────────────────────────────

    def _run(self, pcm: bytes) -> None:
        keep_status = False
        try:
            keep_status = bool(self._run_inner(pcm))
        finally:
            if self._status is not None and not keep_status:
                self._status.set_state("idle")

    def _run_inner(self, pcm: bytes) -> None:
        # 1. STT 识别
        try:
            text = self._stt.transcribe(pcm)
        except Exception as e:
            print(f"[ai] STT 失败: {e}")
            self._record("ai", "", "error", f"STT: {e}")
            self._show_error_message(e)
            if self._status is not None:
                self._status.set_state("error_stt")
            return
        if not text:
            print("[ai] 未识别到内容")
            self._record("ai", "", "empty")
            if self._status is not None:
                self._status.set_state("empty_stt")
            return True
        print(f"[ai] 识别: {text!r}")
        self._show_progress(f"\u5df2\u8bc6\u522b\uff1a{_preview(text)}")
        correction = parse_correction_command(text)
        if correction is not None:
            return self._handle_local_correction(text, correction)
        memo_edit = parse_memo_edit_command(text)
        if memo_edit is not None:
            result = Memo(self._memo_store).edit_text(
                memo_edit.target,
                memo_edit.old,
                memo_edit.new,
            )
            self._record("ai", text, "ok", "memo_edit")
            self._show(result.message)
            return True

        # 2. 读取上下文（优先用 Explicit Selection，其次用 Tracked Segment）
        target = self._env.target_for_instruction()
        selected = target.selected
        if selected:
            print(f"[ai] Explicit Selection: {selected!r}")
        context = selected or target.tracked_segment
        print(
            "[ai] 目标上下文: "
            f"selected_len={len(selected)} tracked_len={len(target.tracked_segment)}"
        )

        # 3. LLM 意图分类
        try:
            self._show_progress("\u6b63\u5728\u7406\u89e3\u6307\u4ee4")
            shortcuts = self._env.shortcuts()
            shortcut_entries = shortcut_intent_entries(
                self._env.shortcut_catalog() if hasattr(self._env, "shortcut_catalog") else ()
            )
            classification_context = IntentContext(
                text=text,
                selected=selected,
                recent_text=context,
                active_application=self._env.active_application(),
                shortcuts=shortcuts,
                shortcut_entries=shortcut_entries,
                memo_records=memo_records(
                    self._memo_store,
                ),
            )
            classification = self._classify_intent_with_timeout(classification_context)
            result = classification.result
        except TimeoutError as e:
            print(f"[ai] 意图分类超时: {e}")
            self._record("ai", text, "error", "intent_timeout")
            if self._status is not None:
                self._status.set_state("error_llm")
            self._show("AI 理解超时，请重试")
            return True
        except Exception as e:
            print(f"[ai] 意图分类失败: {e}，回退到聊天")
            self._record("ai", text, "error", f"LLM: {e}")
            if self._status is not None:
                self._status.set_state("error_llm")
            result = {"type": "chat", "reply": "没听清楚，请再说一次"}

        operation = operation_from_intent(result)
        command_plan = command_plan_from_operation(
            operation,
            instruction=text,
            target=target,
        )
        command_plan = apply_local_risk_policy(
            command_plan,
            instruction=text,
            input_environment=self._env,
            memo_store=self._memo_store,
        )
        intent_source = result.get("_intent_source", "unknown")
        intent_confidence = result.get("_intent_confidence", "")
        cache_hit = bool(result.get("_intent_cache_hit"))
        print(
            f"[ai] intent: {operation.kind} "
            f"source={intent_source} confidence={intent_confidence} cache={cache_hit}"
        )
        self._show_progress(_operation_message(operation))

        keep_status = self._execute_command_plan(command_plan, text, selected, target)
        status, detail = getattr(self._executor, "last_status", ("ok", operation.kind))
        intent_detail = _intent_detail(
            detail,
            intent_source,
            intent_confidence,
            cache_hit,
            target_source=command_plan.target_source,
            output_policy=command_plan.output_policy,
            risk_reason=command_plan.risk_reason,
        )
        self._intent_training.record(
            text=text,
            active_application=classification_context.active_application,
            selected=selected,
            recent_text=context,
            shortcuts=classification_context.shortcuts,
            intent_result=result,
            status=status,
            detail=intent_detail,
            target_source=command_plan.target_source,
            output_policy=command_plan.output_policy,
            risk_reason=command_plan.risk_reason,
            confirmed=status != "pending_confirmation" and command_plan.output_policy == "confirm",
            cancelled=status == "cancelled",
            undone=False,
        )
        self._record("ai", text, status, intent_detail)
        output_text = getattr(self._executor, "last_output_text", "")
        if output_text:
            self._learning.remember_output(
                output_text,
                mode="ai",
                operation_kind=operation.kind,
            )
        return keep_status

    def _execute_command_plan(self, plan, text: str, selected: str, target) -> bool:
        if plan.output_policy == "confirm":
            if self._status is not None and hasattr(self._status, "show_action_card"):
                return bool(self._status.show_action_card(
                    transcript=text,
                    target_source=plan.target_source,
                    operation_kind=plan.operation_kind,
                    preview_text=plan.preview_text or _operation_message(plan.operation),
                    on_confirm=lambda: self._confirm_command_plan(
                        plan,
                        text,
                        selected,
                        target,
                    ),
                    on_cancel=lambda: self._mark_cancelled(plan, text),
                    on_undo=self._undo_last,
                ))
            self._show(f"需要确认：{plan.preview_text or plan.operation_kind}")
            self._executor.execute_plan(plan, text, selected, target, confirmed=False)
            return True
        keep_status = self._executor.execute_plan(plan, text, selected, target)
        if plan.output_policy == "auto" and not keep_status:
            self._show_progress(f"已执行：{_compact_preview(text or plan.preview_text or plan.operation_kind)}")
        return keep_status

    def _mark_cancelled(self, plan, text: str = "") -> bool:
        detail = f"cancelled:{plan.operation_kind};target_source={plan.target_source};output_policy={plan.output_policy}"
        self._executor.last_status = ("cancelled", detail)
        self._record("ai", text, "cancelled", detail)
        return True

    def _confirm_command_plan(self, plan, text: str, selected: str, target) -> bool:
        keep_status = self._executor.execute_plan(
            plan,
            text,
            selected,
            target,
            confirmed=True,
        )
        status, detail = getattr(self._executor, "last_status", ("ok", plan.operation_kind))
        confirm_detail = (
            f"confirmed:{plan.operation_kind};target_source={plan.target_source};"
            f"output_policy={plan.output_policy};risk_reason={plan.risk_reason};{detail}"
        )
        self._record("ai", text, status, confirm_detail)
        output_text = getattr(self._executor, "last_output_text", "")
        if output_text:
            self._learning.remember_output(
                output_text,
                mode="ai",
                operation_kind=plan.operation_kind,
            )
        return keep_status

    def _undo_last(self) -> bool:
        from agent.voice_text_operation import VoiceTextOperation

        return self._executor.execute(VoiceTextOperation("undo"), "撤销", "")

    def _handle_local_correction(self, text: str, correction) -> bool:
        recent = self._learning.recent.text
        if not recent:
            self._show("没有最近一次输出可纠正")
            self._record("ai", text, "error", "local_correction:no_recent_output")
            return True
        if correction.action == "shorten_recent":
            target = self._env.target_for_instruction()
            keep = self._executor.execute(
                operation_from_intent({"type": "edit"}),
                "把刚才那句再短一点",
                target.selected,
                target,
            )
            self._learning.record_correction(correction, source_text=recent)
            return keep or True
        replacement = apply_correction_to_text(recent, correction)
        if replacement == recent:
            self._learning.record_correction(correction, source_text=recent, status="no_change")
            self._show("没有找到要纠正的内容")
            self._record("ai", text, "error", "local_correction:no_change")
            return True
        from agent.input_environment import OperationWindow, ReplacementPlan

        target = self._env.target_for_instruction()
        window = OperationWindow(
            text=recent,
            target=target,
            source="explicit_selection" if target.selected else "tracked_segment",
        )
        result = self._env.apply_replacement_plan(
            window,
            ReplacementPlan(target_text=recent, replacement_text=replacement),
        )
        self._learning.record_correction(correction, source_text=recent)
        if result.ok:
            self._learning.remember_output(replacement, mode="ai", operation_kind="correction")
            self._record("ai", text, "ok", "local_correction")
            return True
        self._show("没有找到要纠正的内容")
        self._record("ai", text, "error", f"local_correction:{result.failure}")
        return True

    def _classify_intent_with_timeout(self, context: IntentContext) -> dict:
        out: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                out.put(("ok", classify_intent_details(
                    self._llm,
                    context,
                    self._intent_fallbacks,
                )))
            except Exception as e:
                out.put(("error", e))

        threading.Thread(target=run, daemon=True, name="AIIntentClassifier").start()
        try:
            status, value = out.get(timeout=_INTENT_TIMEOUT_SECONDS)
        except queue.Empty:
            raise TimeoutError(
                f"intent classification exceeded {_INTENT_TIMEOUT_SECONDS:.1f}s"
            )
        if status == "error":
            raise value
        return value

    def _set_status(self, state: str) -> None:
        if self._status is not None:
            self._status.set_state(state)

    def _show_progress(self, message: str) -> None:
        """Show short non-typing progress feedback while an AI command runs."""
        full = _AI_PREFIX.strip() + " " + message
        if self._status is not None and hasattr(self._status, "show_message"):
            self._status.show_message(full, _PROGRESS_SECONDS)
        else:
            print(f"{_AI_PREFIX}{message}")

    def _show(self, message: str) -> None:
        """Show AI/chat feedback in the floating status HUD."""
        message = message.replace("\n", " ").replace("\r", "")
        delay = max(3.0, min(12.0, len(message) * 0.18))
        full = _AI_PREFIX.strip() + " " + message
        if self._status is not None and hasattr(self._status, "show_typing_message"):
            self._status.show_typing_message(full, delay)
        elif self._status is not None and hasattr(self._status, "show_message"):
            self._status.show_message(full, delay)
        else:
            print(f"{_AI_PREFIX}{message}")

    def _show_error_message(self, error: Exception) -> None:
        msg = str(error)
        if "敏感" in msg or "不安全" in msg or "unsafe" in msg.lower():
            self._show("识别内容被服务商拦截，请松开热键后重新说。可用启停热键快速恢复。")


def _intent_detail(
    detail: str,
    source: str,
    confidence: str,
    cache_hit: bool,
    *,
    target_source: str = "",
    output_policy: str = "",
    risk_reason: str = "",
) -> str:
    parts = [detail] if detail else []
    if source:
        parts.append(f"intent_source={source}")
    if confidence:
        parts.append(f"intent_confidence={confidence}")
    if cache_hit:
        parts.append("intent_cache_hit=true")
    if target_source:
        parts.append(f"target_source={target_source}")
    if output_policy:
        parts.append(f"output_policy={output_policy}")
    if risk_reason:
        parts.append(f"risk_reason={risk_reason}")
    return ";".join(parts)

def _preview(text: str, limit: int = 28) -> str:
    compact = str(text or "").replace("\n", " ").replace("\r", " ").strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _compact_preview(text: str, limit: int = 24) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _operation_message(operation) -> str:
    if operation.kind == "shortcut":
        return f"\u51c6\u5907\u6267\u884c\u5feb\u6377\u952e\uff1a{operation.name or '\u672a\u547d\u540d'}"
    labels = {
        "undo": "\u51c6\u5907\u64a4\u9500",
        "delete": "\u51c6\u5907\u5220\u9664\u5185\u5bb9",
        "edit": "\u51c6\u5907\u7f16\u8f91\u5185\u5bb9",
        "write": "\u51c6\u5907\u751f\u6210\u6587\u5b57",
        "memo_save": "\u51c6\u5907\u4fdd\u5b58\u8bb0\u5fc6",
        "memo_recall": "\u51c6\u5907\u8bfb\u53d6\u8bb0\u5fc6",
        "memo_delete": "\u51c6\u5907\u5220\u9664\u8bb0\u5fc6",
        "memo_list": "\u51c6\u5907\u5217\u51fa\u8bb0\u5fc6",
        "chat": "\u51c6\u5907\u663e\u793a\u56de\u7b54",
    }
    return labels.get(operation.kind, "\u51c6\u5907\u6267\u884c\u6307\u4ee4")
