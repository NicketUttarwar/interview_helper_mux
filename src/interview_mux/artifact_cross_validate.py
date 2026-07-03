"""Cross-artifact consistency checks at segmentation and flow boundaries."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from interview_mux.analysis_memory import enqueue_investigations, load_analysis_state, save_analysis_state
from interview_mux.artifact_completeness import artifact_status, compute_gaps
from interview_mux.llm_flow_hardening import ANALYSIS_READY_ARTIFACT_PATHS, flow_hardening_cfg, flow_hardening_enabled
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext

_cross_validate_overlay_stage: ContextVar[str | None] = ContextVar(
    "cross_validate_overlay_stage",
    default=None,
)


@contextmanager
def cross_validate_pending_overlay(ctx: RunContext, stage_id: str | None) -> Iterator[None]:
    """Treat pending writes for ``stage_id`` as committed during cross-validation."""
    if not stage_id:
        yield
        return
    from interview_mux.write_staging import list_pending_paths

    if not list_pending_paths(ctx, stage_id):
        yield
        return
    token = _cross_validate_overlay_stage.set(stage_id)
    try:
        yield
    finally:
        _cross_validate_overlay_stage.reset(token)


def _overlay_stage_id() -> str | None:
    return _cross_validate_overlay_stage.get()


def _overlay_pending_path(ctx: RunContext, rel: str) -> Any | None:
    """Return staged path for ``rel`` when write-approval overlay is active."""
    overlay = _overlay_stage_id()
    if not overlay:
        return None
    from interview_mux.write_staging import list_pending_paths, staged_path

    if rel not in list_pending_paths(ctx, overlay):
        return None
    candidate = staged_path(ctx, rel, stage_id=overlay)
    return candidate if candidate.is_file() else None


def _committed_json(ctx: RunContext, rel: str) -> Any | None:
    """Read committed artifact JSON; overlay pending writes during write approval."""
    from interview_mux.file_store import read_json as fs_read_json

    p = ctx.final_path(*rel.split("/"))
    if p.is_file():
        return fs_read_json(p)
    overlay = _overlay_pending_path(ctx, rel)
    if overlay is not None:
        return fs_read_json(overlay)
    return None


def _committed_exists(ctx: RunContext, rel: str) -> bool:
    if ctx.final_path(*rel.split("/")).is_file():
        return True
    return _overlay_pending_path(ctx, rel) is not None

HARD_CHECKPOINTS = frozenset(
    {
        "post_boundary_detection",
        "post_segmentation",
        "post_reanchor",
        "post_gaps",
        "pre_flow1",
        "post_sound_plan_flow1",
        "post_sound_plan_flow2",
        "post_sonic_context",
        "pre_sfx_generation",
        "post_mmaudio_qa",
        "pre_mix_flow1",
        "pre_mix_flow2",
        "pre_master_flow1",
        "pre_master_flow2",
        "post_ranking",
        "post_edl_audit_fail",
    }
)

STAGE_CHECKPOINTS: dict[str, str] = {
    "boundary_detection": "post_boundary_detection",
    "segment_classification": "post_segmentation",
    "content_brief_reanchor": "post_reanchor",
    "missing_framing": "post_gaps",
    "sonic_context_build": "post_sonic_context",
    "interview_spine_build": "post_interview_spine",
    "sound_design_palettes": "post_sound_palettes",
    "full_master_ranking": "post_ranking",
    "transitions": "post_transitions",
    "sound_design_plan_flow1": "post_sound_plan_flow1",
    "sound_design_plan_flow2": "post_sound_plan_flow2",
    "sfx_prompt_craft": "pre_sfx_generation",
    "edl_narrative_audit": "post_edl_audit",
    "topic_coverage_audit": "post_coherence",
    "mmaudio_sfx_flow1": "pre_mix_flow1",
    "mmaudio_sfx_flow2": "pre_mix_flow2",
    "master_flow1": "pre_master_flow1",
    "master_flow2": "pre_master_flow2",
}


def _validate_boundary_document(doc: dict[str, Any]) -> list[str]:
    """Validate a boundaries.json document (staged or committed)."""
    if not isinstance(doc, dict):
        return ["segments/boundaries.json invalid"]
    from interview_mux.stage_coupling import read_segment_contract

    contract = read_segment_contract(doc)
    if contract and not contract.get("timeline_valid"):
        return list(contract.get("timeline_errors") or ["boundary timeline invalid"])
    from interview_mux.segment_timeline import validate_boundary_rows, segment_timeline_cfg

    boundaries = doc.get("boundaries") or []
    st_cfg = segment_timeline_cfg()
    return validate_boundary_rows(
        [b for b in boundaries if isinstance(b, dict)],
        require_speaker_id=bool(st_cfg.get("require_speaker_id", True)),
        allow_overlap_ms=int(st_cfg.get("allow_overlap_ms", 0)),
    )


def validate_cross_artifacts_for_stage(
    ctx: RunContext,
    stage_key: str,
    *,
    staged: bool = False,
) -> list[str]:
    """Cross-validate using staged producer artifacts when ``staged=True``."""
    checkpoint = STAGE_CHECKPOINTS.get(stage_key)
    if not checkpoint:
        return []
    if not staged:
        return validate_cross_artifacts(ctx, checkpoint)
    if checkpoint == "post_boundary_detection":
        from interview_mux.artifact_issue_triage import _read_stage_artifact

        _rel, doc = _read_stage_artifact(ctx, stage_key, staged=True)
        if not doc:
            return ["no staged boundaries artifact"]
        return _validate_boundary_document(doc)
    if checkpoint == "post_segmentation":
        return _validate_post_segmentation_staged(ctx)
    return validate_cross_artifacts(ctx, checkpoint)


def validate_cross_artifacts(ctx: RunContext, checkpoint: str) -> list[str]:
    """Return human-readable cross-validation errors (empty = pass)."""
    if checkpoint == "post_boundary_detection":
        return _validate_post_boundary(ctx)
    if checkpoint == "post_segmentation":
        return _validate_post_segmentation(ctx)
    if checkpoint == "post_reanchor":
        return _validate_post_reanchor(ctx)
    if checkpoint == "post_gaps":
        return _validate_post_gaps(ctx)
    if checkpoint == "pre_flow1":
        return _validate_pre_flow1(ctx)
    if checkpoint == "post_sound_palettes":
        from interview_mux.sdp_cross_validate import validate_post_sound_palettes

        return validate_post_sound_palettes(ctx)
    if checkpoint == "post_sonic_context":
        from interview_mux.sdp_cross_validate import validate_post_sonic_context

        return validate_post_sonic_context(ctx)
    if checkpoint == "post_interview_spine":
        return _validate_post_interview_spine(ctx)
    if checkpoint == "post_coherence":
        return _validate_post_coherence(ctx)
    if checkpoint == "post_sound_plan_flow1":
        from interview_mux.sdp_cross_validate import validate_post_sound_plan_flow1

        return validate_post_sound_plan_flow1(ctx)
    if checkpoint == "post_sound_plan_flow2":
        from interview_mux.sdp_cross_validate import validate_post_sound_plan_flow2

        return validate_post_sound_plan_flow2(ctx)
    if checkpoint == "pre_sfx_generation":
        from interview_mux.sdp_cross_validate import validate_pre_sfx_generation

        return validate_pre_sfx_generation(ctx)
    if checkpoint == "post_mmaudio_qa":
        from interview_mux.sdp_cross_validate import validate_post_mmaudio_qa

        return validate_post_mmaudio_qa(ctx)
    if checkpoint == "pre_mix_flow1":
        from interview_mux.sdp_cross_validate import validate_pre_mix

        return validate_pre_mix(ctx, "flow1")
    if checkpoint == "pre_mix_flow2":
        from interview_mux.sdp_cross_validate import validate_pre_mix

        return validate_pre_mix(ctx, "flow2")
    if checkpoint == "pre_master_flow1":
        from interview_mux.sdp_cross_validate import validate_pre_master

        return validate_pre_master(ctx, "flow1")
    if checkpoint == "pre_master_flow2":
        from interview_mux.sdp_cross_validate import validate_pre_master

        return validate_pre_master(ctx, "flow2")
    if checkpoint == "post_ranking":
        return _validate_post_ranking(ctx)
    if checkpoint == "post_transitions":
        hard, _soft = _validate_post_transitions_split(ctx)
        return hard
    if checkpoint == "post_edl_audit":
        return _validate_post_edl_audit(ctx)
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
    with logged_step(f"{stage_key}/cross_validate", ctx=ctx, stage=stage_key):
        if checkpoint == "post_transitions":
            hard_errors, soft_errors = _validate_post_transitions_split(ctx)
            if hard_errors:
                summary = "; ".join(hard_errors[:4])
                ctx.log(
                    f"Cross-artifact validation failed ({checkpoint}): {summary}",
                    level="action",
                    stage=stage_key,
                )
                raise SystemExit(
                    f"Cross-artifact gate ({checkpoint}): {summary}. "
                    f"Fix artifacts and re-run from --from-stage {stage_key}."
                )
            if soft_errors:
                summary = "; ".join(soft_errors[:4])
                enqueue_investigations(
                    ctx,
                    [
                        {
                            "kind": "cross_artifact_invalid",
                            "question": summary,
                            "priority": "medium",
                            "blocking": False,
                            "suggested_action": {"type": "rerun_stage", "stage": stage_key},
                        }
                    ],
                    created_by_stage=stage_key,
                )
            return

        errors = validate_cross_artifacts(ctx, checkpoint)
        if not errors:
            return
        summary = "; ".join(errors[:4])
        hard = checkpoint in HARD_CHECKPOINTS or (
            checkpoint == "post_edl_audit" and _edl_audit_verdict(ctx) == "fail"
        )
        if checkpoint == "post_segmentation":
            status = artifact_status("segments/manifest.json", ctx)
            if status != "complete":
                ctx.log(
                    f"Cross-artifact validation skipped ({checkpoint}): manifest status={status}",
                    level="info",
                    stage=stage_key,
                    action_id="segment.cross_validate.skip",
                    detail={"manifest_status": status, "checkpoint": checkpoint},
                )
                return
        if hard:
            from interview_mux.operator_recovery import log_operator_halt

            fh = flow_hardening_cfg()
            if fh.get("clarification_before_halt", True):
                from interview_mux.artifact_issue_triage import (
                    run_triage_pipeline,
                    triage_enabled,
                    set_clarification_gate,
                )

                if triage_enabled():
                    result = run_triage_pipeline(ctx, stage_key, staged=True)
                    if result.revalidation_ok and result.open_blocking == 0:
                        return
                    set_clarification_gate(
                        ctx,
                        stage_key,
                        message=(
                            f"Cross-artifact validation failed ({checkpoint}): {summary}. "
                            "Resolve issues in the clarification panel."
                        ),
                    )
                    return

            log_operator_halt(
                ctx,
                stage_key=stage_key,
                halt_kind="cross_artifact",
                message=(
                    f"Cross-artifact validation failed ({checkpoint}): {summary}. "
                    f"Fix artifacts and re-run from --from-stage {stage_key}."
                ),
                recovery_from_stage=stage_key,
                action_id="segment.cross_validate.fail",
                extra_detail={"checkpoint": checkpoint, "errors": errors[:6]},
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
    manifest = _committed_json(ctx, "segments/manifest.json")
    if not isinstance(manifest, dict):
        return set()
    segs = manifest.get("segments") or []
    return {str(s.get("segment_id")) for s in segs if isinstance(s, dict) and s.get("segment_id")}


def _validate_post_boundary(ctx: RunContext) -> list[str]:
    if not _committed_exists(ctx, "segments/boundaries.json"):
        return ["segments/boundaries.json missing"]
    doc = _committed_json(ctx, "segments/boundaries.json")
    return _validate_boundary_document(doc)


def _read_boundaries_for_cross_validate(ctx: RunContext) -> dict[str, Any] | None:
    from interview_mux.artifact_issue_triage import _read_stage_artifact

    _rel, staged = _read_stage_artifact(ctx, "boundary_detection", staged=True)
    if isinstance(staged, dict):
        return staged
    doc = _committed_json(ctx, "segments/boundaries.json")
    return doc if isinstance(doc, dict) else None


def _validate_post_segmentation(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    manifest = _committed_json(ctx, "segments/manifest.json")
    if not isinstance(manifest, dict):
        return []
    segs = manifest.get("segments") or []
    manifest_ids = {
        str(s.get("segment_id")) for s in segs if isinstance(s, dict) and s.get("segment_id")
    }
    if not manifest_ids:
        return ["segments/manifest.json has no segment_ids"]

    boundaries = _committed_json(ctx, "segments/boundaries.json")
    if isinstance(boundaries, dict):
        errors.extend(_validate_boundary_document(boundaries))
        for b in boundaries.get("boundaries") or []:
            if not isinstance(b, dict):
                continue
            seg_id = str(b.get("segment_id") or "")
            if seg_id and seg_id not in manifest_ids:
                errors.append(f"boundary segment_id {seg_id} not in manifest")

    from interview_mux.segment_timeline import validate_timeline_monotonic, segment_timeline_cfg

    errors.extend(
        validate_timeline_monotonic(
            [s for s in segs if isinstance(s, dict)],
            allow_overlap_ms=int(segment_timeline_cfg().get("allow_overlap_ms", 0)),
        )
    )

    brief = _committed_json(ctx, "understanding/content_brief.json")
    if isinstance(brief, dict):
        for i, topic in enumerate(brief.get("topics") or []):
            if not isinstance(topic, dict):
                continue
            for seg_id in topic.get("segment_ids") or []:
                if str(seg_id) not in manifest_ids:
                    errors.append(f"content_brief topics[{i}] segment_id {seg_id} not in manifest")

    return errors


def _validate_post_segmentation_staged(ctx: RunContext) -> list[str]:
    """post_segmentation cross-check using staged manifest when present."""
    from interview_mux.artifact_issue_triage import _read_stage_artifact

    errors: list[str] = []
    _rel, manifest = _read_stage_artifact(ctx, "segment_classification", staged=True)
    if not manifest:
        return _validate_post_segmentation(ctx)
    segs = manifest.get("segments") or [] if isinstance(manifest, dict) else []
    manifest_ids = {
        str(s.get("segment_id")) for s in segs if isinstance(s, dict) and s.get("segment_id")
    }
    if not manifest_ids:
        return ["segments/manifest.json has no segment_ids"]

    boundaries = _read_boundaries_for_cross_validate(ctx)
    if boundaries:
        errors.extend(_validate_boundary_document(boundaries))
        for b in boundaries.get("boundaries") or []:
            if not isinstance(b, dict):
                continue
            seg_id = str(b.get("segment_id") or "")
            if seg_id and seg_id not in manifest_ids:
                errors.append(f"boundary segment_id {seg_id} not in manifest")

    from interview_mux.segment_timeline import validate_timeline_monotonic, segment_timeline_cfg

    errors.extend(
        validate_timeline_monotonic(
            [s for s in segs if isinstance(s, dict)],
            allow_overlap_ms=int(segment_timeline_cfg().get("allow_overlap_ms", 0)),
        )
    )

    brief = _committed_json(ctx, "understanding/content_brief.json")
    if isinstance(brief, dict):
        for i, topic in enumerate(brief.get("topics") or []):
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


def _edl_audit_verdict(ctx: RunContext) -> str:
    if not ctx.artifact_exists("flow_1_master/edl_narrative_audit.json"):
        return ""
    doc = ctx.read_json("flow_1_master/edl_narrative_audit.json")
    return str(doc.get("verdict", "")).strip().lower() if isinstance(doc, dict) else ""


def _validate_post_ranking(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    manifest_ids = _manifest_segment_ids(ctx)
    sel = _committed_json(ctx, "flow_1_master/selection.json")
    if not isinstance(sel, dict):
        return ["flow_1_master/selection.json missing"]
    ordered = sel.get("ordered_segment_ids") or []
    for sid in ordered:
        if str(sid) not in manifest_ids:
            errors.append(f"selection segment {sid} not in manifest")
    return errors


def _validate_post_transitions_split(ctx: RunContext) -> tuple[list[str], list[str]]:
    """Hard: invalid segment ids; soft: gap_report VO duplication."""
    from interview_mux.deterministic_lint import transition_gap_overlap_errors

    hard: list[str] = []
    soft: list[str] = []
    if not ctx.artifact_exists("flow_1_master/transitions.json"):
        return hard, soft
    if not ctx.artifact_exists("flow_1_master/selection.json"):
        return ["selection.json missing for transition validation"], soft
    sel = ctx.read_json("flow_1_master/selection.json")
    selection_ids = {str(x) for x in (sel.get("ordered_segment_ids") or [])}
    tr_doc = ctx.read_json("flow_1_master/transitions.json")
    transitions = tr_doc.get("transitions") or []
    for tr in transitions:
        if not isinstance(tr, dict):
            continue
        for key in ("after_segment_id", "before_segment_id"):
            sid = tr.get(key)
            if sid and selection_ids and str(sid) not in selection_ids:
                hard.append(f"transition {key}={sid} not in selection")
    soft = transition_gap_overlap_errors(transitions, ctx)
    return hard, soft


def _validate_post_edl_audit(ctx: RunContext) -> list[str]:
    verdict = _edl_audit_verdict(ctx)
    if verdict == "fail":
        doc = ctx.read_json("flow_1_master/edl_narrative_audit.json")
        issues = doc.get("blocking_issues") or [] if isinstance(doc, dict) else []
        if issues and isinstance(issues[0], dict):
            return [str(issues[0].get("issue", "edl narrative audit fail"))]
        return ["edl_narrative_audit verdict is fail"]
    return []


def _validate_pre_flow1(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    for rel in ANALYSIS_READY_ARTIFACT_PATHS:
        if artifact_status(rel, ctx) != "complete":
            errors.append(f"{rel} is {artifact_status(rel, ctx)}")
    return errors


def _validate_post_interview_spine(ctx: RunContext) -> list[str]:
    from interview_mux.interview_spine.config import spine_enabled
    from interview_mux.prompt_validation import validate_interview_spine

    if not spine_enabled():
        return []
    path = "understanding/interview_spine.json"
    if not ctx.artifact_exists(path):
        return ["understanding/interview_spine.json missing after interview_spine_build"]
    doc = ctx.read_json(path)
    if not isinstance(doc, dict):
        return ["interview_spine.json is not an object"]
    schema_errors = validate_interview_spine(doc)
    return schema_errors[:4]


def _validate_post_coherence(ctx: RunContext) -> list[str]:
    from interview_mux.coherence.config import coherence_active
    from interview_mux.coherence.paths import COHERENCE_REPORT_PATH
    from interview_mux.prompt_validation import validate_coherence_report

    if not coherence_active():
        return []
    if not ctx.artifact_exists(COHERENCE_REPORT_PATH):
        return []
    report = ctx.read_json(COHERENCE_REPORT_PATH)
    if not (report.get("gate") or {}).get("activated"):
        return []
    return validate_coherence_report(report)[:4]


def invalidate_stage_summaries(ctx: RunContext, stage_keys: tuple[str, ...]) -> None:
    """Remove stale stage summaries after manifest mutation."""
    state = load_analysis_state(ctx)
    meta = state.setdefault("meta", {})
    summaries = meta.setdefault("stage_summaries", {})
    for key in stage_keys:
        summaries.pop(key, None)
    save_analysis_state(ctx, state)
    try:
        from interview_mux.context_resolver import invalidate_entries_for_stages

        invalidate_entries_for_stages(ctx, stage_keys)
    except Exception:
        pass
