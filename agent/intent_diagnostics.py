"""Intent diagnostics helpers for desktop review UIs."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from agent.intent_overrides import append_override, find_override, normalize_intent
from agent.intent_training import load_samples, update_sample_review


_WRONG_REVIEW_LABELS = {
    "wrong_intent",
    "wrong_target",
    "unsafe_should_confirm",
    "missing_shortcut",
    "unclear",
}


def load_diagnostics_rows(
    source: Path | str,
    *,
    limit: int = 300,
    intent_type: str = "",
    review_state: str = "",
) -> list[dict]:
    rows = load_samples(source, limit=0)
    indexed = []
    for index, row in enumerate(rows):
        if intent_type and str(row.get("intent_type", "")) != intent_type:
            continue
        review_label = str(row.get("review_label", "") or "")
        if review_state == "reviewed" and not review_label:
            continue
        if review_state == "unreviewed" and review_label:
            continue
        view_row = dict(row)
        view_row["source_index"] = index
        indexed.append(view_row)
    if limit > 0:
        indexed = indexed[-limit:]
    return list(reversed(indexed))


def save_diagnostics_review(
    source: Path | str,
    row: Mapping,
    *,
    label: str,
    note: str = "",
    corrected_intent: Mapping | None = None,
    override_path: Path | str | None = None,
) -> dict:
    index = int(row["source_index"])
    clean_intent = normalize_intent(corrected_intent) if corrected_intent else None
    updated = update_sample_review(
        source,
        index,
        label=label,
        note=note,
        corrected_intent=clean_intent,
    )
    if clean_intent:
        kwargs = {}
        if override_path is not None:
            kwargs["path"] = override_path
        append_override(str(row.get("text") or updated.get("text") or ""), clean_intent, **kwargs)
    view_row = dict(updated)
    view_row["source_index"] = index
    return view_row


def summarize_diagnostics(
    source: Path | str,
    *,
    override_path: Path | str | None = None,
) -> dict:
    rows = load_samples(source, limit=0)
    summary = {
        "total": len(rows),
        "reviewed": 0,
        "unreviewed": 0,
        "correct": 0,
        "wrong": 0,
        "corrected": 0,
        "override_covered": 0,
        "wrong_by_intent": {},
        "accuracy_label": "已标注正确率 -",
    }
    for row in rows:
        review_label = str(row.get("review_label", "") or "")
        if review_label:
            summary["reviewed"] += 1
        else:
            summary["unreviewed"] += 1
        if review_label == "correct":
            summary["correct"] += 1
        elif review_label in _WRONG_REVIEW_LABELS:
            summary["wrong"] += 1
            intent_type = str(row.get("intent_type", "") or "unknown")
            summary["wrong_by_intent"][intent_type] = summary["wrong_by_intent"].get(intent_type, 0) + 1
        corrected = row.get("corrected_intent")
        if isinstance(corrected, Mapping) and corrected.get("type"):
            summary["corrected"] += 1
            kwargs = {}
            if override_path is not None:
                kwargs["path"] = override_path
            if find_override(str(row.get("text", "")), **kwargs):
                summary["override_covered"] += 1
    if summary["reviewed"] > 0:
        accuracy = summary["correct"] / summary["reviewed"] * 100
        summary["accuracy_label"] = f"已标注正确率 {accuracy:.1f}%"
    return summary
