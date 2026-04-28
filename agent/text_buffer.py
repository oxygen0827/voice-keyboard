"""
记录 Agent 打出的文字历史，供语音编辑功能使用。

只记录通过 Agent 打出去的内容，用户手动输入的内容不在此范围。
"""


class TextBuffer:
    def __init__(self, max_entries: int = 20):
        self._entries: list[str] = []
        self._max = max_entries

    def push(self, text: str) -> None:
        if text:
            self._entries.append(text)
            if len(self._entries) > self._max:
                self._entries.pop(0)

    def pop_last(self) -> str:
        return self._entries.pop() if self._entries else ""

    def replace_last(self, new_text: str) -> None:
        if self._entries:
            self._entries[-1] = new_text

    @property
    def last(self) -> str:
        return self._entries[-1] if self._entries else ""

    @property
    def session(self) -> str:
        """当前 session 打出的全部文字（拼接）。"""
        return "".join(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def __bool__(self) -> bool:
        return bool(self._entries)
