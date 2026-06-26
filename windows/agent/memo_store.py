"""Local JSON store for Memo records."""

import json
import threading
import time
from pathlib import Path
from typing import Optional


class MemoStore:
    def __init__(self, path: Optional[Path] = None, legacy_path: Optional[Path] = None):
        self._path = path or Path.home() / ".voice-keyboard" / "memo.json"
        if legacy_path is not None:
            self._legacy_paths = (legacy_path,)
        elif path is None:
            root = Path.home() / ".voice-keyboard"
            self._legacy_paths = (
                root / "reusable_text_memory.json",
                root / "memos.json",
            )
        else:
            self._legacy_paths = ()
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            self._data = self._read_data(self._path)
            return
        for legacy_path in self._legacy_paths:
            if not legacy_path.exists():
                continue
            self._data = self._read_data(legacy_path)
            if self._data:
                self._save()
            return

    def _read_data(self, path: Path) -> dict[str, dict]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            return {
                str(key): self._normalize_record(value)
                for key, value in raw.items()
                if str(key).strip()
            }
        except Exception as e:
            print(f"[memo] read failed {path}: {e}")
            return {}

    def _normalize_record(self, value) -> dict:
        if isinstance(value, dict) and "value" in value:
            aliases = value.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [item.strip() for item in aliases.split(",") if item.strip()]
            return {
                "value": str(value.get("value") or ""),
                "value_type": str(value.get("value_type") or ""),
                "aliases": [str(item) for item in aliases if str(item).strip()],
                "sensitive": bool(value.get("sensitive", False)),
                "updated_at": float(value.get("updated_at") or 0.0),
            }
        return {
            "value": str(value or ""),
            "value_type": "",
            "aliases": [],
            "sensitive": False,
            "updated_at": 0.0,
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(
        self,
        key: str,
        value: str,
        *,
        value_type: str = "",
        aliases: list[str] | tuple[str, ...] = (),
        sensitive: bool | None = None,
    ) -> None:
        with self._lock:
            previous = self._data.get(key, {})
            self._data[key] = {
                "value": str(value or ""),
                "value_type": value_type or previous.get("value_type", ""),
                "aliases": list(aliases or previous.get("aliases", []) or []),
                "sensitive": (
                    bool(sensitive)
                    if sensitive is not None
                    else bool(previous.get("sensitive", False))
                ),
                "updated_at": time.time(),
            }
            self._save()

    def get(self, key: str) -> Optional[str]:
        record = self._data.get(key)
        if record is None:
            return None
        return str(record.get("value") or "")

    def metadata(self, key: str) -> dict:
        record = self._data.get(key) or {}
        return {
            "value_type": str(record.get("value_type") or ""),
            "aliases": tuple(record.get("aliases") or ()),
            "sensitive": bool(record.get("sensitive", False)),
            "updated_at": float(record.get("updated_at") or 0.0),
        }

    def records(self) -> list[dict]:
        return [
            {
                "key": key,
                "value": self.get(key) or "",
                **self.metadata(key),
            }
            for key in self.keys()
        ]

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()
                return True
            return False

    def keys(self) -> list[str]:
        return list(self._data.keys())
