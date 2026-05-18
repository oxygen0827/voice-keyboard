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
            return MemoryOperationResult.show("备忘录功能未启用")
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
            return MemoryOperationResult.show("备忘录功能未启用")
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
            return MemoryOperationResult.show("备忘录功能未启用")
        keys = self._store.keys()
        if not keys:
            return MemoryOperationResult.show("备忘录是空的")
        lines = [f"{key}: {self._store.get(key)}" for key in keys]
        print(f"[memo] 列出 {len(keys)} 条")
        return MemoryOperationResult.insert("\n".join(lines))

    def delete(self, key: str) -> MemoryOperationResult:
        if self._store is None:
            return MemoryOperationResult.show("备忘录功能未启用")
        key = (key or "").strip()
        if not key:
            return MemoryOperationResult.show("没听清楚要删哪一条")
        if self._store.delete(key):
            print(f"[memo] 已删除 {key!r}")
            return MemoryOperationResult.show(f"已忘掉「{key}」")
        return MemoryOperationResult.show(f"没记过「{key}」")
