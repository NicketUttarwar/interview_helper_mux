"""0.1.0 phase scheduler: conductor-owned skip/reorder/rerun; remainder walk only on request."""

from __future__ import annotations

import shutil
from typing import Any

from interview_mux.homunculus.ledger import append_ledger, remainder_requested
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

AGENDA_REL = "mastering/homunculus/agenda.json"
PROTECTED_ISLAND_STAGES = frozenset(
    {
        "low_conf_island_scan",
        "connector_fuse_pass",
        "connector_fuse_pass_pre_ranking",
    }
)
_ISLAND_ARTIFACTS = (
    "analysis/low_conf_must_keep.json",
    "analysis/low_conf_islands.json",
    "analysis/connector_fuse_audit.json",
)


def _order_for(phase: str) -> list[str]:
    return list(ANALYSIS_ORDER if phase == "analysis" else DELIVERY_ORDER)


def _read_agenda(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(AGENDA_REL):
        return {"skipped": [], "remaining": [], "scheduled": [], "reruns": []}
    raw = ctx.read_json(AGENDA_REL)
    if not isinstance(raw, dict):
        return {"skipped": [], "remaining": [], "scheduled": [], "reruns": []}
    raw.setdefault("skipped", [])
    raw.setdefault("remaining", [])
    raw.setdefault("scheduled", [])
    raw.setdefault("reruns", [])
    return raw


def skipped_stages(ctx: RunContext) -> set[str]:
    return {str(s) for s in (_read_agenda(ctx).get("skipped") or [])}


def remaining_stages(ctx: RunContext, phase: str) -> list[str]:
    skipped = skipped_stages(ctx)
    scheduled = [str(s) for s in (_read_agenda(ctx).get("scheduled") or [])]
    order = scheduled if scheduled else _order_for(phase)
    return [s for s in order if not ctx.is_done(s) and s not in skipped]


def write_agenda(ctx: RunContext, phase: str, remaining: list[str], *, source: str) -> dict[str, Any]:
    prev = _read_agenda(ctx)
    doc = {
        "phase": phase,
        "remaining": list(remaining),
        "source": source,
        "seed_order": _order_for(phase),
        "skipped": list(prev.get("skipped") or []),
        "scheduled": list(prev.get("scheduled") or []),
        "reruns": list(prev.get("reruns") or []),
    }
    ctx.write_json(AGENDA_REL, doc)
    append_ledger(
        ctx,
        {
            "kind": "agenda",
            "identity": "agenda",
            "phase": phase,
            "source": source,
            "remaining": remaining[:40],
        },
    )
    return doc


def skip_stage(ctx: RunContext, stage: str, *, reason: str, compensating_fact: str | None = None) -> dict[str, Any]:
    if stage in PROTECTED_ISLAND_STAGES:
        has_art = any(ctx.artifact_exists(rel) for rel in _ISLAND_ARTIFACTS)
        if not has_art:
            raise RuntimeError(
                f"cannot skip {stage}: language-island artifacts missing "
                "(low_conf_island_scan / connector_fuse_pass required)"
            )
    doc = _read_agenda(ctx)
    skipped = [str(s) for s in (doc.get("skipped") or [])]
    if stage not in skipped:
        skipped.append(stage)
    doc["skipped"] = skipped
    if compensating_fact:
        doc.setdefault("skip_reasons", {})
        if isinstance(doc["skip_reasons"], dict):
            doc["skip_reasons"][stage] = {"reason": reason, "compensating_fact": compensating_fact}
    ctx.write_json(AGENDA_REL, doc)
    append_ledger(
        ctx,
        {
            "kind": "skip_stage",
            "identity": f"skip:{stage}",
            "stage": stage,
            "reason": reason,
            "compensating_fact": compensating_fact,
        },
    )
    return doc


def schedule_stage(ctx: RunContext, stage: str, *, before: str | None = None) -> dict[str, Any]:
    doc = _read_agenda(ctx)
    phase = str(doc.get("phase") or "analysis")
    order = list(doc.get("scheduled") or []) or remaining_stages(ctx, phase)
    if stage in order:
        order.remove(stage)
    if before and before in order:
        order.insert(order.index(before), stage)
    else:
        order.insert(0, stage)
    doc["scheduled"] = order
    doc["remaining"] = [s for s in order if not ctx.is_done(s) and s not in skipped_stages(ctx)]
    ctx.write_json(AGENDA_REL, doc)
    append_ledger(
        ctx,
        {"kind": "schedule_stage", "identity": "schedule_stage", "stage": stage, "order": order[:40]},
    )
    return doc


def unmark_stage_only(ctx: RunContext, stage: str) -> int:
    """Archive and remove this stage's done marker. Does not clear downstream."""
    marker = ctx.final_path(".stage_done", stage)
    if not marker.is_file():
        return 0
    doc = _read_agenda(ctx)
    seq = len(list(doc.get("reruns") or [])) + 1
    dest = ctx.path(f"mastering/homunculus/reruns/{seq}")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(marker, dest / stage)
    marker.unlink()
    reruns = list(doc.get("reruns") or [])
    reruns.append({"seq": seq, "stage": stage})
    doc["reruns"] = reruns
    ctx.write_json(AGENDA_REL, doc)
    return seq


def rerun_stage(
    ctx: RunContext,
    stage: str,
    *,
    extra_fact_ids: list[str] | None = None,
    overlay_rel: str | None = None,
) -> dict[str, Any]:
    seq = unmark_stage_only(ctx, stage)
    if extra_fact_ids:
        from interview_mux.homunculus.packer import pack_volley

        pack_volley(ctx, fact_ids=list(extra_fact_ids), tool_id=stage)
    append_ledger(
        ctx,
        {
            "kind": "rerun_stage",
            "identity": "rerun_stage",
            "stage": stage,
            "seq": seq,
            "overlay_rel": overlay_rel,
            "extra_fact_ids": list(extra_fact_ids or []),
        },
    )
    from interview_mux.pipeline import run_single_stage

    setattr(ctx, "_homunculus_inner_stage", True)
    try:
        from interview_mux.homunculus.runtime import dispatch_stage

        dispatch_stage(ctx, stage, lambda: run_single_stage(ctx, stage), source="rerun")
    finally:
        if hasattr(ctx, "_homunculus_inner_stage"):
            delattr(ctx, "_homunculus_inner_stage")
    return {"ok": True, "stage": stage, "seq": seq}


def invalidate_downstream(ctx: RunContext, stage: str) -> dict[str, Any]:
    order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    ctx.clear_from(stage, order)
    append_ledger(
        ctx,
        {"kind": "invalidate_downstream", "identity": "invalidate_downstream", "stage": stage},
    )
    return {"ok": True, "cleared_from": stage}


def request_walk_seed_remainder(ctx: RunContext, *, reason: str = "conductor") -> dict[str, Any]:
    append_ledger(
        ctx,
        {"kind": "walk_seed_remainder", "identity": "walk_seed_remainder", "reason": reason},
    )
    return {"ok": True, "reason": reason}


def walk_seed_agenda(ctx: RunContext, stages: list[str], *, reason: str) -> None:
    """Explicit logged fallback — not a silent linear fall-through."""
    append_ledger(
        ctx,
        {
            "kind": "fallback",
            "identity": "walk_seed_agenda",
            "reason": reason,
            "stages": list(stages)[:80],
        },
    )
    ctx.log(
        f"homunculus seed-agenda fallback ({reason}): {len(stages)} stage(s)",
        level="warning",
        stage="homunculus",
    )
    from interview_mux.gates import check_transcript_review_pending
    from interview_mux.pipeline import run_single_stage

    setattr(ctx, "_homunculus_seed_walk", True)
    try:
        for stage in stages:
            if ctx.is_done(stage) or stage in skipped_stages(ctx):
                continue
            run_single_stage(ctx, stage)
            if stage == "transcript_review_build" and check_transcript_review_pending(ctx):
                break
    finally:
        if hasattr(ctx, "_homunculus_seed_walk"):
            delattr(ctx, "_homunculus_seed_walk")


def run_homunculus_phase(
    ctx: RunContext,
    phase: str,
    remaining: list[str],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Conductor selects tools. Leftover stages walk seed order only if requested."""
    write_agenda(ctx, phase, remaining, source="conductor")
    from interview_mux.homunculus.persona import write_persona
    from interview_mux.homunculus.source_card import build_source_card
    from interview_mux.homunculus.speakers import build_speaker_dossier

    write_persona(ctx)
    try:
        build_source_card(ctx)
    except Exception:
        pass
    if ctx.artifact_exists("understanding/speakers.json") or ctx.artifact_exists("ingest/transcript.json"):
        try:
            build_speaker_dossier(ctx)
        except Exception:
            pass
    conductor_out: dict[str, Any] = {"ok": False, "skipped": True}
    if remaining:
        try:
            from interview_mux.homunculus.loop import run_conductor

            msg = (
                f"Complete the {phase} phase for this tape. Remaining stages (seed order): "
                f"{', '.join(remaining)}. You may skip, reorder, or surgically re-run. "
                f"Select run_stage_* tools. Admit every output. Pack volleys by fact IDs. "
                f"Cite docs via retrieve_canon. Do not invent dialogue. Respect G0. "
                f"Do not skip low_conf_island_scan or connector_fuse_pass unless artifacts exist. "
                f"Prefer MusicGen large for beds. Hard limits apply. "
                f"walk_seed_remainder is optional catch-up only."
            )
            conductor_out = run_conductor(ctx, user_message=msg, client=client)
        except Exception as exc:
            conductor_out = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}
            append_ledger(
                ctx,
                {
                    "kind": "fallback",
                    "identity": "conductor_error",
                    "reason": "conductor_error",
                    "error": conductor_out["message"],
                },
            )
    still = remaining_stages(ctx, phase)
    if still and remainder_requested(ctx):
        walk_seed_agenda(ctx, still, reason="walk_seed_remainder")
    return {"conductor": conductor_out, "remaining_after": remaining_stages(ctx, phase)}
