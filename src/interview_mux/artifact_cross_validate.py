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


def _read_stage_artifact(
    ctx: RunContext,
    stage_key: str,
    *,
    staged: bool = True,
) -> tuple[str | None, dict[str, Any] | None]:
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.write_staging import read_pending_json, staged_path

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return None, None
    if staged and staged_path(ctx, rel, stage_id=stage_key).is_file():
        return rel, read_pending_json(ctx, stage_key, rel)
    if ctx.artifact_exists(rel):
        return rel, ctx.read_json(rel)
    return None, None


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
        "pre_delivery",
        "post_optimal_questions",
        "post_delivery_brief",
        "post_narrative",
        "post_sound_plan",
        "post_sonic_context",
        "pre_sfx_generation",
        "post_mmaudio_qa",
        "pre_mix",
        "pre_master_finalize",
        "post_ranking",
        "post_edl_audit_fail",
        "post_coverage_audit",
        "post_episode_structure",
        "post_edl",
    }
)

STAGE_CHECKPOINTS: dict[str, str] = {
    "boundary_detection": "post_boundary_detection",
    "segment_classification": "post_segmentation",
    "content_brief_reanchor": "post_reanchor",
    "missing_framing": "post_gaps",
    "optimal_questions": "post_optimal_questions",
    "delivery_brief_build": "post_delivery_brief",
    "sonic_context_build": "post_sonic_context",
    "interview_spine_build": "post_interview_spine",
    "sound_design_palettes": "post_sound_palettes",
    "narrative_arc_plan": "post_narrative",
    "full_master_ranking": "post_ranking",
    "transitions": "post_transitions",
    "sound_design_plan": "post_sound_plan",
    "sfx_prompt_craft": "pre_sfx_generation",
    "edl_narrative_audit": "post_edl_audit",
    "topic_coverage_audit": "post_coverage_audit",
    "episode_structure_compose": "post_episode_structure",
    "edl": "post_edl",
    "mmaudio_sfx": "pre_mix",
    "master_finalize": "pre_master_finalize",
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
    if checkpoint == "pre_delivery":
        return _validate_pre_delivery(ctx)
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
    if checkpoint == "post_coverage_audit":
        return _validate_post_coverage_audit(ctx)
    if checkpoint == "post_episode_structure":
        return _validate_post_episode_structure(ctx)
    if checkpoint == "post_edl":
        return _validate_post_edl(ctx)
    if checkpoint == "post_sound_plan" or checkpoint == "post_sound_plan_flow1":
        from interview_mux.sdp_cross_validate import validate_post_sound_plan

        return validate_post_sound_plan(ctx)
    if checkpoint == "post_optimal_questions":
        return _validate_post_optimal_questions(ctx)
    if checkpoint == "post_delivery_brief":
        return _validate_post_delivery_brief(ctx)
    if checkpoint == "post_narrative":
        return _validate_post_narrative(ctx)
    if checkpoint == "pre_sfx_generation":
        from interview_mux.sdp_cross_validate import validate_pre_sfx_generation

        return validate_pre_sfx_generation(ctx)
    if checkpoint == "post_mmaudio_qa":
        from interview_mux.sdp_cross_validate import validate_post_mmaudio_qa

        return validate_post_mmaudio_qa(ctx)
    if checkpoint == "pre_mix":
        from interview_mux.sdp_cross_validate import validate_pre_mix

        return validate_pre_mix(ctx, "podcast")
    if checkpoint == "pre_master_finalize":
        from interview_mux.sdp_cross_validate import validate_pre_master

        return validate_pre_master(ctx, "podcast")
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
                    f"Cross-artifact validation partial ({checkpoint}): manifest status={status}",
                    level="warning",
                    stage=stage_key,
                    action_id="segment.cross_validate.partial",
                    detail={"manifest_status": status, "checkpoint": checkpoint},
                )
                hard = False
        if hard:
            from interview_mux.operator_recovery import log_operator_halt

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

def _validate_speakers_artifact(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not _committed_exists(ctx, "understanding/speakers.json"):
        return errors
    doc = _committed_json(ctx, "understanding/speakers.json")
    if not isinstance(doc, dict):
        return errors
    speakers = doc.get("speakers") or []
    speaker_ids = {
        str(s.get("speaker_id"))
        for s in speakers
        if isinstance(s, dict) and s.get("speaker_id")
    }
    profile = doc.get("conversation_profile") or {}
    fc = str(profile.get("format_class_candidate") or "").lower()
    from interview_mux.conversation_context import role_is_content

    if fc == "panel":
        content_count = sum(
            1
            for s in speakers
            if isinstance(s, dict) and role_is_content(str(s.get("role") or ""))
        )
        if content_count < 2:
            errors.append("panel format requires at least two content speakers in speakers.json")

    manifest = _committed_json(ctx, "segments/manifest.json")
    if isinstance(manifest, dict) and speaker_ids:
        for i, seg in enumerate(manifest.get("segments") or []):
            if not isinstance(seg, dict):
                continue
            sid = str(seg.get("speaker_id") or "")
            if sid and sid not in speaker_ids:
                errors.append(f"manifest segments[{i}] speaker_id {sid} not in speakers.json")
    return errors


def _validate_post_boundary(ctx: RunContext) -> list[str]:
    if not _committed_exists(ctx, "segments/boundaries.json"):
        return ["segments/boundaries.json missing"]
    doc = _committed_json(ctx, "segments/boundaries.json")
    return _validate_boundary_document(doc)

def _read_boundaries_for_cross_validate(ctx: RunContext) -> dict[str, Any] | None:
    _rel, staged = _read_stage_artifact(ctx, "boundary_detection", staged=True)
    if isinstance(staged, dict):
        return staged
    doc = _committed_json(ctx, "segments/boundaries.json")
    return doc if isinstance(doc, dict) else None

def _validate_post_segmentation(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_speakers_artifact(ctx))
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
    boundary_ids: set[str] = set()
    if isinstance(boundaries, dict):
        errors.extend(_validate_boundary_document(boundaries))
        for b in boundaries.get("boundaries") or []:
            if not isinstance(b, dict):
                continue
            seg_id = str(b.get("segment_id") or "")
            if seg_id:
                boundary_ids.add(seg_id)
            if seg_id and seg_id not in manifest_ids:
                errors.append(f"boundary segment_id {seg_id} not in manifest")
        for sid in sorted(manifest_ids - boundary_ids):
            errors.append(f"manifest segment_id {sid} not in boundaries")

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
    boundary_ids: set[str] = set()
    if boundaries:
        errors.extend(_validate_boundary_document(boundaries))
        for b in boundaries.get("boundaries") or []:
            if not isinstance(b, dict):
                continue
            seg_id = str(b.get("segment_id") or "")
            if seg_id:
                boundary_ids.add(seg_id)
            if seg_id and seg_id not in manifest_ids:
                errors.append(f"boundary segment_id {seg_id} not in manifest")
        for sid in sorted(manifest_ids - boundary_ids):
            errors.append(f"manifest segment_id {sid} not in boundaries")

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
    errors: list[str] = []
    gap_objs = compute_gaps("understanding/content_brief.json", brief)
    if gap_objs:
        paths = [g.path if hasattr(g, "path") else str(g) for g in gap_objs]
        errors.append(f"content_brief reanchor incomplete: {', '.join(paths[:6])}")
    manifest_ids = _manifest_segment_ids(ctx)
    if manifest_ids:
        from interview_mux.artifact_repairs import is_manifest_segment_id

        for i, topic in enumerate(brief.get("topics") or []):
            if not isinstance(topic, dict):
                continue
            for seg_id in topic.get("segment_ids") or []:
                s = str(seg_id)
                if not is_manifest_segment_id(s):
                    errors.append(f"content_brief topics[{i}] invalid segment_id format: {s}")
                elif s not in manifest_ids:
                    errors.append(f"content_brief topics[{i}] orphan segment_id {s}")
        for i, claim in enumerate(brief.get("key_claims") or []):
            if not isinstance(claim, dict):
                continue
            for key in ("segment_ids", "evidence_segment_ids"):
                for seg_id in claim.get(key) or []:
                    s = str(seg_id)
                    if manifest_ids and s not in manifest_ids:
                        errors.append(f"content_brief key_claims[{i}] orphan {key} {s}")
    return errors

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
    if not ctx.artifact_exists("master/edl_narrative_audit.json"):
        return ""
    doc = ctx.read_json("master/edl_narrative_audit.json")
    return str(doc.get("verdict", "")).strip().lower() if isinstance(doc, dict) else ""

def _validate_post_ranking(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    manifest_ids = _manifest_segment_ids(ctx)
    sel = _committed_json(ctx, "master/selection.json")
    if not isinstance(sel, dict):
        return ["master/selection.json missing"]
    ordered = sel.get("ordered_segment_ids") or []
    ordered_set = {str(x) for x in ordered}
    for sid in ordered:
        if str(sid) not in manifest_ids:
            errors.append(f"selection segment {sid} not in manifest")
    # Ranking is authoritative: prune narrative chapter segment_ids that fell out of selection
    # so post-commit does not fail a valid reorder.
    plan = _committed_json(ctx, "master/narrative_plan.json")
    if isinstance(plan, dict) and ordered_set:
        chapters = plan.get("chapters") or []
        changed = False
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            prior = [str(s) for s in (ch.get("segment_ids") or [])]
            kept = [s for s in prior if s in ordered_set]
            if kept != prior:
                ch["segment_ids"] = kept
                changed = True
        if changed:
            try:
                ctx.write_json("master/narrative_plan.json", plan, stage_key="narrative_arc_plan", skip_handoff=True)
            except Exception:
                pass
            plan = _committed_json(ctx, "master/narrative_plan.json")
    if isinstance(plan, dict):
        chapters = plan.get("chapters") or []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            for sid in ch.get("segment_ids") or []:
                if ordered and str(sid) not in ordered_set:
                    errors.append(f"narrative chapter segment {sid} missing from selection")
    from interview_mux.delivery_brief import delivery_brief_cfg, estimated_selection_duration_sec, load_delivery_brief

    brief = load_delivery_brief(ctx)
    est = estimated_selection_duration_sec(ctx)
    if brief and est is not None:
        band = brief.get("target_duration_sec") or {}
        try:
            bmin = int(band.get("min") or 0)
            bmax = int(band.get("max") or 0)
        except (TypeError, ValueError):
            bmin, bmax = 0, 0
        if bmax and est > bmax * 1.05:
            msg = f"selection duration ~{est:.0f}s above brief max {bmax}s"
            if bool(delivery_brief_cfg().get("enforce_duration")):
                errors.append(msg)
            else:
                ctx.log(msg, level="warning", stage="full_master_ranking")
        if bmin and est < bmin * 0.85 and ordered:
            msg = f"selection duration ~{est:.0f}s below brief min {bmin}s"
            if bool(delivery_brief_cfg().get("enforce_duration")):
                errors.append(msg)
            else:
                ctx.log(msg, level="warning", stage="full_master_ranking")
    return errors


def _validate_post_optimal_questions(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return ["understanding/gap_report.json missing"]
    report = ctx.read_json("understanding/gap_report.json")
    lines = (
        report.get("interviewer_lines")
        or report.get("lines")
        or report.get("gaps")
        or []
        if isinstance(report, dict)
        else []
    )
    eval_ids: set[str] = set()
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        evals = ctx.read_json("understanding/gap_evaluations.json")
        for row in (evals.get("evaluations") or []) if isinstance(evals, dict) else []:
            if isinstance(row, dict) and row.get("segment_id"):
                eval_ids.add(str(row["segment_id"]))
    from interview_mux.config import merged_config

    thresholds = (merged_config().get("analysis") or {}).get("prompt_thresholds") or {}
    q_max = int(thresholds.get("interviewer_question_max_words", 60))
    setup_max = int(thresholds.get("interviewer_setup_max_words", 20))
    for i, row in enumerate(lines):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("targets_segment_id") or row.get("segment_id") or "")
        if sid and eval_ids and sid not in eval_ids:
            errors.append(f"gap_report interviewer_lines[{i}] segment_id {sid} not in gap_evaluations")
        script = str(row.get("script") or row.get("suggested_line") or row.get("text") or "")
        words = len(script.split()) if script else 0
        kind = str(row.get("kind") or row.get("role") or "").lower()
        lim = setup_max if "setup" in kind else q_max
        if words > lim + 5:
            errors.append(f"gap_report lines[{i}] word count {words} exceeds cap {lim}")
    return errors


def _validate_post_delivery_brief(ctx: RunContext) -> list[str]:
    from interview_mux.prompt_validation import validate_delivery_brief

    if not ctx.artifact_exists("understanding/delivery_brief.json"):
        return ["understanding/delivery_brief.json missing"]
    doc = ctx.read_json("understanding/delivery_brief.json")
    if not isinstance(doc, dict):
        return ["delivery_brief is not an object"]
    errors = validate_delivery_brief(doc)
    dens = doc.get("sfx_density") if isinstance(doc.get("sfx_density"), dict) else {}
    from interview_mux.config import merged_config

    sd = merged_config().get("sound_design") or {}
    max_assets = int(sd.get("max_assets", sd.get("max_assets_flow1", 6)))
    brief_sum = sum(int(dens.get(k) or 0) for k in ("max_beds", "max_punctuators", "max_foley"))
    if brief_sum > max_assets * 2:
        errors.append(f"sfx_density sum {brief_sum} exceeds 2x max_assets {max_assets}")
    band = doc.get("target_duration_sec") or {}
    if isinstance(band, dict):
        try:
            if int(band.get("min") or 0) > int(band.get("ideal") or 0):
                errors.append("target_duration_sec.min > ideal")
            if int(band.get("ideal") or 0) > int(band.get("max") or 0) and int(band.get("max") or 0) > 0:
                errors.append("target_duration_sec.ideal > max")
        except (TypeError, ValueError):
            errors.append("target_duration_sec values must be integers")
    return errors


def _validate_post_narrative(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    plan = _committed_json(ctx, "master/narrative_plan.json")
    if not isinstance(plan, dict):
        return ["master/narrative_plan.json missing"]
    chapters = plan.get("chapters") or []
    manifest_ids = _manifest_segment_ids(ctx)
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        for sid in ch.get("segment_ids") or []:
            if manifest_ids and str(sid) not in manifest_ids:
                errors.append(f"narrative segment {sid} not in manifest")
    from interview_mux.delivery_brief import load_delivery_brief

    brief = load_delivery_brief(ctx)
    if brief:
        budget = brief.get("chapter_budget") or {}
        try:
            cmax = int(budget.get("max") or 0)
        except (TypeError, ValueError):
            cmax = 0
        if cmax and len(chapters) > cmax:
            errors.append(f"chapter count {len(chapters)} exceeds brief max {cmax}")
    return errors


def _validate_pre_delivery(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    for rel in ANALYSIS_READY_ARTIFACT_PATHS:
        if artifact_status(rel, ctx) != "complete":
            errors.append(f"{rel} is {artifact_status(rel, ctx)}")
    return errors


def _validate_post_transitions_split(ctx: RunContext) -> tuple[list[str], list[str]]:
    """Hard: invalid segment ids; soft: gap_report VO duplication."""
    from interview_mux.deterministic_lint import transition_gap_overlap_errors

    hard: list[str] = []
    soft: list[str] = []
    if not ctx.artifact_exists("master/transitions.json"):
        return hard, soft
    if not ctx.artifact_exists("master/selection.json"):
        return ["selection.json missing for transition validation"], soft
    sel = ctx.read_json("master/selection.json")
    selection_ids = {str(x) for x in (sel.get("ordered_segment_ids") or [])}
    tr_doc = ctx.read_json("master/transitions.json")
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
    if verdict != "fail":
        return []
    from interview_mux.gates import audit_issue_covers_optional_vo_gap
    from interview_mux.v2.config import v2_g1_optional

    doc = ctx.read_json("master/edl_narrative_audit.json")
    issues = doc.get("blocking_issues") or [] if isinstance(doc, dict) else []
    if (
        v2_g1_optional()
        and issues
        and all(
            isinstance(item, dict) and audit_issue_covers_optional_vo_gap(ctx, item)
            for item in issues
        )
    ):
        return []
    # Drop transition-order LLM complaints already fixed on disk (selection after→before).
    remaining: list[dict] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        text = " ".join(
            str(x)
            for x in (
                item.get("issue"),
                item.get("detail"),
                " ".join(str(e) for e in (item.get("evidence") or [])),
            )
            if x
        ).lower()
        if "transition" in text and (
            "mis-alignment" in text
            or "violating transition" in text
            or "appears after" in text
            or "positions before" in text
        ):
            if _transitions_match_selection_order(ctx):
                continue
        remaining.append(item)
    if not remaining:
        return []
    if remaining and isinstance(remaining[0], dict):
        return [str(remaining[0].get("issue", "edl narrative audit fail"))]
    return ["edl_narrative_audit verdict is fail"]


def _transitions_match_selection_order(ctx: RunContext) -> bool:
    """True when every after→before pair appears in that order in selection."""
    if not ctx.artifact_exists("master/selection.json") or not ctx.artifact_exists(
        "master/transitions.json"
    ):
        return False
    sel = ctx.read_json("master/selection.json")
    tr = ctx.read_json("master/transitions.json")
    if not isinstance(sel, dict) or not isinstance(tr, dict):
        return False
    order = [str(x) for x in (sel.get("ordered_segment_ids") or [])]
    index = {sid: i for i, sid in enumerate(order)}
    for row in tr.get("transitions") or []:
        if not isinstance(row, dict):
            continue
        a = str(row.get("after_segment_id") or "")
        b = str(row.get("before_segment_id") or "")
        if not a or not b or a not in index or b not in index:
            continue
        if index[a] >= index[b]:
            return False
    return True


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


def _validate_post_coverage_audit(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    coherence_errors = _validate_post_coherence(ctx)
    errors.extend(coherence_errors)
    manifest_ids = _manifest_segment_ids(ctx)
    if not manifest_ids:
        return errors or ["segments/manifest.json has no segment_ids"]
    if not ctx.artifact_exists("master/coverage_audit.json"):
        return errors or ["master/coverage_audit.json missing"]
    doc = ctx.read_json("master/coverage_audit.json")
    if not isinstance(doc, dict):
        return errors + ["coverage_audit is not an object"]
    all_mapped: set[str] = set()
    for i, row in enumerate(doc.get("topic_mappings") or []):
        if not isinstance(row, dict):
            continue
        for sid in row.get("segment_ids") or []:
            s = str(sid)
            all_mapped.add(s)
            if s not in manifest_ids:
                errors.append(f"coverage_audit topic_mappings[{i}] segment_id {s} not in manifest")
    for i, row in enumerate(doc.get("claim_mappings") or []):
        if not isinstance(row, dict):
            continue
        for sid in row.get("segment_ids") or []:
            s = str(sid)
            all_mapped.add(s)
            if s not in manifest_ids:
                errors.append(f"coverage_audit claim_mappings[{i}] segment_id {s} not in manifest")
    orphan_field = doc.get("orphan_segment_ids")
    if isinstance(orphan_field, list):
        for sid in orphan_field:
            s = str(sid)
            if s in all_mapped:
                errors.append(f"coverage_audit orphan_segment_ids lists mapped segment {s}")
            elif s not in manifest_ids:
                errors.append(f"coverage_audit orphan_segment_ids {s} not in manifest")
    computed_orphans = sorted(manifest_ids - all_mapped)
    if computed_orphans and not orphan_field:
        ctx.log(
            f"coverage_audit: {len(computed_orphans)} manifest segment(s) unmapped in topic/claim mappings",
            level="info",
            stage="topic_coverage_audit",
        )
    return errors


def _validate_post_episode_structure(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    path = "understanding/episode_structure.json"
    if not ctx.artifact_exists(path):
        return ["understanding/episode_structure.json missing"]
    doc = ctx.read_json(path)
    if not isinstance(doc, dict):
        return ["episode_structure is not an object"]
    manifest_ids = _manifest_segment_ids(ctx)
    if not manifest_ids:
        return errors
    for sid in doc.get("segment_order") or []:
        s = str(sid)
        if s not in manifest_ids:
            errors.append(f"episode_structure segment_order {s} not in manifest")
    hook = (doc.get("hook_reel") or {}) if isinstance(doc.get("hook_reel"), dict) else {}
    hook_id = str(hook.get("segment_id") or "").strip()
    if hook_id and hook_id not in manifest_ids:
        errors.append(f"episode_structure hook_reel.segment_id {hook_id} not in manifest")
    for i, slot in enumerate(doc.get("slot_plan") or []):
        if not isinstance(slot, dict):
            continue
        for sid in slot.get("bound_segment_ids") or []:
            s = str(sid)
            if s not in manifest_ids:
                errors.append(f"episode_structure slot_plan[{i}] bound_segment_id {s} not in manifest")
    return errors


def _validate_post_edl(ctx: RunContext) -> list[str]:
    from interview_mux.edl_qc import validate_flow1_edl

    if not ctx.artifact_exists("master/edl.json"):
        return ["master/edl.json missing"]
    edl = ctx.read_json("master/edl.json")
    return validate_flow1_edl(ctx, edl)


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
