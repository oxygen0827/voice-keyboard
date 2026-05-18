"""Runtime composition for the desktop Voice Keyboard Engine."""

from dataclasses import dataclass

from agent.config import load as load_config
from agent.history import History
from agent.input_environment import TyperInputEnvironment
from agent.serial_reader import SerialReader
from agent.text_buffer import TextBuffer
from agent.typeup_backend_auth import is_typeup_backend_configured


@dataclass(frozen=True)
class RuntimeOptions:
    no_serial: bool = False
    port: str | None = None


class RuntimeBackend:
    """Restartable runtime components."""

    def __init__(self):
        self.cfg = None
        self.kbd_monitor = None
        self.mouse_monitor = None
        self.reader = None
        self.audio = None
        self.input_environment = None

    def stop(self):
        for attr in ("audio", "reader", "mouse_monitor", "kbd_monitor"):
            comp = getattr(self, attr, None)
            if comp is None:
                continue
            try:
                comp.stop()
            except Exception as e:
                print(f"[agent] 停止 {attr} 失败: {e}")
            setattr(self, attr, None)


def options_from_args(args) -> RuntimeOptions:
    return RuntimeOptions(
        no_serial=bool(getattr(args, "no_serial", False)),
        port=getattr(args, "port", None),
    )


def build_runtime_backend(
    options: RuntimeOptions,
    buf: TextBuffer,
    status_window,
    history: History,
) -> RuntimeBackend:
    bk = RuntimeBackend()
    bk.cfg = load_config()
    from agent.typer import init as typer_init
    typer_init(bk.cfg.get("typing", {}))
    instruction_cfg = bk.cfg.get("instruction_mode", {})
    bk.input_environment = TyperInputEnvironment(
        buf,
        require_selection_for_instruction=instruction_cfg.get(
            "require_selection_for_edit", True
        ),
    )

    try:
        from agent.keyboard_monitor import KeyboardMonitor
        bk.kbd_monitor = KeyboardMonitor(bk.input_environment)
        bk.kbd_monitor.start()
    except Exception as e:
        print(f"[agent] 键盘监听启动失败（{e}），退格同步不可用")

    if not options.no_serial:
        from agent.main import make_serial_handlers
        on_text, on_cmd = make_serial_handlers(
            buf,
            history=history,
            input_environment=bk.input_environment,
        )
        bk.reader = SerialReader(on_text=on_text, on_cmd=on_cmd, port=options.port)
        bk.reader.start()
    else:
        print("[agent] 串口已禁用（纯软件模式）")

    bk.audio = build_audio_runtime(
        bk.cfg,
        buf,
        kbd_monitor=bk.kbd_monitor,
        status_window=status_window,
        history=history,
        input_environment=bk.input_environment,
    )
    return bk


def build_audio_runtime(
    cfg: dict,
    buf: TextBuffer,
    kbd_monitor=None,
    status_window=None,
    history: History | None = None,
    input_environment=None,
):
    stt_cfg = cfg.get("stt", {})
    audio_cfg = cfg.get("audio", {})
    polish_stt_cfg = cfg.get("polish_stt", {})
    provider = stt_cfg.get("provider", "")
    if provider == "typeup_backend" and not stt_cfg.get("access_token"):
        print("[typeup-auth-required] 请先登录 TypeUp 后端账号，跳过音频 STT")
        return None
    _no_api_key_providers = {"volcengine", "aliyun", "typeup_backend"}
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

    editor = None
    llm_cfg = cfg.get("llm", {})
    if is_typeup_backend_configured(llm_cfg):
        try:
            from agent.llm_editor import LLMEditor
            editor = LLMEditor(llm_cfg)
            print("[agent] LLM 编辑功能已启用")
        except Exception as e:
            import traceback
            print(f"[agent] LLM 初始化失败: {e}")
            traceback.print_exc()

    mode = audio_cfg.get("mode", "ptt")
    device = audio_cfg.get("device", "auto")

    ai_handler = None
    if editor:
        try:
            from agent.ai_handler import AIHandler
            from agent.memo_store import MemoStore
            ai_stt = stt
            ai_stt_cfg = cfg.get("ai_stt", {})
            if ai_stt_cfg:
                ai_stt = STTClient(ai_stt_cfg)
                print(f"[agent] AI 键 STT 使用独立 provider: {ai_stt_cfg.get('provider', 'openai')}")
            memo_store = MemoStore()
            ai_handler = AIHandler(
                ai_stt,
                editor,
                buf,
                memo_store=memo_store,
                status_window=status_window,
                history=history,
                input_environment=input_environment,
            )
            ai_key_name = audio_cfg.get("ai_key", "cmd_r")
            existing = memo_store.keys()
            if existing:
                print(f"[memo] 已加载 {len(existing)} 条备忘录: {'、'.join(existing)}")
            print(f"[agent] AI 键已启用，热键: {ai_key_name}")
        except Exception as e:
            print(f"[agent] AIHandler 初始化失败: {e}")

    from agent.main import make_utterance_handler
    utterance_stt = stt
    if polish_stt_cfg:
        try:
            base_stt = stt
            polish_stt = STTClient(polish_stt_cfg)
            print(
                f"[agent] 微润色 STT 使用独立 provider: "
                f"{polish_stt_cfg.get('provider', 'openai')}"
            )

            class _PolishAwareSTT:
                def transcribe(self, pcm: bytes) -> str:
                    return base_stt.transcribe(pcm)

                def transcribe_polished(self, pcm: bytes) -> str:
                    return polish_stt.transcribe(pcm)

            utterance_stt = _PolishAwareSTT()
        except Exception as e:
            print(f"[agent] 微润色 STT 初始化失败，回退主 STT: {e}")
    on_utterance = make_utterance_handler(
        utterance_stt,
        buf,
        kbd_mon=kbd_monitor,
        editor=editor,
        status_window=status_window,
        history=history,
        input_environment=input_environment,
    )

    if mode == "ptt":
        try:
            from agent.push_to_talk import PushToTalk
        except ImportError as e:
            print(f"[agent] PTT 依赖缺失（{e}）")
            return None

        on_ai = ai_handler.handle if ai_handler else None
        on_ai_key_dwn = ai_handler.on_ai_key_down if ai_handler else None

        ptt = PushToTalk(
            on_utterance=on_utterance,
            on_ai_utterance=on_ai,
            on_ai_key_down=on_ai_key_dwn,
            ptt_key=audio_cfg.get("ptt_key", "right_alt"),
            ai_key=audio_cfg.get("ai_key", "cmd_r"),
            toggle_key=audio_cfg.get("toggle_key"),
            device=device,
            status_window=status_window,
            kbd_monitor=kbd_monitor,
        )
        ptt.start()
        return ptt

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
