"""Cross-artifact consistency checks at segmentation and flow boundaries."""

from __future__ import annotations

from interview_mux.analysis_memory import enqueue_investigations, load_analysis_state, save_analysis_state
from interview_mux.artifact_completeness import artifact_status, compute_gaps
from interview_mux.llm_flow_hardening import ANALYSIS_READY_ARTIFACT_PATHS, flow_hardening_cfg, flow_hardening_enabled
from interview_mux.run_context import RunContext

STAGE_CHECKPOINTS: dict[str, str] = {
    "segment_classification": "post_segmentation",
    "content_brief_reanchor": "post_reanchor",
    "missing_framing": "post_gaps",
}


def validate_cross_artifacts(ctx: RunContext, checkpoint: str) -> list[str]:
    """Return human-readable cross-validation errors (empty = pass)."""
    if checkpoint == "post_segmentation":
        return _validate_post_segmentation(ctx)
    if checkpoint == "post_reanchor":
        return _validate_post_reanchor(ctx)
    if checkpoint == "post_gaps":
        return _validate_post_gaps(ctx)
    if checkpoint == "pre_flow1":
        return _validate_pre_flow1(ctx)
    return [f"Unknown cross-validate checkpoint: {checkpoint}"]


def maybe_cross_validate_after_stage(ctx: RunContext, stage_key: str) -> None:
    """Run checkpoint validation after an LLM stage when flow hardening is enabled."""
    if not flow_hardening_enabled():
        return
    if not flow_hardening_cfg().get("cross_validate_enabled", True):
        return
    checkpoint = STAGE_CHECKPOINTS.get(stage_key)
    if not checkpoint:
        return
    errors = validate_cross_artifacts(ctx, checkpoint)
    if not errors:
        return
    summary = "; ".join(errors[:4])
    if checkpoint in ("post_segmentation", "post_reanchor", "post_gaps", "pre_flow1"):
        ctx.log(
            f"Cross-artifact validation failed ({checkpoint}): {summary}",
            level="action",
            stage=stage_key,
        )
        raise SystemExit(
            f"Cross-artifact gate ({checkpoint}): {summary}. "
            f"Fix artifacts and re-run from --from-stage {stage_key}."
        )
    # reserved for future soft checkpoints (non-critical cross-validate paths)
    enqueue_investigations(
        ctx,
        [
            {
                "kind": "cross_artifact_invalid",
                "question": summary,
                "priority": "high",
                "blocking": False,
                "suggested_action": {"type": "rerun_stage", "stage": stage_key},
            }
        ],
        created_by_stage=stage_key,
    )


def _manifest_segment_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return set()
    manifest = ctx.read_json("segments/manifest.json")
    segs = manifest.get("segments") or [] if isinstance(manifest, dict) else []
    return {str(s.get("segment_id")) for s in segs if isinstance(s, dict) and s.get("segment_id")}


def _validate_post_segmentation(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    manifest_ids = _manifest_segment_ids(ctx)
    if not manifest_ids:
        return ["segments/manifest.json has no segment_ids"]

    if ctx.artifact_exists("segments/boundaries.json"):
        boundaries = ctx.read_json("segments/boundaries.json")
        for b in (boundaries.get("boundaries") or []) if isinstance(boundaries, dict) else []:
            if not isinstance(b, dict):
                continue
            seg_id = str(b.get("segment_id") or "")
            if seg_id and seg_id not in manifest_ids:
                errors.append(f"boundary segment_id {seg_id} not in manifest")

    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        segs = manifest.get("segments") or [] if isinstance(manifest, dict) else []
        prev_end = -1
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            start = int(seg.get("start_ms", 0))
            end = int(seg.get("end_ms", 0))
            if prev_end >= 0 and start < prev_end:
                errors.append(f"manifest times not monotonic at {seg.get('segment_id')}")
            prev_end = max(prev_end, end)

    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        for i, topic in enumerate((brief.get("topics") or []) if isinstance(brief, dict) else []):
            if not isinstance(topic, dict):
                continue
            for seg_id in topic.get("segment_ids") or []:
                if str(seg_id) not in manifest_ids:
                    errors.append(f"content_brief topics[{i}] segment_id {seg_id} not in manifest")

    return errors


def _validate_post_reanchor(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("understanding/content_brief.json"):
        return ["understanding/content_brief.json missing"]
    brief = ctx.read_json("understanding/content_brief.json")
    gap_objs = compute_gaps("understanding/content_brief.json", brief)
    if not gap_objs:
        return []
    paths = [g.path if hasattr(g, "path") else str(g) for g in gap_objs]
    return [f"content_brief reanchor incomplete: {', '.join(paths[:6])}"]


def _validate_post_gaps(ctx: RunContext) -> list[str]:
    manifest_ids = _manifest_segment_ids(ctx)
    if not manifest_ids:
        return ["segments/manifest.json has no segment_ids"]
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return []
    evals = ctx.read_json("understanding/gap_evaluations.json")
    evaluations = evals.get("evaluations") or [] if isinstance(evals, dict) else []
    errors: list[str] = []
    for row in evaluations:
        if not isinstance(row, dict):
            continue
        seg_id = str(row.get("segment_id") or "")
        if seg_id and seg_id not in manifest_ids:
            errors.append(f"gap_evaluation segment_id {seg_id} not in manifest")
    return errors


def _validate_pre_flow1(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    for rel in ANALYSIS_READY_ARTIFACT_PATHS:
        if artifact_status(rel, ctx) != "complete":
            errors.append(f"{rel} is {artifact_status(rel, ctx)}")
    return errors


def invalidate_stage_summaries(ctx: RunContext, stage_keys: tuple[str, ...]) -> None:
    """Remove stale stage summaries after manifest mutation."""
    state = load_analysis_state(ctx)
    meta = state.setdefault("meta", {})
    summaries = meta.setdefault("stage_summaries", {})
    for key in stage_keys:
        summaries.pop(key, None)
    save_analysis_state(ctx, state)
