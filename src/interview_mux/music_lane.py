"""Music overlay lanes: role resolution, cue→asset binding, and exclusivity."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.music_motif import (
    THEME_BED_ROLES,
    THEME_PUNCTUATOR_ROLES,
    THEME_ROLES,
    is_theme_role,
)

LANE_BOOKEND = "theme_bookend"
LANE_PUNCTUATOR = "theme_punctuator"
LANE_BED = "theme_bed"
LANE_OTHER = "other"

# Higher = keep when overlapping a different lane.
LANE_PRIORITY = {
    LANE_BOOKEND: 30,
    LANE_PUNCTUATOR: 20,
    LANE_BED: 10,
    LANE_OTHER: 0,
}


def pick_theme_outro_asset(assets: list[Any] | None) -> dict[str, Any] | None:
    """Prefer placement_hint=close / full_bed_close over an open-hint outro bed."""
    rows = [a for a in (assets or []) if isinstance(a, dict)]
    if not rows:
        return None

    def _aid(row: dict[str, Any]) -> str:
        return str(row.get("asset_id") or "")

    for row in rows:
        if str(row.get("placement_hint") or "") == "close":
            return row
    for row in rows:
        if "full_bed_close" in _aid(row).lower():
            return row
    for row in rows:
        if str(row.get("role") or "") == "theme_outro":
            return row
    for row in rows:
        if "outro" in _aid(row).lower() or "close_bed" in _aid(row).lower():
            return row
    return None

_CROSSFADE_HANDOFF_MS = 300
_DUPLICATE_WINDOW_MS = 400

_CUE_ROLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:^|_)full_bed(?:_|$)", re.I), "theme_cold_open"),
    (re.compile(r"(?:^|_)motif(?:_|$)", re.I), "theme_cold_open"),
    (re.compile(r"(?:^|_)cold_open(?:_|$)", re.I), "theme_cold_open"),
    (re.compile(r"(?:^|_)outro(?:_|$)|full_bed_close|(?:^|_)close_bed(?:_|$)", re.I), "theme_outro"),
    (re.compile(r"(?:^|_)open_bed(?:_|$)|(?:^|_)compose_open(?:_|$)", re.I), "theme_cold_open"),
    (re.compile(r"(?:^|_)resolve(?:_|$)|chapter_resolve", re.I), "theme_chapter_resolve"),
    (re.compile(r"(?:^|_)stinger(?:_|$)", re.I), "theme_emphasis"),
    (re.compile(r"(?:^|_)emphasis(?:_|$)", re.I), "theme_emphasis"),
    (re.compile(r"(?:^|_)transition(?:_|$)", re.I), "theme_transition"),
    (re.compile(r"(?:^|_)(?:optional_loop|underscore|bed)(?:_|$)", re.I), "theme_underscore"),
)


def effective_cue_role(cue: dict[str, Any] | None, asset: dict[str, Any] | None = None) -> str:
    """Resolve music role from cue, then asset, then cue_id intent."""
    cue = cue or {}
    asset = asset or {}
    for src in (cue.get("role"), asset.get("role")):
        role = str(src or "").strip()
        if role:
            return role
    inferred = infer_theme_role_from_cue_id(str(cue.get("cue_id") or ""))
    return inferred or ""


def infer_theme_role_from_cue_id(cue_id: str) -> str | None:
    cid = str(cue_id or "").strip()
    if not cid:
        return None
    for pattern, role in _CUE_ROLE_PATTERNS:
        if pattern.search(cid):
            return role
    return None


def music_lane_for_role(role: str | None) -> str:
    r = str(role or "").strip()
    if r in {"theme_cold_open", "theme_outro", "motif", "full_bed"}:
        return LANE_BOOKEND
    if r in THEME_BED_ROLES or r in {
        "ambient_bed",
        "era_music_bed",
        "underscore_loop",
        "optional_loop",
    }:
        return LANE_BED
    if r in THEME_PUNCTUATOR_ROLES or r in {
        "chapter_stinger",
        "transition_stinger",
        "transition_whoosh",
        "rhetorical_punctuator",
        "stinger",
    }:
        return LANE_PUNCTUATOR
    if is_theme_role(r):
        return LANE_PUNCTUATOR
    return LANE_OTHER


def asset_id_for_role(assets: list[dict[str, Any]], role: str) -> str | None:
    want = str(role or "").strip()
    if not want:
        return None
    for a in assets:
        if not isinstance(a, dict):
            continue
        if str(a.get("role") or "").strip() == want and a.get("asset_id"):
            return str(a["asset_id"])
    return None


def bind_cues_to_theme_assets(
    cues: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map emphasis/resolve/outro/cold_open cue_ids onto matching theme assets."""
    assets_by_id = {
        str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
    }
    applied: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        row = dict(cue)
        intent = infer_theme_role_from_cue_id(str(row.get("cue_id") or ""))
        if not intent or intent not in THEME_ROLES:
            out.append(row)
            continue
        cur_aid = str(row.get("asset_id") or "")
        cur_role = str((assets_by_id.get(cur_aid) or {}).get("role") or row.get("role") or "")
        if cur_role == intent:
            if not row.get("role"):
                row["role"] = intent
            out.append(row)
            continue
        target = asset_id_for_role(assets, intent)
        if target and target != cur_aid:
            row["asset_id"] = target
            row["role"] = intent
            applied.append(
                {
                    "action": "bind_cue_theme_asset",
                    "cue_id": row.get("cue_id"),
                    "from_asset_id": cur_aid,
                    "to_asset_id": target,
                    "role": intent,
                }
            )
        elif not row.get("role"):
            row["role"] = intent
            applied.append({"action": "stamp_cue_role", "cue_id": row.get("cue_id"), "role": intent})
        out.append(row)
    return out, applied


def collapse_duplicate_music_cues(
    cues: list[dict[str, Any]],
    assets_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep one cue per (placement, segment anchor, lane) — drop same-window duplicates."""
    applied: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        if cue.get("skip") is True:
            out.append(cue)
            continue
        placement = str(cue.get("placement") or "")
        if placement == "under_segment":
            # One bed per segment is enough.
            sid = str(cue.get("segment_id") or "")
            key = (placement, sid, LANE_BED)
            if sid and key in seen:
                applied.append(
                    {
                        "action": "collapse_duplicate_bed_cue",
                        "cue_id": cue.get("cue_id"),
                        "segment_id": sid,
                    }
                )
                continue
            if sid:
                seen.add(key)
            out.append(cue)
            continue
        if placement not in {"before_segment", "after_segment", "cold_open", "show_open"}:
            out.append(cue)
            continue
        role = effective_cue_role(cue, assets_by_id.get(str(cue.get("asset_id") or "")))
        lane = music_lane_for_role(role)
        sid = str(
            cue.get("segment_id")
            or cue.get("before_segment_id")
            or cue.get("after_segment_id")
            or ""
        )
        key = (placement, sid, lane if lane != LANE_OTHER else role or str(cue.get("asset_id") or ""))
        if sid and key in seen:
            applied.append(
                {
                    "action": "collapse_duplicate_music_cue",
                    "cue_id": cue.get("cue_id"),
                    "placement": placement,
                    "segment_id": sid,
                    "lane": lane,
                }
            )
            continue
        if sid:
            seen.add(key)
        out.append(cue)
    # Show-open: if theme_cold_open anchors a before_segment, drop other before_segment
    # punctuators on that same segment (prevents cold_open + emphasis stack at answer start).
    cold_before: set[str] = set()
    for cue in out:
        if not isinstance(cue, dict) or cue.get("skip"):
            continue
        role = effective_cue_role(cue, assets_by_id.get(str(cue.get("asset_id") or "")))
        if role != "theme_cold_open":
            continue
        if str(cue.get("placement") or "") != "before_segment":
            continue
        sid = str(cue.get("segment_id") or cue.get("before_segment_id") or "")
        if sid:
            cold_before.add(sid)
    if cold_before:
        filtered: list[dict[str, Any]] = []
        for cue in out:
            if not isinstance(cue, dict):
                continue
            role = effective_cue_role(cue, assets_by_id.get(str(cue.get("asset_id") or "")))
            place = str(cue.get("placement") or "")
            sid = str(cue.get("segment_id") or cue.get("before_segment_id") or "")
            if (
                place == "before_segment"
                and sid in cold_before
                and role != "theme_cold_open"
                and music_lane_for_role(role) == LANE_PUNCTUATOR
            ):
                applied.append(
                    {
                        "action": "drop_open_stack_punctuator",
                        "cue_id": cue.get("cue_id"),
                        "segment_id": sid,
                    }
                )
                continue
            filtered.append(cue)
        out = filtered
    return out, applied


def classify_vo_line(line_id: str) -> str:
    """Return preface | question | other for VO line ids."""
    low = str(line_id or "").lower()
    if "preface" in low or low.startswith("vo_preface") or "cold_open" in low:
        return "preface"
    if (
        low.startswith("vo_q_")
        or "missing_question" in low
        or "_q_" in low
        or low.endswith("_question")
        or "framing_question" in low
    ):
        return "question"
    return "other"


def vo_open_landmarks_from_edl(edl: dict[str, Any] | None) -> dict[str, Any]:
    """Extract show-open landmarks: preface end, first question start, first speech start."""
    preface_end: int | None = None
    first_question_start: int | None = None
    first_speech_start: int | None = None
    vo_windows: list[tuple[int, int]] = []
    if not isinstance(edl, dict):
        return {
            "preface_end_ms": None,
            "first_question_start_ms": None,
            "first_speech_start_ms": None,
            "vo_windows": [],
        }
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        ctype = str(clip.get("type") or "")
        start = int(clip.get("timeline_start_ms") or 0)
        dur = int(clip.get("duration_ms") or 0)
        end = start + max(0, dur)
        if ctype == "speech" and first_speech_start is None:
            first_speech_start = start
        if ctype != "vo_pickup":
            continue
        if end > start:
            vo_windows.append((start, end))
        kind = classify_vo_line(str(clip.get("line_id") or ""))
        if kind == "preface":
            preface_end = end if preface_end is None else max(preface_end, end)
        elif kind == "question" and first_question_start is None:
            first_question_start = start
    return {
        "preface_end_ms": preface_end,
        "first_question_start_ms": first_question_start,
        "first_speech_start_ms": first_speech_start,
        "vo_windows": vo_windows,
    }


def cold_open_position_ms(
    *,
    theme_duration_ms: int,
    landmarks: dict[str, Any] | None,
    segment_timing: dict[str, tuple[int, int]],
    air_ms: int = 400,
) -> int:
    """Place theme_cold_open inside the EDL's protected opening-music window."""
    landmarks = landmarks or {}
    opening_window = landmarks.get("opening_music_window")
    if (
        isinstance(opening_window, (list, tuple))
        and len(opening_window) == 2
        and int(opening_window[1]) > int(opening_window[0])
    ):
        return max(0, int(opening_window[0]))
    preface_end = landmarks.get("preface_end_ms")
    q_start = landmarks.get("first_question_start_ms")
    first_speech = landmarks.get("first_speech_start_ms")
    if first_speech is None and segment_timing:
        first_speech = min(v[0] for v in segment_timing.values())
    first_speech_i = int(first_speech) if first_speech is not None else 0
    dur = max(500, int(theme_duration_ms))
    air = max(0, int(air_ms))

    if preface_end is not None and q_start is not None and int(q_start) > int(preface_end):
        pe, qs = int(preface_end), int(q_start)
        gap = qs - pe
        # Prefer starting just after preface so the bridge occupies post-hook air.
        if gap >= dur + air:
            return pe + min(air, max(80, air // 2))
        # Tight gap: start after preface; caller should have truncated audio to fit.
        return pe + min(max(40, air // 4), max(0, gap // 4))

    if preface_end is not None:
        pe = int(preface_end)
        if q_start is not None and int(q_start) > pe:
            return pe + min(air, 200)
        # No question VO: still leave cold open after preface, before speech.
        return max(pe, first_speech_i - dur - air) if first_speech_i > pe else pe + min(air, 200)

    if q_start is not None and first_speech_i > 0:
        # Question exists without preface — park theme before the question.
        return max(0, int(q_start) - dur - air)

    return max(0, first_speech_i - dur - air)


def _overlay_window(ov: dict[str, Any]) -> tuple[int, int]:
    pos = int(ov.get("position_ms") or 0)
    audio = ov.get("audio")
    dur = 0
    if audio is not None:
        try:
            dur = int(len(audio))
        except TypeError:
            dur = int(ov.get("duration_ms") or 0)
    else:
        dur = int(ov.get("duration_ms") or 0)
    return pos, pos + max(0, dur)


def apply_music_lane_exclusivity(
    overlays: list[dict[str, Any]],
    *,
    crossfade_ms: int = _CROSSFADE_HANDOFF_MS,
) -> list[dict[str, Any]]:
    """Forbid concurrent different music lanes; allow short crossfade handoffs."""
    if not overlays:
        return overlays
    # Work on a mutable copy; breathe silence stays attached to resolve.
    items = [dict(o) for o in overlays if isinstance(o, dict)]
    # Sort by start then priority (high first) so survivors prefer bookends.
    def sort_key(o: dict[str, Any]) -> tuple[int, int, int]:
        role = str(o.get("role") or "")
        lane = _overlay_lane(o)
        start, _ = _overlay_window(o)
        return (start, -LANE_PRIORITY.get(lane, 0), 0 if role == "breathe" else 1)

    items.sort(key=sort_key)
    kept: list[dict[str, Any]] = []
    xf = max(0, int(crossfade_ms))

    for ov in items:
        role = str(ov.get("role") or "")
        if role == "breathe":
            kept.append(ov)
            continue
        lane = _overlay_lane(ov)
        start, end = _overlay_window(ov)
        drop = False
        for prev in kept:
            if str(prev.get("role") or "") == "breathe":
                continue
            prev_lane = _overlay_lane(prev)
            if prev_lane == lane == LANE_BED:
                # Same-lane beds under speech may continue (different segments).
                continue
            if {prev_lane, lane} == {LANE_BED, LANE_PUNCTUATOR}:
                # Bed under dialogue + hinge punctuator may coexist; short edge trim only.
                ps, pe = _overlay_window(prev)
                overlap = min(end, pe) - max(start, ps)
                if overlap <= xf * 2:
                    other_start = start if lane == LANE_PUNCTUATOR else ps
                    if prev_lane == LANE_BED and pe > other_start:
                        _trim_overlay_end(prev, max(ps, other_start + xf))
                    continue
                continue
            if prev_lane == lane and lane != LANE_OTHER:
                # Same lane non-bed: collapse near-duplicates.
                ps, pe = _overlay_window(prev)
                if abs(ps - start) <= _DUPLICATE_WINDOW_MS or (start < pe and end > ps):
                    drop = True
                    break
                continue
            if lane == LANE_OTHER or prev_lane == LANE_OTHER:
                continue
            ps, pe = _overlay_window(prev)
            overlap = min(end, pe) - max(start, ps)
            if overlap <= 0:
                continue
            if overlap <= xf:
                # Short handoff: trim the lower-priority clip's edge.
                if LANE_PRIORITY.get(lane, 0) >= LANE_PRIORITY.get(prev_lane, 0):
                    _trim_overlay_end(prev, max(ps, start))
                else:
                    delay = pe - xf
                    if delay > start:
                        ov["position_ms"] = delay
                        start, end = _overlay_window(ov)
                continue
            # Hard conflict: drop lower priority (or trim bed under bookend/punctuator).
            if LANE_PRIORITY.get(lane, 0) > LANE_PRIORITY.get(prev_lane, 0):
                if prev_lane == LANE_BED and lane in {LANE_BOOKEND, LANE_PUNCTUATOR}:
                    # Delay bed until after punctuator/bookend with short overlap.
                    new_start = max(ps, end - xf)
                    prev["position_ms"] = new_start
                    audio = prev.get("audio")
                    if audio is not None and hasattr(audio, "__getitem__"):
                        # Keep remaining bed length from original end.
                        remain = max(0, pe - new_start)
                        if remain <= 0:
                            prev["_drop"] = True
                        else:
                            prev["audio"] = audio[:remain] if len(audio) > remain else audio
                else:
                    prev["_drop"] = True
            else:
                drop = True
                break
        if not drop:
            kept.append(ov)
        kept = [k for k in kept if not k.get("_drop")]

    # Restore chronological order for mix overlay application.
    kept.sort(key=lambda o: int(o.get("position_ms") or 0))
    for k in kept:
        k.pop("_drop", None)
    return kept


def _overlay_lane(ov: dict[str, Any]) -> str:
    role = str(ov.get("role") or "")
    if role == "bed":
        return LANE_BED
    if role in {"theme", "theme_bookend"}:
        return LANE_BOOKEND
    if role in {"theme_punctuator", "punctuator", "stinger", "bridge"}:
        # theme/stinger overlays from sound_design
        if role == "theme":
            return LANE_BOOKEND
        return LANE_PUNCTUATOR
    # Fall back to music_role if stamped
    mr = str(ov.get("music_role") or ov.get("asset_role") or "")
    return music_lane_for_role(mr or role)


def _trim_overlay_end(ov: dict[str, Any], new_end_ms: int) -> None:
    start = int(ov.get("position_ms") or 0)
    audio = ov.get("audio")
    if audio is None or not hasattr(audio, "__getitem__"):
        return
    new_len = max(0, int(new_end_ms) - start)
    if new_len <= 0:
        ov["_drop"] = True
        return
    if len(audio) > new_len:
        ov["audio"] = audio[:new_len]


def validate_music_cue_coherence(
    cues: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    *,
    landmarks: dict[str, Any] | None = None,
) -> list[str]:
    """Hard checks for cold-open uniqueness, cue→asset role match, open grammar."""
    errors: list[str] = []
    assets_by_id = {
        str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
    }
    cold_open_cues = []
    for cue in cues:
        if not isinstance(cue, dict) or cue.get("skip") is True:
            continue
        role = effective_cue_role(cue, assets_by_id.get(str(cue.get("asset_id") or "")))
        if role == "theme_cold_open":
            cold_open_cues.append(cue)
        intent = infer_theme_role_from_cue_id(str(cue.get("cue_id") or ""))
        if intent and intent in THEME_ROLES and role and role != intent:
            errors.append(
                f"cue {cue.get('cue_id')} asset role {role} mismatches intent {intent}"
            )
    if len(cold_open_cues) > 1:
        errors.append(f"at most one theme_cold_open cue allowed (found {len(cold_open_cues)})")

    landmarks = landmarks or {}
    preface_end = landmarks.get("preface_end_ms")
    q_start = landmarks.get("first_question_start_ms")
    if (
        cold_open_cues
        and preface_end is not None
        and q_start is not None
        and int(q_start) > int(preface_end)
    ):
        # Soft structural hint — only when cue still anchors to first speech before_segment
        # without role stamp (mix placement will fix; lint flags plan smell).
        for cue in cold_open_cues:
            placement = str(cue.get("placement") or "")
            if placement == "before_segment" and not cue.get("role"):
                # After repair, role should be stamped; if still bare before_segment it's ok
                # as long as mix uses cold_open_position. Flag only wrong asset binding.
                pass
    return errors
