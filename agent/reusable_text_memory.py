"""Reusable Text Memory operation rules for Instruction Mode."""

from dataclasses import dataclass
from typing import Literal, Protocol


class ReusableTextMemoryStore(Protocol):
    def save(self, key: str, value: str) -> None:
        ...

    def get(self, key: str) -> str | None:
        ...

    def delete(self, key: str) -> bool:
        ...

    def keys(self) -> list[str]:
        ...


MemoryAction = Literal["show", "insert"]


@dataclass(frozen=True)
class MemoryOperationResult:
    action: MemoryAction
    message: str = ""
    text: str = ""

    @classmethod
    def show(cls, message: str) -> "MemoryOperationResult":
        return cls("show", message=message)

    @classmethod
    def insert(cls, text: str) -> "MemoryOperationResult":
        return cls("insert", text=text)


class ReusableTextMemory:
    def __init__(self, store: ReusableTextMemoryStore | None):
        self._store = store

    def save(self, key: str, value: str, selected: str = "") -> MemoryOperationResult:
        if self._store is None:
            return MemoryOperationResult.show("可复用文本功能未启用")
        key = (key or "").strip()
        final_value = selected.strip() or (value or "").strip()
        if not key:
            return MemoryOperationResult.show("没听清楚要记成什么名字")
        if not final_value:
            return MemoryOperationResult.show("没有要记的内容，请先选中或在话里说出来")
        self._store.save(key, final_value)
        print(f"[memo] 已保存 {key!r} = {final_value!r}")
        return MemoryOperationResult.show(f"已记住「{key}」")

    def recall(self, key: str) -> MemoryOperationResult:
        if self._store is None:
            return MemoryOperationResult.show("可复用文本功能未启用")
        key = (key or "").strip()
        if not key:
            return MemoryOperationResult.show("没听清楚要查什么")
        value = self._store.get(key)
        if value is None:
            return MemoryOperationResult.show(f"没记过「{key}」")
        print(f"[memo] 读取 {key!r} = {value!r}")
        return MemoryOperationResult.insert(value)

    def list_all(self) -> MemoryOperationResult:
        if self._store is None:
            return MemoryOperationResult.show("可复用文本功能未启用")
        keys = self._store.keys()
        if not keys:
            return MemoryOperationResult.show("可复用文本是空的")
        lines = [f"{key}: {self._store.get(key)}" for key in keys]
        print(f"[memo] 列出 {len(keys)} 条")
        return MemoryOperationResult.insert("\n".join(lines))

    def delete(self, key: str) -> MemoryOperationResult:
        if self._store is None:
            return MemoryOperationResult.show("可复用文本功能未启用")
        key = (key or "").strip()
        if not key:
            return MemoryOperationResult.show("没听清楚要删哪一条")
        if self._store.delete(key):
            print(f"[memo] 已删除 {key!r}")
            return MemoryOperationResult.show(f"已忘掉「{key}」")
        return MemoryOperationResult.show(f"没记过「{key}」")


@dataclass(frozen=True)
class ReusableTextMemoryMatcher:
    """Matches spoken memory requests to saved Reusable Text Memory names."""

    minimum_overlap: int = 2
    minimum_key_score: float = 0.7
    minimum_request_score: float = 0.6

    def match_key(self, text: str, keys: tuple[str, ...]) -> str | None:
        text_chars = set(text or "")
        best_key = None
        best_score = 0.0
        for key in keys:
            key_chars = set(key)
            if len(key_chars) < self.minimum_overlap:
                continue
            overlap = len(key_chars & text_chars)
            if overlap < self.minimum_overlap:
                continue
            key_score = overlap / len(key_chars)
            request_score = overlap / max(len(text_chars), 1)
            if key_score < self.minimum_key_score and request_score < self.minimum_request_score:
                continue
            score = max(key_score, request_score)
            if score > best_score:
                best_score = score
                best_key = key
        return best_key


def fuzzy_match_memory_key(text: str, keys: tuple[str, ...]) -> str | None:
    return ReusableTextMemoryMatcher().match_key(text, keys)
