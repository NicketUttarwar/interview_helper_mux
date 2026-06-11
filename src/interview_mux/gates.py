from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.disfluency.config import disfluency_enabled
from interview_mux.edl_narrative_qc import validate_flow1_edl_narrative
from interview_mux.edl_qc import validate_flow1_edl
from interview_mux.narrative_qc import validate_flow1_narrative
from interview_mux.operator_quality import record_qc_summary
from interview_mux.run_context import RunContext
from interview_mux.show_description_qc import validate_show_description


def check_transcript_review_pending(ctx: RunContext) -> bool:
    """True when STT review queue exists but operator has not signed off."""
    if ctx.is_done("transcript_review"):
        return False
    return ctx.artifact_exists("transcript/review_queue.json")


def require_transcript_review_clear(ctx: RunContext) -> None:
    if check_transcript_review_pending(ctx):
        raise SystemExit(
            "Transcript review gate: open the GUI, listen to ranked clips, correct text, "
            f"then mark review complete → {ctx.path('transcript/review_queue.json')}"
        )


def check_disfluency_review_pending(ctx: RunContext) -> bool:
    """True when disfluency extract is enabled, events exist, and review is incomplete."""
    if not disfluency_enabled():
        return False
    if ctx.is_done("disfluency_review"):
        return False
    if not ctx.artifact_exists("transcript/disfluencies.json"):
        return False
    doc = ctx.read_json("transcript/disfluencies.json")
    if str(doc.get("status")) == "skipped":
        return False
    events = doc.get("events") or []
    if not events:
        return False
    return any(
        isinstance(e, dict) and e.get("review_status") == "pending" for e in events
    ) or not ctx.is_done("disfluency_review")


def require_disfluency_review_clear(ctx: RunContext) -> None:
    if check_disfluency_review_pending(ctx):
        raise SystemExit(
            "Disfluency review required. Confirm or reject filler events in the GUI, "
            f"then complete review → {ctx.path('transcript/disfluencies.json')}"
        )


def check_g1_vo(ctx: RunContext) -> list[str]:
    """Return list of missing line_ids for delivery=record."""
    report_path = ctx.path("understanding", "gap_report.json")
    if not report_path.is_file():
        return []
    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.path("vo_pickup")
    missing: list[str] = []
    for line in report.get("interviewer_lines") or []:
        if line.get("delivery") != "record":
            continue
        lid = line.get("line_id", "")
        seg = line.get("targets_segment_id", "")
        candidates = [pickup / f"{lid}.wav", pickup / f"{seg}.wav"]
        if not any(p.is_file() for p in candidates):
            missing.append(lid or seg)
    return missing


def require_g1_clear(ctx: RunContext) -> None:
    missing = check_g1_vo(ctx)
    if missing:
        raise SystemExit(
            f"G1 gate: record VO for {missing} → {ctx.path('vo_pickup')}\n"
            f"See {ctx.path('understanding', 'interviewer_script.txt')}"
        )


def set_selected_flow(ctx: RunContext, flow: str) -> None:
    if flow not in ("flow1", "flow2", "flow3"):
        raise ValueError("flow must be flow1, flow2, or flow3")
    meta = ctx.read_json("run_meta.json") if ctx.path("run_meta.json").is_file() else {}
    meta.update(
        {
            "selected_flow": flow,
            "selected_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    ctx.write_json("run_meta.json", meta)


def get_selected_flow(ctx: RunContext) -> str | None:
    p = ctx.path("run_meta.json")
    if not p.is_file():
        return None
    return ctx.read_json("run_meta.json").get("selected_flow")


def is_operator_profile_verified(ctx: RunContext) -> bool:
    """True when analysis_state.meta.operator_verified is set."""
    if not ctx.artifact_exists("understanding/analysis_state.json"):
        return False
    state = ctx.read_json("understanding/analysis_state.json")
    return bool((state.get("meta") or {}).get("operator_verified"))


def check_profile_gate_pending(ctx: RunContext) -> bool:
    """True when Flow 1 is selected but profile is not verified before extended analysis."""
    if get_selected_flow(ctx) != "flow1":
        return False
    if is_operator_profile_verified(ctx):
        return False
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review

    if not analysis_profile_ready_for_review(ctx):
        return False
    return not ctx.is_done("topic_coverage_audit")


_FLOW1_ORDER = (
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "transitions",
    "sound_design_plan_flow1",
    "sound_design_vo_finalize",
    "edl_flow1",
    "assembly_preview",
    "elevenlabs_prompt_craft",
    "elevenlabs_sfx_flow1",
    "mix_flow1",
    "master_flow1",
)


def _flow1_will_run_topic_coverage(ctx: RunContext, from_stage: str | None) -> bool:
    """Whether the next flow1 run would execute topic_coverage_audit."""
    if from_stage and from_stage != "topic_coverage_audit":
        if from_stage not in _FLOW1_ORDER:
            return False
        return _FLOW1_ORDER.index(from_stage) <= _FLOW1_ORDER.index("topic_coverage_audit")
    return not ctx.is_done("topic_coverage_audit") or from_stage == "topic_coverage_audit"


def require_selected_flow_flow1(ctx: RunContext) -> None:
    flow = get_selected_flow(ctx)
    if flow != "flow1":
        raise SystemExit(
            f"Flow 1 stages require selected_flow=flow1 in run_meta.json (current: {flow!r}). "
            "Choose Flow 1 in the GUI (G2) or: python tools/run_flow.py --flow flow1"
        )


def require_selected_flow_flow2(ctx: RunContext) -> None:
    flow = get_selected_flow(ctx)
    if flow != "flow2":
        raise SystemExit(
            f"Flow 2 stages require selected_flow=flow2 in run_meta.json (current: {flow!r}). "
            "Choose Flow 2 in the GUI (G2) or: python tools/run_flow.py --flow flow2"
        )


def require_profile_verified_for_flow1_extended(ctx: RunContext) -> None:
    if is_operator_profile_verified(ctx):
        return
    ctx.log(
        "Profile gate: open Interview profile in the GUI, confirm themes, major questions, "
        "and style, then click Mark profile verified before topic coverage (Flow 1 extended).",
        level="action",
        stage="analysis_profile",
        detail=str(ctx.path("understanding/analysis_state.json")),
    )
    raise SystemExit(
        "Profile gate: mark the interview profile verified before Flow 1 extended stages "
        f"(topic_coverage_audit). → {ctx.path('understanding/analysis_state.json')}"
    )


def check_analysis_artifacts_gate_pending(ctx: RunContext) -> bool:
    """True when flow hardening is on and analysis-ready artifacts are incomplete."""
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review
    from interview_mux.llm_flow_hardening import flow_hardening_enabled

    if not flow_hardening_enabled():
        return False
    return not analysis_profile_ready_for_review(ctx)


def require_analysis_artifacts_complete(ctx: RunContext) -> None:
    """Require analysis critical artifacts complete before flow entry (flow hardening)."""
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review
    from interview_mux.artifact_cross_validate import validate_cross_artifacts
    from interview_mux.llm_flow_hardening import flow_hardening_enabled

    if not flow_hardening_enabled():
        return
    errors = validate_cross_artifacts(ctx, "pre_flow1")
    if errors:
        summary = "; ".join(errors[:4])
        raise SystemExit(
            f"Analysis artifacts gate: {summary}. "
            "Complete analysis stages and Fill gaps before starting flows."
        )
    if not analysis_profile_ready_for_review(ctx):
        raise SystemExit(
            "Analysis artifacts gate: interview profile not ready for review. "
            f"→ {ctx.path('understanding/analysis_state.json')}"
        )


def require_flow1_extended_gates(ctx: RunContext, *, from_stage: str | None = None) -> None:
    """Enforce G2 flow1 selection and profile verification before topic_coverage_audit."""
    from interview_mux.llm_flow_hardening import flow_hardening_enabled

    require_selected_flow_flow1(ctx)
    if _flow1_will_run_topic_coverage(ctx, from_stage):
        require_profile_verified_for_flow1_extended(ctx)
        if flow_hardening_enabled():
            require_analysis_artifacts_complete(ctx)


def narrative_qc_strict_enabled() -> bool:
    nqc = merged_config().get("narrative_qc") or {}
    return bool(nqc.get("strict"))


def check_narrative_qc(
    ctx: RunContext,
    *,
    stage: str,
    require_selection: bool = False,
) -> None:
    """Warn or block on Flow 1 narrative QC before ranking or EDL (BUILD narrative validators)."""
    errors = validate_flow1_narrative(ctx, require_selection=require_selection)
    strict = narrative_qc_strict_enabled()
    if not errors:
        ctx.log(
            "Flow 1 narrative QC passed",
            level="success",
            stage=stage,
            detail="narrative_qc_pass",
        )
        record_qc_summary(
            ctx,
            "narrative_qc",
            {"passed": True, "errors": [], "strict": strict, "at_stage": stage},
        )
        return

    summary = "; ".join(errors[:6])
    if len(errors) > 6:
        summary += f" (+{len(errors) - 6} more)"
    ctx.log(
        f"Flow 1 narrative QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if strict else "warn",
        stage=stage,
        detail="narrative_qc_fail",
    )
    record_qc_summary(
        ctx,
        "narrative_qc",
        {"passed": False, "errors": errors[:12], "strict": strict, "at_stage": stage},
    )
    if strict:
        from interview_mux.analysis_memory import enqueue_investigations

        enqueue_investigations(
            ctx,
            [
                {
                    "kind": "narrative_qc_fail",
                    "question": summary,
                    "priority": "high",
                    "blocking": True,
                    "suggested_action": {"type": "rerun_stage", "stage": "topic_coverage_audit"},
                }
            ],
            created_by_stage=stage,
        )
        raise SystemExit(
            f"narrative_qc strict: {len(errors)} issue(s) before {stage}. "
            f"Fix coverage_audit / selection or set narrative_qc.strict=false. "
            f"Run: python tools/validate_narrative.py --run-id {ctx.run_id}"
        )


def edl_qc_strict_enabled() -> bool:
    eqc = merged_config().get("edl_qc") or {}
    return bool(eqc.get("strict"))


def edl_narrative_qc_strict_enabled() -> bool:
    enqc = merged_config().get("edl_narrative_qc") or {}
    return bool(enqc.get("strict"))


def check_edl_qc(
    ctx: RunContext,
    *,
    stage: str,
    edl: dict | None = None,
    strict: bool | None = None,
) -> None:
    """Warn or block on Flow 1 EDL timeline QC before mix or after EDL build."""
    errors = validate_flow1_edl(ctx, edl)
    use_strict = edl_qc_strict_enabled() if strict is None else strict
    if not errors:
        ctx.log(
            "Flow 1 EDL QC passed",
            level="success",
            stage=stage,
            detail="edl_qc_pass",
        )
        record_qc_summary(
            ctx,
            "edl_qc",
            {"passed": True, "errors": [], "strict": use_strict, "at_stage": stage},
        )
        return

    summary = "; ".join(errors[:6])
    if len(errors) > 6:
        summary += f" (+{len(errors) - 6} more)"
    ctx.log(
        f"Flow 1 EDL QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if use_strict else "warn",
        stage=stage,
        detail="edl_qc_fail",
    )
    record_qc_summary(
        ctx,
        "edl_qc",
        {"passed": False, "errors": errors[:12], "strict": use_strict, "at_stage": stage},
    )
    if use_strict:
        raise SystemExit(
            f"edl_qc strict: {len(errors)} issue(s) before {stage}. "
            f"Fix flow_1_master/edl.json or re-run edl_flow1. "
            f"Run: python tools/validate_edl.py --run-id {ctx.run_id}"
        )


def check_edl_narrative_qc(
    ctx: RunContext,
    *,
    stage: str,
    edl: dict | None = None,
    strict: bool | None = None,
) -> None:
    """Warn or block when final Flow 1 EDL violates narrative intent."""
    errors = validate_flow1_edl_narrative(ctx, edl)
    use_strict = edl_narrative_qc_strict_enabled() if strict is None else strict
    if not errors:
        ctx.log(
            "Flow 1 EDL narrative QC passed",
            level="success",
            stage=stage,
            detail="edl_narrative_qc_pass",
        )
        record_qc_summary(
            ctx,
            "edl_narrative_qc",
            {"passed": True, "errors": [], "strict": use_strict, "at_stage": stage},
        )
        return

    summary = "; ".join(errors[:6])
    if len(errors) > 6:
        summary += f" (+{len(errors) - 6} more)"
    ctx.log(
        f"Flow 1 EDL narrative QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if use_strict else "warn",
        stage=stage,
        detail="edl_narrative_qc_fail",
    )
    record_qc_summary(
        ctx,
        "edl_narrative_qc",
        {"passed": False, "errors": errors[:12], "strict": use_strict, "at_stage": stage},
    )
    if use_strict:
        raise SystemExit(
            f"edl_narrative_qc strict: {len(errors)} issue(s) before {stage}. "
            "Fix final Flow 1 ordering, transitions, coverage, gaps, or audit findings. "
            f"Run: python tools/validate_narrative.py --run-id {ctx.run_id} --include-edl"
        )


def show_description_qc_strict_enabled() -> bool:
    sqc = merged_config().get("show_description_qc") or {}
    return bool(sqc.get("strict"))


def check_show_description_qc(ctx: RunContext, *, stage: str = "podcast_show_description") -> None:
    """Warn or block when show description JSON fails evidence QC."""
    if not ctx.artifact_exists("flow_3_description/show_description.json"):
        return
    doc = ctx.read_json("flow_3_description/show_description.json")
    errors = validate_show_description(ctx, doc if isinstance(doc, dict) else {})
    strict = show_description_qc_strict_enabled()
    if not errors:
        ctx.log(
            "Show description QC passed",
            level="success",
            stage=stage,
            detail="show_description_qc_pass",
        )
        record_qc_summary(
            ctx,
            "show_description_qc",
            {"passed": True, "errors": [], "strict": strict, "at_stage": stage},
        )
        return
    summary = "; ".join(errors[:6])
    ctx.log(
        f"Show description QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if strict else "warn",
        stage=stage,
        detail="show_description_qc_fail",
    )
    record_qc_summary(
        ctx,
        "show_description_qc",
        {"passed": False, "errors": errors[:12], "strict": strict, "at_stage": stage},
    )
    if strict:
        raise SystemExit(
            f"show_description_qc strict: {len(errors)} issue(s). "
            f"Run: python tools/validate_show_description.py --run-id {ctx.run_id}"
        )
