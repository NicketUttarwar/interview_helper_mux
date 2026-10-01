"""Documents derived from the selection follow every selection commit.

The selection (``master/selection.json``) is the air order. Several documents
are derived from it and key on its ids or its order-lock revision: the nugget
lay-up plan copies both, and the sound design plan anchors cues on segment
ids. Until ISSUES 113 nothing reconciled them when the selection changed
under a seat freeze. A removal that the constitution permitted (an overlap
union retiring an absorbed id, a junction omit, a remap) bumped the selection
revision and left the lay-up plan one revision behind with a retired id in
it; the EDL loader then failed closed on the stale plan, and the heal that
re-fits the plan was refused because it wrote under its own key rather than
the plan owner's. Every run that hit an overlap union under hard freeze
stopped there.

This module is the one place that reconciliation happens, called from the
selection's single write point right after the write. It is deterministic
and never widens the air order: it drops or re-anchors references to ids the
commit already removed, and copies the committed order lock. Writes land
under each document's owner key, with the End-A reason
``selection_dependents_reconcile`` under freeze: paperwork for a removal the
constitution already allowed, never a new seat.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

END_A_REASON = "selection_dependents_reconcile"
LAYUP_OWNER = "nugget_layup_compose"
SDP_REL = "understanding/sound_design_plan.json"
_CUE_ANCHOR_KEYS = ("segment_id", "before_segment_id", "after_segment_id", "under_segment_id")


def _ids(doc: dict[str, Any] | None) -> list[str]:
    if not isinstance(doc, dict):
        return []
    return [str(s) for s in (doc.get("ordered_segment_ids") or []) if s]


def nearest_live_anchor(
    removed: str, previous_ids: list[str], current_ids: list[str], *, key: str
) -> str:
    """The live segment a cue anchored on ``removed`` should anchor on now.

    ``before_segment_id`` moves forward to the next live segment in the old
    order (the cue still plays before the same stretch of tape);
    ``after_segment_id`` moves back to the previous live one. A plain
    ``segment_id`` / ``under_segment_id`` takes the previous live segment,
    then the next. Empty when no live neighbour exists.
    """
    live = set(current_ids)
    if removed not in previous_ids:
        return ""
    i = previous_ids.index(removed)
    before = [s for s in previous_ids[:i] if s in live]
    after = [s for s in previous_ids[i + 1 :] if s in live]
    if key == "before_segment_id":
        order = after[:1] + before[-1:]
    elif key == "after_segment_id":
        order = before[-1:] + after[:1]
    else:
        order = before[-1:] + after[:1]
    return order[0] if order else ""


def reanchor_sound_design_cues(
    plan: dict[str, Any], *, previous_ids: list[str], current_ids: list[str]
) -> tuple[dict[str, Any], list[str]]:
    """Re-anchor or skip cues whose anchor left the selection. Pure."""
    notes: list[str] = []
    if not isinstance(plan, dict):
        return plan, notes
    live = set(current_ids)
    out = dict(plan)
    flows = out.get("flow_plans")
    if not isinstance(flows, dict):
        return out, notes
    flows = dict(flows)
    for flow_name, flow in list(flows.items()):
        if not isinstance(flow, dict) or not isinstance(flow.get("cues"), list):
            continue
        cues: list[Any] = []
        changed = False
        for cue in flow["cues"]:
            if not isinstance(cue, dict) or cue.get("skip"):
                cues.append(cue)
                continue
            new_cue = dict(cue)
            for key in _CUE_ANCHOR_KEYS:
                sid = str(new_cue.get(key) or "").strip()
                if not sid or sid in live:
                    continue
                dest = nearest_live_anchor(sid, previous_ids, current_ids, key=key)
                if dest:
                    new_cue[key] = dest
                    notes.append(f"{flow_name}:{new_cue.get('cue_id') or key}:{sid}->{dest}")
                else:
                    new_cue["skip"] = True
                    new_cue["skip_reason"] = f"{END_A_REASON}:anchor_removed:{sid}"
                    notes.append(f"{flow_name}:{new_cue.get('cue_id') or key}:{sid}->skip")
                changed = True
            cues.append(new_cue)
        if changed:
            flow = dict(flow)
            flow["cues"] = cues
            flows[flow_name] = flow
    out["flow_plans"] = flows
    return out, notes


def _reconcile_layup_plan(ctx: RunContext, notes: list[str]) -> None:
    from interview_mux.nugget_layup import (
        PLAN_REL,
        adopt_layup_plan_to_selection,
        layup_freshness_errors,
        nugget_layup_enabled,
    )

    if not nugget_layup_enabled() or not ctx.artifact_exists(PLAN_REL):
        return
    try:
        plan = ctx.read_json(PLAN_REL)
    except Exception:
        return
    if not isinstance(plan, dict):
        return
    meta = plan.get("_meta") if isinstance(plan.get("_meta"), dict) else {}
    if meta.get("stale"):
        # The unfrozen cascade asked for a recompose; the plan is not ours to fit.
        return
    if not layup_freshness_errors(ctx, plan):
        return
    # Owner key: the plan belongs to nugget_layup_compose whoever moved the
    # selection; fitting it to the committed order is that owner's paperwork.
    result = adopt_layup_plan_to_selection(
        ctx, persist=True, stage=LAYUP_OWNER, publish_gap=False
    )
    if result.get("ok"):
        left = layup_freshness_errors(ctx)
        notes.append("layup_plan_adopted" if not left else f"layup_plan_still_stale:{left[0][:80]}")
    else:
        notes.append(f"layup_plan_adopt_failed:{str(result.get('error') or '')[:80]}")


def _reconcile_sound_design_plan(
    ctx: RunContext, notes: list[str], *, previous_ids: list[str], current_ids: list[str]
) -> None:
    if not ctx.artifact_exists(SDP_REL):
        return
    try:
        plan = ctx.read_json(SDP_REL)
    except Exception:
        return
    if not isinstance(plan, dict):
        return
    fixed, cue_notes = reanchor_sound_design_cues(
        plan, previous_ids=previous_ids, current_ids=current_ids
    )
    if not cue_notes:
        return
    from interview_mux.seat_authority import persist_frozen_seat_doc

    meta = plan.get("_meta") if isinstance(plan.get("_meta"), dict) else {}
    owner = str(meta.get("producer_stage") or "").strip() or "sound_design_plan"
    try:
        landed = persist_frozen_seat_doc(
            ctx, SDP_REL, fixed, reason=END_A_REASON, stage_key=owner, skip_handoff=True
        )
    except Exception as exc:  # noqa: BLE001 - reported, the barrier judges the rest
        notes.append(f"sdp_reanchor_failed:{type(exc).__name__}")
        return
    notes.append(f"sdp_cues_reanchored:{len(cue_notes)}" if landed else "sdp_reanchor_skipped")


def reconcile_selection_dependents(
    ctx: RunContext,
    *,
    producer: str,
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> list[str]:
    """Fit the lay-up plan and the sound design plan to the committed selection.

    Called after every selection write. Cheap when nothing drifted: two reads.
    Returns the notes it logged (empty when nothing needed doing).
    """
    notes: list[str] = []
    previous_ids = _ids(previous)
    current_ids = _ids(current)
    if not current_ids:
        return notes
    try:
        _reconcile_layup_plan(ctx, notes)
    except Exception as exc:  # noqa: BLE001 - never fail the commit for paperwork
        notes.append(f"layup_plan_reconcile_error:{type(exc).__name__}")
    if previous_ids and previous_ids != current_ids:
        try:
            _reconcile_sound_design_plan(
                ctx, notes, previous_ids=previous_ids, current_ids=current_ids
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"sdp_reconcile_error:{type(exc).__name__}")
    if notes:
        try:
            ctx.log(
                f"selection dependents reconciled ({producer}): " + ", ".join(notes[:6]),
                level="info",
                stage=str(producer or "").split(":")[0] or None,
                action_id="selection.dependents_reconcile",
                detail={"notes": notes[:20], "producer": producer},
            )
        except Exception:
            pass
    return notes
