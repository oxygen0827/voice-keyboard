"""Runtime composition for the desktop Voice Keyboard Engine."""

from dataclasses import dataclass
import sys

from agent.config import load as load_config
from agent.history import History
from agent.input_environment import TyperInputEnvironment
from agent.serial_reader import SerialReader
from agent.speech_interpretation_providers import SpeechInterpretationProviderFactory
from agent.text_buffer import TextBuffer


@dataclass(frozen=True)
class RuntimeOptions:
    no_serial: bool = False
    port: str | None = None


class RuntimeBackend:
    """Restartable runtime components."""

    def __init__(self):
        self.cfg = None
        self.reader = None
        self.audio = None
        self.ime_monitor = None
        self.input_environment = None
        self.hotkeys = {}

    def stop(self):
        for attr in ("audio", "ime_monitor", "reader"):
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
    bk.input_environment = TyperInputEnvironment(buf)

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
        status_window=status_window,
        history=history,
        input_environment=bk.input_environment,
    )
    bk.ime_monitor = getattr(bk.audio, "_correction_ime_monitor", None)
    audio_cfg = bk.cfg.get("audio", {})
    bk.hotkeys = {
        "ptt_key": audio_cfg.get("ptt_key", "right_alt"),
        "ai_key": audio_cfg.get("ai_key", default_ai_key()),
    }
    return bk



def default_ai_key() -> str:
    return "alt_r" if sys.platform == "win32" else "cmd_r"

def build_audio_runtime(
    cfg: dict,
    buf: TextBuffer,
    status_window=None,
    history: History | None = None,
    input_environment=None,
):
    audio_cfg = cfg.get("audio", {})
    mode = audio_cfg.get("mode", "ptt")
    device = audio_cfg.get("device", "auto")
    providers = SpeechInterpretationProviderFactory().create_provider_set(cfg)
    if providers is None:
        return None
    ai_handler = None
    if providers.text_operation_editor is not None and providers.instruction_stt is not None:
        try:
            from agent.ai_handler import AIHandler
            from agent.ai_intent import IntentFallbackOptions
            from agent.intent_training import IntentTrainingConfig, IntentTrainingRecorder
            from agent.memo_store import MemoStore
            from agent.operation_confirmation import make_operation_confirmation
            memo_store = MemoStore()
            instruction_cfg = cfg.get("instruction_mode", {})
            ai_handler = AIHandler(
                providers.instruction_stt,
                providers.text_operation_editor,
                buf,
                memo_store=memo_store,
                status_window=status_window,
                history=history,
                input_environment=input_environment,
                intent_fallbacks=IntentFallbackOptions.from_config(
                    instruction_cfg.get("intent_fallbacks", {})
                ),
                intent_training=IntentTrainingRecorder(
                    IntentTrainingConfig.from_config(instruction_cfg)
                ),
                confirm_operation=make_operation_confirmation(
                    status_window=status_window,
                ),
            )
            ai_key_name = audio_cfg.get("ai_key", default_ai_key())
            existing = memo_store.keys()
            if existing:
                print(f"[memo] 已加载 {len(existing)} 条备忘: {'、'.join(existing)}")
            print(f"[agent] AI 键已启用，热键: {ai_key_name}")
        except Exception as e:
            print(f"[agent] AIHandler 初始化失败: {e}")

    from agent.main import make_utterance_handler
    correction_tracker = None
    utterance_handler_or_mode = make_utterance_handler(
        providers.utterance_stt,
        buf,
        editor=providers.text_operation_editor,
        status_window=status_window,
        history=history,
        input_environment=input_environment,
        correction_config=cfg.get("correction_memory", {}),
        return_mode=True,
    )
    if hasattr(utterance_handler_or_mode, "handle_utterance"):
        on_utterance = utterance_handler_or_mode.handle_utterance
        correction_tracker = getattr(utterance_handler_or_mode, "correction_tracker", None)
        correction_scheduler = getattr(utterance_handler_or_mode, "correction_scheduler", None)
    else:
        on_utterance = utterance_handler_or_mode
        correction_scheduler = None

    if mode == "ptt":
        try:
            from agent.push_to_talk import PushToTalk
        except ImportError as e:
            print(f"[agent] PTT 依赖缺失（{e}）")
            return None

        on_ai = ai_handler.handle if ai_handler else None
        def on_manual_key_press(key) -> None:
            if correction_tracker is None:
                return
            correction_tracker.record_key_press(key)
            if (
                correction_scheduler is not None
                and hasattr(correction_scheduler, "schedule_after_edit")
            ):
                correction_scheduler.schedule_after_edit()

        def on_manual_key_release(_key) -> None:
            if (
                correction_tracker is not None
                and correction_scheduler is not None
                and hasattr(correction_scheduler, "schedule_after_edit")
            ):
                correction_scheduler.schedule_after_edit()

        def on_committed_text(text: str) -> None:
            if (cfg.get("correction_memory", {}) or {}).get("debug", False):
                preview = str(text or "").replace("\n", "\\n")[:40]
                print(f"[ime] committed text captured={preview!r}")
            if correction_tracker is None:
                return
            committed = correction_tracker.record_committed_text(text)
            if (
                committed
                and
                correction_scheduler is not None
                and hasattr(correction_scheduler, "schedule_after_edit")
            ):
                correction_scheduler.schedule_after_edit()

        ptt = PushToTalk(
            on_utterance=on_utterance,
            on_ai_utterance=on_ai,
            ptt_key=audio_cfg.get("ptt_key", "right_alt"),
            ai_key=audio_cfg.get("ai_key", default_ai_key()),
            toggle_key=audio_cfg.get("toggle_key"),
            device=device,
            xiao_ble_options=audio_cfg.get("xiao_ble", {}),
            on_key_press=(
                on_manual_key_press
                if correction_tracker is not None
                else None
            ),
            on_key_release=(
                on_manual_key_release
                if correction_tracker is not None
                else None
            ),
            status_window=status_window,
        )
        ptt.start()
        if correction_tracker is not None:
            try:
                from agent.ime_commit_monitor import ImeCommitMonitor

                ime_monitor = ImeCommitMonitor(on_committed_text)
                ime_monitor.start()
                ptt._correction_ime_monitor = ime_monitor
            except Exception as e:
                print(f"[ime] monitor init failed: {e}")
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
