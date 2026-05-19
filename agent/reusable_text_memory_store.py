"""Simple JSON store for Reusable Text Memory."""

import json
import threading
from pathlib import Path
from typing import Optional


class ReusableTextMemoryStore:
    def __init__(self, path: Optional[Path] = None):
        self._path = path or Path.home() / ".voice-keyboard" / "reusable_text_memory.json"
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        path = self._path
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._data = raw if isinstance(raw, dict) else {}
        except Exception as e:
            print(f"[reusable-text-memory] 读取失败 {path}: {e}")
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()
                return True
            return False

    def keys(self) -> list[str]:
        return list(self._data.keys())
