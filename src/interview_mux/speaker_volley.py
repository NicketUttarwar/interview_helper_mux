"""Speaker volley — conversation units between speakers in the podcast timeline.

See docs/cross-cutting/volley-glossary.md. This module is *not* LLM message-packet
assembly (that is LLM volley / compact_for_volley / local_volley_framer).
"""

from __future__ import annotations

from typing import Any


def _seg_type(seg: dict[str, Any]) -> str:
    return str(seg.get("type") or seg.get("segment_type") or seg.get("label") or "").lower()


def _speaker(seg: dict[str, Any]) -> str:
    return str(seg.get("speaker_id") or seg.get("speaker") or "").strip()


def detect_speaker_volleys(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect contiguous speaker-conversation units from ordered segments.

    Prefers Q→A pairs; also groups adjacent speaker-role flips into short volleys
    (max span 6 segments) when types are missing.
    """
    if not segments:
        return []
    volleys: list[dict[str, Any]] = []
    used: set[str] = set()

    for i in range(len(segments) - 1):
        a, b = segments[i], segments[i + 1]
        aid = str(a.get("segment_id") or "")
        bid = str(b.get("segment_id") or "")
        if not aid or not bid or aid in used or bid in used:
            continue
        ta, tb = _seg_type(a), _seg_type(b)
        sa, sb = _speaker(a), _speaker(b)
        kind = None
        if "question" in ta and "answer" in tb:
            kind = "qa"
        elif sa and sb and sa != sb:
            kind = "speaker_turn"
        if not kind:
            continue
        ids = [aid, bid]
        used.add(aid)
        used.add(bid)
        # Extend while alternating speakers / continuing answer chain
        j = i + 2
        while j < len(segments) and len(ids) < 6:
            c = segments[j]
            cid = str(c.get("segment_id") or "")
            if not cid or cid in used:
                break
            prev = segments[j - 1]
            if _speaker(c) and _speaker(prev) and _speaker(c) != _speaker(prev):
                ids.append(cid)
                used.add(cid)
                j += 1
                continue
            tc = _seg_type(c)
            if kind == "qa" and "answer" in tc:
                ids.append(cid)
                used.add(cid)
                j += 1
                continue
            break
        volleys.append(
            {
                "speaker_volley_id": f"sv_{ids[0]}_{ids[-1]}",
                "segment_ids": ids,
                "kind": kind,
                "locked": True,
            }
        )
    return volleys


def check_speaker_volley_integrity(
    order: list[str],
    volleys: list[dict[str, Any]],
    *,
    only_locked: bool = True,
) -> tuple[bool, list[str]]:
    """Return (ok, flags). Fail when a locked volley's segments are split/reordered."""
    idx = {str(sid): i for i, sid in enumerate(order)}
    flags: list[str] = []
    for v in volleys:
        if only_locked and not v.get("locked", True):
            continue
        ids = [str(s) for s in (v.get("segment_ids") or [])]
        present = [s for s in ids if s in idx]
        if len(present) < 2:
            continue
        positions = [idx[s] for s in present]
        lo = min(positions)
        if positions != list(range(lo, lo + len(present))):
            flags.append(f"speaker_volley_split:{v.get('speaker_volley_id') or present[0]}")
            continue
        if sorted(present, key=lambda s: idx[s]) != present:
            flags.append(f"speaker_volley_reorder:{v.get('speaker_volley_id') or present[0]}")
    return (not flags), flags


def compact_speaker_volleys_for_llm_volley(volleys: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Compact speaker volleys for inclusion in an LLM volley (message packet)."""
    out: list[dict[str, Any]] = []
    for v in volleys or []:
        out.append(
            {
                "speaker_volley_id": v.get("speaker_volley_id"),
                "segment_ids": list(v.get("segment_ids") or []),
                "kind": v.get("kind"),
                "locked": bool(v.get("locked", True)),
            }
        )
    return out


# Back-compat alias name used in some call sites before glossary qualification
compact_speaker_volleys_for_volley = compact_speaker_volleys_for_llm_volley
