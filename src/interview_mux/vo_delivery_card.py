"""Planner cards for synthetic VO diction. Input only — never aired.

``next_beat_card`` and ``episode_card`` do not read a run, write a file, or
call a model. Callers attach a returned string to the stage-input JSON.
"""

from __future__ import annotations

import re
from typing import Any

_MAX_CHARS = 400

_INTERNAL_ID = re.compile(
    r"\b(?:seg(?:ment)?|line|clip|turn|nug|vo)[\s_-]*\d+[a-z0-9_]*\b",
    re.IGNORECASE,
)
_CHAPTER_LABEL = re.compile(
    r"\bchapters?\s+(?:\d+|[ivxlcdm]+)\s*[:.\-–—]?\s*",
    re.IGNORECASE,
)
_EDIT_PHRASE = re.compile(
    r"\b(?:this|that|the|next|previous|prior|earlier|a|an)\s+"
    r"(?:segments?|clips?|chapters?)\b",
    re.IGNORECASE,
)
_BOILERPLATE = re.compile(
    r"gap_type\s*=|orient the listener|unlocks the next native|"
    r"without restating|add conversational value",
    re.IGNORECASE,
)


def _piece(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    raw = text.strip()
    if not raw or _BOILERPLATE.search(raw):
        return ""
    cleaned = _INTERNAL_ID.sub(" ", raw)
    cleaned = _CHAPTER_LABEL.sub(" ", cleaned)
    cleaned = _EDIT_PHRASE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n.,;:-")
    return cleaned


def _cap(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    cut = text[:_MAX_CHARS].rsplit(" ", 1)[0].strip()
    return cut or text[:_MAX_CHARS].strip()


def _speakable(piece: str) -> bool:
    """Drop editor notes the spoken-line check would reject if they were aired."""
    from interview_mux.spoken_meta_lint import spoken_structure_hits

    return not spoken_structure_hits(piece)


def _join_unique(parts: list[Any]) -> str | None:
    kept: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        piece = _piece(raw)
        key = piece.lower()
        if not piece or key in seen or not _speakable(piece):
            continue
        seen.add(key)
        kept.append(piece)
    if not kept:
        return None
    return _cap(" ".join(kept))


def next_beat_card(
    *,
    chapter_title: str | None = None,
    listener_confusion: str | None = None,
    handoff_need: str | None = None,
    mission: str | None = None,
) -> str | None:
    """Short description of the next native, or None when no summary exists."""
    return _join_unique([chapter_title, listener_confusion, handoff_need, mission])


def episode_card(
    brief: dict[str, Any] | None = None,
    *,
    through_line: str | None = None,
) -> str | None:
    """A few sentences on the whole conversation. None when the brief has no thesis."""
    doc = brief if isinstance(brief, dict) else {}
    thesis = _piece(doc.get("thesis"))
    if not thesis:
        return None
    topic_names: list[str] = []
    for row in doc.get("topics") or []:
        name = _piece(
            (row.get("name") or row.get("label")) if isinstance(row, dict) else row
        )
        if name and name.lower() not in {n.lower() for n in topic_names}:
            topic_names.append(name)
        if len(topic_names) >= 4:
            break
    guest = ""
    for key in ("guest_name", "interviewee_name", "subject_name"):
        guest = _piece(doc.get(key))
        if guest:
            break
    parts: list[str] = [thesis]
    if topic_names:
        parts.append(", ".join(topic_names))
    if guest:
        parts.append(guest)
    through = _piece(through_line)
    if through and through.lower() != thesis.lower():
        parts.append(through)
    return _cap(" ".join(parts))


def apply_gap_delivery_cards(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach top-level cards from summaries already on a gap-compose payload."""
    if not isinstance(payload, dict):
        return payload
    targets = payload.get("target_native_contexts")
    missions = payload.get("vo_missions")
    evals = payload.get("gap_evaluations")
    confusion: dict[str, str] = {}
    if isinstance(evals, dict):
        for row in evals.get("evaluations") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                text = row.get("listener_confusion")
                if isinstance(text, str) and text.strip():
                    confusion[str(row["segment_id"])] = text
    ids: list[str] = []
    ordered = payload.get("ordered_segment_ids")
    if isinstance(ordered, list) and ordered:
        ids = [str(s) for s in ordered if s]
    else:
        seen: set[str] = set()
        for source in (targets, missions, confusion):
            if isinstance(source, dict):
                for key in source:
                    sid = str(key)
                    if sid not in seen:
                        seen.add(sid)
                        ids.append(sid)
    cards: dict[str, str] = {}
    for sid in ids:
        tgt = targets.get(sid) if isinstance(targets, dict) else None
        mission = missions.get(sid) if isinstance(missions, dict) else None
        card = next_beat_card(
            chapter_title=tgt.get("chapter_title") if isinstance(tgt, dict) else None,
            listener_confusion=confusion.get(sid),
            mission=mission.get("mission") if isinstance(mission, dict) else None,
        )
        if card:
            cards[sid] = card
    if cards:
        payload["next_beat_cards"] = cards
    talking = payload.get("talking_points")
    through = talking.get("through_line") if isinstance(talking, dict) else None
    episode = episode_card(
        payload.get("content_brief") if isinstance(payload.get("content_brief"), dict) else None,
        through_line=through if isinstance(through, str) else None,
    )
    if episode:
        payload["episode_card"] = episode
    return payload
