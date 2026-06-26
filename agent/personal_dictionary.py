"""Local personal dictionary store for correction and hotword hints."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from agent.memo import _SENSITIVE_VALUE_PATTERNS


DEFAULT_DICTIONARY_PATH = Path.home() / ".voice-keyboard" / "personal_dictionary.json"


@dataclass(frozen=True)
class DictionaryEntry:
    term: str
    phrase: str = ""
    source: str = "manual"
    confidence: float = 1.0
    updated_at: float = 0.0


class PersonalDictionaryStore:
    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_DICTIONARY_PATH
        self._data: dict[str, dict] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[dictionary] read failed {self._path}: {e}")
            self._data = {}
            return
        if not isinstance(raw, dict):
            self._data = {}
            return
        self._data = {
            str(key): self._normalize_record(key, value)
            for key, value in raw.items()
            if str(key).strip()
        }

    def _normalize_record(self, key: object, value: object) -> dict:
        if isinstance(value, dict):
            term = str(value.get("term") or key or "").strip()
            phrase = str(value.get("phrase") or "").strip()
            source = str(value.get("source") or "manual").strip() or "manual"
            try:
                confidence = float(value.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 1.0
            try:
                updated_at = float(value.get("updated_at") or 0.0)
            except (TypeError, ValueError):
                updated_at = 0.0
        else:
            term = str(value or key or "").strip()
            phrase = ""
            source = "legacy"
            confidence = 1.0
            updated_at = 0.0
        return {
            "term": term,
            "phrase": phrase,
            "source": source,
            "confidence": confidence,
            "updated_at": updated_at,
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def entries(self) -> list[DictionaryEntry]:
        return [
            DictionaryEntry(
                term=record["term"],
                phrase=record.get("phrase", ""),
                source=record.get("source", "manual"),
                confidence=float(record.get("confidence", 1.0)),
                updated_at=float(record.get("updated_at", 0.0)),
            )
            for _key, record in sorted(self._data.items())
        ]

    def terms(self) -> list[str]:
        return [entry.term for entry in self.entries()]

    def hotwords(self, limit: int = 100) -> list[str]:
        words = []
        for entry in self.entries():
            term = entry.term.strip()
            if term and term not in words:
                words.append(term)
            if len(words) >= limit:
                break
        return words

    def prompt_hint(self, limit: int = 30) -> str:
        hints = []
        for entry in self.entries()[:limit]:
            term = entry.term.strip()
            if not term:
                continue
            phrase = entry.phrase.strip()
            hints.append(f"{term}（{phrase}）" if phrase else term)
        if not hints:
            return ""
        return (
            "个人词典候选词（只在音频发音明显匹配时参考，"
            "不要因为候选词存在而凭空输出）："
            + "、".join(hints)
        )

    def get(self, term: str) -> DictionaryEntry | None:
        record = self._data.get(term)
        if record is None:
            return None
        return DictionaryEntry(
            term=record["term"],
            phrase=record.get("phrase", ""),
            source=record.get("source", "manual"),
            confidence=float(record.get("confidence", 1.0)),
            updated_at=float(record.get("updated_at", 0.0)),
        )

    def save(
        self,
        term: str,
        *,
        phrase: str = "",
        source: str = "manual",
        confidence: float = 1.0,
    ) -> None:
        term = str(term or "").strip()
        phrase = str(phrase or "").strip()
        if not term:
            raise ValueError("term is required")
        if _looks_sensitive(term) or _looks_sensitive(phrase):
            raise ValueError("sensitive values cannot be saved to dictionary")
        self._data[term] = {
            "term": term,
            "phrase": phrase,
            "source": str(source or "manual"),
            "confidence": float(confidence),
            "updated_at": time.time(),
        }
        self._save()

    def delete(self, term: str) -> bool:
        term = str(term or "").strip()
        if term not in self._data:
            return False
        del self._data[term]
        self._save()
        return True


def _looks_sensitive(value: str) -> bool:
    return any(pattern.search(value or "") for pattern in _SENSITIVE_VALUE_PATTERNS)
