"""
AI 键统一处理：STT → LLM 意图分类 → 快捷键 / 编辑 / 写作 / 撤回 / 聊天

意图分类规则：
  shortcut — 明确的快捷键操作，直接执行
  edit     — 修改/润色/编辑文字，改选中内容或上一句
  write    — 给主题/要求让 AI 生成新内容，直接打入，不自动删除
  undo     — 撤回上一次 AI 操作（恢复被删的原文，或删掉写入的内容）
  chat     — 其他（问题、聊天、不确定），回复打到输入框后按字数自动删除
"""

import json
import threading
import time

from pynput import keyboard as _kb

from agent.typer import (
    erase_last, get_selection, jump_to_end, replace_selection,
    send_shortcut, type_text, list_shortcuts,
)

_AI_PREFIX = " [AI]: "

_CLASSIFY_SYSTEM = """你是语音键盘助手的意图分类器。根据用户说的话返回一个JSON对象，不要包含任何其他内容。

判断依据是用户说的话，而不是是否有选中文字。有选中文字只是上下文参考。

本软件的功能：
- 按住 Option 键说话：语音转文字，原样打入当前输入框
- 按住 Command 键说话，有以下几种模式：
  * 快捷键：说出操作名称直接执行系统快捷键
  * 编辑：修改/润色/删除当前段落或选中的文字
  * 写作：给出主题或要求，AI 帮你写内容并逐句打入
  * 撤回：撤销上一次 AI 操作，恢复原文
  * 聊天：问任何问题，AI 回复显示在输入框并自动删除

规则（按优先级）：
1. 明确的快捷键操作 → {"type":"shortcut","name":"快捷键名称"}
2. 撤回/撤销/恢复上一步操作 → {"type":"undo"}
3. 明确要求删除/清除选中内容或当前段落（不是修改，是直接删掉） → {"type":"delete"}
4. 用户说的话明确要求修改/润色/编辑已有文字 → {"type":"edit"}
5. 用户给出主题、要求或提纲，让AI帮写新内容 → {"type":"write"}
6. 其他（提问、聊天、不确定、没有明确编辑或写作指令） → {"type":"chat","reply":"回答或提示，最多50字"}"""

_WRITE_SYSTEM = """你是一个写作助手。根据用户的要求直接输出所需内容，不要有任何前缀、解释或额外说明。只输出内容本身。不要使用换行，所有内容写成连续的段落。必须使用完整的中文标点符号（逗号、句号、问号、感叹号），不得省略任何标点。"""

_SENTENCE_END = frozenset('。！？.!?…，,；;')
_MAX_PENDING  = 40   # 超过此字符数强制输出，防止模型不加标点时卡住


class AIHandler:
    def __init__(self, stt_client, llm_editor, buf):
        self._stt             = stt_client
        self._llm             = llm_editor
        self._buf             = buf
        self._last_ai_output  = ""
        self._erase_timer: threading.Timer | None = None
        self._lock            = threading.Lock()   # 保护数据字段
        self._io_lock         = threading.Lock()   # 串行化所有输入框 IO（删+打）
        # (op, old_text, new_text): op='edit'|'write'
        self._undo_stack: list[tuple[str, str, str]] = []

    def on_ai_key_down(self) -> None:
        """AI 键按下时立即调用，取消定时器，但保留待删文字供 _run() 处理。"""
        with self._lock:
            if self._erase_timer is not None:
                self._erase_timer.cancel()
                self._erase_timer = None

    def handle(self, pcm: bytes) -> None:
        """AI 键松开后调用，在后台线程执行。"""
        threading.Thread(target=self._run, args=(pcm,), daemon=True, name="AIHandler").start()

    # ── 内部流程 ──────────────────────────────────────────────────────

    def _run(self, pcm: bytes) -> None:
        # 0. 删掉上一条 AI 文字（此时 Command 已松开，不会触发 Cmd+Backspace）
        with self._io_lock:
            with self._lock:
                pending = self._last_ai_output
                self._last_ai_output = ""
            if pending:
                erase_last(pending)

        # 1. STT 识别
        try:
            text = self._stt.transcribe(pcm)
        except Exception as e:
            print(f"[ai] STT 失败: {e}")
            return
        if not text:
            print("[ai] 未识别到内容")
            return
        print(f"[ai] 识别: {text!r}")

        # 2. 读取上下文（优先用鼠标选中内容，其次用当前段落）
        selected = get_selection()
        context  = selected or self._buf.current_segment

        # 3. 构造分类请求
        shortcuts = list_shortcuts()
        user_msg  = f"可用快捷键：{'、'.join(shortcuts)}\n"
        if selected:
            user_msg += f"用户选中的文字：\"{selected}\"\n"
        elif context:
            user_msg += f"用户最近打的文字：\"{context}\"\n"
        user_msg += f"用户说：\"{text}\""

        # 4. LLM 意图分类
        try:
            raw    = self._llm.chat(_CLASSIFY_SYSTEM, user_msg)
            raw    = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(raw)
        except Exception as e:
            print(f"[ai] 意图分类失败: {e}，回退到聊天")
            result = {"type": "chat", "reply": "没听清楚，请再说一次"}

        intent = result.get("type", "chat")
        print(f"[ai] 意图: {intent}")

        # 5. 执行
        if intent == "shortcut":
            name = result.get("name", "")
            if not send_shortcut(name):
                self._show(f"没有找到快捷键：{name}")
        elif intent == "undo":
            self._do_undo()
        elif intent == "delete":
            self._do_delete(selected)
        elif intent == "edit":
            self._do_edit(text, selected)
        elif intent == "write":
            self._do_write(text, selected)
        else:
            reply = result.get("reply", "")
            if reply:
                if selected:
                    # 取消选中，光标跳到输入框末尾，避免 type_text 覆盖选中内容
                    jump_to_end()
                self._show(reply)

    def _do_edit(self, instruction: str, selected: str) -> None:
        if selected:
            # 有鼠标选中内容，直接用
            try:
                corrected = self._llm.edit(selected, instruction)
            except Exception as e:
                print(f"[ai] 编辑失败: {e}")
                return
            print(f"[ai] 编辑结果: {corrected!r}")
            replace_selection(corrected)
            self._buf.clear()
            self._buf.push(corrected)
            return

        if self._buf.cursor_uncertain:
            # 鼠标点击过，光标位置不可信，提示用户手动选中
            self._show("请先选中你想修改的内容")
            return

        segment = self._buf.current_segment
        if not segment:
            self._show("没有可编辑的内容")
            return

        try:
            corrected = self._llm.edit(segment, instruction)
        except Exception as e:
            print(f"[ai] 编辑失败: {e}")
            return
        print(f"[ai] 编辑结果: {corrected!r}")

        self._push_undo('edit', segment, corrected)
        with self._io_lock:
            # 先取消定时器，清掉 AI 文字（它在输入框最末尾）
            with self._lock:
                if self._erase_timer is not None:
                    self._erase_timer.cancel()
                    self._erase_timer = None
                pending = self._last_ai_output
                self._last_ai_output = ""
            if pending:
                erase_last(pending)
            # 再删段落、打入修改结果
            erase_last(segment)
            type_text(corrected)
            self._buf.replace_segment(corrected)

    def _do_write(self, instruction: str, selected: str) -> None:
        """根据用户指令流式生成内容，逐句打入输入框，不自动删除。"""
        if selected:
            jump_to_end()

        write_instruction = instruction + "（必须加上完整的中文标点符号，包括逗号和句号，不得省略）"
        pending = ""
        total   = ""
        try:
            for chunk in self._llm.chat_stream(_WRITE_SYSTEM, write_instruction):
                chunk = chunk.replace('\n', ' ').replace('\r', ' ')
                pending += chunk
                while True:
                    idx = next((i for i, c in enumerate(pending) if c in _SENTENCE_END), -1)
                    if idx == -1:
                        # 没有标点但积累太长，强制输出
                        if len(pending) >= _MAX_PENDING:
                            type_text(pending)
                            self._buf.push(pending)
                            total  += pending
                            pending = ""
                        break
                    sentence = pending[:idx + 1]
                    pending  = pending[idx + 1:]
                    type_text(sentence)
                    self._buf.push(sentence)
                    total += sentence
        except Exception as e:
            print(f"[ai] 写作失败: {e}")
            return

        if pending.strip():
            type_text(pending)
            self._buf.push(pending)
            total += pending

        if total:
            self._push_undo('write', '', total)

    def _do_delete(self, selected: str) -> None:
        """删除选中内容或当前段落。"""
        if selected:
            # 有选中内容，直接按 Backspace 删掉
            self._push_undo('edit', selected, '')
            _ctrl = _kb.Controller()
            _ctrl.press(_kb.Key.backspace)
            _ctrl.release(_kb.Key.backspace)
            self._buf.trim_end(len(selected))
            return

        if self._buf.cursor_uncertain:
            self._show("请先选中你想删除的内容")
            return

        segment = self._buf.current_segment
        if not segment:
            self._show("没有可删除的内容")
            return

        self._push_undo('edit', segment, '')
        with self._io_lock:
            with self._lock:
                if self._erase_timer is not None:
                    self._erase_timer.cancel()
                    self._erase_timer = None
                pending = self._last_ai_output
                self._last_ai_output = ""
            if pending:
                erase_last(pending)
            erase_last(segment)
            self._buf.replace_segment('')

    def _push_undo(self, op: str, old: str, new: str) -> None:
        self._undo_stack.append((op, old, new))
        if len(self._undo_stack) > 5:
            self._undo_stack.pop(0)

    def _do_undo(self) -> None:
        if not self._undo_stack:
            self._show("没有可撤回的操作")
            return
        op, old, new = self._undo_stack.pop()
        print(f"[ai] 撤回: op={op} old={old!r} new={new!r}")
        with self._io_lock:
            with self._lock:
                if self._erase_timer is not None:
                    self._erase_timer.cancel()
                    self._erase_timer = None
                pending = self._last_ai_output
                self._last_ai_output = ""
            if pending:
                erase_last(pending)
            if new:
                erase_last(new)
            if op == 'edit':
                if old:
                    type_text(old)
                self._buf.replace_segment(old)
            else:  # write
                self._buf.trim_end(len(new))

            if old and op == 'write':
                type_text(old)
                self._buf.push(old)

    def _show(self, message: str) -> None:
        """把 AI 消息追加到输入框，按字数等待后自动删除。"""
        message = message.replace("\n", " ").replace("\r", "")
        full = _AI_PREFIX + message

        with self._io_lock:
            # 取消定时器，读取并清空待删内容
            with self._lock:
                if self._erase_timer is not None:
                    self._erase_timer.cancel()
                    self._erase_timer = None
                pending = self._last_ai_output
                self._last_ai_output = ""

            if pending:
                erase_last(pending)
            type_text(full)

            delay = max(2.0, len(message) * 0.15)
            with self._lock:
                self._last_ai_output = full
                self._erase_timer = threading.Timer(delay, self._auto_erase, args=(full,))
                self._erase_timer.start()

    def _auto_erase(self, expected: str) -> None:
        with self._io_lock:
            with self._lock:
                if self._last_ai_output != expected:
                    return
                self._last_ai_output = ""
                self._erase_timer = None
            erase_last(expected)
