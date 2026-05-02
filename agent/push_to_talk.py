"""
Push-to-Talk 录音模块，支持两个热键：
  ptt_key  — 普通听写（dictation），松开后调 on_utterance
  edit_key — 语音编辑（edit），松开后调 on_edit_utterance

两个键互斥：一个按下时另一个无效。
"""

import threading
from typing import Callable, Optional

import sounddevice as sd
from pynput import keyboard as kb

from agent.audio_monitor import find_device

SAMPLE_RATE = 16000


def _parse_key(key_str: str):
    try:
        return getattr(kb.Key, key_str)
    except AttributeError:
        return kb.KeyCode.from_char(key_str)


def _parse_keys(key_input) -> list:
    """支持单个字符串或字符串列表，统一返回 pynput key 列表。"""
    if isinstance(key_input, list):
        return [_parse_key(k) for k in key_input]
    return [_parse_key(key_input)]


class PushToTalk:
    def __init__(
        self,
        on_utterance:      Callable[[bytes], None],
        on_edit_utterance: Optional[Callable[[bytes], None]] = None,
        ptt_key:           str = "right_alt",
        edit_key:          str = "right_ctrl",
        device:            Optional[str] = "auto",
    ):
        self._on_utterance      = on_utterance
        self._on_edit_utterance = on_edit_utterance
        self._ptt_keys          = _parse_keys(ptt_key)
        self._edit_keys         = _parse_keys(edit_key) if on_edit_utterance else []
        self._device_hint       = device
        self._device_idx        = None
        self._active_key        = None   # 当前正在录音用哪个键
        self._active_trigger    = None   # 触发本次录音的具体按键，用于 release 配对
        self._buf: list[bytes]  = []
        self._stream: Optional[sd.RawInputStream] = None
        self._listener: Optional[kb.Listener]     = None

    def start(self):
        self._device_idx = find_device(self._device_hint)
        if self._device_idx is None:
            print("[ptt] 使用系统默认麦克风")
        else:
            info = sd.query_devices(self._device_idx)
            print(f"[ptt] 使用麦克风: {info['name']}")

        self._listener = kb.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

        hints = [f"{'/'.join(str(k) for k in self._ptt_keys)} 说话"]
        if self._edit_keys:
            hints.append(f"{'/'.join(str(k) for k in self._edit_keys)} 语音编辑")
        print(f"[ptt] 按住 {' | '.join(hints)}")

    def stop(self):
        if self._listener:
            self._listener.stop()
        self._close_stream()

    # ── 键盘事件 ─────────────────────────────────────────────────

    def _on_press(self, key):
        if self._active_key is not None:
            return  # 已有键按下，忽略另一个
        if key in self._ptt_keys:
            self._active_key     = "dictate"
            self._active_trigger = key
            self._start_recording()
        elif self._edit_keys and key in self._edit_keys:
            self._active_key     = "edit"
            self._active_trigger = key
            self._start_recording()

    def _on_release(self, key):
        if key != self._active_trigger:
            return
        if self._active_key == "dictate":
            self._stop_recording(mode="dictate")
        elif self._active_key == "edit":
            self._stop_recording(mode="edit")
        self._active_trigger = None

    # ── 录音控制 ─────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        self._buf.append(bytes(indata))

    def _start_recording(self):
        self._buf = []
        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=self._device_idx,
            blocksize=1024,
            callback=self._audio_callback,
        )
        self._stream.start()
        label = "录音中" if self._active_key == "dictate" else "编辑指令录音中"
        print(f"[ptt] {label}... ", end="\r", flush=True)

    def _stop_recording(self, mode: str):
        self._active_key = None
        self._close_stream()

        pcm = b"".join(self._buf)
        self._buf = []

        if len(pcm) < SAMPLE_RATE * 2 * 0.3:
            print("[ptt] 录音太短，跳过    ")
            return

        label    = "识别中" if mode == "dictate" else "解析编辑指令"
        callback = self._on_utterance if mode == "dictate" else self._on_edit_utterance
        print(f"[ptt] {label}...    ", end="\r", flush=True)
        threading.Thread(
            target=callback,
            args=(pcm,),
            daemon=True,
            name=f"PTT-{mode}",
        ).start()

    def _close_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
