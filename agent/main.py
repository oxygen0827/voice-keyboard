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
from agent.typer import init as typer_init, list_shortcuts, send_shortcut, type_text


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

def make_utterance_handler(stt_client, buf: TextBuffer, kbd_mon=None):
    def on_utterance(pcm: bytes):
        try:
            text = stt_client.transcribe(pcm)
            if text:
                print(f"[stt] {text!r}")
                type_text(text)
                buf.push(text)
                if kbd_mon is not None:
                    kbd_mon.notify_voice_output()
            else:
                print("[stt] 识别结果为空")
        except Exception as e:
            print(f"[stt] 请求失败: {e}")
    return on_utterance


# ── 音频管线 ───────────────────────────────────────────────────────

def _build_audio(cfg: dict, buf: TextBuffer, kbd_monitor=None):
    stt_cfg = cfg.get("stt", {})
    provider = stt_cfg.get("provider", "")
    _no_api_key_providers = {"volcengine", "aliyun"}
    if not stt_cfg.get("api_key") and provider not in _no_api_key_providers:
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

    # AI 键处理器
    ai_handler = None
    if editor:
        try:
            from agent.ai_handler import AIHandler
            ai_handler = AIHandler(stt, editor, buf)
            ai_key_name = audio_cfg.get("ai_key", "cmd_r")
            print(f"[agent] AI 键已启用，热键: {ai_key_name}")
        except Exception as e:
            print(f"[agent] AIHandler 初始化失败: {e}")

    on_utterance = make_utterance_handler(stt, buf, kbd_mon=kbd_monitor)

    if mode == "ptt":
        try:
            from agent.push_to_talk import PushToTalk
        except ImportError as e:
            print(f"[agent] PTT 依赖缺失（{e}）")
            return None

        on_ai         = ai_handler.handle        if ai_handler else None
        on_ai_key_dwn = ai_handler.on_ai_key_down if ai_handler else None

        ptt = PushToTalk(
            on_utterance=on_utterance,
            on_ai_utterance=on_ai,
            on_ai_key_down=on_ai_key_dwn,
            ptt_key=audio_cfg.get("ptt_key", "right_alt"),
            ai_key=audio_cfg.get("ai_key", "cmd_r"),
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
    typer_init(cfg.get("typing", {}))
    buf = TextBuffer()
    print("[agent] Voice Keyboard Agent 启动")

    # ── 键盘退格监听（同步 TextBuffer）─────────────────────────────
    try:
        from agent.keyboard_monitor import KeyboardMonitor
        kbd_monitor = KeyboardMonitor(buf)
        kbd_monitor.start()
    except Exception as e:
        print(f"[agent] 键盘监听启动失败（{e}），退格同步不可用")
        kbd_monitor = None

    # ── 鼠标点击监听（光标位移检测）───────────────────────────────
    try:
        from agent.mouse_monitor import MouseMonitor
        mouse_monitor = MouseMonitor(buf)
        mouse_monitor.start()
    except Exception as e:
        print(f"[agent] 鼠标监听启动失败（{e}），行选择模式不可用")
        mouse_monitor = None

    # ── 串口 ─────────────────────────────────────────────────────
    reader = None
    if not args.no_serial:
        on_text, on_cmd = make_serial_handlers(buf)
        reader = SerialReader(on_text=on_text, on_cmd=on_cmd, port=args.port)
        reader.start()
    else:
        print("[agent] 串口已禁用（纯软件模式）")

    # ── 音频 STT + 编辑 ──────────────────────────────────────────
    monitor = _build_audio(cfg, buf, kbd_monitor=kbd_monitor)

    def shutdown(sig, frame):
        print("\n[agent] 退出")
        if kbd_monitor:
            kbd_monitor.stop()
        if mouse_monitor:
            mouse_monitor.stop()
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
