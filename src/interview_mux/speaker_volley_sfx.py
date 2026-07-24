"""Bind soundscape / SDP cues to speaker volleys (conversation units).

See docs/cross-cutting/volley-glossary.md — speaker volley ≠ LLM volley.
"""

from __future__ import annotations

from typing import Any


def bind_cues_to_speaker_volleys(
    cues: list[dict[str, Any]],
    speaker_volleys: list[dict[str, Any]],
    *,
    segment_to_time: dict[str, tuple[float, float]] | None = None,
) -> list[dict[str, Any]]:
    """Annotate cues with speaker_volley_id or hinge metadata.

    Beds (under_speech / ambient) attach to the overlapping volley when
    segment_to_time is provided; otherwise round-robin by index for beds and
    mark stingers as hinges between volleys.
    """
    if not cues:
        return []
    volleys = [v for v in speaker_volleys if isinstance(v, dict) and v.get("speaker_volley_id")]
    if not volleys:
        return [dict(c) for c in cues]

    out: list[dict[str, Any]] = []
    bed_i = 0
    for cue in cues:
        c = dict(cue)
        role = str(c.get("role") or c.get("asset_role") or c.get("kind") or "").lower()
        verb = str(c.get("music_transition") or c.get("verb") or "").lower()
        is_bed = "bed" in role or verb in ("under_speech", "around_vo", "bed_morph")
        is_stinger = "stinger" in role or "punctuat" in role or verb in (
            "between_islands",
            "motif_callback",
            "resolve_swell",
        )
        is_cold = "cold_open" in role or role == "cold_open"
        if is_cold and volleys:
            c["speaker_volley_id"] = volleys[0].get("speaker_volley_id")
            c["before_first_speaker_volley"] = True
        elif is_stinger and len(volleys) >= 2:
            # Hinge after volley i for stinger index
            hi = min(bed_i, len(volleys) - 2)
            c["hinge_after_volley_id"] = volleys[hi].get("speaker_volley_id")
            c["speaker_volley_hinge"] = True
            bed_i += 1
        elif is_bed:
            vid = None
            if segment_to_time and c.get("start_sec") is not None:
                start = float(c.get("start_sec") or 0)
                for v in volleys:
                    # Prefer first segment id of volley if times known
                    for sid in v.get("segment_ids") or []:
                        span = (segment_to_time or {}).get(str(sid))
                        if not span:
                            continue
                        if span[0] <= start <= span[1]:
                            vid = v.get("speaker_volley_id")
                            break
                    if vid:
                        break
            if not vid:
                vid = volleys[bed_i % len(volleys)].get("speaker_volley_id")
                bed_i += 1
            c["speaker_volley_id"] = vid
        out.append(c)
    return out


def speaker_volleys_from_structure(doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    raw = doc.get("speaker_volleys")
    return [v for v in raw if isinstance(v, dict)] if isinstance(raw, list) else []
