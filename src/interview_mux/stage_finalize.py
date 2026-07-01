"""In-run post-stage finalization for full autopilot UX."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from interview_mux.decision_copy import (
    issue_detail,
    issue_headline,
    propagation_detail,
    propagation_headline,
    stage_title,
    warning_detail,
    warning_headline,
)
from interview_mux.full_autopilot import full_autopilot_enabled
from interview_mux.operator_decisions import (
    DecisionOption,
    OperatorDecision,
    clear_stage_decisions,
    new_decision_id,
    pending_decision_count,
    set_stage_decisions,
)
from interview_mux.operator_clarifications_store import items_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS


@dataclass
class FinalizeResult:
    ok: bool
    stage_key: str
    operator_decisions: list[OperatorDecision] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    downstream_job: dict[str, Any] | None = None
    phase: str = "complete"
    open_blocking: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stage_key": self.stage_key,
            "operator_decisions": [d.to_dict() for d in self.operator_decisions],
            "warnings": self.warnings,
            "errors": self.errors,
            "downstream_job": self.downstream_job,
            "phase": self.phase,
            "open_blocking": self.open_blocking,
            "pending_decision_count": len(self.operator_decisions),
        }


def write_finalize_job_phase(ctx: Any, stage_key: str, *, phase: str = "auto_resolving") -> None:
    if not ctx.artifact_exists("gui_job.json"):
        return
    job = ctx.read_json("gui_job.json")
    if not isinstance(job, dict):
        return
    job["phase"] = phase
    job["substep"] = "artifact_resolution"
    job["stage"] = stage_key
    ctx.write_json("gui_job.json", job)


def clear_finalize_job_phase(ctx: Any, stage_key: str) -> None:
    if not ctx.artifact_exists("gui_job.json"):
        return
    job = ctx.read_json("gui_job.json")
    if not isinstance(job, dict):
        return
    if str(job.get("stage") or "") != stage_key:
        return
    job.pop("phase", None)
    job.pop("substep", None)
    job.pop("failure_kind", None)
    pending = pending_decision_count(ctx, stage_key)
    job["pending_decision_count"] = pending
    ctx.write_json("gui_job.json", job)


def _build_issue_decisions(ctx: Any, stage_key: str) -> list[OperatorDecision]:
    from interview_mux.artifact_auto_resolve import can_auto_resolve_issue, pick_recommended_choice
    from interview_mux.artifact_issue_triage import triage_cfg

    cfg = triage_cfg()
    decisions: list[OperatorDecision] = []
    for item in items_for_stage(ctx, stage_key):
        if item.get("status") != "open" or item.get("blocking") is False:
            continue
        if can_auto_resolve_issue(item, cfg=cfg):
            continue
        options_raw = item.get("options") or []
        options: list[DecisionOption] = []
        for opt in options_raw:
            if not isinstance(opt, dict):
                continue
            value = opt.get("value") if "value" in opt else opt.get("choice") or opt.get("label")
            label = str(opt.get("label") or value or "Apply")
            conf = opt.get("confidence")
            try:
                confidence = float(conf) if conf is not None else None
            except (TypeError, ValueError):
                confidence = None
            options.append(DecisionOption(label=label, value=value, confidence=confidence))
        if not options:
            options = [
                DecisionOption(label="Apply automatic repair", value="accept_auto_repair"),
                DecisionOption(label="Dismiss this issue", value="dismiss"),
            ]
        rec = pick_recommended_choice(item, cfg=cfg)
        decisions.append(
            OperatorDecision(
                id=str(item.get("id") or new_decision_id()),
                kind="issue_choice",
                headline=issue_headline(item),
                detail=issue_detail(item, stage_key),
                context={
                    "issue_id": item.get("id"),
                    "segment_id": item.get("segment_id"),
                    "artifact_path": item.get("artifact_path"),
                },
                options=options,
                recommended=rec,
            )
        )
    return decisions


def _build_propagation_decision(ctx: Any, stage_key: str, plan: dict[str, Any]) -> OperatorDecision | None:
    if not plan.get("has_blocking"):
        return None
    inv = plan.get("invalidate_from") or (plan.get("stale_stages") or [None])[0]
    if not inv:
        return None
    title = stage_title(str(inv))
    return OperatorDecision(
        id=new_decision_id(),
        kind="propagation",
        headline=propagation_headline(plan),
        detail=propagation_detail(plan),
        context={
            "invalidate_from": inv,
            "stale_stages": plan.get("stale_stages") or [],
            "cross_errors": (plan.get("cross_errors") or [])[:6],
        },
        options=[
            DecisionOption(label=f"Re-run {title}", value={"action": "propagation", "invalidate_from": inv}),
            DecisionOption(label="Skip — I'll fix manually", value={"action": "skip_propagation"}),
        ],
        recommended={"action": "propagation", "invalidate_from": inv},
    )


def _build_warning_decision(warnings: list[str]) -> OperatorDecision | None:
    if not warnings:
        return None
    return OperatorDecision(
        id=new_decision_id(),
        kind="acknowledge_warning",
        headline=warning_headline(len(warnings)),
        detail=warning_detail(warnings),
        context={"warnings": warnings[:6]},
        options=[DecisionOption(label="Continue to review", value="acknowledge")],
        recommended="acknowledge",
    )


def _try_auto_propagation(
    ctx: Any,
    stage_key: str,
    *,
    runner: Any | None,
    run_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    from interview_mux.artifact_issue_triage import get_propagation_plan, triage_cfg
    from interview_mux.artifact_root_cause import can_downstream_auto_continue, invalidate_stale_downstream

    plan = get_propagation_plan(ctx, stage_key)
    if not plan.get("has_blocking"):
        return plan, None

    cfg = triage_cfg()
    inv = plan.get("invalidate_from")
    if inv and stage_key in ("boundary_detection", "segment_classification"):
        if can_downstream_auto_continue(ctx) and runner and run_id and cfg.get("auto_resolve_chain_downstream", True):
            try:
                from interview_mux.artifact_root_cause import record_downstream_auto_continue

                invalidate_stale_downstream(ctx, stage_key)
                runner.invalidate_from(run_id, str(inv))
                target = "segment_classification" if stage_key == "boundary_detection" else str(inv)
                job = runner.start(run_id, mode="stage", from_stage=target, stage=target)
                record_downstream_auto_continue(ctx)
                return get_propagation_plan(ctx, stage_key), job
            except Exception:
                pass
        try:
            invalidate_stale_downstream(ctx, stage_key)
            if runner and run_id and inv:
                runner.invalidate_from(run_id, str(inv))
            return get_propagation_plan(ctx, stage_key), None
        except Exception:
            pass
    return plan, None


def finalize_stage_outputs(
    ctx: Any,
    stage_key: str,
    *,
    runner: Any | None = None,
    run_id: str | None = None,
    mode: str = "autopilot",
) -> FinalizeResult:
    """Run triage, autopilot resolve, risk advance, propagation, and queue operator decisions."""
    from interview_mux.operator_action_trace import begin_action, end_action

    trace_id = begin_action(
        "stage_finalize.start",
        run_dir=Path(ctx.run_dir),
        stage=stage_key,
        origin="pipeline",
        summary=f"Finalize outputs for {stage_key}",
        detail={"mode": mode},
    )
    result = FinalizeResult(ok=False, stage_key=stage_key)
    try:
        result = _finalize_stage_outputs_impl(
            ctx, stage_key, runner=runner, run_id=run_id, mode=mode, result=result,
        )
        end_action(
            trace_id,
            run_dir=Path(ctx.run_dir),
            status="ok" if result.ok else "error",
            detail={"phase": result.phase, "open_blocking": result.open_blocking},
        )
        return result
    except Exception:
        end_action(trace_id, run_dir=Path(ctx.run_dir), status="error")
        raise


def _finalize_stage_outputs_impl(
    ctx: Any,
    stage_key: str,
    *,
    runner: Any | None,
    run_id: str | None,
    mode: str,
    result: FinalizeResult,
) -> FinalizeResult:
    """Inner finalize body (logged + traced by caller)."""
    if stage_key not in STAGE_ARTIFACT_DISK_PATHS:
        result.ok = True
        result.phase = "complete"
        return result

    from interview_mux.artifact_issue_triage import (
        blocking_issues_remaining,
        get_propagation_plan,
        run_triage_pipeline,
        triage_enabled,
    )

    if not triage_enabled():
        result.ok = True
        return result

    write_finalize_job_phase(ctx, stage_key)
    ctx.log(
        f"stage_finalize.start stage={stage_key} mode={mode}",
        level="action",
        stage=stage_key,
        action_id="stage_finalize.start",
        detail={"mode": mode},
    )

    triage_result = run_triage_pipeline(ctx, stage_key, staged=True)
    if triage_result.errors:
        result.warnings.extend(triage_result.errors[:3])

    use_autopilot = mode == "autopilot" or full_autopilot_enabled()
    if use_autopilot:
        from interview_mux.artifact_auto_resolve import AutoResolveOutcome, auto_resolve_stage, risk_based_force_advance

        resolve = auto_resolve_stage(ctx, stage_key, runner=runner, run_id=run_id, autopilot=True)
        result.warnings.extend(resolve.warnings[:6])
        if resolve.errors:
            result.errors.extend(resolve.errors[:4])
        if resolve.downstream_job:
            result.downstream_job = resolve.downstream_job

        if blocking_issues_remaining(ctx, stage_key) > 0:
            risk_warnings = risk_based_force_advance(
                ctx, stage_key, runner=runner, run_id=run_id,
            )
            result.warnings.extend(risk_warnings)

    plan, chain_job = _try_auto_propagation(ctx, stage_key, runner=runner, run_id=run_id)
    if chain_job and not result.downstream_job:
        result.downstream_job = chain_job
    plan = plan or get_propagation_plan(ctx, stage_key)

    decisions: list[OperatorDecision] = []
    decisions.extend(_build_issue_decisions(ctx, stage_key))
    prop_dec = _build_propagation_decision(ctx, stage_key, plan)
    if prop_dec:
        decisions.append(prop_dec)
    warn_dec = _build_warning_decision([w for w in result.warnings if w])
    if warn_dec and not decisions:
        decisions.append(warn_dec)

    if decisions:
        set_stage_decisions(ctx, stage_key, decisions, warnings=result.warnings)
        ctx.log(
            f"itr.decision.queue_set stage={stage_key} count={len(decisions)}",
            level="info",
            stage=stage_key,
            action_id="itr.decision.queue_set",
            detail={
                "count": len(decisions),
                "kinds": [str(d.kind) for d in decisions],
            },
        )
    else:
        clear_stage_decisions(ctx, stage_key)
        ctx.log(
            f"itr.decision.queue_clear stage={stage_key}",
            level="info",
            stage=stage_key,
            action_id="itr.decision.queue_clear",
        )

    from interview_mux.artifact_auto_resolve import revalidate_for_itr_gate

    ok, errors, downstream = revalidate_for_itr_gate(ctx, stage_key, artifact_source="staged")
    result.open_blocking = blocking_issues_remaining(ctx, stage_key)
    result.operator_decisions = decisions
    result.errors.extend(errors)
    result.errors.extend([f"downstream: {e}" for e in downstream[:3]])

    if decisions:
        result.ok = True
        result.phase = "operator_decisions"
        clear_finalize_job_phase(ctx, stage_key)
        ctx.log(
            f"stage_finalize.decisions stage={stage_key} count={len(decisions)}",
            level="action",
            stage=stage_key,
            action_id="stage_finalize.decisions",
            detail={"count": len(decisions)},
        )
        return result

    if not ok or downstream or result.open_blocking > 0:
        if use_autopilot and result.open_blocking == 0:
            result.ok = True
            result.phase = "awaiting_save"
        else:
            result.ok = False
            result.phase = "failed"
            ctx.log(
                f"stage_finalize.failed stage={stage_key} open={result.open_blocking}",
                level="error",
                stage=stage_key,
                action_id="stage_finalize.failed",
                detail={
                    "failure_kind": "auto_resolve_exhausted",
                    "open_blocking": result.open_blocking,
                    "errors": result.errors[:3],
                },
            )
            if ctx.artifact_exists("gui_job.json"):
                job = ctx.read_json("gui_job.json")
                if isinstance(job, dict):
                    job["failure_kind"] = "auto_resolve_exhausted"
                    ctx.write_json("gui_job.json", job)
    else:
        result.ok = True
        result.phase = "awaiting_save"
        from interview_mux.artifact_issue_triage import clear_clarification_gate

        clear_clarification_gate(ctx, stage_key)

    clear_finalize_job_phase(ctx, stage_key)
    ctx.log(
        f"stage_finalize.complete stage={stage_key} ok={result.ok} phase={result.phase}",
        level="success" if result.ok else "info",
        stage=stage_key,
        action_id="stage_finalize.complete",
        detail={"ok": result.ok, "phase": result.phase, "open_blocking": result.open_blocking},
    )
    return result


def post_llm_stage_hooks(
    ctx: Any,
    stage_key: str,
    *,
    runner: Any | None = None,
    run_id: str | None = None,
) -> bool:
    """Post-LLM hook: finalize (full autopilot) or legacy triage + cross-validate gate."""
    from interview_mux.analysis_orchestrator import ALL_LLM_STAGES

    if stage_key not in ALL_LLM_STAGES:
        return True

    if full_autopilot_enabled():
        result = finalize_stage_outputs(ctx, stage_key, runner=runner, run_id=run_id)
        if not result.ok and result.phase == "failed":
            return False
        from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage

        maybe_cross_validate_after_stage(ctx, stage_key)
        return True

    from interview_mux.artifact_issue_triage import maybe_repair_before_cross_validate, run_triage_pipeline, triage_enabled

    if triage_enabled():
        run_triage_pipeline(ctx, stage_key, staged=True)
    if maybe_repair_before_cross_validate(ctx, stage_key):
        from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage

        maybe_cross_validate_after_stage(ctx, stage_key)
        return True
    return False


def resolve_operator_decision(
    ctx: Any,
    stage_key: str,
    decision_id: str,
    choice: Any,
    *,
    runner: Any | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Apply one wizard decision and return updated queue state."""
    from interview_mux.artifact_issue_triage import execute_propagation, execute_recovery_action, resolve_issue
    from interview_mux.operator_decisions import (
        current_decision,
        mark_decision_resolved,
        stage_decisions_summary,
    )

    current = current_decision(ctx, stage_key)
    if not current or str(current.get("id")) != decision_id:
        return {"ok": False, "errors": ["Decision not found or not current"], **stage_decisions_summary(ctx, stage_key)}

    kind = str(current.get("kind") or "")
    ctx.log(
        f"itr.decision.resolve start stage={stage_key} id={decision_id} kind={kind}",
        level="action",
        stage=stage_key,
        action_id="itr.decision.resolve",
        detail={"decision_id": decision_id, "kind": kind, "choice": str(choice)[:200]},
    )
    errors: list[str] = []
    if kind == "issue_choice":
        issue_id = str((current.get("context") or {}).get("issue_id") or decision_id)
        ok, errs = resolve_issue(ctx, stage_key, issue_id, choice)
        errors.extend(errs)
        if not ok:
            return {"ok": False, "errors": errors, **stage_decisions_summary(ctx, stage_key)}
    elif kind == "propagation":
        if isinstance(choice, dict) and choice.get("action") == "skip_propagation":
            pass
        else:
            inv = None
            if isinstance(choice, dict):
                inv = choice.get("invalidate_from")
            inv = inv or (current.get("context") or {}).get("invalidate_from")
            if inv:
                result = execute_propagation(
                    ctx,
                    stage_key,
                    invalidate_from=str(inv),
                    runner=runner,
                    run_id=run_id,
                )
                if not result.ok:
                    errors.extend(result.errors)
                    return {"ok": False, "errors": errors, **stage_decisions_summary(ctx, stage_key)}
    elif kind == "upstream_rerun":
        if choice != "skip":
            issue_id = str((current.get("context") or {}).get("issue_id") or decision_id)
            upstream = (current.get("context") or {}).get("upstream_stage")
            result = execute_recovery_action(
                ctx,
                stage_key,
                issue_id,
                "rerun_upstream",
                upstream_stage=str(upstream) if upstream else None,
                runner=runner,
                run_id=run_id,
            )
            if not result.ok:
                errors.extend(result.errors)
    elif kind == "acknowledge_warning":
        pass
    else:
        return {"ok": False, "errors": [f"Unknown decision kind: {kind}"], **stage_decisions_summary(ctx, stage_key)}

    mark_decision_resolved(ctx, stage_key, decision_id)
    summary = stage_decisions_summary(ctx, stage_key)
    if summary.get("ready_for_review"):
        from interview_mux.artifact_issue_triage import clear_clarification_gate

        clear_clarification_gate(ctx, stage_key)
        clear_finalize_job_phase(ctx, stage_key)
    ctx.log(
        f"itr.decision.resolve done stage={stage_key} ready={summary.get('ready_for_review')} "
        f"open={summary.get('open_count', 0)}",
        level="success" if not errors else "warning",
        stage=stage_key,
        action_id="itr.decision.resolve",
        detail={
            "ready_for_review": summary.get("ready_for_review"),
            "open_count": summary.get("open_count"),
            "errors": errors[:2],
        },
    )
    return {"ok": True, "errors": errors, "ready_for_review": summary.get("ready_for_review"), **summary}
