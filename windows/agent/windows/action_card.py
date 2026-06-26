"""Small Windows AI action card for command confirmation."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk


class WindowsActionCard:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def show(
        self,
        *,
        transcript: str,
        target_source: str,
        operation_kind: str,
        preview_text: str = "",
        auto_executed: bool = False,
        on_confirm=None,
        on_cancel=None,
        on_undo=None,
    ) -> bool:
        with self._lock:
            self._thread = threading.Thread(
                target=self._run,
                kwargs={
                    "transcript": transcript,
                    "target_source": target_source,
                    "operation_kind": operation_kind,
                    "preview_text": preview_text,
                    "auto_executed": auto_executed,
                    "on_confirm": on_confirm,
                    "on_cancel": on_cancel,
                    "on_undo": on_undo,
                },
                daemon=True,
                name="WindowsActionCard",
            )
            self._thread.start()
        return True

    def _run(
        self,
        *,
        transcript: str,
        target_source: str,
        operation_kind: str,
        preview_text: str,
        auto_executed: bool,
        on_confirm,
        on_cancel,
        on_undo,
    ) -> None:
        root = tk.Tk()
        root.title("AI Action")
        root.attributes("-topmost", True)
        try:
            root.attributes("-toolwindow", True)
        except Exception:
            pass
        root.geometry("+520+520")
        root.resizable(False, False)
        _try_no_activate(root)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        title = "AI 已执行" if auto_executed else "AI 动作需要确认"
        ttk.Label(frame, text=title, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"识别：{_clip(transcript, 80)}").pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, text=f"目标：{target_source or 'none'}  动作：{operation_kind}").pack(anchor="w")
        preview = tk.Text(frame, width=54, height=5, wrap="word")
        preview.insert("1.0", preview_text or "")
        preview.configure(state="disabled")
        preview.pack(fill="both", pady=(8, 8))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        def close() -> None:
            try:
                root.destroy()
            except Exception:
                pass

        def confirm() -> None:
            if on_confirm:
                threading.Thread(target=on_confirm, daemon=True).start()
            close()

        def cancel() -> None:
            if on_cancel:
                on_cancel()
            close()

        def undo() -> None:
            if on_undo:
                threading.Thread(target=on_undo, daemon=True).start()
            close()

        if auto_executed:
            ttk.Button(buttons, text="撤销", command=undo).pack(side="left")
            ttk.Button(buttons, text="关闭", command=close).pack(side="right")
            root.after(6500, close)
        else:
            ttk.Button(buttons, text="确认", command=confirm).pack(side="left")
            ttk.Button(buttons, text="取消", command=cancel).pack(side="left", padx=6)
            if on_undo:
                ttk.Button(buttons, text="撤销", command=undo).pack(side="right")
        root.mainloop()


def _clip(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[:limit] + "..."


def _try_no_activate(root: tk.Tk) -> None:
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        get_style = ctypes.windll.user32.GetWindowLongW
        set_style = ctypes.windll.user32.SetWindowLongW
        ex_style = get_style(hwnd, -20)
        set_style(hwnd, -20, ex_style | 0x08000000 | 0x00000080)
    except Exception:
        pass
