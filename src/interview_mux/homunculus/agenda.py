"""0.1.0 phase scheduler: conductor-owned skip/reorder/rerun; remainder walk only on request."""

from __future__ import annotations

import shutil
from typing import Any

from interview_mux.homunculus.ledger import append_ledger, remainder_requested
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER, SHIP_AFTER_MASTER

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
_PRE_RANKING_ROUNDS = "analysis/connector_fuse_rounds.json"
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
    ("source_topology_build", "understanding/source_topology.json"),
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


_GAP_FILL_ANALYSIS_PREREQS = frozenset({"missing_framing", "gap_framing_compose"})


def _restore_skipped_gap_prereqs(ctx: RunContext) -> None:
    """Re-materialize skip artifacts so delivery is not blocked after a wrap discard."""
    try:
        from interview_mux.gap_fill_eligibility import (
            assess_gap_fill_eligibility,
            gap_fill_was_skipped,
        )
        from interview_mux.stages.gaps import ensure_gap_fill_skipped
    except Exception:
        return
    if not gap_fill_was_skipped(ctx):
        return
    decision = assess_gap_fill_eligibility(ctx)
    ensure_gap_fill_skipped(ctx, reason=decision.reason, signals=decision.signals)


def pending_analysis_for_delivery(ctx: RunContext) -> list[str]:
    """Analysis producers topic_coverage_audit needs before a delivery walk."""
    pending: list[str] = []
    gap_skipped = False
    native_only = False
    try:
        from interview_mux.pipeline_mode import is_native_only

        native_only = bool(is_native_only(ctx))
    except Exception:
        native_only = False
    try:
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        gap_skipped = bool(gap_fill_was_skipped(ctx))
    except Exception:
        gap_skipped = False
    if native_only:
        gap_skipped = True
    if gap_skipped:
        _restore_skipped_gap_prereqs(ctx)
    for stage, rel in DELIVERY_ANALYSIS_PREREQS:
        if gap_skipped and stage in _GAP_FILL_ANALYSIS_PREREQS:
            if ctx.artifact_exists(rel):
                if not ctx.is_done(stage):
                    ctx.mark_done(stage, force=True)
                continue
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
    "source_topology_build": (
        "understanding/source_topology.json",
        "understanding/flow_adaptation.json",
    ),
    "content_context": ("understanding/content_brief.json",),
    "talking_points_compose": ("understanding/talking_points.json",),
    "ideal_cuts_propose": ("understanding/ideal_cuts.json",),
    "ideal_cuts_materialize": ("understanding/ideal_cuts_materialized.json",),
    "boundary_detection": ("segments/boundaries.json",),
    "segment_classification": ("segments/manifest.json",),
    "content_brief_reanchor": ("understanding/content_brief.json",),
    "framing_posture_decide": ("understanding/framing_posture_decision.json",),
    "episode_structure_compose": (),
    "chapter_close_hitch": ("mastering/chapter_close_hitch.json",),
    "full_master_ranking": ("master/selection.json",),
    "transitions": ("master/transitions.json",),
    "sound_design_plan": ("understanding/sound_design_plan.json",),
    "vo_synthesize": ("mastering/vo_synthesize.json",),
}

# Delivery producers — skip only when THIS stage wrote its output. Skip never marks done.
PROTECTED_DELIVERY_OUTPUTS: dict[str, tuple[str, ...]] = {
    "edl_narrative_audit": ("master/edl_narrative_audit.json",),
    "edl": ("master/edl.json",),
    "assembly_preview": ("master/assembly_preview.wav",),
    "listen_delight_audit": ("mastering/listen_delight_audit.json",),
    "nugget_layup_compose": ("understanding/nugget_layup_plan.json",),
    "vo_line_adjudicate": ("understanding/vo_line_adjudication.json",),
    "music_palette_compose": ("sound_design/music_palette_compose.json",),
    "sfx_prompt_craft": ("sound_design/sfx_prompts.json",),
    "mmaudio_sfx": ("sound_design/mmaudio_qa.json",),
    "mix": ("master/assembly.wav",),
    "junction_snip_qa": ("master/seam_autopsy.json",),
    "master_finalize": ("master/master.wav", "master/post_master_quality.json"),
    "master_transcript_build": ("master/transcript.json",),
    "episode_meta_build": ("publish/episode_meta.json",),
    "episode_cover_prompt_craft": ("publish/cover_prompt.json",),
    "podcast_encode_mp3": ("publish/audio.mp3",),
    "podcast_publish": ("publish/chapters.json",),
}

MUSIC_SKIP_GUARD = frozenset(
    {"sfx_prompt_craft", "mmaudio_sfx", "music_palette_compose", "mix"}
)
MUSIC_REQUIRES_ASSEMBLY = frozenset(
    {"music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"}
)

IDENTICAL_ERROR_REL = "mastering/homunculus/identical_stage_errors.json"
IDENTICAL_ERROR_CAP = 3
HOLLOW_SKIP_FP = "hollow_skip_blocked:{stage}:outputs_missing"


class HollowSkipBlockedError(RuntimeError):
    """10C: structured refuse when skip would hide a hollow .stage_done marker."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload.get("reason") or "hollow_done"))


def _speaker_samples_present(ctx: RunContext) -> bool:
    """True when topology speaker_stats each have an on-disk sample WAV."""
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return False
    try:
        topo = ctx.read_json("understanding/source_topology.json")
    except Exception:
        return False
    stats = topo.get("speaker_stats") if isinstance(topo, dict) else []
    if not isinstance(stats, list) or not stats:
        return True
    sample_dir = ctx.path("understanding", "speaker_samples")
    for row in stats:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("speaker_id") or "")
        if sid and not (sample_dir / f"{sid}.wav").is_file():
            return False
    return True


def _refuse_topology_skip_without_samples(ctx: RunContext, stage: str) -> None:
    """2A: synthetic path needs topology + speaker samples before skip."""
    if stage != "source_topology_build":
        return
    try:
        from interview_mux.pipeline_mode import is_native_only

        if is_native_only(ctx):
            return
    except Exception:
        pass
    has_topo = ctx.artifact_exists("understanding/source_topology.json") and ctx.artifact_exists(
        "understanding/flow_adaptation.json"
    )
    if has_topo and _speaker_samples_present(ctx):
        return
    raise RuntimeError(
        "cannot skip source_topology_build: topology and speaker sample WAVs required "
        "when pipeline_mode is not native_only"
    )


def _block_hollow_skip(ctx: RunContext, stage: str) -> None:
    """10C: refuse skip when .stage_done lies — unmark once, fingerprint escalation."""
    if not ctx.is_done(stage) or stage_outputs_present(ctx, stage):
        return
    fingerprint = HOLLOW_SKIP_FP.format(stage=stage)
    hit = note_identical_stage_error(ctx, stage, fingerprint)
    from interview_mux.homunculus.budget import remaining as budget_remaining

    remaining_budget = budget_remaining(ctx, stage)
    count = int(hit.get("count") or 0)
    exhausted = bool(hit.get("exhausted"))
    if count <= 1:
        unmark_hollow_delivery_producers(ctx, {stage})
        if ctx.is_done(stage):
            unmark_stage_only(ctx, stage)
    payload: dict[str, Any] = {
        "ok": False,
        "reason": "hollow_done",
        "stage": stage,
        "action": "unmark_and_rerun_once" if count <= 1 else "needs_operator",
        "remaining_rerun_budget": remaining_budget,
        "do_not": ["skip_stage", "invalidate_downstream"],
        "attempt": count,
        "exhausted": exhausted,
        "operator_card": (
            "Stage marked done but output incomplete — rerun required. "
            "Do not skip or invalidate downstream."
        ),
    }
    if count >= 2 or exhausted:
        try:
            from interview_mux.homunculus.issues import write_homunculus_plan

            plan = resolve_stage_plan(ctx, stage)
            write_homunculus_plan(
                ctx,
                last_target=stage,
                blockers=[f"hollow_done:{stage}"],
                attempted_heals=[f"hollow_skip_blocked x{count}"],
                recommended_next=str(plan.get("recommended_next") or stage),
                reason="hollow_skip_escalation",
            )
        except Exception:
            pass
        try:

            def _mark(meta: dict[str, Any]) -> None:
                meta["needs_operator"] = True
                meta["needs_operator_stage"] = stage
                meta["needs_operator_reason"] = fingerprint[:240]

            ctx.mutate_run_meta(_mark)
        except Exception:
            pass
        payload["action"] = "needs_operator"
    append_ledger(
        ctx,
        {
            "kind": "hollow_skip_blocked",
            "identity": f"hollow_skip:{stage}",
            "stage": stage,
            "attempt": count,
            "exhausted": exhausted,
        },
    )
    raise HollowSkipBlockedError(payload)


def _refuse_music_before_assembly(ctx: RunContext, stage: str, *, action: str) -> None:
    """Theme/SFX generation is post-assembly. Conductor must not jump the EDL."""
    if stage not in MUSIC_REQUIRES_ASSEMBLY:
        return
    if ctx.artifact_exists("master/assembly.wav") or ctx.artifact_exists(
        "master/assembly_preview.wav"
    ):
        return
    raise RuntimeError(
        f"cannot {action} {stage}: assembly audio missing — "
        "run nugget_layup_compose → transitions → vo_synthesize → edl → "
        "assembly_preview before MusicGen/SFX"
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


def stage_required_outputs(stage: str) -> tuple[str, ...]:
    if stage in PROTECTED_DELIVERY_OUTPUTS:
        return PROTECTED_DELIVERY_OUTPUTS[stage]
    if stage in PROTECTED_CORE_STAGES:
        return PROTECTED_CORE_STAGES[stage]
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage)
    return (rel,) if rel else ()


def _sdp_producer_stage(ctx: RunContext) -> str:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return ""
    try:
        doc = ctx.read_json("understanding/sound_design_plan.json")
    except Exception:
        return ""
    if not isinstance(doc, dict):
        return ""
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    return str(meta.get("producer_stage") or "")


def delivery_sdp_present(ctx: RunContext) -> bool:
    """True only after sound_design_plan itself wrote SDP and transitions exist."""
    if not ctx.artifact_exists("master/transitions.json"):
        return False
    return _sdp_producer_stage(ctx) == "sound_design_plan"


def _pre_ranking_rounds_present(ctx: RunContext) -> bool:
    """True only after the pre-ranking fuse pass wrote its own rounds doc.

    The first ``connector_fuse_pass`` may leave ``connector_fuse_audit.json``
    (and even a post_sanitize rounds file). Those must not satisfy
    ``connector_fuse_pass_pre_ranking`` or remaining_stages drops the pass,
    ranking looks done, and maybe_require then loops on a self-prerequisite.
    """
    if not ctx.artifact_exists(_PRE_RANKING_ROUNDS):
        return False
    try:
        doc = ctx.read_json(_PRE_RANKING_ROUNDS)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    return str(doc.get("pass_id") or "") == "pre_ranking"


def _final_mtime(ctx: RunContext, *parts: str) -> float | None:
    path = ctx.final_path(*parts)
    if not path.is_file():
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def assembly_stale_versus_edl(ctx: RunContext) -> bool:
    """True when assembly is not the mix of the live AirOrder generation."""
    try:
        from interview_mux.air_order import mix_stale_versus_live

        return mix_stale_versus_live(ctx)
    except Exception:
        pass
    edl_m = _final_mtime(ctx, "master", "edl.json")
    asm_m = _final_mtime(ctx, "master", "assembly.wav")
    if edl_m is None or asm_m is None:
        return False
    return edl_m > asm_m + 1.0


def _producer_older_than_assembly(ctx: RunContext, *parts: str) -> bool:
    asm_m = _final_mtime(ctx, "master", "assembly.wav")
    other_m = _final_mtime(ctx, *parts)
    if asm_m is None or other_m is None:
        return False
    return asm_m > other_m + 1.0


def stage_outputs_present(ctx: RunContext, stage: str) -> bool:
    if stage == "low_conf_island_scan":
        return ctx.artifact_exists("analysis/low_conf_islands.json") or ctx.artifact_exists(
            "analysis/low_conf_must_keep.json"
        )
    if stage == "connector_fuse_pass":
        return ctx.artifact_exists("analysis/connector_fuse_audit.json")
    if stage == "connector_fuse_pass_pre_ranking":
        return _pre_ranking_rounds_present(ctx)
    if stage == "sound_design_plan":
        return delivery_sdp_present(ctx)
    if stage == "vo_synthesize":
        if not ctx.artifact_exists("mastering/vo_synthesize.json"):
            return False
        if not ctx.artifact_exists("master/transitions.json"):
            return False
        try:
            from interview_mux.transition_vo import current_transition_pairs_missing

            return not current_transition_pairs_missing(ctx)
        except Exception:
            return False
    if stage in MUSIC_REQUIRES_ASSEMBLY:
        if not (
            ctx.artifact_exists("master/assembly.wav")
            or ctx.artifact_exists("master/assembly_preview.wav")
        ):
            return False
        rels = stage_required_outputs(stage)
        if not (bool(rels) and all(ctx.artifact_exists(rel) for rel in rels)):
            return False
        if stage == "mmaudio_sfx":
            try:
                from interview_mux.artifact_completeness import artifact_status

                return artifact_status("sound_design/mmaudio_qa.json", ctx) == "complete"
            except Exception:
                return False
        return True
    if stage == "edl":
        if not ctx.artifact_exists("master/edl.json"):
            return False
        try:
            from interview_mux.order_hash import order_drift_heal_action

            sel = (
                ctx.read_json("master/selection.json")
                if ctx.artifact_exists("master/selection.json")
                else None
            )
            edl_doc = ctx.read_json("master/edl.json")
            if (
                order_drift_heal_action(
                    sel if isinstance(sel, dict) else None,
                    edl_doc if isinstance(edl_doc, dict) else None,
                )
                not in {"ok", "stamp"}
            ):
                return False
            from interview_mux.order_hash import edl_speech_clip_ids, get_order_lock

            lock = get_order_lock(sel if isinstance(sel, dict) else {}) or {}
            lock_ids = [str(s) for s in (lock.get("ordered_segment_ids") or []) if s]
            clip_ids = edl_speech_clip_ids(edl_doc if isinstance(edl_doc, dict) else {})
            sel_ids = [
                str(s)
                for s in ((sel or {}).get("ordered_segment_ids") or [])
                if s
            ] if isinstance(sel, dict) else []
            seated = lock_ids or sel_ids
            if clip_ids and seated and clip_ids != seated:
                return False
        except Exception:
            return True
        return True
    if stage == "mix":
        try:
            from interview_mux.air_order import mix_outputs_seated

            return bool(mix_outputs_seated(ctx))
        except Exception:
            if assembly_stale_versus_edl(ctx):
                return False
            needed = stage_required_outputs(stage)
            return bool(needed) and all(ctx.artifact_exists(rel) for rel in needed)
    if stage == "junction_snip_qa" and (
        assembly_stale_versus_edl(ctx)
        or _producer_older_than_assembly(ctx, "master", "seam_autopsy.json")
    ):
        return False
    if stage == "master_finalize" and (
        assembly_stale_versus_edl(ctx)
        or _producer_older_than_assembly(ctx, "master", "master.wav")
    ):
        return False
    if stage == "nugget_layup_compose":
        # Plan on disk is the producer output. Freshness/hash drift must not
        # look like a missing artifact — that unmarked compose on EDL resume
        # and rewrote G1 after a selection-order heal.
        rels = stage_required_outputs(stage)
        return bool(rels) and all(ctx.artifact_exists(rel) for rel in rels)
    needed = stage_required_outputs(stage)
    if not needed:
        return ctx.is_done(stage)
    return all(ctx.artifact_exists(rel) for rel in needed)


def unmark_hollow_delivery_producers(
    ctx: RunContext, stages: list[str] | set[str] | None = None
) -> list[str]:
    """Clear .stage_done when the producer output is missing or from another stage."""
    if stages is None:
        want = set(PROTECTED_CORE_STAGES) | set(PROTECTED_DELIVERY_OUTPUTS) | set(
            PROTECTED_ISLAND_STAGES
        )
    else:
        want = {str(s) for s in stages}
    cleared: list[str] = []
    for stage in sorted(want):
        if stage == "mmaudio_sfx" and not stage_outputs_present(ctx, stage):
            # Empty QA with theme WAVs already on disk is a label hole, not a
            # missing producer — rebuild QA instead of regenerating MusicGen.
            try:
                from interview_mux.mmaudio_asset_qa import heal_mmaudio_qa_wav_parity

                heal_mmaudio_qa_wav_parity(ctx)
            except Exception:
                pass
            if stage_outputs_present(ctx, stage) and not ctx.is_done(stage):
                ctx.mark_done(stage, force=True)
        if ctx.is_done(stage) and not stage_outputs_present(ctx, stage):
            unmark_stage_only(ctx, stage)
            cleared.append(stage)
    if cleared:
        ctx.log(
            "homunculus unmarked hollow delivery producers: " + ", ".join(cleared),
            level="warning",
            stage=cleared[0],
        )
    return cleared


def unskip_hollow_stages(ctx: RunContext, stages: list[str] | set[str]) -> list[str]:
    """Drop skip entries that never produced their output — skip without artifact is a hole."""
    want = {str(s) for s in stages}
    unmark_hollow_delivery_producers(ctx, want)
    doc = _read_agenda(ctx)
    skipped = [str(s) for s in (doc.get("skipped") or [])]
    keep: list[str] = []
    dropped: list[str] = []
    for sid in skipped:
        hollow = sid in want and not stage_outputs_present(ctx, sid)
        if hollow:
            dropped.append(sid)
        else:
            keep.append(sid)
    if not dropped:
        return []
    doc["skipped"] = keep
    ctx.write_json(AGENDA_REL, doc)
    ctx.log(
        "homunculus unskipped hollow stages (missing outputs): " + ", ".join(dropped),
        level="warning",
        stage=dropped[0],
    )
    append_ledger(
        ctx,
        {
            "kind": "unskip_hollow",
            "identity": "unskip_hollow",
            "stages": dropped[:40],
        },
    )
    return dropped


def prepare_delivery_guardrails(ctx: RunContext, stages: list[str] | set[str] | None = None) -> list[str]:
    """Unmark/unskip hollow producers so resume cannot fake progress. Returns hole ids."""
    want = set(stages) if stages is not None else set(_order_for("delivery"))
    holes = unmark_hollow_prepare_stages(ctx)
    holes.extend(unmark_hollow_delivery_producers(ctx, want))
    holes.extend(unskip_hollow_stages(ctx, want))
    return list(dict.fromkeys(holes))


def note_identical_stage_error(ctx: RunContext, stage: str, fingerprint: str) -> dict[str, Any]:
    """Cap identical prestage/input errors via operator/identical_failures.json."""
    from interview_mux.identical_failures import record_identical_failure

    row = record_identical_failure(
        ctx,
        failed_stage=stage,
        producer="homunculus_agenda",
        reason=fingerprint[:400],
    )
    # Keep legacy mirror for older readers.
    doc: dict[str, Any] = {}
    if ctx.artifact_exists(IDENTICAL_ERROR_REL):
        raw = ctx.read_json(IDENTICAL_ERROR_REL)
        if isinstance(raw, dict):
            doc = raw
    key = f"{stage}:{fingerprint[:160]}"
    doc[key] = {
        "stage": stage,
        "fingerprint": fingerprint[:160],
        "count": int(row.get("count") or 0),
    }
    ctx.write_json(IDENTICAL_ERROR_REL, doc, skip_handoff=True)
    exhausted = bool(row.get("halt"))
    if exhausted:
        def _mark(meta: dict[str, Any]) -> None:
            meta["needs_operator"] = True
            meta["needs_operator_stage"] = stage
            meta["needs_operator_reason"] = fingerprint[:240]

        try:
            ctx.mutate_run_meta(_mark)
        except Exception:
            pass
        try:
            from interview_mux.homunculus.issues import write_homunculus_plan

            plan = resolve_stage_plan(ctx, stage)
            write_homunculus_plan(
                ctx,
                last_target=stage,
                blockers=[f"identical_error:{fingerprint[:120]}"],
                attempted_heals=[f"identical_stage_error x{int(row.get('count') or 0)}"],
                recommended_next=str(plan.get("recommended_next") or stage),
                reason="identical_error_exhausted",
            )
        except Exception:
            pass
    return {
        "count": int(row.get("count") or 0),
        "exhausted": exhausted,
        "stage": stage,
    }


def remaining_stages(ctx: RunContext, phase: str) -> list[str]:
    # Analysis remainder is .stage_done (shared brief/manifest paths are not
    # unique producers). Delivery remainder is on-disk producer output so a
    # palettes SDP or skip marker cannot hide sound_design_plan / mix / ship.
    if phase != "delivery":
        return [s for s in _order_for(phase) if not ctx.is_done(s)]
    return [s for s in _order_for(phase) if not stage_outputs_present(ctx, s)]


def ship_after_master_remaining(ctx: RunContext) -> list[str]:
    """Cover / encode / publish stages still missing after master.wav exists."""
    return [s for s in SHIP_AFTER_MASTER if not stage_outputs_present(ctx, s)]


def backfill_delivery_holes_after_master(ctx: RunContext) -> list[str]:
    """Mark unmarked pre-master delivery holes once master_finalize has already shipped.

    vo_synthesize was inserted between edl_narrative_audit and edl. Runs that
    already mixed/finalized must not rewind; persist a pair-gap report from
    on-disk transition WAVs and close the marker.
    """
    if not ctx.artifact_exists("master/master.wav") or not ctx.is_done("master_finalize"):
        return []
    filled: list[str] = []
    for stage in DELIVERY_ORDER:
        if stage in SHIP_AFTER_MASTER:
            break
        if ctx.is_done(stage):
            continue
        if stage == "vo_synthesize":
            try:
                from interview_mux.transition_vo import (
                    current_transition_pairs_missing,
                    persist_vo_pair_gap,
                )

                missing = current_transition_pairs_missing(ctx)
                persist_vo_pair_gap(
                    ctx,
                    missing,
                    source="post_master_hole_backfill",
                    extra={"backfilled": True},
                    skip_handoff=True,
                    stage_key="vo_synthesize",
                )
            except Exception:
                ctx.write_json(
                    "mastering/vo_synthesize.json",
                    {"still_missing_pairs": [], "last_source": "post_master_hole_backfill"},
                    skip_handoff=True,
                    stage_key="vo_synthesize",
                )
        ctx.mark_done(stage, force=True)
        filled.append(stage)
        ctx.log(
            f"homunculus backfilled pre-master hole {stage} (master already exists)",
            level="warning",
            stage=stage,
        )
    return filled


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
    if compensating_fact and not ctx.artifact_exists(compensating_fact):
        # Fact IDs are not compensating artifacts. A skip without the on-disk
        # output is a hole (exec_087 skipped transitions with fact 67b9d444).
        compensating_fact = None
    _refuse_music_before_assembly(ctx, stage, action="skip")
    _block_hollow_skip(ctx, stage)
    _refuse_topology_skip_without_samples(ctx, stage)
    if stage == "chapter_close_hitch":
        from interview_mux.chapter_close_hitch import hitch_latch_committed

        if not hitch_latch_committed(ctx):
            raise RuntimeError(
                "cannot skip chapter_close_hitch until the one-shot latch is committed"
            )
    if stage in MUSIC_SKIP_GUARD:
        from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

        if not delivery_sdp_present(ctx):
            raise RuntimeError(
                f"cannot skip {stage}: sound_design_plan has not written the delivery SDP"
            )
        missing_theme = missing_sdp_asset_wavs(ctx)
        if missing_theme:
            raise RuntimeError(
                f"cannot skip {stage}: missing WAV for asset_id "
                + ", ".join(missing_theme[:6])
                + " — run music_palette_compose → sfx_prompt_craft → mmaudio_sfx"
            )
    if stage == "vo_synthesize":
        from interview_mux.transition_vo import current_transition_pairs_missing

        if not ctx.artifact_exists("master/transitions.json"):
            raise RuntimeError(
                "cannot skip vo_synthesize: master/transitions.json missing"
            )
        missing = current_transition_pairs_missing(ctx)
        if missing:
            raise RuntimeError(
                "cannot skip vo_synthesize: current transition pairs missing WAV: "
                + ", ".join(missing[:6])
            )
    if stage in PROTECTED_ISLAND_STAGES:
        if not stage_outputs_present(ctx, stage):
            raise RuntimeError(
                f"cannot skip {stage}: language-island artifacts missing "
                "(low_conf_island_scan / connector_fuse_pass / "
                "connector_fuse_pass_pre_ranking required)"
            )
    protected = (
        stage in PROTECTED_CORE_STAGES
        or stage in PROTECTED_DELIVERY_OUTPUTS
        or stage in PROTECTED_ISLAND_STAGES
        or bool(stage_required_outputs(stage))
    )
    if protected and not stage_outputs_present(ctx, stage):
        needed = stage_required_outputs(stage)
        raise RuntimeError(
            f"cannot skip {stage}: required artifact missing "
            f"({', '.join(needed) if needed else stage})"
        )
    # Skip is an agenda note only — never mark_done. Walk still runs unless
    # stage_outputs_present is true for this producer.
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
    _refuse_music_before_assembly(ctx, stage, action="rerun")
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


def heal_air_order_integrity(ctx: RunContext) -> dict[str, Any]:
    """Deterministic repair for reverse tape jumps and late opening clusters."""
    from interview_mux.stages.selection import finalize_selection_order

    if not ctx.artifact_exists("master/selection.json"):
        return {"ok": False, "error": "no_selection"}
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return {"ok": False, "error": "invalid_selection"}
    try:
        out = finalize_selection_order(ctx, sel, stage="full_master_ranking", apply_cta=True)
        from interview_mux.artifact_writes import write_validated_artifact

        write_validated_artifact(
            ctx,
            "master/selection.json",
            out,
            merge_from_disk=True,
            stage_key="full_master_ranking",
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    append_ledger(
        ctx,
        {"kind": "heal_air_order_integrity", "identity": "heal_air_order_integrity"},
    )
    return {"ok": True}


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


def resolve_stage_plan(ctx: RunContext, stage: str) -> dict[str, Any]:
    """ADG-backed plan: blockers, prereqs, invalidation, recommended next stage."""
    from interview_mux.artifact_dependency_graph import transitive_invalidate, upstream_closure

    stage = str(stage or "").strip()
    if not stage:
        raise ValueError("stage required")
    prereq_chain = upstream_closure(stage)
    invalidate_set = transitive_invalidate(stage)
    blockers: list[str] = []
    native_only = False
    try:
        from interview_mux.pipeline_mode import is_native_only

        native_only = bool(is_native_only(ctx))
    except Exception:
        native_only = False
    gap_skipped = native_only
    if not gap_skipped:
        try:
            from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

            gap_skipped = bool(gap_fill_was_skipped(ctx))
        except Exception:
            gap_skipped = False
    for prereq_stage, rel in DELIVERY_ANALYSIS_PREREQS:
        if gap_skipped and prereq_stage in _GAP_FILL_ANALYSIS_PREREQS:
            if ctx.artifact_exists(rel) and not ctx.is_done(prereq_stage):
                ctx.mark_done(prereq_stage, force=True)
            continue
        if not ctx.artifact_exists(rel):
            blockers.append(f"missing_artifact:{rel}")
            continue
        if not ctx.is_done(prereq_stage):
            blockers.append(f"stage_not_done:{prereq_stage}")
    skip = skipped_stages(ctx)
    for up in prereq_chain:
        if up in skip:
            continue
        if not stage_outputs_present(ctx, up):
            blockers.append(f"upstream_incomplete:{up}")
    recommended_next = stage
    for token in blockers:
        if token.startswith("stage_not_done:"):
            recommended_next = token.split(":", 1)[1]
            break
        if token.startswith("upstream_incomplete:"):
            recommended_next = token.split(":", 1)[1]
            break
        if token.startswith("missing_artifact:"):
            for ps, rel in DELIVERY_ANALYSIS_PREREQS:
                if rel == token.split(":", 1)[1]:
                    recommended_next = ps
                    break
            break
    pipeline_mode_val: str | None = None
    try:
        from interview_mux.pipeline_mode import resolve_effective_mode

        pipeline_mode_val = str(resolve_effective_mode(ctx).get("mode") or "") or None
    except Exception:
        pipeline_mode_val = None
    return {
        "stage": stage,
        "blockers": blockers,
        "prereq_chain": prereq_chain,
        "invalidate_set": invalidate_set,
        "recommended_next": recommended_next,
        "pipeline_mode": pipeline_mode_val,
    }


def rerun_with_impact(ctx: RunContext, stage: str) -> dict[str, Any]:
    """8A: invalidate downstream plus ADG transitive consumer set."""
    from interview_mux.artifact_dependency_graph import transitive_invalidate

    stage = str(stage or "").strip()
    if not stage:
        raise ValueError("stage required")
    invalidate_set = transitive_invalidate(stage)
    cleared = invalidate_downstream(ctx, stage)
    append_ledger(
        ctx,
        {
            "kind": "rerun_with_impact",
            "identity": "rerun_with_impact",
            "stage": stage,
            "invalidate_set": invalidate_set[:40],
        },
    )
    return {
        "ok": True,
        "stage": stage,
        "invalidate_set": invalidate_set,
        **cleared,
    }


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
    from interview_mux.gates import g0_blocks_analysis
    from interview_mux.pipeline import run_single_stage

    setattr(ctx, "_homunculus_seed_walk", True)
    try:
        from interview_mux.web.job_progress import notify_batch_plan

        walk_stages = list(stages)
        if g0_blocks_analysis(ctx) and ctx.artifact_exists("ingest/transcript.json"):
            from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

            stage_order = {sid: idx for idx, sid in enumerate(ANALYSIS_ORDER + DELIVERY_ORDER)}
            g0_idx = stage_order.get("transcript_review_build")
            if g0_idx is not None:
                walk_stages = [
                    s for s in walk_stages if stage_order.get(s, 10**9) <= g0_idx
                ]

        notify_batch_plan(
            ctx.run_id,
            walk_stages,
            message=f"Walking {len(walk_stages)} remaining stage(s) ({reason})",
        )
        prepare_delivery_guardrails(ctx, walk_stages)
        for stage in walk_stages:
            if ctx.is_done(stage) and stage_outputs_present(ctx, stage):
                continue
            if ctx.is_done(stage) and not stage_outputs_present(ctx, stage):
                unmark_stage_only(ctx, stage)
            if stage in skipped_stages(ctx) and stage_outputs_present(ctx, stage):
                continue
            try:
                _refuse_g0_locked_rerun(ctx, stage, action="walk")
                _refuse_delivery_timeline_rewind(ctx, stage, action="walk")
                _refuse_music_before_assembly(ctx, stage, action="walk")
            except RuntimeError:
                if prepare_outputs_present(ctx, stage) and not ctx.is_done(stage):
                    ctx.mark_done(stage, force=True)
                continue
            try:
                run_single_stage(ctx, stage)
            except Exception as exc:
                fp = f"{type(exc).__name__}:{str(exc)[:160]}"
                hit = note_identical_stage_error(ctx, stage, fp)
                if hit.get("exhausted"):
                    ctx.log(
                        f"homunculus identical error cap on {stage} — needs_operator ({fp})",
                        level="error",
                        stage=stage,
                    )
                    break
                raise
            if stage == "transcript_review_build" and g0_blocks_analysis(ctx):
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
    seed = _order_for(phase)
    # Resume slices (from_stage=edl) must not pull earlier hollow producers
    # (nugget_layup / sound_design_plan) back into the walk — that regenerates
    # MusicGen after a junction/mix order heal.
    if phase == "delivery" and prior:
        first = prior[0]
        start_idx = seed.index(first) if first in seed else 0
        forward = set(seed[start_idx:])
        holes = prepare_delivery_guardrails(ctx, forward)
        allow = set(prior) | (set(holes) & forward)
    else:
        holes = prepare_delivery_guardrails(ctx, set(prior) | set(seed))
        allow = set(prior) | set(holes)
    remaining = [s for s in remaining_stages(ctx, phase) if s in allow]
    write_agenda(ctx, phase, remaining, source="conductor")
    if phase == "delivery":
        if ctx.artifact_exists("master/master.wav") and ctx.is_done("master_finalize"):
            filled = backfill_delivery_holes_after_master(ctx)
            if filled:
                remaining = [s for s in remaining if s not in filled and not ctx.is_done(s)]
                write_agenda(ctx, phase, remaining, source="conductor")
        try:
            from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

            if delivery_sdp_present(ctx) and not missing_sdp_asset_wavs(ctx):
                from interview_mux.delivery_recovery import MUSIC_BEFORE_MIX

                kept: list[str] = []
                for sid in remaining:
                    if sid == "mmaudio_sfx" and not stage_outputs_present(ctx, sid):
                        try:
                            from interview_mux.mmaudio_asset_qa import heal_mmaudio_qa_wav_parity

                            heal_mmaudio_qa_wav_parity(ctx)
                        except Exception:
                            pass
                    if sid in MUSIC_BEFORE_MIX and stage_outputs_present(ctx, sid):
                        if not ctx.is_done(sid):
                            ctx.mark_done(sid, force=True)
                        if not ctx.is_done(sid):
                            # Hollow QA/palette files must not drop the generator.
                            kept.append(sid)
                            continue
                        ctx.log(
                            f"homunculus keeping {sid} — SDP theme WAVs already on disk",
                            level="info",
                            stage=sid,
                        )
                        continue
                    kept.append(sid)
                if kept != remaining:
                    remaining = kept
                    write_agenda(ctx, phase, remaining, source="conductor")
        except Exception:
            pass
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
            remaining = [s for s in remaining_stages(ctx, phase) if s in allow]
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
            from interview_mux.web.job_progress import notify_batch_plan

            notify_batch_plan(
                ctx.run_id,
                remaining,
                message=(
                    f"Homunculus selecting next {phase} stage "
                    f"({len(remaining)} remaining)"
                ),
            )
            msg = (
                f"Complete the {phase} phase for this tape. Remaining stages (seed order): "
                f"{', '.join(remaining)}. You may skip, reorder, or surgically re-run. "
                f"Select run_stage_* tools. Admit every output. Pack volleys by fact IDs. "
                f"Cite docs via retrieve_canon. Do not invent dialogue. Respect G0. "
                f"Do not skip low_conf_island_scan or connector_fuse_pass unless artifacts exist. "
                f"Do not skip content_context, talking_points_compose, ideal_cuts_propose, "
                f"ideal_cuts_materialize, boundary_detection, episode_structure_compose, "
                f"or chapter_close_hitch unless artifacts exist (hitch only after latch). "
                f"Do not skip transitions, sound_design_plan, edl, assembly_preview, "
                f"listen_delight_audit, mix, junction_snip_qa, master_finalize, or ship "
                f"stages without their on-disk outputs. Prefer MusicGen large for beds. "
                f"Do not run mix until sound_design/assets WAVs exist for every SDP asset_id "
                f"(music_palette_compose → sfx_prompt_craft → mmaudio_sfx). Hard limits apply. "
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
    still = [s for s in remaining_stages(ctx, phase) if s in allow]
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
    elif still and phase == "delivery" and ctx.artifact_exists("master/master.wav"):
        pmq: dict[str, Any] | None = None
        pmq_missing = not ctx.artifact_exists("master/post_master_quality.json")
        if not pmq_missing:
            loaded = ctx.read_json("master/post_master_quality.json")
            pmq = loaded if isinstance(loaded, dict) else None
        pmq_failed = pmq_missing or bool(
            pmq
            and (
                pmq.get("status") == "fail"
                or pmq.get("publish_allowed") is False
            )
        )
        if pmq_failed:
            pre_ship = [s for s in still if s not in SHIP_AFTER_MASTER]
            if pre_ship:
                from interview_mux.v2.config import DELIVERY_ORDER

                delivery_only = set(DELIVERY_ORDER)
                pre_ship = [s for s in pre_ship if s in delivery_only]
                if ctx.artifact_exists("master/assembly.wav") and "mix" in DELIVERY_ORDER:
                    mix_idx = DELIVERY_ORDER.index("mix")
                    pre_ship = [s for s in pre_ship if s in DELIVERY_ORDER[mix_idx:]]
            if pre_ship:
                ctx.log(
                    "homunculus delivery remastering after failed post-master quality "
                    f"({len(pre_ship)} stage(s))",
                    level="warning",
                    stage=pre_ship[0],
                )
                walk_seed_agenda(ctx, pre_ship, reason="delivery_walk_unpublishable_master")
        else:
            ship = ship_after_master_remaining(ctx)
            if ship:
                ctx.log(
                    "homunculus delivery walking remaining ship stages "
                    f"({len(ship)} stage(s))",
                    level="warning",
                    stage=ship[0],
                )
                walk_seed_agenda(ctx, ship, reason="delivery_walk_to_publish")
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
    return {"conductor": conductor_out, "remaining_after": [s for s in remaining_stages(ctx, phase) if s in allow]}
