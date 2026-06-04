"""Offer reuse of prior execution artifacts before running expensive pipeline stages."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "updated_at": self.updated_at,
            "execution_number": self.execution_number,
            "paths": self.paths,
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


# Relative paths to copy/check. Trailing "/" = non-empty directory. "glob:" prefix = expand.
_STAGE_REUSE_OUTPUTS: dict[str, tuple[str, ...]] = {
    "audio_preclean": ("preclean/lineage.json", "preclean/provider.json", "preclean/isolated.wav"),
    "ingest": ("ingest/normalized.wav", "ingest/checksums.json"),
    "transcribe": ("transcript/full.json", "transcript/speakers.json"),
    "transcript_review_build": (
        "transcript/review_queue.json",
        "glob:transcript/review_clips/*.wav",
    ),
    "source_acoustic_profile": ("understanding/source_acoustic_profile.json",),
    "speaker_roles": ("understanding/speakers.json",),
    "content_context": ("understanding/content_brief.json",),
    "boundary_detection": ("segments/boundaries.json",),
    "segment_classification": ("segments/manifest.json",),
    "sound_design_palettes": ("understanding/sound_design_plan.json",),
    "missing_framing": ("understanding/gap_evaluations.json",),
    "optimal_questions": (
        "understanding/gap_report.json",
        "understanding/interviewer_script.txt",
    ),
    "vo_ingest": (),
    "topic_coverage_audit": ("flow_1_master/coverage_audit.json",),
    "narrative_arc_plan": ("flow_1_master/narrative_plan.json",),
    "full_master_ranking": ("flow_1_master/selection.json",),
    "transitions": ("flow_1_master/transitions.json",),
    "sound_design_plan_flow1": ("understanding/sound_design_plan.json",),
    "sound_design_vo_finalize": ("understanding/sound_design_plan.json",),
    "edl_narrative_audit": ("flow_1_master/edl_narrative_audit.json",),
    "edl_flow1": ("flow_1_master/edl.json",),
    "assembly_preview": ("flow_1_master/assembly_preview.wav",),
    "elevenlabs_prompt_craft": ("sound_design/elevenlabs_prompts.json",),
    "elevenlabs_sfx_flow1": (
        "glob:sound_design/assets/*.wav",
        "glob:flow_1_master/sfx/*.wav",
    ),
    "mix_flow1": ("flow_1_master/assembly.wav",),
    "master_flow1": ("flow_1_master/master.wav",),
    "highlight_selection": ("flow_2_highlights/selection.json",),
    "sound_design_plan_flow2": ("understanding/sound_design_plan.json",),
    "elevenlabs_sfx_flow2": (
        "glob:sound_design/assets/*.wav",
        "glob:flow_2_highlights/sfx/*.wav",
    ),
    "mix_flow2": ("flow_2_highlights/assembly.wav",),
    "master_flow2": ("flow_2_highlights/master.wav",),
    "podcast_show_description": ("flow_3_description/show_description.json",),
    "export_show_description": ("flow_3_description/show_description.md",),
}


def stage_reuse_offers_enabled() -> bool:
    if _no_reuse_offers:
        return False
    cfg = merged_config().get("journey_ui") or {}
    if not isinstance(cfg, dict):
        return True
    return bool(cfg.get("enable_stage_reuse_offers", True))


def _read_meta(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("run_meta.json"):
        return {}
    raw = ctx.read_json("run_meta.json")
    return raw if isinstance(raw, dict) else {}


def _write_meta(ctx: RunContext, meta: dict[str, Any]) -> None:
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json("run_meta.json", meta)


def input_audio_path_for_run(ctx: RunContext) -> str | None:
    path = _read_meta(ctx).get("input_audio_path")
    return str(path) if path else None


def get_reuse_decision(ctx: RunContext, stage_id: str) -> dict[str, Any] | None:
    row = (_read_meta(ctx).get("stage_reuse") or {}).get(stage_id)
    return row if isinstance(row, dict) else None


def record_reuse_decision(
    ctx: RunContext,
    stage_id: str,
    *,
    action: str,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    meta = _read_meta(ctx)
    reuse = dict(meta.get("stage_reuse") or {})
    now = datetime.now(timezone.utc).isoformat()
    entry: dict[str, Any] = {"action": action, "at": now}
    if source_run_id:
        entry["source_run_id"] = source_run_id
    reuse[stage_id] = entry
    meta["stage_reuse"] = reuse
    _write_meta(ctx, meta)
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
    meta = _read_meta(ctx)
    reuse = meta.get("stage_reuse")
    if not isinstance(reuse, dict) or not reuse:
        return
    idx = order.index(from_stage)
    for sid in order[idx:]:
        reuse.pop(sid, None)
    meta["stage_reuse"] = reuse
    _write_meta(ctx, meta)


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
            parent = ctx.path(parent_rel)
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
        dir_path = ctx.path(spec.rstrip("/"))
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
    if stage_id == "audio_preclean":
        return True
    if stage_id == "vo_ingest":
        return source_ctx.is_done("vo_ingest")
    specs = stage_reuse_output_specs(stage_id)
    if not specs:
        return True
    for spec in specs:
        if spec.startswith("glob:"):
            expanded = _expand_spec_paths_fixed(spec, source_ctx)
            if stage_id.startswith("elevenlabs_sfx"):
                if not expanded:
                    return False
            elif stage_id == "transcript_review_build":
                pass
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
    p = ctx.path(rel)
    return p.is_file() and p.stat().st_size > 0


def find_reuse_candidates(ctx: RunContext, stage_id: str) -> list[ReuseCandidate]:
    input_path = input_audio_path_for_run(ctx)
    if not input_path:
        return []
    candidates: list[ReuseCandidate] = []
    for run_id in RunContext.list_runs():
        if run_id == ctx.run_id:
            continue
        if not RunContext.exists(run_id):
            continue
        source = RunContext(run_id, create=False)
        if input_audio_path_for_run(source) != input_path:
            continue
        if not prior_run_has_reusable_stage(source, stage_id):
            continue
        if stage_id == "vo_ingest" and not _gap_reports_match(ctx, source):
            continue
        meta = _read_meta(source)
        paths = list_copy_paths_for_stage(source, stage_id)
        candidates.append(
            ReuseCandidate(
                run_id=run_id,
                updated_at=meta.get("updated_at"),
                execution_number=meta.get("execution_number"),
                paths=paths,
            )
        )

    def sort_key(c: ReuseCandidate) -> str:
        return c.updated_at or ""

    return sorted(candidates, key=sort_key, reverse=True)


def list_copy_paths_for_stage(source_ctx: RunContext, stage_id: str) -> list[str]:
    specs = stage_reuse_output_specs(stage_id)
    paths: list[str] = []
    for spec in specs:
        paths.extend(_expand_spec_paths_fixed(spec, source_ctx))
    if stage_id == "vo_ingest":
        pickup = source_ctx.path("vo_pickup")
        if pickup.is_dir():
            for p in sorted(pickup.glob("*.wav")):
                rel = str(p.relative_to(source_ctx.run_dir)).replace("\\", "/")
                paths.append(rel)
    return sorted(set(paths))


def apply_stage_reuse(ctx: RunContext, stage_id: str, source_run_id: str) -> list[str]:
    if not RunContext.exists(source_run_id):
        raise ValueError(f"Source run not found: {source_run_id}")
    source = RunContext(source_run_id, create=False)
    if not prior_run_has_reusable_stage(source, stage_id):
        raise ValueError(f"Run {source_run_id} does not have reusable outputs for {stage_id}")

    copied: list[str] = []
    for rel in list_copy_paths_for_stage(source, stage_id):
        src = source.path(rel)
        if not src.is_file():
            continue
        dest = ctx.path(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel)

    if stage_id == "vo_ingest":
        if not _gap_reports_match(ctx, source):
            raise ValueError(
                "Cannot reuse vo_ingest: gap_report.json differs from source execution."
            )
        pickup = source.path("vo_pickup")
        if pickup.is_dir():
            ctx.path("vo_pickup").mkdir(parents=True, exist_ok=True)
            for wav in sorted(pickup.glob("*.wav")):
                rel = str(wav.relative_to(source.run_dir)).replace("\\", "/")
                dest = ctx.path(rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(wav, dest)
                if rel not in copied:
                    copied.append(rel)

    _validate_copied_artifacts(ctx, stage_id)
    ctx.mark_done(stage_id)

    if stage_id == "vo_ingest":
        ctx.write_json(
            "analysis_complete.json",
            {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "run_id": ctx.run_id,
                "reused_from": source_run_id,
            },
        )

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


def reuse_offer_payload(ctx: RunContext, stage_id: str) -> dict[str, Any]:
    decision = get_reuse_decision(ctx, stage_id)
    candidates = find_reuse_candidates(ctx, stage_id)
    return {
        "stage_id": stage_id,
        "eligible": bool(candidates) and stage_reuse_offers_enabled(),
        "candidates": [c.to_dict() for c in candidates],
        "pending_decision": decision,
    }


def pending_reuse_stage(ctx: RunContext, stage_id: str) -> bool:
    """True when reuse is available but operator has not decided yet."""
    if not stage_reuse_offers_enabled():
        return False
    if ctx.is_done(stage_id):
        return False
    if get_reuse_decision(ctx, stage_id):
        return False
    return bool(find_reuse_candidates(ctx, stage_id))


def resolve_before_stage_run(ctx: RunContext, stage_id: str) -> Disposition:
    """Return 'skipped' when reuse applied; 'run' to execute stage; raise when offer needed."""
    if ctx.is_done(stage_id):
        return "skipped"

    if not stage_reuse_offers_enabled():
        return "run"

    if _auto_reuse_from:
        source = RunContext(_auto_reuse_from, create=False)
        if prior_run_has_reusable_stage(source, stage_id):
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
            source_id = str(decision.get("source_run_id") or "")
            if not source_id:
                return "run"
            apply_stage_reuse(ctx, stage_id, source_id)
            return "skipped"
        if action == "decline":
            return "run"

    candidates = find_reuse_candidates(ctx, stage_id)
    if not candidates:
        return "run"

    raise StageReuseOfferPending(stage_id, candidates)


def check_stage_reuse_before_execute(
    ctx: RunContext,
    stage_ids: list[str],
) -> StageReuseOfferPending | None:
    """Return pending offer for the first stage in execute order that needs a decision."""
    if not stage_reuse_offers_enabled():
        return None
    for sid in stage_ids:
        if pending_reuse_stage(ctx, sid):
            return StageReuseOfferPending(sid, find_reuse_candidates(ctx, sid))
    return None


def _gap_reports_match(a: RunContext, b: RunContext) -> bool:
    pa = a.path("understanding/gap_report.json")
    pb = b.path("understanding/gap_report.json")
    if not pa.is_file() or not pb.is_file():
        return True
    return pa.read_bytes() == pb.read_bytes()
