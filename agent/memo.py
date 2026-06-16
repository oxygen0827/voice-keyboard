"""Memo operation rules for Instruction Mode."""

from dataclasses import dataclass
import re
from typing import Literal, Protocol


class MemoStore(Protocol):
    def save(self, key: str, value: str) -> None:
        ...

    def get(self, key: str) -> str | None:
        ...

    def delete(self, key: str) -> bool:
        ...

    def keys(self) -> list[str]:
        ...


MemoOperationAction = Literal["show", "insert"]
MemoResolutionStatus = Literal["exact", "unique", "ambiguous", "none"]


@dataclass(frozen=True)
class MemoOperationResult:
    action: MemoOperationAction
    message: str = ""
    text: str = ""

    @classmethod
    def show(cls, message: str) -> "MemoOperationResult":
        return cls("show", message=message)

    @classmethod
    def insert(cls, text: str) -> "MemoOperationResult":
        return cls("insert", text=text)


@dataclass(frozen=True)
class MemoEditCommand:
    target: str
    old: str
    new: str


@dataclass(frozen=True)
class MemoRecord:
    key: str
    value: str = ""
    aliases: tuple[str, ...] = ()
    value_type: str = ""
    sensitive: bool = False


@dataclass(frozen=True)
class MemoResolution:
    status: MemoResolutionStatus
    key: str = ""
    candidates: tuple[str, ...] = ()
    query: str = ""
    value_type: str = ""

    @property
    def can_recall(self) -> bool:
        return self.status in {"exact", "unique"} and bool(self.key)

    def feedback(self) -> str:
        if self.status == "ambiguous" and self.candidates:
            return f"找到多个备忘：{'、'.join(self.candidates)}，请说得更具体"
        return "没有找到匹配的备忘"


class Memo:
    def __init__(self, store: MemoStore | None):
        self._store = store

    def save(self, key: str, value: str, selected: str = "") -> MemoOperationResult:
        if self._store is None:
            return MemoOperationResult.show("备忘功能未启用")
        key = (key or "").strip()
        final_value = selected.strip() or (value or "").strip()
        if not key:
            return MemoOperationResult.show("没听清楚要记成什么名字")
        if not final_value:
            return MemoOperationResult.show("没有要记的内容，请先选中或在话里说出来")
        self._store.save(key, final_value)
        print(f"[memo] 已保存 {key!r} ({_value_log_summary(key, final_value)})")
        return MemoOperationResult.show(f"已记住「{key}」")

    def recall(self, key: str) -> MemoOperationResult:
        if self._store is None:
            return MemoOperationResult.show("备忘功能未启用")
        key = (key or "").strip()
        if not key:
            return MemoOperationResult.show("没听清楚要查什么")
        value = self._store.get(key)
        if value is None:
            return MemoOperationResult.show(f"没记过「{key}」")
        print(f"[memo] 读取 {key!r} ({_value_log_summary(key, value)})")
        return MemoOperationResult.insert(value)

    def list_all(self) -> MemoOperationResult:
        if self._store is None:
            return MemoOperationResult.show("备忘功能未启用")
        keys = self._store.keys()
        if not keys:
            return MemoOperationResult.show("备忘是空的")
        lines = [f"{key}: {redact_memo_value(key, self._store.get(key) or '')}" for key in keys]
        print(f"[memo] 列出 {len(keys)} 条")
        return MemoOperationResult.insert("\n".join(lines))

    def delete(self, key: str) -> MemoOperationResult:
        if self._store is None:
            return MemoOperationResult.show("备忘功能未启用")
        key = (key or "").strip()
        if not key:
            return MemoOperationResult.show("没听清楚要删哪一条")
        if self._store.delete(key):
            print(f"[memo] 已删除 {key!r}")
            return MemoOperationResult.show(f"已忘掉「{key}」")
        return MemoOperationResult.show(f"没记过「{key}」")

    def edit_text(self, target: str, old: str, new: str) -> MemoOperationResult:
        if self._store is None:
            return MemoOperationResult.show("备忘功能未启用")
        target = (target or "").strip()
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new:
            return MemoOperationResult.show("没听清楚要把什么改成什么")
        keys = self._store.keys()
        candidates = _memo_edit_candidates(keys, self._store.get, target, old)
        if not candidates:
            return MemoOperationResult.show("没有找到要编辑的备忘")
        if len(candidates) > 1:
            return MemoOperationResult.show(
                f"找到多个备忘：{'、'.join(candidates)}，请说得更具体"
            )
        key = candidates[0]
        value = self._store.get(key) or ""
        new_key = _replace_term(key, old, new)
        new_value = _replace_term(value, old, new)
        if new_key == key and new_value == value:
            return MemoOperationResult.show(f"没有在「{key}」里找到「{old}」")
        self._store.save(new_key, new_value)
        if new_key != key:
            self._store.delete(key)
        print(
            "[memo] 已编辑 "
            f"{key!r} -> {new_key!r} ({_value_log_summary(new_key, new_value)})"
        )
        return MemoOperationResult.show(f"已更新「{new_key}」")


@dataclass(frozen=True)
class MemoMatcher:
    """Matches spoken memory requests to saved Memo names."""

    minimum_overlap: int = 2
    minimum_key_score: float = 0.7
    minimum_request_score: float = 0.6

    def match_key(self, text: str, keys: tuple[str, ...]) -> str | None:
        records = tuple(MemoRecord(key=key) for key in keys)
        result = MemoResolver(
            minimum_overlap=self.minimum_overlap,
            minimum_key_score=self.minimum_key_score,
            minimum_request_score=self.minimum_request_score,
        ).resolve(text, records)
        return result.key if result.can_recall else None


@dataclass(frozen=True)
class _ScoredMemoCandidate:
    record: MemoRecord
    score: float
    match_kind: str
    value_type: str


@dataclass(frozen=True)
class MemoResolver:
    minimum_overlap: int = 2
    minimum_key_score: float = 0.7
    minimum_request_score: float = 0.6
    unique_threshold: float = 0.78
    ambiguity_margin: float = 0.08

    def resolve(
        self,
        text: str,
        records: tuple[MemoRecord, ...],
    ) -> MemoResolution:
        query = extract_memo_query(text)
        query_text = normalize_memo_text(query)
        if len(query_text) < self.minimum_overlap or not records:
            return MemoResolution("none", query=query)

        candidates = [
            candidate for record in records
            if (candidate := self._score_record(query_text, record)) is not None
        ]
        if not candidates:
            return MemoResolution("none", query=query)

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        top = candidates[0]
        tied = [
            candidate for candidate in candidates
            if top.score - candidate.score <= self.ambiguity_margin
        ]
        if len(tied) > 1:
            return MemoResolution(
                "ambiguous",
                candidates=tuple(candidate.record.key for candidate in tied),
                query=query,
                value_type=top.value_type,
            )
        if top.match_kind == "exact":
            return MemoResolution(
                "exact",
                key=top.record.key,
                candidates=(top.record.key,),
                query=query,
                value_type=top.value_type,
            )
        if top.score >= self.unique_threshold:
            return MemoResolution(
                "unique",
                key=top.record.key,
                candidates=(top.record.key,),
                query=query,
                value_type=top.value_type,
            )
        return MemoResolution("none", query=query)

    def _score_record(
        self,
        query_text: str,
        record: MemoRecord,
    ) -> _ScoredMemoCandidate | None:
        key_text = normalize_memo_text(record.key)
        value_type = record.value_type or detect_memo_value_type(record.key, record.value)
        query_type = detect_memo_query_type(query_text)
        name_aliases = _record_name_aliases(record)
        type_aliases = _record_type_aliases(value_type)
        for alias in name_aliases:
            if alias and query_text == alias:
                return _ScoredMemoCandidate(record, 1.0, "exact", value_type)

        best_score = 0.0
        best_kind = "fuzzy"
        for alias in name_aliases:
            score = _substring_score(query_text, alias)
            if score > best_score:
                best_score = score
                best_kind = "alias"

        if query_type and query_type == value_type:
            type_score = 0.9 if query_text in type_aliases else 0.84
            if type_score > best_score:
                best_score = type_score
                best_kind = "type"

        fuzzy_score = self._fuzzy_score(query_text, key_text)
        if fuzzy_score > best_score:
            best_score = fuzzy_score
            best_kind = "fuzzy"

        if best_score <= 0:
            return None
        return _ScoredMemoCandidate(record, best_score, best_kind, value_type)

    def _fuzzy_score(self, query_text: str, key_text: str) -> float:
        if len(query_text) < self.minimum_overlap or len(key_text) < self.minimum_overlap:
            return 0.0
        if _is_generic_type_alias(key_text) and key_text != query_text:
            return 0.0
        query_chars = set(query_text)
        key_chars = set(key_text)
        overlap = len(key_chars & query_chars)
        if overlap < self.minimum_overlap:
            return 0.0
        key_score = overlap / len(key_chars)
        request_score = overlap / max(len(query_chars), 1)
        if key_score < self.minimum_key_score and request_score < self.minimum_request_score:
            return 0.0
        return max(key_score, request_score)


def fuzzy_match_memo_key(text: str, keys: tuple[str, ...]) -> str | None:
    return MemoMatcher().match_key(text, keys)


def memo_key_matches_request(text: str, key: str) -> bool:
    return fuzzy_match_memo_key(text, (key,)) == key


def resolve_memo_key(
    text: str,
    records: tuple[MemoRecord, ...],
) -> MemoResolution:
    return MemoResolver().resolve(text, records)


def parse_memo_edit_command(text: str) -> MemoEditCommand | None:
    cleaned = str(text or "").strip().strip("。！？!? ")
    recent = _parse_recent_memo_edit_command(cleaned)
    if recent is not None:
        return recent
    patterns = (
        r"^把(.+?)这条(?:记忆|备忘|备忘)(?:里|中的)?(.+?)(?:改成|替换成|写成)(.+)$",
        r"^(?:把)?(?:记忆|备忘|备忘)(?:里|中的)?(.+?)(?:改成|替换成|写成)(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned)
        if not match:
            continue
        groups = tuple(_clean_memo_edit_part(group) for group in match.groups())
        if len(groups) == 3:
            target, old, new = groups
        else:
            target, old, new = "", groups[0], groups[1]
        if old and new and old != new:
            return MemoEditCommand(target=target, old=old, new=new)
    return None


def _parse_recent_memo_edit_command(cleaned: str) -> MemoEditCommand | None:
    if not cleaned.startswith("刚刚说的"):
        return None
    body = cleaned[len("刚刚说的"):]
    marker_match = re.search(r"(实际上是|其实是|应该是|要写成|写成|改成)", body)
    if not marker_match:
        return None
    before = body[:marker_match.start()]
    new = _clean_memo_edit_part(body[marker_match.end():])
    split_match = re.search(r"[，,]?(那个|其中的)", before)
    if split_match:
        target = _clean_memo_edit_part(before[:split_match.start()])
        old = _clean_memo_edit_part(before[split_match.end():])
    else:
        target = ""
        old = _clean_memo_edit_part(before)
    if old and new and old != new:
        return MemoEditCommand(target=target, old=old, new=new)
    return None


_QUERY_PREFIXES = (
    "查询一下", "查一下", "查询", "插入一下", "输入一下", "填入一下", "插入", "输入", "填入",
)
_QUERY_SUFFIXES = (
    "是什么", "是多少", "是啥", "是哪个", "叫什么", "叫啥", "多少", "什么", "是", "呢", "啊", "呀",
)
_DROP_WORDS = (
    "我的", "我", "一下", "给我", "帮我", "请", "请问", "打出来", "说出来",
)
_PUNCTUATION_RE = re.compile(r"[\s,，.。?？!！:：;；\"'“”‘’（）()【】\[\]《》<>]+")
_SENSITIVE_KEY_HINTS = (
    "api", "apikey", "api_key", "密钥", "秘钥", "key", "token", "password", "passwd", "密码",
    "secret", "ssh", "私钥", "访问", "服务器",
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bssh\s+-p\s+\d+\s+\S+@\S+", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_-]{32,}\b"),
    re.compile(r"(token|api[_ -]?key|password|secret)=", re.IGNORECASE),
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_TYPE_ALIASES = {
    "contact.email": ("邮箱", "邮箱地址", "电子邮箱", "邮件地址", "email"),
    "contact.phone": ("手机号", "手机号码", "电话号码", "联系电话", "电话"),
    "repo_url": ("仓库地址", "项目地址", "代码仓库", "仓库链接", "github"),
    "ssh_endpoint": ("ssh", "ssh地址", "服务器地址", "访问地址"),
    "api_key": ("api密钥", "密钥", "秘钥", "apikey", "api_key", "key", "token"),
    "address": ("地址", "住址", "地点", "位置"),
}


def extract_memo_query(text: str) -> str:
    query = (text or "").strip()
    for prefix in _QUERY_PREFIXES:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            break
    for word in _DROP_WORDS:
        query = query.replace(word, "")
    changed = True
    while changed and query:
        changed = False
        for suffix in _QUERY_SUFFIXES:
            if query.endswith(suffix):
                query = query[: -len(suffix)].strip()
                changed = True
                break
    return query


def normalize_memo_text(text: str) -> str:
    normalized = _PUNCTUATION_RE.sub("", text or "").lower()
    replacements = (
        ("手机号码", "手机号"),
        ("电话号码", "手机号"),
        ("联系电话", "手机号"),
        ("手机", "手机号"),
        ("电话", "手机号"),
        ("住址", "地址"),
        ("家庭地址", "地址"),
        ("电子邮箱", "邮箱"),
        ("邮件地址", "邮箱"),
        ("邮箱地址", "邮箱"),
    )
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    return normalized


def detect_memo_query_type(query_text: str) -> str:
    text = normalize_memo_text(query_text)
    for value_type, aliases in _TYPE_ALIASES.items():
        if any(normalize_memo_text(alias) == text for alias in aliases):
            return value_type
    if any(marker in text for marker in ("邮箱", "email")):
        return "contact.email"
    if any(marker in text for marker in ("手机号", "联系电话")):
        return "contact.phone"
    if "仓库" in text and any(marker in text for marker in ("地址", "链接", "url")):
        return "repo_url"
    if "ssh" in text or "服务器" in text:
        return "ssh_endpoint"
    if any(marker in text for marker in ("api", "密钥", "秘钥", "token")):
        return "api_key"
    if any(marker in text for marker in ("地址", "住址", "地点")):
        return "address"
    return ""


def detect_memo_value_type(key: str, value: str) -> str:
    key_text = normalize_memo_text(key)
    value_text = value or ""
    if "github.com" in value_text.lower() or ("仓库" in key_text and "地址" in key_text):
        return "repo_url"
    if re.search(r"\bssh\b", value_text, re.IGNORECASE) or "服务器" in key_text:
        return "ssh_endpoint"
    if _EMAIL_RE.search(value_text) or any(marker in key_text for marker in ("邮箱", "email")):
        return "contact.email"
    if _PHONE_RE.search(value_text) or any(marker in key_text for marker in ("手机号", "联系电话")):
        return "contact.phone"
    if is_sensitive_memo(key, value) and any(
        marker in key_text for marker in ("api", "密钥", "秘钥", "key", "token")
    ):
        return "api_key"
    if any(marker in key_text for marker in ("地址", "住址", "地点", "位置")):
        return "address"
    return "text"


def redact_memo_value(key: str, value: str) -> str:
    if is_sensitive_memo(key, value):
        return "[已隐藏]"
    return value


def is_sensitive_memo(key: str, value: str) -> bool:
    key_text = normalize_memo_text(key)
    value_text = value or ""
    if any(hint in key_text for hint in _SENSITIVE_KEY_HINTS):
        return True
    return any(pattern.search(value_text) for pattern in _SENSITIVE_VALUE_PATTERNS)


def _value_log_summary(key: str, value: str) -> str:
    visibility = "sensitive, hidden" if is_sensitive_memo(key, value) else "value hidden"
    return f"{visibility}, {len(value or '')} chars"


def _record_name_aliases(record: MemoRecord) -> tuple[str, ...]:
    return _merge_aliases((record.key, *record.aliases))


def _record_type_aliases(value_type: str) -> tuple[str, ...]:
    return _merge_aliases(_TYPE_ALIASES.get(value_type, ()))


def _merge_aliases(raw_aliases: tuple[str, ...]) -> tuple[str, ...]:
    aliases = []
    for alias in raw_aliases:
        normalized = normalize_memo_text(alias)
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return tuple(aliases)


def _is_generic_type_alias(text: str) -> bool:
    generic_aliases = {
        normalize_memo_text(alias)
        for aliases in _TYPE_ALIASES.values()
        for alias in aliases
    }
    return text in generic_aliases


def _substring_score(query_text: str, alias: str) -> float:
    if len(query_text) < 2 or len(alias) < 2:
        return 0.0
    if query_text in alias:
        return min(0.96, len(query_text) / max(len(alias), 1) + 0.45)
    if alias in query_text:
        return min(0.96, len(alias) / max(len(query_text), 1) + 0.45)
    return 0.0


def _memo_edit_candidates(keys: list[str], get_value, target: str, old: str) -> list[str]:
    target_text = normalize_memo_text(target)
    old_text = normalize_memo_text(old)
    matches = []
    for key in keys:
        value = get_value(key) or ""
        key_text = normalize_memo_text(key)
        value_text = normalize_memo_text(value)
        if target_text and target_text not in key_text and target_text not in value_text:
            continue
        if old_text in key_text or old_text in value_text:
            matches.append(key)
    return matches


def _replace_term(text: str, old: str, new: str) -> str:
    if not text or not old:
        return text
    flags = re.IGNORECASE if old.isascii() else 0
    return re.sub(re.escape(old), new, text, flags=flags)


def _clean_memo_edit_part(text: str) -> str:
    return str(text or "").strip().strip("\"'“”‘’ ，,")
