"""Personal Lexicon for local speech normalization and reusable text aliases."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import threading
from typing import Optional


@dataclass(frozen=True)
class LexiconRule:
    spoken: str
    written: str
    kind: str = "correction"


@dataclass(frozen=True)
class SelectionLexiconLearning:
    spoken: str
    kind: str = "alias"


class PersonalLexicon:
    def __init__(self, path: Optional[Path] = None):
        self._path = path or Path.home() / ".voice-keyboard" / "personal_lexicon.json"
        self._lock = threading.Lock()
        self._rules: dict[str, LexiconRule] = {}
        self._load()

    def normalize(self, text: str) -> str:
        normalized = str(text or "")
        for rule in sorted(self._rules.values(), key=lambda item: len(item.spoken), reverse=True):
            if not rule.spoken or rule.spoken == rule.written:
                continue
            normalized = normalized.replace(rule.spoken, rule.written)
        normalized = self._normalize_phonetic_aliases(normalized)
        return normalized

    def remember(self, spoken: str, written: str, kind: str = "correction") -> bool:
        spoken = _clean_term(spoken)
        written = _clean_term(written)
        if not spoken or not written or spoken == written:
            return False
        with self._lock:
            self._rules[spoken] = LexiconRule(spoken=spoken, written=written, kind=kind or "correction")
            self._save()
        print(f"[lexicon] 已记住 {spoken!r} -> {written!r} ({kind or 'correction'})")
        return True

    def remember_with_variants(self, spoken: str, written: str, kind: str = "correction") -> tuple[str, ...]:
        phonetic_kind = "phonetic_alias" if kind == "alias" else kind
        return (spoken,) if self.remember(spoken, written, phonetic_kind) else ()

    def forget(self, spoken: str) -> bool:
        spoken = _clean_term(spoken)
        if not spoken:
            return False
        with self._lock:
            if spoken not in self._rules:
                return False
            del self._rules[spoken]
            self._save()
        print(f"[lexicon] 已删除 {spoken!r}")
        return True

    def aliases_for(self, written: str) -> tuple[str, ...]:
        target = _clean_term(written)
        aliases = [
            rule.spoken for rule in self._rules.values()
            if rule.kind in {"alias", "phonetic_alias"} and rule.written == target
        ]
        return tuple(aliases)

    def rules(self) -> tuple[LexiconRule, ...]:
        return tuple(self._rules.values())

    def list_text(self) -> str:
        if not self._rules:
            return "个人词库是空的"
        return "\n".join(
            f"{rule.spoken} -> {rule.written} ({rule.kind})"
            for rule in self._rules.values()
        )

    def _normalize_phonetic_aliases(self, text: str) -> str:
        normalized = str(text or "")
        rules = [
            rule for rule in self._rules.values()
            if rule.kind == "phonetic_alias" and _phonetic_signature(rule.spoken)
        ]
        if not rules:
            return normalized
        for token in sorted(set(_candidate_phonetic_tokens(normalized)), key=len, reverse=True):
            token_signature = _phonetic_signature(token)
            if not token_signature:
                continue
            for rule in rules:
                if _phonetic_signatures_match(token_signature, _phonetic_signature(rule.spoken)):
                    normalized = normalized.replace(token, rule.written)
                    break
        return normalized

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._rules = _parse_rules(raw)
        except Exception as e:
            print(f"[lexicon] 读取失败 {self._path}: {e}")
            self._rules = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "rules": [
                {
                    "spoken": rule.spoken,
                    "written": rule.written,
                    "kind": rule.kind,
                }
                for rule in self._rules.values()
            ],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_lexicon_learning(text: str) -> LexiconRule | None:
    cleaned = str(text or "").strip().strip("。！？!? ")
    patterns = (
        (r"^以后(?:我)?说(.+?)(?:就是|就写成|写成|改成)(.+)$", "alias"),
        (r"^以后听到(.+?)(?:就是|就写成|写成|改成)(.+)$", "alias"),
        (r"^不是(.+?)(?:，|,)?是(.+)$", "correction"),
        (r"^刚才那个词(?:是|写成)(.+)$", "correction"),
    )
    for pattern, kind in patterns:
        match = re.match(pattern, cleaned)
        if not match:
            continue
        if len(match.groups()) == 1:
            return None
        spoken = _clean_term(match.group(1))
        written = _clean_term(match.group(2))
        if spoken and written and spoken != written:
            return LexiconRule(spoken=spoken, written=written, kind=kind)
    return None


def parse_selection_lexicon_learning(text: str) -> SelectionLexiconLearning | None:
    cleaned = str(text or "").strip().strip("。！？!? ")
    patterns = (
        (r"^以后(?:我)?说(?:的)?(.+?)(?:就是|就写成|写成|改成)(?:这个词|选中的词|选中这个词|这个)$", "alias"),
        (r"^(?:这个词|选中的词|选中这个词)(?:读作|念作|叫做)(.+)$", "alias"),
        (r"^以后听到(?:的)?(.+?)(?:就是|就写成|写成|改成)(?:这个词|选中的词|选中这个词|这个)$", "alias"),
    )
    for pattern, kind in patterns:
        match = re.match(pattern, cleaned)
        if not match:
            continue
        spoken = _clean_term(match.group(1))
        if spoken:
            return SelectionLexiconLearning(spoken=spoken, kind=kind)
    return None


def parse_lexicon_forget(text: str) -> str:
    cleaned = str(text or "").strip().strip("。！？!? ")
    patterns = (
        r"^(?:忘记|删除|删掉|清除)(?:个人词库里)?(?:我说)?(.+?)(?:这个说法|这个词|的说法)?$",
        r"^以后不要把(.+?)(?:改成|写成|当成).+$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned)
        if match:
            return _clean_term(match.group(1))
    return ""


def is_lexicon_list_request(text: str) -> bool:
    cleaned = str(text or "").strip()
    return "个人词库" in cleaned and any(marker in cleaned for marker in ("列出", "查看", "看一下", "有什么"))


def _parse_rules(raw) -> dict[str, LexiconRule]:
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = raw.get("rules", [])
    else:
        rows = []
    rules: dict[str, LexiconRule] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        spoken = _clean_term(str(row.get("spoken", "")))
        written = _clean_term(str(row.get("written", "")))
        kind = str(row.get("kind", "correction") or "correction")
        if spoken and written and spoken != written:
            rules[spoken] = LexiconRule(spoken=spoken, written=written, kind=kind)
    return rules


def _clean_term(text: str) -> str:
    return str(text or "").strip().strip("\"'“”‘’。！？!? ，,")


_PHONETIC_CONFUSIONS = (
    ("g", "k"),
    ("n", ""),
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def _candidate_phonetic_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for match in _CJK_RE.finditer(text or ""):
        segment = match.group(0)
        for size in range(min(6, len(segment)), 1, -1):
            for start in range(0, len(segment) - size + 1):
                token = segment[start:start + size]
                if token not in tokens:
                    tokens.append(token)
    return tuple(tokens)


def _phonetic_signature(text: str) -> str:
    cleaned = _clean_term(text)
    try:
        from pypinyin import Style, lazy_pinyin
        return "".join(lazy_pinyin(cleaned, style=Style.NORMAL, errors="default"))
    except Exception:
        return cleaned


def _phonetic_signatures_match(candidate: str, reference: str) -> bool:
    if not candidate or not reference:
        return False
    return _relaxed_signature(candidate) == _relaxed_signature(reference)


def _relaxed_signature(signature: str) -> str:
    relaxed = signature
    for old, new in _PHONETIC_CONFUSIONS:
        relaxed = relaxed.replace(old, new)
    return relaxed
