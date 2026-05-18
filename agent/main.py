"""
Voice Keyboard Agent —— PC 端后台程序入口。

用法：
  python -m agent.main                    # 正常启动
  python -m agent.main --no-serial        # 纯软件模式，不搜索 ESP32 串口
  python -m agent.main --list-devices     # 列出可用麦克风设备
  python -m agent.main --install          # 注册开机自启动
  python -m agent.main --uninstall        # 移除开机自启动
  python -m agent.main --headless         # 不启动悬浮状态窗（桌面端托管模式）
"""

import argparse
import json
import os
import re
import signal
import sys
import threading
import time

# 打包后显式指定 CA 证书路径，供 requests 等直接读取环境变量使用。
if getattr(sys, "frozen", False):
    try:
        import certifi
        from pathlib import Path

        exe_dir = Path(sys.executable).resolve().parent
        resources_dir = exe_dir.parent / "Resources"
        bundled_candidates = [
            resources_dir / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "certifi" / "cacert.pem",
            resources_dir / "openssl.ca",
        ]
        _ca_path = None
        for p in bundled_candidates:
            if p.exists():
                _ca_path = str(p)
                break
        if _ca_path is None:
            _ca_path = certifi.where()

        os.environ.setdefault("SSL_CERT_FILE", _ca_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca_path)
        print(f"[agent] 使用 CA 证书: {_ca_path}")
    except ImportError:
        pass

# 打包模式下日志重定向到文件，必须在所有 print 之前
from agent import log_setup as _log_setup
_log_setup.setup()

import sounddevice as sd

from agent.autostart import install, uninstall
from agent.history import History
from agent.input_environment import TyperInputEnvironment
from agent.runtime_composition import RuntimeOptions, build_runtime_backend, options_from_args
from agent.text_buffer import TextBuffer


# ── 串口回调 ───────────────────────────────────────────────────────

def make_serial_handlers(buf: TextBuffer, history: History | None = None, input_environment=None):
    from agent.typer import list_shortcuts, send_shortcut
    env = input_environment or TyperInputEnvironment(buf)

    def on_text(text: str):
        print(f"[agent] 打字: {text!r}")
        try:
            env.insert_dictation(text)
            if history is not None:
                history.append("dictate", text, "ok")
        except Exception as e:
            print(f"[agent] 打字失败: {e}")
            if history is not None:
                history.append("dictate", text, "error", f"typing: {e}")

    def on_cmd(cmd: str):
        print(f"[agent] 指令: {cmd}")
        if not send_shortcut(cmd):
            print(f"[agent] 未知指令: {cmd}，支持: {list_shortcuts()}")

    return on_text, on_cmd


# ── STT 回调 ───────────────────────────────────────────────────────

_POLISH_SYSTEM = """你是文字润色助手。对用户说的话做最轻度的润色：
- 去掉口语填充词（嗯、啊、呃、那个、就是说、然后呢之类）
- 修正明显的错别字和不通顺的地方
- 加上合适的标点

严格遵守：保留原意和说话风格，不要扩写、不要总结、不要改写措辞。
直接输出润色后的文字，不要任何解释、前缀或引号。"""


_POLISH_LABEL_RE = re.compile(r"^(?:润色后|润色结果|修改后|修改结果|优化后|优化结果|结果|输出)\s*[:：]\s*")
_LEADING_INVISIBLE_RE = re.compile(r"^[\s\ufeff\u200b\u200c\u200d]+")
_LEADING_HASH_MARK_RE = re.compile(r"^[#＃]{1,6}[\s:：、，。,.!?！？;；-]*")


def _clean_generated_text(text: str) -> str:
    cleaned = str(text or "").strip().strip("\"'“”")
    for _ in range(4):
        before = cleaned
        cleaned = _LEADING_INVISIBLE_RE.sub("", cleaned)
        cleaned = _LEADING_HASH_MARK_RE.sub("", cleaned).strip()
        if cleaned == before:
            break
    return cleaned.strip().strip("\"'“”")


def _clean_polished_text(text: str) -> str:
    cleaned = _clean_generated_text(text)
    cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned).strip()
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    for _ in range(3):
        before = cleaned
        cleaned = _POLISH_LABEL_RE.sub("", cleaned).strip()
        cleaned = _clean_generated_text(cleaned)
        cleaned = re.sub(r"^[-*•]\s+", "", cleaned).strip()
        if cleaned == before:
            break
    return _clean_generated_text(cleaned)


def make_utterance_handler(stt_client, buf: TextBuffer, kbd_mon=None, editor=None,
                           status_window=None, history: History | None = None,
                           input_environment=None):
    env = input_environment or TyperInputEnvironment(buf)

    def on_utterance(
        pcm: bytes,
        polish: bool = False,
        clear_status: bool = True,
        progress_status: bool = True,
    ):
        mode = "polish" if polish else "dictate"
        try:
            if polish and hasattr(stt_client, "transcribe_polished"):
                text = stt_client.transcribe_polished(pcm)
            else:
                text = stt_client.transcribe(pcm)
        except Exception as e:
            print(f"[stt] 请求失败: {e}")
            if history is not None:
                history.append(mode, "", "error", f"STT: {e}")
            if status_window is not None and progress_status:
                status_window.set_state("error_stt")
            return
        text = _clean_generated_text(text)
        if not text:
            print("[stt] 识别结果为空")
            if history is not None:
                history.append(mode, "", "empty")
            if status_window is not None and progress_status:
                status_window.set_state("empty_stt")
            return
        print(f"[stt] {text!r}")
        if polish and editor is not None:
            if status_window is not None and progress_status:
                status_window.set_state("polishing")
            try:
                polished = _clean_polished_text(editor.chat(_POLISH_SYSTEM, text))
                if polished:
                    print(f"[stt] 微润色 → {polished!r}")
                    text = polished
            except Exception as e:
                print(f"[stt] 润色失败，回退原文: {e}")
        try:
            env.insert_dictation(text)
        except Exception as e:
            print(f"[stt] 打字失败: {e}")
            if status_window is not None and progress_status:
                status_window.set_state("error_typing")
            if history is not None:
                history.append(mode, text, "error", f"typing: {e}")
            return
        if history is not None:
            history.append(mode, text, "ok")
        if kbd_mon is not None:
            kbd_mon.notify_voice_output()
        if status_window is not None and clear_status:
            status_window.set_state("idle")
        if clear_status:
            print("[typeup] 输入完成")
    return on_utterance


def build_backend(args, buf: TextBuffer, status_window, history: History):
    return build_runtime_backend(options_from_args(args), buf, status_window, history)


def _llm_configured(llm_cfg: dict) -> bool:
    from agent.typeup_backend_auth import is_typeup_backend_configured
    return is_typeup_backend_configured(llm_cfg)


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
    parser.add_argument("--result-json",  default=None,        help="把一次性命令的 JSON 结果写入指定文件")
    parser.add_argument("--permissions-json", action="store_true", help="输出 macOS 权限状态 JSON 后退出")
    parser.add_argument("--request-accessibility", action="store_true", help="请求 macOS 辅助功能权限后退出")
    parser.add_argument("--request-input-monitoring", action="store_true", help="请求 macOS 输入监听权限后退出")
    parser.add_argument("--request-microphone", action="store_true", help="请求 macOS 麦克风权限后退出")
    parser.add_argument("--install",      action="store_true", help="注册开机自启动")
    parser.add_argument("--uninstall",    action="store_true", help="移除开机自启动")
    parser.add_argument("--no-ui",        action="store_true", help="不启动菜单栏/主窗口（纯命令行）")
    parser.add_argument("--headless",     action="store_true", help="不启动悬浮状态窗（供桌面端托管）")
    args = parser.parse_args()
    if getattr(sys, "frozen", False):
        args.no_serial = True

    def emit_json(payload):
        text = json.dumps(payload, ensure_ascii=False)
        if args.result_json:
            try:
                with open(args.result_json, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as e:
                print(f"[agent] 写入 JSON 结果失败: {e}")
        print(text)

    if args.list_devices:
        list_devices()
        return
    if args.permissions_json:
        from agent import permissions as _perm
        emit_json(_perm.all_status())
        return
    if args.request_accessibility:
        from agent import permissions as _perm
        emit_json({"accessibility": _perm.request_accessibility()})
        return
    if args.request_input_monitoring:
        from agent import permissions as _perm
        emit_json({"input_monitoring": _perm.request_input_monitoring()})
        return
    if args.request_microphone:
        from agent import permissions as _perm
        emit_json({"microphone": _perm.request_microphone_sync()})
        return
    if args.install:
        install()
        return
    if args.uninstall:
        uninstall()
        return

    from agent.config import ensure_user_config
    ensure_user_config()

    # 启动权限自检（仅 macOS）
    try:
        from agent import permissions as _perm
        print(f"[perm] {_perm.summary_log()}")
    except Exception as e:
        print(f"[perm] 自检失败: {e}")

    buf = TextBuffer()
    history = History()
    history.compact()

    # ── 状态悬浮窗 ───────────────────────────────────────────────
    status_window = None
    if not args.headless:
        try:
            if sys.platform == "win32":
                from agent.status_window_win import StatusWindow
            else:
                from agent.status_window import StatusWindow
            status_window = StatusWindow()
        except Exception as e:
            print(f"[agent] 状态悬浮窗启动失败（{e}），将以无窗口模式运行")

    print("[agent] Voice Keyboard Agent 启动")

    # ── 后端 ─────────────────────────────────────────────────────
    backend_lock = threading.Lock()
    backend = build_backend(args, buf, status_window, history)

    def reload_backend():
        with backend_lock:
            print("[agent] === 热重载后端 ===")
            backend.stop()
            new_bk = build_backend(args, buf, status_window, history)
            backend.cfg          = new_bk.cfg
            backend.kbd_monitor  = new_bk.kbd_monitor
            backend.mouse_monitor= new_bk.mouse_monitor
            backend.reader       = new_bk.reader
            backend.audio        = new_bk.audio
            print("[agent] 热重载完成")

    def retype(text: str):
        # 历史 tab「再次打字」回调，UI 已隐藏后调度
        env = TyperInputEnvironment(buf)
        try:
            env.insert_dictation(text)
            history.append("dictate", text, "ok", detail="retype")
        except Exception as e:
            print(f"[agent] retype 失败: {e}")

    # ── UI（菜单栏 + 主窗口）───────────────────────────────────────
    ui_app = None
    if status_window is not None and not args.no_ui:
        try:
            from agent.ui.app import UIApp
            from agent.memo_store import MemoStore
            ui_app = UIApp(
                history=history,
                memos=MemoStore(),
                reload_backend=reload_backend,
                retype_callback=retype,
            )
            status_window.add_main_thread_setup(ui_app.build)
        except Exception as e:
            import traceback
            print(f"[agent] UI 初始化失败: {e}")
            traceback.print_exc()
            ui_app = None

    def shutdown(sig=None, frame=None):
        print("\n[agent] 退出")
        with backend_lock:
            backend.stop()
        if status_window:
            status_window.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("[agent] 运行中，Ctrl+C 退出\n")
    if status_window is not None:
        status_window.run()
    else:
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
