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
from interview_mux.show_notes_qc import validate_show_description


def _gate_exit(ctx: RunContext, message: str, *, stage: str, level: str = "error") -> None:
    ctx.log(message, level=level, stage=stage)
    raise SystemExit(message)


def sync_post_listen_gate_state(ctx: RunContext) -> dict:
    """Persist post_listen_gate_state on run_meta from listen results and optional QA block."""
    sound_cfg = merged_config().get("sound_design") or {}
    raw_mode = str(sound_cfg.get("post_listen_gate_mode", "warn")).lower()
    mode = "block_mix" if raw_mode == "block" else raw_mode
    if mode not in {"soft", "warn", "block_mix"}:
        mode = "warn"

    blocked = set(check_post_listen_gate_pending(ctx))
    if bool(sound_cfg.get("block_mix_on_mmaudio_qa_fail", False)):
        from interview_mux.mmaudio_asset_qa import load_mmaudio_qa

        qa = load_mmaudio_qa(ctx)
        for row in qa.get("assets") or []:
            if isinstance(row, dict) and row.get("verdict") == "fail":
                aid = str(row.get("asset_id") or "")
                if aid:
                    blocked.add(aid)

    state = {
        "mode": mode,
        "blocked_assets": sorted(blocked),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    def patch(meta: dict) -> None:
        meta["post_listen_gate_state"] = state

    ctx.mutate_run_meta(patch)
    return state


def check_post_listen_gate_pending(ctx: RunContext) -> list[str]:
    """Return asset_ids with failed listen results when post_listen gate is blocking."""
    sound_cfg = merged_config().get("sound_design") or {}
    post_listen_mode = str(sound_cfg.get("post_listen_gate_mode", "warn")).lower()
    if post_listen_mode not in {"block", "block_mix"}:
        return []
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    listen = meta.get("sfx_listen_results") or []
    latest: dict[str, str] = {}
    for row in listen:
        if isinstance(row, dict) and row.get("asset_id"):
            latest[str(row.get("asset_id"))] = str(row.get("result") or "")
    return sorted(aid for aid, result in latest.items() if result == "fail")


def require_post_listen_clear(ctx: RunContext, *, stage: str) -> None:
    failed = check_post_listen_gate_pending(ctx)
    if failed:
        _gate_exit(
            ctx,
            f"Post-listen gate: failed listen result(s) for {', '.join(failed[:6])}. "
            "Re-listen in the GUI and mark Pass before mix.",
            stage=stage,
        )


def check_transcript_review_pending(ctx: RunContext) -> bool:
    """True when STT review queue exists but operator has not signed off."""
    if ctx.is_done("transcript_review"):
        return False
    return ctx.artifact_exists("transcript/review_queue.json")


def require_transcript_review_clear(ctx: RunContext) -> None:
    if check_transcript_review_pending(ctx):
        _gate_exit(
            ctx,
            "Transcript review gate: open the GUI, listen to ranked clips, correct text, "
            f"then mark review complete → {ctx.path('transcript/review_queue.json')}",
            stage="transcript_review",
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
    if str(doc.get("status")) in {"skipped", "no_assets", "disabled"}:
        return False
    events = doc.get("events") or []
    if not events:
        return False
    return any(
        isinstance(e, dict) and e.get("review_status") == "pending" for e in events
    ) or not ctx.is_done("disfluency_review")


def require_disfluency_review_clear(ctx: RunContext) -> None:
    if check_disfluency_review_pending(ctx):
        _gate_exit(
            ctx,
            "Disfluency review required. Confirm or reject filler events in the GUI, "
            f"then complete review → {ctx.path('transcript/disfluencies.json')}",
            stage="disfluency_review",
        )


def check_g1_vo(ctx: RunContext) -> list[str]:
    """Return missing line_ids for blocking delivery=record VO (first_try severity filter)."""
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    from interview_mux.first_try import line_requires_vo

    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.final_path("vo_pickup")
    missing: list[str] = []
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or not line_requires_vo(line):
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
        _gate_exit(
            ctx,
            f"G1 gate: record VO for {missing} → {ctx.path('vo_pickup')}\n"
            f"See {ctx.path('understanding', 'interviewer_script.txt')}",
            stage="g1_vo_pickup",
            level="warning",
        )


def is_operator_profile_verified(ctx: RunContext) -> bool:
    """True when analysis_state.meta.operator_verified is set."""
    if not ctx.artifact_exists("understanding/analysis_state.json"):
        return False
    state = ctx.read_json("understanding/analysis_state.json")
    return bool((state.get("meta") or {}).get("operator_verified"))


def check_profile_gate_pending(ctx: RunContext) -> bool:
    """True when profile is not verified before delivery extended analysis."""
    if is_operator_profile_verified(ctx):
        return False
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review

    if not analysis_profile_ready_for_review(ctx):
        return False
    return not ctx.is_done("topic_coverage_audit")


_DELIVERY_ORDER = (
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "transitions",
    "sound_design_plan",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "master_finalize",
)


_LEGACY_DELIVERY_STAGE_ALIASES = {
    "sound_design_plan_flow1": "sound_design_plan",
    "edl_flow1": "edl",
    "mmaudio_sfx_flow1": "mmaudio_sfx",
    "mix_flow1": "mix",
    "master_flow1": "master_finalize",
}


def _delivery_will_run_topic_coverage(ctx: RunContext, from_stage: str | None) -> bool:
    """Whether the next delivery run would execute topic_coverage_audit."""
    if from_stage:
        from_stage = _LEGACY_DELIVERY_STAGE_ALIASES.get(from_stage, from_stage)
        if from_stage != "topic_coverage_audit":
            if from_stage not in _DELIVERY_ORDER:
                return False
            return _DELIVERY_ORDER.index(from_stage) <= _DELIVERY_ORDER.index("topic_coverage_audit")
    return not ctx.is_done("topic_coverage_audit") or from_stage == "topic_coverage_audit"


def require_profile_verified_for_delivery(ctx: RunContext) -> None:
    if is_operator_profile_verified(ctx):
        return
    ctx.log(
        "Profile gate: open Interview profile in the GUI, confirm themes, major questions, "
        "and style, then click Mark profile verified before topic coverage (delivery).",
        level="action",
        stage="analysis_profile",
        detail=str(ctx.path("understanding/analysis_state.json")),
    )
    raise SystemExit(
        "Profile gate: mark the interview profile verified before delivery extended stages "
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
    """Require analysis critical artifacts complete before delivery entry (flow hardening)."""
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review
    from interview_mux.artifact_cross_validate import validate_cross_artifacts
    from interview_mux.llm_flow_hardening import flow_hardening_enabled

    if not flow_hardening_enabled():
        return
    errors = validate_cross_artifacts(ctx, "pre_delivery")
    if errors:
        summary = "; ".join(errors[:4])
        _gate_exit(
            ctx,
            f"Analysis artifacts gate: {summary}. "
            "Complete analysis stages and Fill gaps before starting delivery.",
            stage="analysis_profile",
        )
    if not analysis_profile_ready_for_review(ctx):
        _gate_exit(
            ctx,
            "Analysis artifacts gate: interview profile not ready for review. "
            f"→ {ctx.path('understanding/analysis_state.json')}",
            stage="analysis_profile",
        )


def require_delivery_gates(ctx: RunContext, *, from_stage: str | None = None) -> None:
    """Enforce profile verification before topic_coverage_audit."""
    from interview_mux.llm_flow_hardening import flow_hardening_enabled

    if _delivery_will_run_topic_coverage(ctx, from_stage):
        require_profile_verified_for_delivery(ctx)
        if flow_hardening_enabled():
            require_analysis_artifacts_complete(ctx)


# Backward-compat aliases
require_profile_verified_for_flow1_extended = require_profile_verified_for_delivery
require_flow1_extended_gates = require_delivery_gates


def get_selected_flow(ctx: RunContext) -> str:
    return "podcast"


def set_selected_flow(ctx: RunContext, flow: str) -> None:
    _ = (ctx, flow)


def require_selected_flow_flow1(ctx: RunContext) -> None:
    return


def require_selected_flow_flow2(ctx: RunContext) -> None:
    raise RuntimeError("Flow 2 removed")


def narrative_qc_strict_enabled() -> bool:
    nqc = merged_config().get("narrative_qc") or {}
    return bool(nqc.get("strict"))


def check_narrative_qc(
    ctx: RunContext,
    *,
    stage: str,
    require_selection: bool = False,
) -> None:
    """Warn or block on narrative QC before ranking or EDL."""
    errors = validate_flow1_narrative(ctx, require_selection=require_selection)
    strict = narrative_qc_strict_enabled()
    if not errors:
        ctx.log(
            "Narrative QC passed",
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
        f"Narrative QC failed ({len(errors)} issue(s)): {summary}",
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
    """Warn or block on EDL timeline QC before mix or after EDL build."""
    errors = validate_flow1_edl(ctx, edl)
    use_strict = edl_qc_strict_enabled() if strict is None else strict
    if not errors:
        ctx.log(
            "EDL QC passed",
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
        f"EDL QC failed ({len(errors)} issue(s)): {summary}",
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
            f"Fix master/edl.json or re-run edl. "
            f"Run: python tools/validate_edl.py --run-id {ctx.run_id}"
        )


def check_edl_narrative_qc(
    ctx: RunContext,
    *,
    stage: str,
    edl: dict | None = None,
    strict: bool | None = None,
) -> None:
    """Warn or block when final EDL violates narrative intent."""
    errors = validate_flow1_edl_narrative(ctx, edl)
    use_strict = edl_narrative_qc_strict_enabled() if strict is None else strict
    if not errors:
        ctx.log(
            "EDL narrative QC passed",
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
        f"EDL narrative QC failed ({len(errors)} issue(s)): {summary}",
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
            "Fix final ordering, transitions, coverage, gaps, or audit findings. "
            f"Run: python tools/validate_narrative.py --run-id {ctx.run_id} --include-edl"
        )


def show_notes_qc_strict_enabled() -> bool:
    sqc = merged_config().get("show_notes_qc") or merged_config().get("show_notes_qc") or {}
    return bool(sqc.get("strict"))


# Backward-compat alias
show_notes_qc_strict_enabled = show_notes_qc_strict_enabled


def check_show_notes_qc(ctx: RunContext, *, stage: str = "show_notes") -> None:
    """Warn or block when show notes JSON fails evidence QC."""
    for path in ("show_notes/show_notes.json", "show_notes/show_description.json"):
        if not ctx.artifact_exists(path):
            continue
        doc = ctx.read_json(path)
        errors = validate_show_description(ctx, doc if isinstance(doc, dict) else {})
        strict = show_notes_qc_strict_enabled()
        if not errors:
            ctx.log(
                "Show notes QC passed",
                level="success",
                stage=stage,
                detail="show_notes_qc_pass",
            )
            record_qc_summary(
                ctx,
                "show_notes_qc",
                {"passed": True, "errors": [], "strict": strict, "at_stage": stage},
            )
            return
        summary = "; ".join(errors[:6])
        ctx.log(
            f"Show notes QC failed ({len(errors)} issue(s)): {summary}",
            level="error" if strict else "warn",
            stage=stage,
            detail="show_notes_qc_fail",
        )
        record_qc_summary(
            ctx,
            "show_notes_qc",
            {"passed": False, "errors": errors[:12], "strict": strict, "at_stage": stage},
        )
        if strict:
            raise SystemExit(
                f"show_notes_qc strict: {len(errors)} issue(s). "
                f"Run: python tools/validate_show_description.py --run-id {ctx.run_id}"
            )
        return


# Backward-compat alias
check_show_notes_qc = check_show_notes_qc
