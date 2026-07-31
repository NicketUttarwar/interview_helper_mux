"""1..N speaker delivery plan: clone voice + address labels for synthetic inserts."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _speakers_list(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("understanding/speakers.json"):
        return []
    doc = ctx.read_json("understanding/speakers.json")
    if not isinstance(doc, dict):
        return []
    rows = doc.get("speakers") or []
    return [r for r in rows if isinstance(r, dict) and r.get("speaker_id")]


def _display_name(row: dict[str, Any]) -> str | None:
    for key in ("display_name", "name", "label", "full_name"):
        val = str(row.get(key) or "").strip()
        if val and val.lower() not in {"unknown", "speaker", "spk"}:
            return val
    return None


def _role(row: dict[str, Any]) -> str:
    return str(row.get("role") or row.get("speaker_role") or "unknown").lower()


def _talk_ms(row: dict[str, Any]) -> float:
    for key in ("talk_time_ms", "duration_ms", "total_ms", "speaking_ms"):
        try:
            return float(row.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0.0


def infer_group_label(ctx: RunContext, speaker_count: int) -> str:
    """Context-appropriate collective term when names are unknown."""
    brief = {}
    if ctx.artifact_exists("understanding/content_brief.json"):
        try:
            brief = ctx.read_json("understanding/content_brief.json") or {}
        except Exception:
            brief = {}
    blob = " ".join(
        [
            str(brief.get("title") or ""),
            str(brief.get("summary") or ""),
            " ".join(str(t) for t in (brief.get("topics") or [])[:8]),
        ]
    ).lower()
    if any(w in blob for w in ("founder", "startup", "ceo", "co-founder")):
        return "the founders" if speaker_count != 1 else "the founder"
    if any(w in blob for w in ("team", "colleagues", "employees")):
        return "the team"
    if any(w in blob for w in ("friend", "friends", "mates")):
        return "friends"
    if speaker_count >= 3:
        return "speakers"
    if speaker_count == 1:
        return "the speaker"
    return "speakers"


def build_speaker_delivery_plan(ctx: RunContext) -> dict[str, Any]:
    """Compute clone speaker + address labels for gap VO / transitions."""
    from interview_mux.source_topology import pickup_eligible_speaker_id

    rows = _speakers_list(ctx)
    count = len(rows)
    pickup = pickup_eligible_speaker_id(ctx)

    interviewer_ids = [str(r["speaker_id"]) for r in rows if _role(r) in {"interviewer", "host", "frame"}]
    content_ids = [
        str(r["speaker_id"])
        for r in rows
        if _role(r) in {"interviewee", "guest", "content", "storyteller", "unknown"}
        or str(r["speaker_id"]) not in interviewer_ids
    ]

    clear_interviewer = bool(interviewer_ids) and count >= 2
    clone_id: str | None = None
    insert_strategy = "dyad_pickup"

    if count <= 1:
        clone_id = str(rows[0]["speaker_id"]) if rows else pickup
        insert_strategy = "monologue_self_clone"
        clear_interviewer = False
    elif clear_interviewer:
        clone_id = pickup or interviewer_ids[0]
        insert_strategy = "dyad_pickup"
    else:
        # No clear interviewer — self-clone primary content speaker (most talk time)
        ranked = sorted(rows, key=_talk_ms, reverse=True)
        clone_id = str(ranked[0]["speaker_id"]) if ranked else pickup
        insert_strategy = "self_clone_no_interviewer" if count == 2 else "panel_dynamic"
        if count >= 3 and pickup:
            clone_id = pickup
            insert_strategy = "panel_dynamic"

    group = infer_group_label(ctx, max(count, 1))
    address_labels: dict[str, str] = {}
    for r in rows:
        sid = str(r["speaker_id"])
        name = _display_name(r)
        address_labels[sid] = name if name else group

    return {
        "version": 1,
        "speaker_count": count,
        "expected_typical": 2,
        "clear_interviewer": clear_interviewer,
        "clone_speaker_id": clone_id,
        "pickup_eligible_speaker_id": pickup,
        "insert_strategy": insert_strategy,
        "address_mode": "names_when_known",
        "group_label": group,
        "address_labels": address_labels,
        "interviewer_speaker_ids": interviewer_ids,
        "content_speaker_ids": content_ids or [str(r["speaker_id"]) for r in rows],
    }


def write_speaker_delivery_plan(ctx: RunContext) -> dict[str, Any]:
    plan = build_speaker_delivery_plan(ctx)
    ctx.write_json("understanding/speaker_delivery_plan.json", plan)
    return plan
