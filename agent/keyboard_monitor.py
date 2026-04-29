"""
全局键盘监听，追踪用户手动按 Backspace / Delete，实时同步 TextBuffer。

设计要点：
  - 只监听 Backspace 和 Delete 两个键，不干扰其他按键逻辑
  - typer.py 调用 erase_last() 时会设置 _erasing=True 标志，
    此时 pynput 回调也会收到我们自己发出的退格事件，
    通过 typer.is_erasing() 判断并忽略，避免双重扣减
  - 运行在独立守护线程，不阻塞主流程

已知限制：
  监听是全局的，用户在其他应用按退格时也会触发 trim_end。
  缓解措施：超过 TRACK_TIMEOUT 秒没有语音输出，停止追踪退格，
  同时标记 cursor_uncertain，触发编辑时走行选择剪贴板模式（更准确）。
"""

import time

from pynput import keyboard as kb

import agent.typer as typer
from agent.text_buffer import TextBuffer

# 超过此时长（秒）没有语音输出，退格不再同步 buf
# 避免用户切到其他应用按退格时污染 buf
TRACK_TIMEOUT = 30.0


class KeyboardMonitor:
    """监听 Backspace/Delete，实时同步 TextBuffer。"""

    def __init__(self, buf: TextBuffer):
        self._buf           = buf
        self._listener      = None
        self._last_voice_ts = 0.0   # 上次语音输出的时间戳

    def notify_voice_output(self) -> None:
        """每次语音打字后调用，刷新追踪窗口。"""
        self._last_voice_ts = time.monotonic()

    def _within_track_window(self) -> bool:
        return (time.monotonic() - self._last_voice_ts) < TRACK_TIMEOUT

    def start(self):
        self._listener = kb.Listener(
            on_press=self._on_press,
            daemon=True,
        )
        self._listener.start()
        print(f"[kbd] 键盘退格监听已启动（语音输出后 {TRACK_TIMEOUT}s 内同步 Backspace）")

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key):
        # 忽略我们自己调用 erase_last 时发出的退格
        if typer.is_erasing():
            return

        if key == kb.Key.backspace:
            if self._within_track_window():
                self._buf.trim_end(1)
            else:
                # 超出追踪窗口：可能是其他应用的退格，
                # 标记不确定，下次编辑走行选择模式
                self._buf.cursor_uncertain = True
        elif key == kb.Key.delete:
            # Delete 键删除光标右边的字符，方向相反，
            # 无法直接对应 buf.last，只能标记 cursor_uncertain
            self._buf.cursor_uncertain = True
