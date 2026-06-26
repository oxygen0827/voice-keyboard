"""Runtime handler factories for desktop Voice Keyboard Engine composition."""

from agent.dictation_mode import make_utterance_handler as _make_dictation_utterance_handler
from agent.history import History
from agent.input_environment import TyperInputEnvironment
from agent.text_buffer import TextBuffer


def make_serial_handlers(
    buf: TextBuffer,
    history: History | None = None,
    input_environment=None,
):
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


def make_utterance_handler(
    stt_client,
    buf: TextBuffer,
    editor=None,
    status_window=None,
    history: History | None = None,
    input_environment=None,
    correction_memory=None,
    correction_tracker=None,
    correction_scheduler=None,
    correction_config=None,
    learning=None,
    return_mode: bool = False,
):
    return _make_dictation_utterance_handler(
        stt_client,
        buf,
        editor=editor,
        status_window=status_window,
        history=history,
        input_environment=input_environment,
        correction_memory=correction_memory,
        correction_tracker=correction_tracker,
        correction_scheduler=correction_scheduler,
        correction_config=correction_config,
        learning=learning,
        return_mode=return_mode,
    )
