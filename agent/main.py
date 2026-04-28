"""
Voice Keyboard Agent —— PC 端后台程序入口。

用法：
  python -m agent.main                    # 正常启动
  python -m agent.main --no-serial        # 纯软件模式，不搜索 ESP32 串口
  python -m agent.main --list-devices     # 列出可用麦克风设备
  python -m agent.main --install          # 注册开机自启动
  python -m agent.main --uninstall        # 移除开机自启动
"""

import argparse
import signal
import sys
import time

import sounddevice as sd

from agent.autostart import install, uninstall
from agent.config import load as load_config
from agent.serial_reader import SerialReader
from agent.text_buffer import TextBuffer
from agent.typer import erase_last, list_shortcuts, send_shortcut, type_text


# ── 串口回调 ───────────────────────────────────────────────────────

def make_serial_handlers(buf: TextBuffer):
    def on_text(text: str):
        print(f"[agent] 打字: {text!r}")
        type_text(text)
        buf.push(text)

    def on_cmd(cmd: str):
        print(f"[agent] 指令: {cmd}")
        if not send_shortcut(cmd):
            print(f"[agent] 未知指令: {cmd}，支持: {list_shortcuts()}")

    return on_text, on_cmd


# ── STT 回调 ───────────────────────────────────────────────────────

def make_utterance_handler(stt_client, buf: TextBuffer):
    def on_utterance(pcm: bytes):
        try:
            text = stt_client.transcribe(pcm)
            if text:
                print(f"[stt] {text!r}")
                type_text(text)
                buf.push(text)
            else:
                print("[stt] 识别结果为空")
        except Exception as e:
            print(f"[stt] 请求失败: {e}")
    return on_utterance


# ── 语音编辑回调 ───────────────────────────────────────────────────

def make_edit_handler(stt_client, editor, buf: TextBuffer, vad_monitor=None):
    def on_edit_utterance(pcm: bytes):
        # 1. 识别编辑指令
        try:
            instruction = stt_client.transcribe(pcm)
        except Exception as e:
            print(f"[edit] STT 失败: {e}")
            if vad_monitor:
                vad_monitor.resume()
            return

        if not instruction:
            print("[edit] 未识别到编辑指令")
            if vad_monitor:
                vad_monitor.resume()
            return

        original = buf.last
        if not original:
            print("[edit] 没有可编辑的内容（还没有打过字）")
            if vad_monitor:
                vad_monitor.resume()
            return

        print(f"[edit] 指令: {instruction!r}")
        print(f"[edit] 原文: {original!r}")

        # 2. LLM 修改
        try:
            corrected = editor.edit(original, instruction)
        except Exception as e:
            print(f"[edit] LLM 失败: {e}")
            if vad_monitor:
                vad_monitor.resume()
            return

        print(f"[edit] 修改后: {corrected!r}")

        # 3. 擦掉原文，打入修改后的文字
        erase_last(original)
        type_text(corrected)
        buf.replace_last(corrected)

        if vad_monitor:
            vad_monitor.resume()

    return on_edit_utterance


# ── 音频管线 ───────────────────────────────────────────────────────

def _build_audio(cfg: dict, buf: TextBuffer):
    stt_cfg = cfg.get("stt", {})
    if not stt_cfg.get("api_key"):
        print("[agent] 未配置 stt.api_key，跳过音频 STT")
        print("[agent] 提示: cp config.yaml.example config.yaml 然后填入 API Key")
        return None

    try:
        from agent.stt import STTClient
    except ImportError as e:
        print(f"[agent] STT 依赖缺失（{e}）")
        return None

    try:
        stt = STTClient(stt_cfg)
    except Exception as e:
        print(f"[agent] STT 初始化失败: {e}")
        return None

    # LLM 编辑器（可选）
    editor = None
    llm_cfg = cfg.get("llm", {})
    if llm_cfg.get("api_key"):
        try:
            from agent.llm_editor import LLMEditor
            editor = LLMEditor(llm_cfg)
            print("[agent] LLM 编辑功能已启用")
        except Exception as e:
            print(f"[agent] LLM 初始化失败: {e}")

    audio_cfg = cfg.get("audio", {})
    mode      = audio_cfg.get("mode", "ptt")
    device    = audio_cfg.get("device", "auto")

    on_utterance = make_utterance_handler(stt, buf)

    if mode == "ptt":
        try:
            from agent.push_to_talk import PushToTalk
        except ImportError as e:
            print(f"[agent] PTT 依赖缺失（{e}）")
            return None

        on_edit = None
        if editor:
            on_edit = make_edit_handler(stt, editor, buf, vad_monitor=None)

        ptt = PushToTalk(
            on_utterance=on_utterance,
            on_edit_utterance=on_edit,
            ptt_key=audio_cfg.get("ptt_key", "right_alt"),
            edit_key=audio_cfg.get("edit_key", "right_ctrl"),
            device=device,
        )
        ptt.start()
        return ptt

    else:  # vad
        try:
            from agent.audio_monitor import AudioMonitor
        except ImportError as e:
            print(f"[agent] VAD 依赖缺失（{e}）")
            return None

        monitor = AudioMonitor(
            on_utterance=on_utterance,
            device=device,
            vad_level=audio_cfg.get("vad_aggressiveness", 2),
        )
        monitor.start()

        # VAD 模式下，编辑键仍用 PTT 方式（避免 VAD 误触发）
        if editor:
            try:
                from agent.push_to_talk import PushToTalk
                on_edit = make_edit_handler(stt, editor, buf, vad_monitor=monitor)

                edit_ptt = PushToTalk(
                    on_utterance=on_utterance,       # 备用，正常用 VAD
                    on_edit_utterance=on_edit,
                    ptt_key=audio_cfg.get("ptt_key", "right_alt"),
                    edit_key=audio_cfg.get("edit_key", "right_ctrl"),
                    device=device,
                )

                # 按下编辑键时暂停 VAD
                _orig_press = edit_ptt._on_press

                def _patched_press(key):
                    from pynput.keyboard import Key
                    edit_key_obj = edit_ptt._edit_key
                    if key == edit_key_obj:
                        monitor.pause()
                    _orig_press(key)

                edit_ptt._listener  # will be set in start()
                edit_ptt._on_press = _patched_press
                edit_ptt.start()
                return monitor  # 主对象返回 monitor
            except ImportError:
                pass

        return monitor


# ── 入口 ───────────────────────────────────────────────────────────

def list_devices():
    print("\n可用麦克风设备：\n")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            default = " ← 系统默认" if i == sd.default.device[0] else ""
            print(f"  [{i:2d}] {d['name']}{default}")
    print(
        "\n在 config.yaml 中填写设备序号或名称片段：\n"
        "  audio:\n"
        "    device: 2\n"
        "    device: \"MacBook\"\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Voice Keyboard Agent")
    parser.add_argument("--port",         default=None,        help="指定串口路径")
    parser.add_argument("--no-serial",    action="store_true", help="不搜索 ESP32 串口（纯软件模式）")
    parser.add_argument("--list-devices", action="store_true", help="列出可用麦克风设备后退出")
    parser.add_argument("--install",      action="store_true", help="注册开机自启动")
    parser.add_argument("--uninstall",    action="store_true", help="移除开机自启动")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return
    if args.install:
        install()
        return
    if args.uninstall:
        uninstall()
        return

    cfg = load_config()
    buf = TextBuffer()
    print("[agent] Voice Keyboard Agent 启动")

    # ── 串口 ─────────────────────────────────────────────────────
    reader = None
    if not args.no_serial:
        on_text, on_cmd = make_serial_handlers(buf)
        reader = SerialReader(on_text=on_text, on_cmd=on_cmd, port=args.port)
        reader.start()
    else:
        print("[agent] 串口已禁用（纯软件模式）")

    # ── 音频 STT + 编辑 ──────────────────────────────────────────
    monitor = _build_audio(cfg, buf)

    def shutdown(sig, frame):
        print("\n[agent] 退出")
        if reader:
            reader.stop()
        if monitor:
            monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("[agent] 运行中，Ctrl+C 退出\n")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
