"""Speaker-flow construction and cheap prefilters for audio probes."""

from __future__ import annotations

import re
from typing import Any

_NON_ASCII = re.compile(r"[^\x00-\x7f]")
_COMMON_EN = frozenset(
    """
    the a an and or but if then so to of in on at for with from by as is was are were be been being
    i you he she it we they me him her us them my your his its our their this that these those
    not no yes yeah um uh like just really very also can could would should will shall may might
    what when where who why how which about into over after before up down out all any some more
    most other new only own same such than too both few many much own under again further once
    """.split()
)


def build_speaker_flows(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    """Build uninterrupted same-speaker flows from timed words."""
    words = transcript.get("words") or []
    flows: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    idx = 0
    for w in words:
        if not isinstance(w, dict):
            continue
        text = str(w.get("text") or "").strip()
        if not text:
            continue
        try:
            start = int(w.get("start_ms") or 0)
            end = int(w.get("end_ms") or start)
        except (TypeError, ValueError):
            continue
        spk = str(w.get("speaker_id") or w.get("speaker") or "spk_unknown")
        conf = w.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_f = None
        if cur is None or cur["speaker_id"] != spk:
            if cur is not None:
                flows.append(cur)
            idx += 1
            cur = {
                "speaker_flow_id": f"sf_{idx:03d}",
                "speaker_id": spk,
                "start_ms": start,
                "end_ms": end,
                "words": [w],
                "text_parts": [text],
                "confidences": [conf_f] if conf_f is not None else [],
            }
        else:
            cur["end_ms"] = max(int(cur["end_ms"]), end)
            cur["words"].append(w)
            cur["text_parts"].append(text)
            if conf_f is not None:
                cur["confidences"].append(conf_f)
    if cur is not None:
        flows.append(cur)
    for f in flows:
        f["text"] = " ".join(f.pop("text_parts"))
        confs = f.pop("confidences")
        f["mean_confidence"] = (sum(confs) / len(confs)) if confs else None
        f["duration_ms"] = max(0, int(f["end_ms"]) - int(f["start_ms"]))
        f["word_count"] = len(f.get("words") or [])
    return flows


def _has_non_ascii(text: str) -> bool:
    return bool(_NON_ASCII.search(text or ""))


def _uncommon_ratio(text: str) -> float:
    toks = [t.strip(".,!?;:\"'()[]").lower() for t in (text or "").split()]
    toks = [t for t in toks if t.isalpha() and len(t) > 2]
    if not toks:
        return 0.0
    uncommon = sum(1 for t in toks if t not in _COMMON_EN and t.isascii())
    return uncommon / len(toks)


def flow_signals(flow: dict[str, Any], *, low_conf: float = 0.85) -> dict[str, Any]:
    text = str(flow.get("text") or "")
    mean_c = flow.get("mean_confidence")
    low = mean_c is not None and float(mean_c) < low_conf
    non_ascii = _has_non_ascii(text)
    uncommon = _uncommon_ratio(text)
    words = flow.get("words") or []
    brick_count = 0
    for w in words:
        if not isinstance(w, dict):
            continue
        try:
            c = float(w.get("confidence")) if w.get("confidence") is not None else 1.0
        except (TypeError, ValueError):
            c = 1.0
        if c < low_conf:
            brick_count += 1
    one_off = brick_count == 1 and not non_ascii and uncommon < 0.15 and len(words) >= 4
    return {
        "non_ascii": non_ascii,
        "uncommon_ratio": uncommon,
        "low_confidence": low,
        "brick_count": brick_count,
        "one_off_miscomprehension": one_off,
        "long_turn": int(flow.get("duration_ms") or 0) >= 20_000,
        "stress_proxy": (1.0 - float(mean_c)) if mean_c is not None else (0.4 if non_ascii else 0.2),
    }


def passes_prefilter(prefilter: str, signals: dict[str, Any]) -> tuple[bool, str]:
    if prefilter == "escalation_only":
        return False, "escalation_only"
    if prefilter == "vernacular_candidate":
        if signals.get("one_off_miscomprehension"):
            return False, "one_off_miscomprehension"
        if signals.get("non_ascii") or signals.get("uncommon_ratio", 0) >= 0.2:
            return True, "vernacular_signal"
        if signals.get("low_confidence") and signals.get("brick_count", 0) >= 2:
            return True, "brick_cluster"
        return False, "no_vernacular_signal"
    if prefilter == "stress_or_salience":
        if float(signals.get("stress_proxy") or 0) >= 0.25 or signals.get("long_turn"):
            return True, "stress"
        return False, "low_stress"
    if prefilter == "low_confidence":
        if signals.get("low_confidence") or signals.get("brick_count", 0) >= 2:
            return True, "low_confidence"
        return False, "ok_confidence"
    if prefilter == "long_turn":
        return (True, "long_turn") if signals.get("long_turn") else (False, "short_turn")
    if prefilter == "always_sample":
        return True, "always_sample"
    return True, "default"
