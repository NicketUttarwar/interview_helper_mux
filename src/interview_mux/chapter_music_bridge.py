"""Chapter music-bridge grammar: sparse 4s speech-free music at hinges.

Listener pattern: prior underbed faces out → 4s music-only → same stem carries
into the next substantial VO / native. Never before short transition/hitch lines.

Canon: plan chapter_music_bridges; docs/cross-cutting/sound-design.md.
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config

CHAPTER_MUSIC_BRIDGE_AIR_KIND = "chapter_music_bridge"

_LIGHT_CUE_ROLES = frozenset({"vo_bridge", "story_bridge"})
_LIGHT_CATEGORIES = frozenset({"story_bridge", "vo_bridge"})
_LIGHT_TRANSITION_TYPES = frozenset({"bridge", "micro"})
_EXCLUDE_GAP_TYPES = frozenset(
    {
        "ok_with_light_bridge",
        "missing_callback",
        "seam_hitch",
        "reorder_bridge",
        "clone_adjacency_hitch",
    }
)

_DEFAULTS: dict[str, Any] = {
    "chapter_music_bridge_enable": True,
    "chapter_music_bridge_ms": 4000,
    "min_bridge_separation_ms": 45_000,
    "vo_bridge_min_duration_ms": 6000,
    "vo_bridge_min_words": 18,
}


def chapter_music_bridge_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg or merged_config()
    mastering = root.get("mastering") if isinstance(root.get("mastering"), dict) else {}
    raw = (
        mastering.get("music_continuity")
        if isinstance(mastering.get("music_continuity"), dict)
        else {}
    )
    out = dict(_DEFAULTS)
    for key, default in _DEFAULTS.items():
        if key in raw and raw[key] is not None:
            try:
                if isinstance(default, bool):
                    out[key] = bool(raw[key])
                else:
                    out[key] = type(default)(raw[key])
            except (TypeError, ValueError):
                out[key] = default
    return out


def bridge_duration_ms(cfg: dict[str, Any] | None = None) -> int:
    return max(1000, int(chapter_music_bridge_cfg(cfg).get("chapter_music_bridge_ms") or 4000))


def _word_count(text: str) -> int:
    return len([w for w in str(text or "").split() if w])


def is_light_transition_line(line: dict[str, Any] | None) -> bool:
    """True for short hitch / light-bridge VO that must never earn a music bridge."""
    if not isinstance(line, dict):
        return True
    cue = str(line.get("cue_role") or line.get("role") or "").strip().lower()
    if cue in _LIGHT_CUE_ROLES:
        return True
    cat = str(line.get("line_category") or line.get("category") or "").strip().lower()
    if cat in _LIGHT_CATEGORIES:
        return True
    tr = str(line.get("transition_type") or "").strip().lower()
    if tr == "chapter":
        return False
    if tr in _LIGHT_TRANSITION_TYPES:
        return True
    gap = str(line.get("gap_type") or "").strip().lower()
    if gap in _EXCLUDE_GAP_TYPES:
        return True
    if bool(line.get("required_seam_hitch") or line.get("clone_adjacency_hitch")):
        return True
    if bool(line.get("seam_hitch") or line.get("reorder_bridge")):
        return True
    return False


def is_substantial_vo_line(
    line: dict[str, Any] | None,
    *,
    measured_duration_ms: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> bool:
    """Longer inserts only — dense packages / substantial VO, not micro bridges."""
    if not isinstance(line, dict):
        return False
    if is_light_transition_line(line):
        return False
    conf = chapter_music_bridge_cfg(cfg)
    min_dur = int(conf.get("vo_bridge_min_duration_ms") or 6000)
    min_words = int(conf.get("vo_bridge_min_words") or 18)

    detail = str(line.get("detail_budget") or "").strip().lower()
    dense_package = detail == "dense" or bool(line.get("information_package_id"))

    dur = measured_duration_ms
    if dur is None:
        if line.get("duration_ms") is not None:
            try:
                dur = int(line.get("duration_ms") or 0)
            except (TypeError, ValueError):
                dur = 0
        else:
            try:
                dur = int(float(line.get("estimated_duration_sec") or 0) * 1000)
            except (TypeError, ValueError):
                dur = 0
    words = _word_count(str(line.get("text") or ""))

    if dense_package and (int(dur or 0) >= min_dur or words >= min_words):
        return True
    if int(dur or 0) >= min_dur and words >= min_words:
        return True
    # Pre-synth: word floor alone when duration unknown.
    if int(dur or 0) <= 0 and words >= min_words and dense_package:
        return True
    if int(dur or 0) >= min_dur:
        return True
    return False


def vo_line_earns_bridge(
    line: dict[str, Any] | None,
    *,
    montage_move: str = "",
    first_after_chapter_hinge: bool = False,
    measured_duration_ms: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> bool:
    """VO-intro path: package / music_face_out / first after hinge + substantial."""
    if not chapter_music_bridge_cfg(cfg).get("chapter_music_bridge_enable", True):
        return False
    if not is_substantial_vo_line(line, measured_duration_ms=measured_duration_ms, cfg=cfg):
        return False
    move = str(montage_move or (line or {}).get("montage_move") or "").strip()
    if move in {"information_package", "music_face_out"}:
        return True
    if first_after_chapter_hinge:
        return True
    if str((line or {}).get("detail_budget") or "").strip().lower() == "dense":
        return True
    if (line or {}).get("information_package_id"):
        return True
    return False


def chapter_hinge_earns_bridge(
    *,
    transition_type: str = "",
    is_chapter_scale: bool = False,
    scene_resolve: bool = False,
    same_answer: bool = False,
    cfg: dict[str, Any] | None = None,
) -> bool:
    if not chapter_music_bridge_cfg(cfg).get("chapter_music_bridge_enable", True):
        return False
    if same_answer:
        return False
    if scene_resolve:
        return True
    tr = str(transition_type or "").strip().lower()
    if tr == "chapter" or is_chapter_scale:
        return True
    return False


def apply_bridge_sparsity(
    opportunities: list[dict[str, Any]],
    *,
    segment_durs: dict[str, int] | None = None,
    ordered_segment_ids: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Keep at most one bridge per after_segment; enforce min air-time separation."""
    conf = chapter_music_bridge_cfg(cfg)
    if not conf.get("chapter_music_bridge_enable", True):
        return [o for o in opportunities if str(o.get("kind") or "") != "chapter_music_bridge"]
    min_sep = int(conf.get("min_bridge_separation_ms") or 45_000)
    bridge_ms = bridge_duration_ms(conf)
    durs = segment_durs or {}
    ordered = list(ordered_segment_ids or [])
    if not ordered:
        # Infer a stable order from first-seen segment ids in opportunities.
        seen_ord: list[str] = []
        for row in opportunities:
            sid = str(row.get("segment_id") or row.get("after_segment_id") or "")
            if sid and sid not in seen_ord:
                seen_ord.append(sid)
        ordered = seen_ord
    cum: dict[str, int] = {}
    running = 0
    for sid in ordered:
        cum[sid] = running
        running += int(durs.get(sid) or 0)

    def _air_pos(after: str) -> int:
        if after in cum:
            return int(cum[after]) + int(durs.get(after) or 0)
        return 0

    out: list[dict[str, Any]] = []
    seen_after: set[str] = set()
    last_air_ms = -10**12
    for row in opportunities:
        kind = str(row.get("kind") or "")
        if kind != "chapter_music_bridge":
            out.append(row)
            continue
        sid = str(row.get("segment_id") or "")
        after = str(row.get("after_segment_id") or sid)
        if after and after in seen_after:
            continue
        pos = _air_pos(after)
        if last_air_ms >= 0 and pos - last_air_ms < min_sep:
            continue
        enriched = dict(row)
        enriched.setdefault("duration_ms", bridge_ms)
        enriched.setdefault("suggested_role", "theme_transition")
        enriched.setdefault("preserve_bridge_ms", bridge_ms)
        enriched.setdefault("carry_into_next", True)
        enriched.setdefault("break_contiguous_bed", True)
        out.append(enriched)
        if after:
            seen_after.add(after)
        last_air_ms = pos
    return out


def montage_move_for_segment(plan: dict[str, Any] | None, segment_id: str) -> str:
    if not isinstance(plan, dict) or not segment_id:
        return ""
    script = plan.get("air_script") if isinstance(plan.get("air_script"), dict) else {}
    for beat in script.get("beats") or []:
        if not isinstance(beat, dict):
            continue
        if str(beat.get("segment_id") or "") == segment_id:
            return str(beat.get("montage_move") or "")
    return ""
