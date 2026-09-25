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
    framing_yes = True
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict) and "gap_framing_enabled" in meta:
                framing_yes = bool(meta.get("gap_framing_enabled"))
    except Exception:
        framing_yes = True

    if count <= 1:
        clone_id = str(rows[0]["speaker_id"]) if rows else pickup
        insert_strategy = "monologue_self_clone"
        clear_interviewer = False
    elif clear_interviewer:
        clone_id = pickup or interviewer_ids[0]
        insert_strategy = "dyad_pickup"
    elif framing_yes and count >= 2:
        # G-Framing Yes: never self-clone the talk-dominant guest as interviewer VO.
        clone_id = pickup
        insert_strategy = "dyad_pickup" if pickup else "no_frame_speaker_for_clone"
    else:
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


def write_speaker_delivery_plan(
    ctx: RunContext, *, stage_key: str | None = None
) -> dict[str, Any]:
    from interview_mux.write_staging import active_stage_id

    plan = build_speaker_delivery_plan(ctx)
    sk = stage_key or active_stage_id() or "selection_order_sanitize"
    ctx.write_json("understanding/speaker_delivery_plan.json", plan, stage_key=sk)
    return plan


_MODE_TO_VO_SHAPE: dict[str, str] = {
    "documentary_bridge": "third_person",
    "guide_summary": "third_person",
    "hook_montage": "third_person",
    "conversational_host": "third_person",
    "sparse_source": "third_person",
    "hybrid_bespoke": "third_person",
}


def vo_shape_to_pov(shape: str) -> str:
    """Map episode vo_shape onto bridge/compose POV labels."""
    key = str(shape or "").strip().lower()
    if key in {"first_person", "host_first_person"}:
        return "host_first_person"
    if key in {"second_person", "host_second_person"}:
        return "host_second_person"
    return "expository_third_person"


def _narrative_mode_vo_shape(ctx: RunContext) -> str:
    for rel in ("mastering/mastering_plan.json", "master/narrative_plan.json"):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        mode = str(doc.get("narrative_mode") or doc.get("confirmed_mode") or "").strip()
        if mode in _MODE_TO_VO_SHAPE:
            return _MODE_TO_VO_SHAPE[mode]
    return ""


def _opener_vo_shape(ctx: RunContext) -> str:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return ""
    try:
        from interview_mux.opening_orientation import is_episode_orientation

        gap = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return ""
    if not isinstance(gap, dict):
        return ""
    for line in gap.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        if not is_episode_orientation(line):
            continue
        shape = str(line.get("vo_shape") or "").strip()
        if shape:
            return shape
        return "third_person"
    return ""


def episode_vo_identity(ctx: RunContext | None = None) -> dict[str, Any]:
    """One clone speaker, one approved ref WAV, one vo_shape for the episode."""
    speaker_id = ""
    vo_shape = "third_person"
    ref_wav = ""
    if ctx is None:
        return {"speaker_id": speaker_id, "ref_wav": ref_wav, "vo_shape": vo_shape}
    if ctx.artifact_exists("understanding/speaker_delivery_plan.json"):
        try:
            sdp = ctx.read_json("understanding/speaker_delivery_plan.json")
            if isinstance(sdp, dict):
                speaker_id = str(sdp.get("clone_speaker_id") or "").strip()
                locked = str(sdp.get("vo_shape") or "").strip()
                if locked:
                    vo_shape = locked
        except Exception:
            speaker_id = ""
    if not speaker_id:
        from interview_mux.source_topology import pickup_eligible_speaker_id

        speaker_id = str(pickup_eligible_speaker_id(ctx) or "").strip()
    opener = _opener_vo_shape(ctx)
    if opener:
        vo_shape = opener
    else:
        mode_shape = _narrative_mode_vo_shape(ctx)
        if mode_shape:
            vo_shape = mode_shape
    if speaker_id:
        ref_wav = f"understanding/speaker_samples/{speaker_id}.wav"
    return {
        "speaker_id": speaker_id,
        "ref_wav": ref_wav,
        "vo_shape": vo_shape or "third_person",
    }


def stamp_episode_vo_identity(ctx: RunContext, line: dict[str, Any]) -> dict[str, Any]:
    """Force clone speaker + vo_shape onto a gap/transition/layup line."""
    ident = episode_vo_identity(ctx)
    out = dict(line)
    if ident.get("speaker_id"):
        out["voice_speaker_id"] = ident["speaker_id"]
    if ident.get("vo_shape"):
        out["vo_shape"] = ident["vo_shape"]
    return out


def apply_episode_vo_identity_to_edl(ctx: RunContext, edl: dict[str, Any]) -> dict[str, Any]:
    """Stamp the episode clone onto seated synthetic clips that omitted voice_speaker_id."""
    ident = episode_vo_identity(ctx)
    locked = str(ident.get("speaker_id") or "").strip()
    if not locked or not isinstance(edl, dict):
        return edl
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        if str(clip.get("type") or "") not in {"vo_pickup", "transition"}:
            continue
        if not str(clip.get("voice_speaker_id") or "").strip():
            clip["voice_speaker_id"] = locked
    return edl
