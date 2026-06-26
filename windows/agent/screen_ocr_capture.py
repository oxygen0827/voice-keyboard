"""Screen OCR fallback for text capture on macOS.

This is a conservative Capture Path for applications that do not expose their
focused text through Accessibility.  It only returns recognized text; callers
decide whether the text is trustworthy enough for learning.
"""

from __future__ import annotations

import difflib
import platform
import re
from dataclasses import dataclass

from agent.focused_text_capture import FocusedTextProbe, FocusedTextSnapshot


_OS = platform.system()
Quartz = None
NSWorkspace = None
_CJK_TERM_RE = re.compile(r"[\u3400-\u9fff]{2,}")

if _OS == "Darwin":
    import Quartz
    from AppKit import NSWorkspace


@dataclass(frozen=True)
class OcrTextLine:
    text: str
    confidence: float = 0.0


def capture_screen_text(
    *,
    reference_text: str = "",
    max_chars: int = 4000,
) -> FocusedTextSnapshot:
    """OCR the frontmost macOS window and return recognized text diagnostics."""
    if _OS != "Darwin" or Quartz is None:
        return FocusedTextSnapshot(
            source="ocr_unsupported",
            confidence="unsupported",
            probes=(FocusedTextProbe("platform", False, detail=_OS),),
        )

    app_name, bundle_id, pid = _frontmost_app_identity()
    probes: list[FocusedTextProbe] = []
    image, image_source, capture_detail, capture_window_id = _capture_frontmost_image(pid)
    probes.append(FocusedTextProbe("ScreenCapture", image is not None, detail=capture_detail))
    if image is None:
        return FocusedTextSnapshot(
            source="ocr_unavailable",
            confidence="unsupported",
            app_name=app_name,
            bundle_id=bundle_id,
            pid=pid,
            probes=tuple(probes),
        )

    lines, ocr_detail = _recognize_text(image)
    probes.append(FocusedTextProbe("VisionOCR", bool(lines), detail=ocr_detail))
    raw_text = "\n".join(line.text for line in lines if line.text)
    text = _select_relevant_ocr_text(
        raw_text,
        reference_text=reference_text,
        max_chars=max_chars,
    )
    if _frontmost_app_may_be_voice_keyboard(app_name, bundle_id) and _looks_like_voice_keyboard_ui(raw_text):
        own_window_ids = _window_ids_for_pid(pid)
        fallback_text, fallback_source, fallback_probes = _fallback_below_window_ocr_text(
            frontmost_window_id=capture_window_id,
            fallback_window_ids=own_window_ids,
            reference_text=reference_text,
            max_chars=max_chars,
        )
        probes.extend(fallback_probes)
        if not fallback_text:
            fallback_text, fallback_source, fallback_probes = _fallback_visible_ocr_text(
                excluded_pid=pid,
                reference_text=reference_text,
                max_chars=max_chars,
            )
            probes.extend(fallback_probes)
        if fallback_text:
            text = fallback_text
            image_source = fallback_source
        else:
            text = ""
            image_source = "ocr_self_ui"
    else:
        bottom_text, bottom_probes = _bottom_region_ocr_text(
            image,
            reference_text=reference_text,
            max_chars=max_chars,
        )
        probes.extend(bottom_probes)
        if bottom_text:
            text = bottom_text
            image_source = f"{image_source}_bottom"
    return FocusedTextSnapshot(
        text=text,
        source=image_source,
        confidence="medium" if text else "unsupported",
        app_name=app_name,
        bundle_id=bundle_id,
        pid=pid,
        probes=tuple(probes),
    )


def _frontmost_app_identity() -> tuple[str, str, int | None]:
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return "", "", None
        return (
            str(app.localizedName() or ""),
            str(app.bundleIdentifier() or ""),
            int(app.processIdentifier()) if app.processIdentifier() else None,
        )
    except Exception:
        return "", "", None


def _frontmost_app_may_be_voice_keyboard(app_name: str, bundle_id: str) -> bool:
    value = f"{app_name or ''} {bundle_id or ''}".lower()
    markers = (
        "voice keyboard",
        "voicekeyboard",
        "python",
        "org.python",
    )
    return any(marker in value for marker in markers)


def _capture_frontmost_image(pid: int | None):
    window_id = _frontmost_window_id(pid)
    if window_id is not None:
        image = _capture_window_image(window_id)
        if image is not None:
            width = _image_width(image)
            height = _image_height(image)
            return image, "ocr_window", f"window={window_id};size={width}x{height}", window_id
    image = _capture_screen_image()
    if image is not None:
        width = _image_width(image)
        height = _image_height(image)
        return image, "ocr_screen", f"screen;size={width}x{height}", None
    return None, "ocr_unavailable", "capture_failed", None


def _frontmost_window_id(pid: int | None) -> int | None:
    ids = _window_ids_for_pid(pid)
    return ids[0] if ids else None


def _window_ids_for_pid(pid: int | None) -> tuple[int, ...]:
    rows = _window_info_rows()
    if not rows or not pid:
        return ()
    ids = []
    for row in rows:
        if not _window_row_matches_pid(row, pid):
            continue
        window_id = _window_id_from_row(row)
        if window_id is not None:
            ids.append(window_id)
    return tuple(ids)


def _window_info_rows():
    try:
        options = Quartz.kCGWindowListOptionOnScreenOnly | getattr(
            Quartz,
            "kCGWindowListExcludeDesktopElements",
            16,
        )
        return Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    except Exception:
        return []


def _window_row_matches_pid(row, pid: int) -> bool:
    owner_key = getattr(Quartz, "kCGWindowOwnerPID", "kCGWindowOwnerPID")
    try:
        if int(row.get(owner_key, -1)) != int(pid):
            return False
    except Exception:
        return False
    return _window_id_from_row(row) is not None


def _window_id_from_row(row) -> int | None:
    number_key = getattr(Quartz, "kCGWindowNumber", "kCGWindowNumber")
    layer_key = getattr(Quartz, "kCGWindowLayer", "kCGWindowLayer")
    bounds_key = getattr(Quartz, "kCGWindowBounds", "kCGWindowBounds")
    try:
        if int(row.get(layer_key, 0) or 0) != 0:
            return None
        bounds = row.get(bounds_key) or {}
        width = float(bounds.get("Width", 0) or 0)
        height = float(bounds.get("Height", 0) or 0)
        if width < 80 or height < 40:
            return None
        return int(row.get(number_key))
    except Exception:
        return None


def _fallback_visible_window_id(excluded_pid: int | None = None) -> int | None:
    ids = _fallback_visible_window_ids(excluded_pid=excluded_pid)
    return ids[0] if ids else None


def _fallback_visible_window_ids(excluded_pid: int | None = None) -> list[int]:
    owner_key = getattr(Quartz, "kCGWindowOwnerPID", "kCGWindowOwnerPID")
    ids = []
    for row in _window_info_rows():
        try:
            if excluded_pid is not None and int(row.get(owner_key, -1)) == int(excluded_pid):
                continue
        except Exception:
            pass
        window_id = _window_id_from_row(row)
        if window_id is not None:
            ids.append(window_id)
    return ids


def _capture_fallback_visible_image(excluded_pid: int | None = None):
    window_id = _fallback_visible_window_id(excluded_pid=excluded_pid)
    if window_id is None:
        return None, "", ""
    image = _capture_window_image(window_id)
    if image is None:
        return None, "", ""
    width = _image_width(image)
    height = _image_height(image)
    return image, "ocr_window_fallback", f"window={window_id};size={width}x{height};fallback=non_frontmost"


def _fallback_below_window_ocr_text(
    *,
    frontmost_window_id: int | None,
    fallback_window_ids: tuple[int, ...] = (),
    reference_text: str = "",
    max_chars: int = 4000,
) -> tuple[str, str, tuple[FocusedTextProbe, ...]]:
    probes: list[FocusedTextProbe] = []
    window_ids = _dedupe_window_ids(
        (frontmost_window_id,) + tuple(fallback_window_ids or ())
    )
    if not window_ids:
        probes.append(
            FocusedTextProbe(
                "ScreenCaptureBelowWindow",
                False,
                detail="no_frontmost_window_id",
            )
        )
        return "", "", tuple(probes)

    attempts = 0
    for window_id in window_ids:
        attempts += 1
        image = _capture_below_window_image(window_id)
        if image is None:
            probes.append(
                FocusedTextProbe(
                    "ScreenCaptureBelowWindow",
                    False,
                    detail=f"window={window_id};capture_failed;attempt={attempts}",
                )
            )
            continue

        width = _image_width(image)
        height = _image_height(image)
        probes.append(
            FocusedTextProbe(
                "ScreenCaptureBelowWindow",
                True,
                detail=f"below_window={window_id};size={width}x{height};attempt={attempts}",
            )
        )
        lines, ocr_detail = _recognize_text(image)
        probes.append(FocusedTextProbe("VisionOCRBelowWindow", bool(lines), detail=ocr_detail))
        raw_text = "\n".join(line.text for line in lines if line.text)
        if not raw_text or _looks_like_voice_keyboard_ui(raw_text):
            continue

        selected = _select_relevant_ocr_text(
            raw_text,
            reference_text=reference_text,
            max_chars=max_chars,
        )
        if not _ocr_text_matches_reference(
            reference_text,
            selected or raw_text,
            allow_repeated_correction_shape=True,
        ):
            continue
        return selected, "ocr_screen_below_window", tuple(probes)

    probes.append(
        FocusedTextProbe(
            "ScreenCaptureBelowWindow",
            False,
            detail=f"attempts={attempts};no_relevant_below_window",
        )
    )
    return "", "", tuple(probes)


def _fallback_visible_ocr_text(
    *,
    excluded_pid: int | None = None,
    reference_text: str = "",
    max_chars: int = 4000,
) -> tuple[str, str, tuple[FocusedTextProbe, ...]]:
    probes: list[FocusedTextProbe] = []
    attempts = 0
    for window_id in _fallback_visible_window_ids(excluded_pid=excluded_pid)[:8]:
        attempts += 1
        image = _capture_window_image(window_id)
        if image is None:
            continue
        lines, ocr_detail = _recognize_text(image)
        raw_text = "\n".join(line.text for line in lines if line.text)
        if not raw_text or _looks_like_voice_keyboard_ui(raw_text):
            continue
        selected = _select_relevant_ocr_text(
            raw_text,
            reference_text=reference_text,
            max_chars=max_chars,
        )
        if not _ocr_text_matches_reference(reference_text, selected or raw_text):
            continue
        width = _image_width(image)
        height = _image_height(image)
        probes.append(
            FocusedTextProbe(
                "ScreenCaptureFallback",
                True,
                detail=f"window={window_id};size={width}x{height};attempts={attempts}",
            )
        )
        probes.append(
            FocusedTextProbe(
                "VisionOCRFallback",
                bool(lines),
                detail=ocr_detail,
            )
        )
        return selected, "ocr_window_fallback", tuple(probes)
    probes.append(
        FocusedTextProbe(
            "ScreenCaptureFallback",
            False,
            detail=f"attempts={attempts};no_relevant_window",
        )
    )
    return "", "", tuple(probes)


def _capture_window_image(window_id: int):
    try:
        return Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            window_id,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )
    except Exception:
        return None


def _capture_below_window_image(window_id: int):
    try:
        return Quartz.CGWindowListCreateImage(
            Quartz.CGRectInfinite,
            getattr(Quartz, "kCGWindowListOptionOnScreenBelowWindow", 4),
            window_id,
            Quartz.kCGWindowImageDefault,
        )
    except Exception:
        return None


def _bottom_region_ocr_text(
    image,
    *,
    reference_text: str = "",
    max_chars: int = 4000,
) -> tuple[str, tuple[FocusedTextProbe, ...]]:
    probes: list[FocusedTextProbe] = []
    if not reference_text:
        return "", tuple(probes)
    bottom = _capture_bottom_region_image(image)
    if bottom is None:
        probes.append(FocusedTextProbe("ScreenCaptureBottomRegion", False, detail="crop_failed"))
        return "", tuple(probes)
    width = _image_width(bottom)
    height = _image_height(bottom)
    probes.append(
        FocusedTextProbe(
            "ScreenCaptureBottomRegion",
            True,
            detail=f"size={width}x{height}",
        )
    )
    lines, ocr_detail = _recognize_text(bottom)
    probes.append(FocusedTextProbe("VisionOCRBottomRegion", bool(lines), detail=ocr_detail))
    raw_text = "\n".join(line.text for line in lines if line.text)
    selected = _select_changed_repeated_cjk_line(raw_text, reference_text)
    if not selected:
        return "", tuple(probes)
    if not _ocr_text_matches_reference(
        reference_text,
        selected,
        allow_repeated_correction_shape=True,
    ):
        return "", tuple(probes)
    return selected[-max_chars:], tuple(probes)


def _capture_bottom_region_image(image, *, fraction: float = 0.42):
    try:
        width = _image_width(image)
        height = _image_height(image)
        if width <= 0 or height <= 0:
            return None
        crop_height = max(1, int(height * max(0.1, min(float(fraction), 0.9))))
        y = max(0, height - crop_height)
        rect = Quartz.CGRectMake(0, y, width, crop_height)
        return Quartz.CGImageCreateWithImageInRect(image, rect)
    except Exception:
        return None


def _dedupe_window_ids(values: tuple[int | None, ...]) -> tuple[int, ...]:
    seen = set()
    ids = []
    for value in values:
        if value is None:
            continue
        try:
            window_id = int(value)
        except Exception:
            continue
        if window_id in seen:
            continue
        seen.add(window_id)
        ids.append(window_id)
    return tuple(ids)


def _capture_screen_image():
    try:
        return Quartz.CGWindowListCreateImage(
            Quartz.CGRectInfinite,
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
            Quartz.kCGWindowImageDefault,
        )
    except Exception:
        return None


def _recognize_text(image) -> tuple[tuple[OcrTextLine, ...], str]:
    try:
        request = Quartz.VNRecognizeTextRequest.alloc().init()
        _configure_text_request(request)
        handler = Quartz.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
        result = handler.performRequests_error_([request], None)
    except Exception as e:
        return (), f"exception={e}"

    ok = True
    err = None
    if isinstance(result, tuple):
        ok = bool(result[0])
        err = result[1] if len(result) > 1 else None
    elif result is False:
        ok = False
    if not ok:
        return (), f"perform_failed={err}"

    lines: list[OcrTextLine] = []
    for observation in list(request.results() or []):
        try:
            candidates = list(observation.topCandidates_(1) or [])
        except Exception:
            continue
        for candidate in candidates[:1]:
            text = str(candidate.string() or "").strip()
            if not text:
                continue
            try:
                confidence = float(candidate.confidence())
            except Exception:
                confidence = 0.0
            lines.append(OcrTextLine(text=text, confidence=confidence))
    if not lines:
        return (), "lines=0"
    avg = sum(line.confidence for line in lines) / len(lines)
    return tuple(lines), f"lines={len(lines)};avg={avg:.2f}"


def _configure_text_request(request) -> None:
    for selector, value in (
        ("setRecognitionLanguages_", ["zh-Hans", "zh-Hant", "en-US"]),
        ("setAutomaticallyDetectsLanguage_", True),
        ("setUsesLanguageCorrection_", True),
        ("setRecognitionLevel_", 0),
    ):
        try:
            getattr(request, selector)(value)
        except Exception:
            continue


def _select_relevant_ocr_text(
    text: str,
    *,
    reference_text: str = "",
    max_chars: int = 4000,
) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    reference = str(reference_text or "").strip()
    repeated_line = _select_repeated_cjk_line(value, reference)
    if repeated_line:
        return repeated_line[-max_chars:]
    if len(value) <= max_chars:
        return value
    if not reference:
        return value[-max_chars:]
    matcher = difflib.SequenceMatcher(a=reference, b=value, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
    if not blocks:
        return value[-max_chars:]
    start = max(0, min(block.b for block in blocks) - max_chars // 3)
    end = min(len(value), start + max_chars)
    return value[start:end].strip()


def _looks_like_voice_keyboard_ui(text: str) -> bool:
    value = str(text or "")
    if "Voice Keyboard" not in value:
        return False
    markers = ("设置", "快捷键", "历史", "词典", "输入诊断", "权限")
    return sum(1 for marker in markers if marker in value) >= 2


def _select_repeated_cjk_line(text: str, reference_text: str) -> str:
    changed = _select_changed_repeated_cjk_line(text, reference_text)
    if changed:
        return changed
    if _normalized_text(reference_text) and _normalized_text(reference_text) in _normalized_text(text):
        return reference_text
    return ""


def _select_changed_repeated_cjk_line(text: str, reference_text: str) -> str:
    if not reference_text:
        return ""
    reference_terms = _repeated_cjk_term_counts(reference_text)
    if not reference_terms:
        return ""
    best_line = ""
    best_score = 0.0
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if len(line) < 2 or _looks_like_voice_keyboard_ui(line):
            continue
        if _normalized_text(line) == _normalized_text(reference_text):
            continue
        value_terms = _repeated_cjk_term_counts(line)
        if not value_terms:
            continue
        for reference, reference_count in reference_terms.items():
            if reference_count < 2:
                continue
            for value, value_count in value_terms.items():
                if value_count < 2:
                    continue
                if abs(len(reference) - len(value)) > 1:
                    continue
                similarity = _cjk_term_similarity(reference, value)
                if similarity < 0.3:
                    continue
                score = similarity + min(reference_count, value_count) * 0.1
                if score > best_score:
                    best_score = score
                    best_line = line
    return best_line


def _ocr_text_matches_reference(
    reference_text: str,
    text: str,
    *,
    allow_repeated_correction_shape: bool = False,
) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    reference = str(reference_text or "").strip()
    if not reference:
        return True
    if reference in value:
        return True
    reference_terms = _cjk_terms(reference)
    value_terms = _cjk_terms(value)
    if not reference_terms or not value_terms:
        return False
    for reference_term in reference_terms:
        for value_term in value_terms:
            if reference_term in value_term or value_term in reference_term:
                return True
            ratio = difflib.SequenceMatcher(
                a=reference_term,
                b=value_term,
                autojunk=False,
            ).ratio()
            if ratio >= 0.6:
                return True
    if allow_repeated_correction_shape and _looks_like_repeated_cjk_correction(
        reference,
        value,
    ):
        return True
    return False


def _cjk_terms(text: str) -> tuple[str, ...]:
    return tuple(_CJK_TERM_RE.findall(str(text or "")))


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _looks_like_repeated_cjk_correction(reference_text: str, text: str) -> bool:
    reference_terms = _repeated_cjk_term_counts(reference_text)
    value_terms = _repeated_cjk_term_counts(text)
    if not reference_terms or not value_terms:
        return False
    for reference, reference_count in reference_terms.items():
        if reference_count < 2:
            continue
        for value, value_count in value_terms.items():
            if value_count < 2:
                continue
            if abs(len(reference) - len(value)) > 1:
                continue
            if min(len(reference), len(value)) < 2:
                continue
            if _cjk_term_similarity(reference, value) >= 0.3:
                return True
    return False


def _repeated_cjk_term_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for term in _cjk_terms(text):
        if 2 <= len(term) <= 8:
            counts[term] = counts.get(term, 0) + 1
    return counts


def _cjk_term_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 1.0
    if set(left) & set(right):
        return difflib.SequenceMatcher(a=left, b=right, autojunk=False).ratio()
    return 0.0


def _image_width(image) -> int:
    try:
        return int(Quartz.CGImageGetWidth(image))
    except Exception:
        return 0


def _image_height(image) -> int:
    try:
        return int(Quartz.CGImageGetHeight(image))
    except Exception:
        return 0
