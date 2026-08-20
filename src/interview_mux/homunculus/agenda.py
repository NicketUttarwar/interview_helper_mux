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
# After G0 is closed, re-STT / re-ingest / re-clip is not a surgical rerun — pack g0_transcript.
G0_LOCKED_RERUN_STAGES = frozenset(
    {"transcribe", "ingest", "audio_preclean", "transcript_review_build"}
)
# Delivery must not rewind the classified timeline; fill gap artifacts instead.
DELIVERY_LOCKED_TIMELINE_STAGES = frozenset(
    {
        "transcript_review_build",
        "speaker_roles",
        "content_context",
        "talking_points_compose",
        "ideal_cuts_propose",
        "ideal_cuts_materialize",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
    }
)
DELIVERY_ANALYSIS_PREREQS: tuple[tuple[str, str], ...] = (
    ("boundary_detection", "segments/boundaries.json"),
    ("segment_classification", "segments/manifest.json"),
    ("content_brief_reanchor", "understanding/content_brief.json"),
    ("missing_framing", "understanding/gap_evaluations.json"),
    ("gap_framing_compose", "understanding/gap_report.json"),
    ("delivery_brief_build", "understanding/delivery_brief.json"),
)
PREPARE_STAGE_OUTPUTS: dict[str, tuple[str, ...]] = {
    "audio_preclean": (
        "preclean/isolated.wav",
        "preclean/provider.json",
        "preclean/lineage.json",
    ),
    "ingest": ("ingest/normalized.wav",),
    "transcribe": ("transcript/full.json",),
}


def prepare_outputs_present(ctx: RunContext, stage: str) -> bool:
    needed = PREPARE_STAGE_OUTPUTS.get(stage)
    if not needed:
        return True
    if stage in {"ingest", "transcribe"}:
        return all(ctx.artifact_exists(rel) for rel in needed)
    return any(ctx.artifact_exists(rel) for rel in needed)


def unmark_hollow_prepare_stages(ctx: RunContext) -> list[str]:
    """Clear .stage_done for prepare stages that never wrote their artifacts."""
    cleared: list[str] = []
    for stage in G0_LOCKED_RERUN_STAGES:
        if ctx.is_done(stage) and not prepare_outputs_present(ctx, stage):
            unmark_stage_only(ctx, stage)
            cleared.append(stage)
    return cleared


def _refuse_g0_locked_rerun(ctx: RunContext, stage: str, *, action: str) -> None:
    from interview_mux.homunculus.packer import g0_closed

    if stage not in G0_LOCKED_RERUN_STAGES:
        return
    if not g0_closed(ctx):
        return
    if not prepare_outputs_present(ctx, stage):
        # Hollow done marker — this is the first real run, not a post-G0 rerun.
        return
    raise RuntimeError(
        f"cannot {action} {stage}: G0 is closed; pack g0_transcript instead of re-running STT"
    )


def _manifest_has_classified_segments(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("segments/manifest.json"):
        return False
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return False
    segs = man.get("segments") if isinstance(man, dict) else []
    return any(
        isinstance(s, dict) and s.get("segment_id") and s.get("speaker_role")
        for s in (segs or [])
    )


def _refuse_classified_manifest_rerun(ctx: RunContext, stage: str, *, action: str) -> None:
    """Nested gap-eval often asks to reclassify when it only saw G0 words."""
    if stage != "segment_classification":
        return
    if not _manifest_has_classified_segments(ctx):
        return
    raise RuntimeError(
        f"cannot {action} segment_classification: classified segment_id and "
        "speaker_role already exist; pack segment_manifest for gap eval"
    )


def _delivery_phase_active(ctx: RunContext) -> bool:
    return str(_read_agenda(ctx).get("phase") or "") == "delivery"


def pending_analysis_for_delivery(ctx: RunContext) -> list[str]:
    """Analysis producers topic_coverage_audit needs before a delivery walk."""
    pending: list[str] = []
    for stage, rel in DELIVERY_ANALYSIS_PREREQS:
        if ctx.artifact_exists(rel) and ctx.is_done(stage):
            continue
        if ctx.artifact_exists(rel) and not ctx.is_done(stage):
            ctx.mark_done(stage, force=True)
            continue
        pending.append(stage)
    return pending


def _refuse_delivery_timeline_rewind(ctx: RunContext, stage: str, *, action: str) -> None:
    """Do not rewind the classified timeline after G0 when artifacts already exist."""
    if stage not in DELIVERY_LOCKED_TIMELINE_STAGES:
        return
    from interview_mux.homunculus.packer import g0_closed

    if not g0_closed(ctx):
        return
    if stage == "transcript_review_build":
        if not ctx.is_done(stage):
            ctx.mark_done(stage, force=True)
        raise RuntimeError(
            f"cannot {action} transcript_review_build: G0 is closed"
        )
    if stage == "segment_classification":
        _refuse_classified_manifest_rerun(ctx, stage, action=action)
        return
    needed = PROTECTED_CORE_STAGES.get(stage) or ()
    has_art = bool(needed) and all(ctx.artifact_exists(rel) for rel in needed)
    classified = _manifest_has_classified_segments(ctx)
    if not has_art and not classified:
        return
    if has_art and not ctx.is_done(stage):
        ctx.mark_done(stage, force=True)
    raise RuntimeError(
        f"cannot {action} {stage}: timeline artifacts exist after G0; "
        "pack existing facts and fill missing_framing / gap_framing_compose / "
        "delivery_brief_build instead of rewinding the classified tape"
    )


# Required analysis stages — skip only when the compensating artifact exists.
PROTECTED_CORE_STAGES: dict[str, tuple[str, ...]] = {
    "ingest": ("ingest/normalized.wav",),
    "transcribe": ("transcript/full.json",),
    "content_context": ("understanding/content_brief.json",),
    "talking_points_compose": ("understanding/talking_points.json",),
    "ideal_cuts_propose": ("understanding/ideal_cuts.json",),
    "ideal_cuts_materialize": ("understanding/ideal_cuts_materialized.json",),
    "boundary_detection": ("segments/boundaries.json",),
    "segment_classification": ("segments/manifest.json",),
    "content_brief_reanchor": ("understanding/content_brief.json",),
    "episode_structure_compose": (),
    "chapter_close_hitch": ("mastering/chapter_close_hitch.json",),
}


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
    # Seed order is the remainder walk. Conductor `skipped` / `scheduled` may
    # reorder tools, but leftover walk must still run incomplete stages
    # (a skip without .stage_done is a hole, not progress).
    return [s for s in _order_for(phase) if not ctx.is_done(s)]


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
    if stage == "chapter_close_hitch":
        from interview_mux.chapter_close_hitch import hitch_latch_committed

        if not hitch_latch_committed(ctx):
            raise RuntimeError(
                "cannot skip chapter_close_hitch until the one-shot latch is committed"
            )
    if stage in PROTECTED_ISLAND_STAGES:
        has_art = any(ctx.artifact_exists(rel) for rel in _ISLAND_ARTIFACTS)
        if not has_art:
            raise RuntimeError(
                f"cannot skip {stage}: language-island artifacts missing "
                "(low_conf_island_scan / connector_fuse_pass required)"
            )
    if stage in PROTECTED_CORE_STAGES:
        needed = PROTECTED_CORE_STAGES[stage]
        has_art = bool(needed) and all(ctx.artifact_exists(rel) for rel in needed)
        if compensating_fact:
            has_art = has_art or ctx.artifact_exists(compensating_fact)
        if not has_art:
            raise RuntimeError(
                f"cannot skip {stage}: required analysis artifact missing "
                f"({', '.join(needed) if needed else 'episode_structure_compose'})"
            )
        if not ctx.is_done(stage):
            ctx.mark_done(stage, force=True)
    if stage in PROTECTED_ISLAND_STAGES and not ctx.is_done(stage):
        if any(ctx.artifact_exists(rel) for rel in _ISLAND_ARTIFACTS):
            ctx.mark_done(stage, force=True)
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
    _refuse_g0_locked_rerun(ctx, stage, action="rerun")
    _refuse_classified_manifest_rerun(ctx, stage, action="rerun")
    _refuse_delivery_timeline_rewind(ctx, stage, action="rerun")
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
    _refuse_g0_locked_rerun(ctx, stage, action="invalidate")
    _refuse_delivery_timeline_rewind(ctx, stage, action="invalidate")
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
        unmark_hollow_prepare_stages(ctx)
        for stage in stages:
            if ctx.is_done(stage) or stage in skipped_stages(ctx):
                continue
            try:
                _refuse_g0_locked_rerun(ctx, stage, action="walk")
                _refuse_delivery_timeline_rewind(ctx, stage, action="walk")
            except RuntimeError:
                if prepare_outputs_present(ctx, stage) and not ctx.is_done(stage):
                    ctx.mark_done(stage, force=True)
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
    prior = list(remaining)
    cleared = unmark_hollow_prepare_stages(ctx)
    want = set(prior) | set(cleared)
    remaining = [s for s in _order_for(phase) if s in want and not ctx.is_done(s)]
    write_agenda(ctx, phase, remaining, source="conductor")
    if phase == "delivery":
        pending_analysis = pending_analysis_for_delivery(ctx)
        if pending_analysis:
            ctx.log(
                "homunculus delivery blocked on analysis prereqs — "
                f"walking {pending_analysis}",
                level="warning",
                stage=pending_analysis[0],
            )
            walk_seed_agenda(ctx, pending_analysis, reason="delivery_needs_analysis")
            pending_analysis = pending_analysis_for_delivery(ctx)
            if pending_analysis:
                ctx.log(
                    "homunculus delivery still blocked on analysis "
                    f"({', '.join(pending_analysis)}); topic_coverage must wait",
                    level="warning",
                    stage=pending_analysis[0],
                )
                return {
                    "conductor": {
                        "ok": False,
                        "blocked_on_analysis": pending_analysis,
                    },
                    "remaining_after": remaining_stages(ctx, phase),
                }
            remaining = [s for s in _order_for(phase) if s in want and not ctx.is_done(s)]
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
                f"Do not skip content_context, talking_points_compose, ideal_cuts_propose, "
                f"ideal_cuts_materialize, boundary_detection, episode_structure_compose, "
                f"or chapter_close_hitch unless artifacts exist (hitch only after latch). Prefer MusicGen large for beds. Hard limits apply. "
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
    still = [s for s in remaining if not ctx.is_done(s)]
    if still:
        ctx.log(
            f"homunculus {phase} incomplete after conductor "
            f"({len(still)} remaining; master QA must wait)",
            level="info",
            stage=still[0],
        )
    if still and remainder_requested(ctx):
        walk_seed_agenda(ctx, still, reason="walk_seed_remainder")
    elif (
        still
        and phase == "delivery"
        and not ctx.artifact_exists("master/master.wav")
    ):
        ctx.log(
            "homunculus delivery walking remaining seed to master "
            f"({len(still)} stage(s))",
            level="warning",
            stage=still[0],
        )
        walk_seed_agenda(ctx, still, reason="delivery_walk_to_master")
    elif phase == "analysis":
        pending = pending_analysis_for_delivery(ctx)
        prereq_ids = {s for s, _ in DELIVERY_ANALYSIS_PREREQS}
        if pending and any(s in prereq_ids for s in still):
            ctx.log(
                "homunculus analysis filling delivery prereqs — "
                f"walking {still[:12]}",
                level="warning",
                stage=still[0],
            )
            walk_seed_agenda(ctx, still, reason="analysis_fill_delivery_prereqs")
    return {"conductor": conductor_out, "remaining_after": remaining_stages(ctx, phase)}
