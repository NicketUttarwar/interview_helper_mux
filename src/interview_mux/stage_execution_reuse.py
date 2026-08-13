"""Offer reuse of prior execution artifacts before running expensive pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.journey_state import read_run_meta
from interview_mux.run_context import RunContext
from interview_mux.source_audio_hash import (
    hash_short_from_full,
    hashes_match,
    parse_hash_from_run_id,
)
from interview_mux.web.stages import STAGE_BY_ID

Disposition = Literal["run", "skipped"]

# CLI / batch overrides (set via configure_stage_reuse_cli).
_auto_reuse_from: str | None = None
_no_reuse_offers: bool = False


def configure_stage_reuse_cli(
    *,
    reuse_from: str | None = None,
    no_reuse_offers: bool = False,
) -> None:
    global _auto_reuse_from, _no_reuse_offers
    _auto_reuse_from = reuse_from
    _no_reuse_offers = no_reuse_offers


def reset_stage_reuse_cli() -> None:
    configure_stage_reuse_cli(reuse_from=None, no_reuse_offers=False)


@dataclass(frozen=True)
class ReuseCandidate:
    run_id: str
    updated_at: str | None
    execution_number: int | None
    paths: list[str]
    source_audio_hash: str | None = None
    source_audio_hash_short: str | None = None
    hash_in_run_id: str | None = None
    same_source_audio: bool = False
    match_kind: Literal["hash"] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "updated_at": self.updated_at,
            "execution_number": self.execution_number,
            "paths": self.paths,
            "source_audio_hash": self.source_audio_hash,
            "source_audio_hash_short": self.source_audio_hash_short,
            "hash_in_run_id": self.hash_in_run_id,
            "same_source_audio": self.same_source_audio,
            "match_kind": self.match_kind,
        }


class StageReuseOfferPending(Exception):
    """Pipeline paused until operator accepts or declines reuse."""

    def __init__(self, stage_id: str, candidates: list[ReuseCandidate]) -> None:
        self.stage_id = stage_id
        self.candidates = candidates
        ids = ", ".join(c.run_id for c in candidates[:3])
        extra = f" (+{len(candidates) - 3} more)" if len(candidates) > 3 else ""
        super().__init__(
            f"Stage '{stage_id}' can reuse outputs from a previous execution ({ids}{extra}). "
            "Choose reuse or run fresh in the GUI, then continue."
        )


# Transcript artifact paths copied on explicit reuse accept (final paths, not staging).
_TRANSCRIPT_STAGES = frozenset({"transcribe", "transcript_review_build", "transcript_review"})

_TRANSCRIPT_REUSE_CORE: tuple[str, ...] = (
    "transcript/full.json",
    "transcript/speakers.json",
    "transcript/corrections.json",
    "operator/transcript_corrected.json",
    "operator/transcript_corrected.txt",
    "operator/transcript_corrections.json",
)

# Relative paths to copy/check. Trailing "/" = non-empty directory. "glob:" prefix = expand.
_STAGE_REUSE_OUTPUTS: dict[str, tuple[str, ...]] = {
    "audio_preclean": ("preclean/lineage.json", "preclean/provider.json", "preclean/isolated.wav"),
    "ingest": ("ingest/normalized.wav", "ingest/checksums.json", "ingest/loudness.json"),
    "transcribe": _TRANSCRIPT_REUSE_CORE,
    "transcript_review_build": (
        "transcript/review_queue.json",
        "transcript/corrections.json",
        "glob:transcript/review_clips/*.wav",
    ),
    "source_acoustic_profile": ("understanding/source_acoustic_profile.json",),
    "interview_spine_build": (
        "understanding/interview_spine.json",
        "understanding/interview_spine/embeddings.npz",
    ),
    "speaker_roles": ("understanding/speakers.json",),
    "source_topology_build": (
        "understanding/source_topology.json",
        "understanding/flow_adaptation.json",
        "glob:understanding/speaker_samples/*.wav",
    ),
    "content_context": ("understanding/content_brief.json",),
    "boundary_detection": ("segments/boundaries.json",),
    "segment_classification": ("segments/manifest.json",),
    "sound_design_palettes": ("understanding/sound_design_plan.json",),
    "missing_framing": (
        "understanding/gap_evaluations.json",
        "understanding/gap_fill_skip.json",
    ),
    "optimal_questions": (
        "understanding/gap_report.json",
        "understanding/interviewer_script.txt",
        "understanding/gap_fill_skip.json",
    ),
    "delivery_brief_build": ("understanding/delivery_brief.json",),
    "soundscape_policy_build": ("understanding/soundscape_policy.json",),
    "episode_structure_compose": ("understanding/episode_structure.json",),
    "vo_ingest": (),
    "topic_coverage_audit": ("master/coverage_audit.json",),
    "narrative_arc_plan": ("master/narrative_plan.json",),
    "full_master_ranking": ("master/selection.json",),
    "transitions": ("master/transitions.json",),
    "sound_design_plan": ("understanding/sound_design_plan.json",),
    "sound_design_vo_finalize": ("understanding/sound_design_plan.json",),
    "edl_narrative_audit": ("master/edl_narrative_audit.json",),
    "edl": ("master/edl.json",),
    "assembly_preview": ("master/assembly_preview.wav",),
    "sfx_prompt_craft": ("sound_design/sfx_prompts.json",),
    "mmaudio_sfx": (
        "glob:sound_design/assets/*.wav",
        "glob:master/sfx/*.wav",
    ),
    "mix": ("master/assembly.wav",),
    "junction_snip_qa": (
        "master/junction_snip_qa.json",
        "master/junction_feel_audit.json",
        "master/seam_autopsy.json",
        "master/render_ledger.json",
        "master/failure_review.json",
        "master/remediation_plan.json",
        "master/remediation_run_log.json",
    ),
    "master_finalize": ("master/master.wav",),
    "transcript_review": (
        "transcript/corrections.json",
        "transcript/full.json",
        "operator/transcript_corrected.json",
        "operator/transcript_corrected.txt",
        "operator/transcript_corrections.json",
    ),
    "analysis_profile": (
        "understanding/analysis_state.json",
        "understanding/investigation_queue.json",
        "operator/analysis_profile.json",
    ),
    "g1_vo_pickup": (
        "glob:vo_pickup/*.wav",
        "glob:vo_pickup/clean/*.wav",
        "glob:vo_pickup/normalized/*.wav",
    ),
    "mux_flow1": ("master/assembly.wav",),
    "sonic_context_build": ("understanding/sonic_context.json",),
    "content_brief_reanchor": ("understanding/content_brief.json",),
    "boundary_topic_resplit": ("segments/boundaries.json",),
}


# Copied when present but not required for reuse eligibility.
_STAGE_REUSE_OPTIONAL: dict[str, frozenset[str]] = {
    "transcribe": frozenset(
        {
            "transcript/corrections.json",
            "operator/transcript_corrected.json",
            "operator/transcript_corrected.txt",
            "operator/transcript_corrections.json",
        }
    ),
    "transcript_review_build": frozenset({"transcript/corrections.json"}),
    "transcript_review": frozenset(
        {
            "operator/transcript_corrected.json",
            "operator/transcript_corrected.txt",
            "operator/transcript_corrections.json",
        }
    ),
}

# Glob specs that may legitimately match zero files (stage still reusable).
_STAGE_REUSE_OPTIONAL_GLOBS: dict[str, frozenset[str]] = {
    "transcript_review_build": frozenset({"glob:transcript/review_clips/*.wav"}),
}


def stage_reuse_offers_enabled() -> bool:
    if _no_reuse_offers:
        return False
    cfg = merged_config().get("journey_ui") or {}
    if not isinstance(cfg, dict):
        return True
    return bool(cfg.get("enable_stage_reuse_offers", True))


def stage_reuse_blocks_execute() -> bool:
    """Return True when reuse offers block stage execution."""
    if not stage_reuse_offers_enabled():
        return False
    return True


def _stored_source_audio_hash(ctx: RunContext) -> str | None:
    """Source-audio hash from run_meta without re-reading the pipeline WAV."""
    return ctx.source_audio_hash(recompute=False)


def _hash_short_for_ctx(ctx: RunContext) -> str | None:
    meta = read_run_meta(ctx)
    short = meta.get("source_audio_hash_short")
    if short:
        return str(short)
    full = _stored_source_audio_hash(ctx)
    if full:
        return hash_short_from_full(full)
    return parse_hash_from_run_id(ctx.run_id)


def _reuse_lookback_limit() -> int:
    from interview_mux.session_lineage import stage_reuse_lookback_limit

    return stage_reuse_lookback_limit()


def _reuse_candidate_for_source(
    ctx: RunContext,
    source: RunContext,
    stage_id: str,
    source_run_id: str,
) -> ReuseCandidate:
    meta = read_run_meta(source)
    paths = list_copy_paths_for_stage(source, stage_id)
    src_hash = _stored_source_audio_hash(source)
    src_short = (
        meta.get("source_audio_hash_short")
        or (hash_short_from_full(src_hash) if src_hash else None)
        or parse_hash_from_run_id(source_run_id)
    )
    hash_in_id = parse_hash_from_run_id(source_run_id)
    return ReuseCandidate(
        run_id=source_run_id,
        updated_at=meta.get("updated_at"),
        execution_number=meta.get("execution_number"),
        paths=paths,
        source_audio_hash=str(src_hash) if src_hash else None,
        source_audio_hash_short=str(src_short) if src_short else None,
        hash_in_run_id=hash_in_id,
        same_source_audio=True,
        match_kind="hash",
    )


def source_audio_hashes_match(current: RunContext, source: RunContext) -> bool:
    """True when both runs have a source-audio hash and they match."""
    cur_hash = _stored_source_audio_hash(current)
    src_hash = _stored_source_audio_hash(source)
    if cur_hash and src_hash and hashes_match(cur_hash, src_hash):
        return True
    cur_short = _hash_short_for_ctx(current)
    src_short = _hash_short_for_ctx(source)
    return bool(cur_short and src_short and hashes_match(cur_short, src_short))


def runs_share_source_audio(current: RunContext, source: RunContext) -> bool:
    return source_audio_hashes_match(current, source)


def get_reuse_decision(ctx: RunContext, stage_id: str) -> dict[str, Any] | None:
    row = (read_run_meta(ctx).get("stage_reuse") or {}).get(stage_id)
    return row if isinstance(row, dict) else None


def record_reuse_decision(
    ctx: RunContext,
    stage_id: str,
    *,
    action: str,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    entry: dict[str, Any] = {"action": action, "at": now}
    if source_run_id:
        entry["source_run_id"] = source_run_id

    def _patch(meta: dict[str, Any]) -> None:
        reuse = dict(meta.get("stage_reuse") or {})
        reuse[stage_id] = entry
        meta["stage_reuse"] = reuse

    ctx.mutate_run_meta(_patch)
    from interview_mux.web.stages import STAGE_BY_ID

    title = STAGE_BY_ID.get(stage_id).title if STAGE_BY_ID.get(stage_id) else stage_id
    if action == "accept":
        ctx.log(
            f"Reusing {title} outputs from {source_run_id}.",
            level="success",
            stage=stage_id,
            detail={"stage_reuse": entry},
        )
    else:
        ctx.log(
            f"Running {title} fresh (declined reuse).",
            level="info",
            stage=stage_id,
            detail={"stage_reuse": entry},
        )
    return entry


def clear_stage_reuse_from(ctx: RunContext, from_stage: str, order: list[str]) -> None:
    if from_stage not in order:
        return
    reuse = read_run_meta(ctx).get("stage_reuse")
    if not isinstance(reuse, dict) or not reuse:
        return
    idx = order.index(from_stage)

    def _patch(meta: dict[str, Any]) -> None:
        block = dict(meta.get("stage_reuse") or {})
        for sid in order[idx:]:
            block.pop(sid, None)
        if block:
            meta["stage_reuse"] = block
        elif "stage_reuse" in meta:
            del meta["stage_reuse"]

    ctx.mutate_run_meta(_patch)


def stage_reuse_output_specs(stage_id: str) -> tuple[str, ...]:
    if stage_id in _STAGE_REUSE_OUTPUTS:
        return _STAGE_REUSE_OUTPUTS[stage_id]
    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return ()
    return tuple(info.artifacts) + tuple(info.audio_outputs)


def _expand_spec_paths_fixed(spec: str, ctx: RunContext) -> list[str]:
    if spec.startswith("glob:"):
        rel_glob = spec[5:]
        if "/" in rel_glob:
            parent_rel, _, pat = rel_glob.partition("/")
            parent = ctx.final_path(*parent_rel.split("/"))
        else:
            parent = ctx.run_dir
            pat = rel_glob
        if not parent.is_dir():
            return []
        return [
            str(p.relative_to(ctx.run_dir)).replace("\\", "/")
            for p in sorted(parent.glob(pat))
            if p.is_file()
        ]
    if spec.endswith("/"):
        dir_path = ctx.final_path(*spec.rstrip("/").split("/"))
        if not dir_path.is_dir():
            return []
        return [
            str(p.relative_to(ctx.run_dir)).replace("\\", "/")
            for p in sorted(dir_path.rglob("*"))
            if p.is_file()
        ]
    return [spec]


def prior_run_has_reusable_stage(source_ctx: RunContext, stage_id: str) -> bool:
    if not source_ctx.is_done(stage_id):
        return False
    specs = stage_reuse_output_specs(stage_id)
    optional = _STAGE_REUSE_OPTIONAL.get(stage_id, frozenset())
    optional_globs = _STAGE_REUSE_OPTIONAL_GLOBS.get(stage_id, frozenset())
    if not specs:
        if stage_id == "vo_ingest":
            pickup = source_ctx.final_path("vo_pickup")
            return pickup.is_dir() and any(pickup.rglob("*.wav"))
        return True
    for spec in specs:
        if spec in optional:
            continue
        if spec.startswith("glob:"):
            expanded = _expand_spec_paths_fixed(spec, source_ctx)
            if spec not in optional_globs and not expanded:
                return False
            continue
        if spec.endswith("/"):
            expanded = _expand_spec_paths_fixed(spec, source_ctx)
            if not expanded:
                return False
            continue
        if not prior_run_has_file(source_ctx, spec):
            return False
    return True


def prior_run_has_file(ctx: RunContext, rel: str) -> bool:
    p = ctx.final_path(*rel.split("/"))
    return p.is_file() and p.stat().st_size > 0


_SDP_REUSE_STAGES = frozenset(
    {
        "sound_design_palettes",
        "sound_design_plan",
        "sound_design_vo_finalize",
    }
)


def _sdp_source_conflict(ctx: RunContext, source_run_id: str, stage_id: str) -> str | None:
    if stage_id not in _SDP_REUSE_STAGES:
        return None
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return None
    reuse = read_run_meta(ctx).get("stage_reuse") or {}
    if not isinstance(reuse, dict):
        return None
    for sid, row in reuse.items():
        if sid not in _SDP_REUSE_STAGES or not isinstance(row, dict):
            continue
        prior_source = row.get("source_run_id")
        if prior_source and prior_source != source_run_id:
            return (
                f"Cannot reuse {stage_id}: sound_design_plan.json was already reused from "
                f"{prior_source}. Invalidate SDP-dependent stages or run fresh."
            )
    return None


def find_reuse_candidates(ctx: RunContext, stage_id: str) -> list[ReuseCandidate]:
    from interview_mux.session_lineage import recent_prior_execution_run_ids

    current_hash = _stored_source_audio_hash(ctx)
    hash_short = _hash_short_for_ctx(ctx)
    if not current_hash and not hash_short:
        return []

    for prior_id in recent_prior_execution_run_ids(ctx, limit=_reuse_lookback_limit()):
        if not RunContext.exists(prior_id):
            continue
        source = RunContext(prior_id, create=False)
        if not source_audio_hashes_match(ctx, source):
            continue
        if not prior_run_has_reusable_stage(source, stage_id):
            continue
        if stage_id == "vo_ingest" and not _gap_reports_match(ctx, source):
            continue
        return [_reuse_candidate_for_source(ctx, source, stage_id, prior_id)]
    return []


def list_copy_paths_for_stage(source_ctx: RunContext, stage_id: str) -> list[str]:
    specs = stage_reuse_output_specs(stage_id)
    paths: list[str] = []
    for spec in specs:
        paths.extend(_expand_spec_paths_fixed(spec, source_ctx))
    if stage_id == "vo_ingest":
        pickup = source_ctx.final_path("vo_pickup")
        if pickup.is_dir():
            for p in sorted(pickup.glob("*.wav")):
                rel = str(p.relative_to(source_ctx.run_dir)).replace("\\", "/")
                paths.append(rel)
    return sorted(set(paths))


def _reuse_dest(ctx: RunContext, rel: str, *, use_staging: bool, stage_id: str) -> Path:
    if use_staging and stage_id not in _TRANSCRIPT_STAGES:
        from interview_mux.write_staging import staged_path

        dest = staged_path(ctx, rel, stage_id=stage_id)
    else:
        dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _apply_gate_meta_reuse(ctx: RunContext, source: RunContext, stage_id: str) -> None:
    src_meta = read_run_meta(source)
    if stage_id == "analysis_profile":
        verified = src_meta.get("profile_verified_at")
        if verified:
            ctx.mutate_run_meta(lambda m: m.update({"profile_verified_at": verified}))


def apply_stage_reuse(ctx: RunContext, stage_id: str, source_run_id: str) -> list[str]:
    if not RunContext.exists(source_run_id):
        raise ValueError(f"Source run not found: {source_run_id}")
    sdp_err = _sdp_source_conflict(ctx, source_run_id, stage_id)
    if sdp_err:
        raise ValueError(sdp_err)
    source = RunContext(source_run_id, create=False)
    if not prior_run_has_reusable_stage(source, stage_id):
        raise ValueError(f"Run {source_run_id} does not have reusable outputs for {stage_id}")

    from interview_mux.file_store import atomic_copy, write_json as fs_write_json
    from interview_mux.run_lock import RunDirectoryLock
    from interview_mux.write_staging import (
        _staging_lock,
        enter_stage_staging,
        exit_stage_staging,
        write_approval_enabled,
    )

    use_staging = write_approval_enabled() and stage_id not in _TRANSCRIPT_STAGES
    if use_staging:
        enter_stage_staging(stage_id)

    copied: list[str] = []
    staging_lock = _staging_lock(ctx, stage_id) if use_staging else None
    with RunDirectoryLock(source_run_id):
        try:
            if staging_lock is not None:
                staging_lock.acquire()
            for rel in list_copy_paths_for_stage(source, stage_id):
                src = source.final_path(*rel.split("/"))
                if not src.is_file():
                    continue
                dest = _reuse_dest(ctx, rel, use_staging=use_staging, stage_id=stage_id)
                atomic_copy(src, dest)
                copied.append(rel)

            if stage_id == "vo_ingest" or stage_id == "g1_vo_pickup":
                if stage_id == "vo_ingest" and not _gap_reports_match(ctx, source):
                    raise ValueError(
                        "Cannot reuse vo_ingest: gap_report.json differs from source execution."
                    )
                pickup = source.final_path("vo_pickup")
                if pickup.is_dir():
                    ctx.final_path("vo_pickup").mkdir(parents=True, exist_ok=True)
                    for wav in sorted(pickup.rglob("*.wav")):
                        rel = str(wav.relative_to(source.run_dir)).replace("\\", "/")
                        dest = _reuse_dest(ctx, rel, use_staging=use_staging, stage_id=stage_id)
                        atomic_copy(wav, dest)
                        if rel not in copied:
                            copied.append(rel)

            if stage_id == "vo_ingest":
                analysis_data = {
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "run_id": ctx.run_id,
                    "reused_from": source_run_id,
                }
                if use_staging:
                    dest = _reuse_dest(
                        ctx, "analysis_complete.json", use_staging=True, stage_id=stage_id
                    )
                    fs_write_json(dest, analysis_data)
                    copied.append("analysis_complete.json")
                else:
                    ctx.write_json("analysis_complete.json", analysis_data)

            _apply_gate_meta_reuse(ctx, source, stage_id)
            _validate_copied_artifacts(ctx, stage_id)
            if stage_id in _TRANSCRIPT_STAGES:
                if stage_id == "transcript_review_build" and ctx.artifact_exists(
                    "transcript/review_queue.json"
                ):
                    ctx.mark_done("transcript_review_build", force=True)
                elif stage_id == "transcribe":
                    ctx.mark_done("transcribe", force=True)
                # Prefer operator-corrected text over raw STT copy when both landed.
                from interview_mux.stages.transcript_review import (
                    prefer_operator_corrected_transcript,
                    set_transcript_reuse_pending_edit,
                )

                prefer_operator_corrected_transcript(ctx)
                # One-time edit interstitial only on initial transcript reuse (transcribe).
                if stage_id == "transcribe":
                    set_transcript_reuse_pending_edit(ctx, True)
                # transcript_review gate stays open until operator Save and continue
                # (reuse edit interstitial) or Save and complete review.
            else:
                from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

                primary = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
                if not copied:
                    raise ValueError(
                        f"Reuse copied no files for {stage_id} — cannot mark stage done"
                    )
                if primary and not ctx.artifact_exists(primary):
                    raise ValueError(
                        f"Reuse did not copy required artifact {primary} for {stage_id}"
                    )
                ctx.mark_done(stage_id)
        finally:
            if staging_lock is not None:
                staging_lock.release()
            if use_staging:
                exit_stage_staging()

    now = datetime.now(timezone.utc).isoformat()

    def _mark_applied(meta: dict[str, Any]) -> None:
        reuse = dict(meta.get("stage_reuse") or {})
        row = dict(reuse.get(stage_id) or {})
        row["applied_at"] = now
        reuse[stage_id] = row
        meta["stage_reuse"] = reuse

    ctx.mutate_run_meta(_mark_applied)
    ctx.log(
        f"stage_reuse_applied: copied {len(copied)} file(s) from {source_run_id}",
        level="success",
        stage=stage_id,
        detail={"copied": copied, "source_run_id": source_run_id},
    )
    return copied


def _validate_copied_artifacts(ctx: RunContext, stage_id: str) -> None:
    from interview_mux.prompt_validation import (
        STAGE_ARTIFACT_DISK_PATHS,
        validate_artifact_write,
        validate_stage_artifacts,
    )

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
    if rel and ctx.artifact_exists(rel):
        raw = ctx.read_json(rel)
        if isinstance(raw, dict):
            errors = validate_artifact_write(rel, raw)
            if errors:
                raise ValueError(f"Reused artifact {rel} failed validation: {'; '.join(errors[:4])}")
            stage_errors = validate_stage_artifacts(stage_id, raw)
            if stage_errors:
                raise ValueError(
                    f"Reused stage {stage_id} failed schema check: {'; '.join(stage_errors[:4])}"
                )
            from interview_mux.artifact_lifecycle import validate_reuse_copy

            reuse_errors = validate_reuse_copy(ctx, stage_id, "")
            if reuse_errors:
                raise ValueError(
                    f"Reused artifact {rel} failed sufficiency: {'; '.join(reuse_errors[:4])}"
                )


def reuse_already_applied(ctx: RunContext, stage_id: str) -> bool:
    """True when accept reuse already copied outputs (done or awaiting write approval)."""
    from interview_mux.write_staging import has_pending_writes

    if ctx.is_done(stage_id):
        return True
    if has_pending_writes(ctx, stage_id):
        return True
    decision = get_reuse_decision(ctx, stage_id)
    return bool(decision and decision.get("action") == "accept" and decision.get("applied_at"))


def reuse_candidates_if_undecided(ctx: RunContext, stage_id: str) -> list[ReuseCandidate]:
    if not stage_reuse_offers_enabled():
        return []
    if ctx.is_done(stage_id):
        return []
    if get_reuse_decision(ctx, stage_id):
        return []
    return find_reuse_candidates(ctx, stage_id)


def reuse_offer_payload(ctx: RunContext, stage_id: str) -> dict[str, Any]:
    decision = get_reuse_decision(ctx, stage_id)
    candidates = find_reuse_candidates(ctx, stage_id)
    return {
        "stage_id": stage_id,
        "eligible": bool(candidates),
        "blocking": bool(candidates) and stage_reuse_blocks_execute(),
        "candidates": [c.to_dict() for c in candidates],
        "pending_decision": decision,
        "current_source_audio_hash_short": (
            read_run_meta(ctx).get("source_audio_hash_short")
            or (
                hash_short_from_full(ctx.source_audio_hash())
                if ctx.source_audio_hash()
                else None
            )
        ),
    }


def pending_reuse_stage(ctx: RunContext, stage_id: str) -> bool:
    """True when reuse is available but operator has not decided yet."""
    return bool(reuse_candidates_if_undecided(ctx, stage_id))


def resolve_before_stage_run(ctx: RunContext, stage_id: str) -> Disposition:
    """Return 'skipped' when reuse applied; 'run' to execute stage; raise when offer needed."""
    if ctx.is_done(stage_id):
        return "skipped"

    if not stage_reuse_offers_enabled():
        return "run"

    if _auto_reuse_from:
        source = RunContext(_auto_reuse_from, create=False)
        if (
            source_audio_hashes_match(ctx, source)
            and prior_run_has_reusable_stage(source, stage_id)
        ):
            record_reuse_decision(
                ctx, stage_id, action="accept", source_run_id=_auto_reuse_from
            )
            apply_stage_reuse(ctx, stage_id, _auto_reuse_from)
            return "skipped"
        return "run"

    decision = get_reuse_decision(ctx, stage_id)
    if decision:
        action = str(decision.get("action") or "")
        if action == "accept":
            if reuse_already_applied(ctx, stage_id):
                return "skipped"
            source_id = str(decision.get("source_run_id") or "")
            if not source_id:
                return "run"
            apply_stage_reuse(ctx, stage_id, source_id)
            return "skipped"
        if action == "decline":
            return "run"

    candidates = reuse_candidates_if_undecided(ctx, stage_id)
    if not candidates:
        return "run"

    raise StageReuseOfferPending(stage_id, candidates)


def check_stage_reuse_before_execute(
    ctx: RunContext,
    stage_ids: list[str],
) -> StageReuseOfferPending | None:
    """Return pending offer for the first stage in execute order that needs a decision."""
    if not stage_reuse_blocks_execute():
        return None
    for sid in stage_ids:
        candidates = reuse_candidates_if_undecided(ctx, sid)
        if candidates:
            return StageReuseOfferPending(sid, candidates)
    return None


def _gap_reports_match(a: RunContext, b: RunContext) -> bool:
    pa = a.path("understanding/gap_report.json")
    pb = b.path("understanding/gap_report.json")
    if not pa.is_file() or not pb.is_file():
        return True
    return pa.read_bytes() == pb.read_bytes()
