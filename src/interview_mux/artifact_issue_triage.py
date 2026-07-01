"""Artifact Issue Triage & Remediation (ITR) orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from interview_mux.artifact_cross_validate import (
    STAGE_CHECKPOINTS,
    validate_cross_artifacts,
    validate_cross_artifacts_for_stage,
)
from interview_mux.artifact_repairs import (
    apply_choice_to_boundaries,
    apply_choice_to_manifest,
    apply_repairs_for_stage,
)
from interview_mux.artifact_clarification_llm import infer_options_local_llm
from interview_mux.config import merged_config
from interview_mux.issue_severity_rules import (
    ClassifiedIssue,
    classify_cross_validate_message,
    classify_lint_message,
    classify_schema_error,
    repair_priority,
    should_auto_repair,
    should_llm_options,
)
from interview_mux.operator_clarifications_store import (
    issue_id_for,
    items_for_stage,
    load_clarifications,
    mark_resolved,
    open_blocking_count,
    upsert_items,
)
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, validate_artifact_write
from interview_mux.write_staging import staged_path, write_pending_content


def triage_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    base = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "enabled": True,
        "auto_repair_minor": True,
        "auto_repair_noise": True,
        "local_llm_for_important": True,
        "pre_cross_validate_repair": True,
        "max_resolution_rounds": 3,
        "max_operator_prompts_per_stage": 8,
        "allow_promote_with_open_investigations": True,
        "allow_partial_then_repair": True,
        "revalidate_downstream_on_segment_fix": True,
        "segment_overlap_policy": "drop_duplicate_then_llm_pick",
        "record_repairs_in_artifact_meta": True,
        "max_upstream_reruns_per_run": 2,
        "max_downstream_auto_continue": 1,
        "boundary_merge_threshold_ms": 500,
        "require_propagation_before_segment_approve": True,
        "upstream_rerun_invalidate_downstream": True,
        "auto_resolve_min_confidence": 0.70,
        "auto_resolve_confidence_gap": 0.15,
        "auto_resolve_chain_downstream": True,
        "max_auto_resolve_attempts_per_stage": 2,
        "auto_advance_after_itr_clear": True,
        "min_segments_after_auto_resolve": 1,
        "max_segments_deleted_per_fix_all": 0.50,
        "auto_resolve_max_issues_per_pass": 50,
    }
    raw = base.get("artifact_issue_triage") or {}
    return {**defaults, **raw}


def triage_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(triage_cfg(cfg).get("enabled", True))


@dataclass
class TriageResult:
    stage_key: str
    collected: int = 0
    auto_fixed: int = 0
    open_blocking: int = 0
    revalidation_ok: bool = False
    errors: list[str] = field(default_factory=list)
    applied_repairs: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "stage_key": self.stage_key,
            "collected": self.collected,
            "auto_fixed": self.auto_fixed,
            "open_blocking": self.open_blocking,
            "revalidation_ok": self.revalidation_ok,
            "errors": self.errors[:8],
        }


def _read_stage_artifact(ctx: Any, stage_key: str, *, staged: bool = True) -> tuple[str | None, dict[str, Any] | None]:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return None, None
    try:
        if staged:
            p = staged_path(ctx, rel, stage_id=stage_key)
            if p.is_file():
                import json

                raw = json.loads(p.read_text(encoding="utf-8"))
                return rel, raw if isinstance(raw, dict) else None
        if ctx.artifact_exists(rel):
            raw = ctx.read_json(rel)
            return rel, raw if isinstance(raw, dict) else None
    except Exception:
        return rel, None
    return rel, None


def _write_stage_artifact(ctx: Any, stage_key: str, rel: str, data: dict[str, Any]) -> None:
    write_pending_content(ctx, stage_key, rel, data=data)


def _enqueue_noise_investigations(ctx: Any, stage_key: str, issues: list[ClassifiedIssue]) -> None:
    from interview_mux.analysis_memory import enqueue_investigations

    items: list[dict[str, Any]] = []
    for issue in issues:
        if issue.severity != "noise":
            continue
        items.append(
            {
                "id": issue_id_for(stage_key, issue.message, issue.segment_id),
                "kind": "artifact_validation",
                "question": issue.message,
                "blocking": False,
                "priority": "low",
            }
        )
    if items:
        enqueue_investigations(ctx, items, created_by_stage=stage_key)


@dataclass
class RecoveryResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    job: dict[str, Any] | None = None
    upstream_stage: str | None = None
    invalidated_from: str | None = None


def revalidate_downstream_on_segment_fix(ctx: Any, stage_key: str) -> list[str]:
    from interview_mux.artifact_root_cause import revalidate_downstream_for_stage

    return revalidate_downstream_for_stage(ctx, stage_key)


def get_propagation_plan(ctx: Any, stage_key: str) -> dict[str, Any]:
    from interview_mux.artifact_root_cause import compute_stale_downstream

    return compute_stale_downstream(ctx, stage_key).summary()


def _maybe_enqueue_propagation_investigations(ctx: Any, stage_key: str, plan_summary: dict[str, Any]) -> None:
    if not plan_summary.get("has_blocking"):
        return
    from interview_mux.analysis_memory import enqueue_investigations

    inv_from = plan_summary.get("invalidate_from") or stage_key
    summary = "; ".join((plan_summary.get("cross_errors") or [])[:3])
    enqueue_investigations(
        ctx,
        [
            {
                "kind": "manifest_propagation",
                "question": f"Downstream stale after {stage_key} fix: {summary or 'stale stages'}",
                "blocking": True,
                "priority": "high",
                "suggested_action": {"type": "rerun_stage", "stage": inv_from},
            }
        ],
        created_by_stage=stage_key,
    )


def collect_issues(
    ctx: Any,
    stage_key: str,
    *,
    staged: bool = True,
    lint_errors: list[str] | None = None,
    schema_errors: list[str] | None = None,
) -> list[ClassifiedIssue]:
    issues: list[ClassifiedIssue] = []
    rel, artifact = _read_stage_artifact(ctx, stage_key, staged=staged)

    for err in lint_errors or []:
        issues.append(classify_lint_message(stage_key, str(err), artifact_path=rel))

    for err in schema_errors or []:
        issues.append(classify_schema_error(stage_key, str(err), artifact_path=rel))

    if triage_cfg().get("pre_cross_validate_repair", True):
        if STAGE_CHECKPOINTS.get(stage_key):
            for err in validate_cross_artifacts_for_stage(ctx, stage_key, staged=staged):
                issues.append(classify_cross_validate_message(stage_key, str(err), artifact_path=rel))

    if not schema_errors and rel and artifact:
        for err in validate_artifact_write(rel, artifact):
            issues.append(classify_schema_error(stage_key, str(err), artifact_path=rel))

    seen: set[str] = set()
    unique: list[ClassifiedIssue] = []
    for it in issues:
        if it.message in seen:
            continue
        seen.add(it.message)
        unique.append(it)
    return unique


def apply_deterministic_repairs(
    ctx: Any,
    stage_key: str,
    issues: list[ClassifiedIssue],
    artifacts: dict[str, Any],
    *,
    rel_path: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[ClassifiedIssue]]:
    cfg = triage_cfg()
    patched, applied = apply_repairs_for_stage(ctx, stage_key, artifacts, rel_path=rel_path)
    remaining = list(issues)

    if not cfg.get("auto_repair_minor", True):
        return patched, applied, remaining

    still: list[ClassifiedIssue] = []
    for issue in remaining:
        if should_auto_repair(issue) or issue.severity == "noise":
            continue
        still.append(issue)
    return patched, applied, still


def revalidate_after_repair(ctx: Any, stage_key: str, *, staged: bool = True) -> tuple[bool, list[str]]:
    errors: list[str] = []
    rel, artifact = _read_stage_artifact(ctx, stage_key, staged=staged)
    if rel and artifact:
        errors.extend(validate_artifact_write(rel, artifact))

    checkpoint = STAGE_CHECKPOINTS.get(stage_key)
    if checkpoint and triage_cfg().get("pre_cross_validate_repair", True):
        errors.extend(validate_cross_artifacts_for_stage(ctx, stage_key, staged=staged))

    return len(errors) == 0, errors


def _issues_to_clarification_items(
    ctx: Any,
    stage_key: str,
    issues: list[ClassifiedIssue],
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    items: list[dict[str, Any]] = []
    max_prompts = int(triage_cfg().get("max_operator_prompts_per_stage") or 8)
    prompt_count = 0

    for issue in issues:
        if issue.severity == "noise":
            continue
        iid = issue_id_for(stage_key, issue.message, issue.segment_id)
        item = issue.to_dict(stage_key=stage_key, issue_id=iid)
        item["created_at"] = now

        from interview_mux.artifact_root_cause import (
            build_recovery_actions,
            resolve_upstream_for_issue,
        )

        upstream = issue.upstream_stage or resolve_upstream_for_issue(issue, stage_key, ctx)
        if upstream:
            item["suggested_upstream_stage"] = upstream
        item["recovery_actions"] = build_recovery_actions(issue, stage_key, ctx)

        if should_llm_options(issue) and prompt_count < max_prompts:
            item["options"] = infer_options_local_llm(ctx, issue, artifacts, stage_key=stage_key)
            if item["options"]:
                prompt_count += 1
        elif issue.repair_strategy:
            from interview_mux.artifact_clarification_llm import _rule_based_options

            item["options"] = _rule_based_options(issue, artifacts)

        if issue.severity in ("minor", "noise"):
            item["blocking"] = False

        from interview_mux.artifact_auto_resolve import can_auto_resolve_issue, pick_recommended_choice

        rec = pick_recommended_choice(item)
        if rec is not None:
            item["recommended_choice"] = rec
        item["auto_resolvable"] = can_auto_resolve_issue(item)

        items.append(item)
    return items


def run_triage_pipeline(
    ctx: Any,
    stage_key: str,
    *,
    lint_errors: list[str] | None = None,
    schema_errors: list[str] | None = None,
    staged: bool = True,
) -> TriageResult:
    result = TriageResult(stage_key=stage_key)
    if not triage_enabled():
        return result

    ctx.log(
        f"itr.triage.start stage={stage_key} staged={staged}",
        level="info",
        stage=stage_key,
        action_id="itr.triage.start",
        detail={"staged": staged},
    )

    rel, artifact = _read_stage_artifact(ctx, stage_key, staged=staged)
    if not rel or not artifact:
        ctx.log(
            f"itr.triage.complete stage={stage_key} skipped=no_artifact",
            level="info",
            stage=stage_key,
            action_id="itr.triage.complete",
            detail={"open_blocking": 0, "auto_fixed": 0},
        )
        return result

    max_rounds = int(triage_cfg().get("max_resolution_rounds") or 3)
    for round_idx in range(max_rounds):
        issues = collect_issues(
            ctx,
            stage_key,
            staged=staged,
            lint_errors=lint_errors if round_idx == 0 else None,
            schema_errors=schema_errors if round_idx == 0 else None,
        )
        if round_idx == 0:
            _enqueue_noise_investigations(ctx, stage_key, issues)
        result.collected = len(issues)
        patched, applied, remaining = apply_deterministic_repairs(
            ctx, stage_key, issues, artifact, rel_path=rel
        )
        if applied:
            artifact = patched
            _write_stage_artifact(ctx, stage_key, rel, artifact)
            result.applied_repairs.extend(applied)
            result.auto_fixed += len(applied)

        downstream_errors: list[str] = []
        if applied and stage_key in ("segment_classification", "boundary_detection"):
            downstream_errors = revalidate_downstream_on_segment_fix(ctx, stage_key)
            if downstream_errors:
                plan = get_propagation_plan(ctx, stage_key)
                _maybe_enqueue_propagation_investigations(ctx, stage_key, plan)

        ok, val_errors = revalidate_after_repair(ctx, stage_key, staged=staged)
        result.revalidation_ok = ok and not downstream_errors
        result.errors = val_errors + downstream_errors
        if ok and not remaining:
            result.open_blocking = 0
            ctx.log(
                f"itr.triage.complete stage={stage_key} open=0 auto_fixed={result.auto_fixed}",
                level="info",
                stage=stage_key,
                action_id="itr.triage.complete",
                detail={
                    "open_blocking": 0,
                    "auto_fixed": result.auto_fixed,
                    "collected": result.collected,
                },
            )
            return result

        if not ok:
            remaining = collect_issues(ctx, stage_key, staged=staged)

        items = _issues_to_clarification_items(ctx, stage_key, remaining, artifact)
        for it in items:
            if it.get("severity") in ("minor", "noise"):
                it["status"] = "auto_fixed"
                it["blocking"] = False
        upsert_items(ctx, items)
        result.open_blocking = open_blocking_count(ctx, stage_key)

        blocking_items = [it for it in items if it.get("blocking") and it.get("status") == "open"]
        if not blocking_items:
            break

    result.open_blocking = open_blocking_count(ctx, stage_key)
    ctx.log(
        f"itr.triage.complete stage={stage_key} open={result.open_blocking} auto_fixed={result.auto_fixed}",
        level="info",
        stage=stage_key,
        action_id="itr.triage.complete",
        detail={
            "open_blocking": result.open_blocking,
            "auto_fixed": result.auto_fixed,
            "collected": result.collected,
            "errors": (result.errors or [])[:2],
        },
    )
    return result


def run_resolution_loop(ctx: Any, stage_key: str, **kwargs: Any) -> TriageResult:
    return run_triage_pipeline(ctx, stage_key, **kwargs)


def blocking_issues_remaining(ctx: Any, stage_key: str) -> int:
    return open_blocking_count(ctx, stage_key)


def clear_resolved_clarifications(ctx: Any, stage_key: str) -> None:
    from interview_mux.operator_clarifications_store import clear_resolved_for_stage

    clear_resolved_for_stage(ctx, stage_key)


def list_stage_issues(ctx: Any, stage_key: str) -> list[dict[str, Any]]:
    return items_for_stage(ctx, stage_key)


def resolve_issue(ctx: Any, stage_key: str, issue_id: str, choice: Any) -> tuple[bool, list[str]]:
    doc = load_clarifications(ctx)
    issue: dict[str, Any] | None = None
    for it in doc.get("items") or []:
        if isinstance(it, dict) and str(it.get("id")) == issue_id:
            issue = it
            break
    if not issue:
        return False, ["Issue not found"]

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key) or issue.get("artifact_path")
    if not rel:
        return False, ["No artifact path"]
    _, artifact = _read_stage_artifact(ctx, stage_key, staged=True)
    if not artifact:
        return False, ["Artifact not found in staging"]

    if choice == "dismiss":
        issue["status"] = "dismissed"
        issue["blocking"] = False
        upsert_items(ctx, [issue])
        return True, []

    if choice in ("fabricate_all", "accept_auto_repair"):
        patched, _ = apply_repairs_for_stage(ctx, stage_key, artifact)
    elif rel.endswith("boundaries.json"):
        patched = apply_choice_to_boundaries(artifact, issue, choice)
    elif rel.endswith("manifest.json"):
        patched = apply_choice_to_manifest(artifact, issue, choice)
    else:
        patched, _ = apply_repairs_for_stage(ctx, stage_key, artifact)

    _write_stage_artifact(ctx, stage_key, rel, patched)
    mark_resolved(ctx, issue_id, chosen=choice)
    if stage_key in ("segment_classification", "boundary_detection"):
        revalidate_downstream_on_segment_fix(ctx, stage_key)
    ok, errors = revalidate_after_repair(ctx, stage_key, staged=True)
    return ok, errors


def execute_recovery_action(
    ctx: Any,
    stage_key: str,
    issue_id: str,
    action: str,
    *,
    upstream_stage: str | None = None,
    runner: Any | None = None,
    run_id: str | None = None,
) -> RecoveryResult:
    """Execute operator recovery action (apply_repair, rerun_upstream, dismiss)."""
    if action == "apply_repair":
        ok, errors = resolve_issue(ctx, stage_key, issue_id, "accept_auto_repair")
        return RecoveryResult(ok=ok, errors=errors)

    if action == "dismiss":
        ok, errors = resolve_issue(ctx, stage_key, issue_id, "dismiss")
        return RecoveryResult(ok=ok, errors=errors)

    if action == "rerun_upstream":
        from interview_mux.artifact_root_cause import can_upstream_rerun, record_upstream_rerun

        if not can_upstream_rerun(ctx):
            return RecoveryResult(ok=False, errors=["Upstream rerun cap reached for this run"])

        doc = load_clarifications(ctx)
        issue: dict[str, Any] | None = None
        for it in doc.get("items") or []:
            if isinstance(it, dict) and str(it.get("id")) == issue_id:
                issue = it
                break
        target = upstream_stage or (issue or {}).get("suggested_upstream_stage")
        if not target:
            from interview_mux.llm_flow_hardening import resolve_llm_upstream_stage

            target = resolve_llm_upstream_stage(ctx, stage_key)
        if not target:
            return RecoveryResult(ok=False, errors=["No upstream stage identified"])

        if issue:
            issue["status"] = "pending_upstream_rerun"
            issue["evidence"] = {**(issue.get("evidence") or {}), "upstream_stage": target}
            upsert_items(ctx, [issue])

        invalidated_from = target
        job_payload: dict[str, Any] | None = None
        if runner and run_id and triage_cfg().get("upstream_rerun_invalidate_downstream", True):
            runner.invalidate_from(run_id, target)
            invalidated_from = target
            job_payload = runner.start(
                run_id,
                mode="stage",
                from_stage=target,
                stage=target,
            )
        record_upstream_rerun(ctx)
        return RecoveryResult(
            ok=True,
            job=job_payload,
            upstream_stage=target,
            invalidated_from=invalidated_from,
        )

    return RecoveryResult(ok=False, errors=[f"Unknown action: {action}"])


def execute_propagation(
    ctx: Any,
    stage_key: str,
    *,
    invalidate_from: str,
    rerun_stages: list[str] | None = None,
    runner: Any | None = None,
    run_id: str | None = None,
) -> RecoveryResult:
    """Invalidate downstream stages and optionally start upstream rerun."""
    if runner and run_id:
        from interview_mux.artifact_root_cause import invalidate_stale_downstream

        invalidate_stale_downstream(ctx, invalidate_from)
        runner.invalidate_from(run_id, invalidate_from)
        target = (rerun_stages or [invalidate_from])[0]
        job = runner.start(run_id, mode="stage", from_stage=target, stage=target)
        return RecoveryResult(ok=True, job=job, invalidated_from=invalidate_from, upstream_stage=target)
    return RecoveryResult(ok=False, errors=["Runner not available"])


def clear_clarification_gate(ctx: Any, stage_key: str) -> None:
    if not ctx.artifact_exists("gui_job.json"):
        return
    job = ctx.read_json("gui_job.json")
    if not isinstance(job, dict):
        return
    if str(job.get("status")) != "needs_clarification":
        return
    if str(job.get("stage") or "") != stage_key:
        return
    job["status"] = "awaiting_write_approval"
    job.pop("itr_blocking_count", None)
    job.pop("clarification_pending", None)
    job["message"] = f"{stage_key}: artifact issues resolved — review staged outputs."
    ctx.write_json("gui_job.json", job)


def _clarification_gate_payload(ctx: Any, stage_key: str, *, message: str | None = None) -> dict[str, Any]:
    count = open_blocking_count(ctx, stage_key)
    payload: dict[str, Any] = {
        "stage": stage_key,
        "message": message
        or f"{stage_key}: {count} artifact issue(s) need clarification before saving.",
        "itr_blocking_count": count,
    }
    try:
        from interview_mux.artifact_auto_resolve import get_stage_issues_summary

        summary = get_stage_issues_summary(ctx, stage_key)
        payload["can_fix_all"] = bool(summary.get("can_fix_all"))
        payload["bridge_eligible"] = bool(summary.get("bridge_eligible"))
        payload["itr_open_blocking"] = int(summary.get("open_blocking") or count)
    except Exception:
        payload["can_fix_all"] = True
    return payload


def set_clarification_gate(ctx: Any, stage_key: str, *, message: str | None = None) -> None:
    from interview_mux.full_autopilot import full_autopilot_enabled

    if full_autopilot_enabled():
        ctx.log(
            f"{stage_key}: clarification gate suppressed (full_autopilot) — use decision wizard",
            level="info",
            stage=stage_key,
            action_id="itr.gate.suppressed",
        )
        return
    if not ctx.artifact_exists("gui_job.json"):
        return
    job = ctx.read_json("gui_job.json")
    if not isinstance(job, dict):
        return
    count = open_blocking_count(ctx, stage_key)
    if count <= 0:
        return
    payload = _clarification_gate_payload(ctx, stage_key, message=message)
    # Defer visible gate while the pipeline worker still holds the run lock.
    if str(job.get("status")) in ("running", "running_with_warnings"):
        job["clarification_pending"] = True
        job.update(payload)
        ctx.write_json("gui_job.json", job)
        return
    job["status"] = "needs_clarification"
    job.update(payload)
    job.pop("clarification_pending", None)
    ctx.write_json("gui_job.json", job)


def apply_clarification_gate_after_pause(ctx: Any, stage_key: str) -> bool:
    """Promote deferred ITR gate after the pipeline releases the run lock."""
    if not triage_enabled():
        return False
    if open_blocking_count(ctx, stage_key) <= 0:
        return False
    job = ctx.read_json("gui_job.json") if ctx.artifact_exists("gui_job.json") else {}
    if not isinstance(job, dict):
        job = {}
    if not job.get("clarification_pending") and str(job.get("status")) == "needs_clarification":
        return True
    payload = _clarification_gate_payload(ctx, stage_key)
    job["status"] = "needs_clarification"
    job.update(payload)
    job.pop("clarification_pending", None)
    ctx.write_json("gui_job.json", job)
    return True


def maybe_repair_before_cross_validate(ctx: Any, stage_key: str) -> bool:
    if not triage_enabled() or not triage_cfg().get("pre_cross_validate_repair", True):
        return True
    result = run_triage_pipeline(ctx, stage_key, staged=True)
    if result.open_blocking > 0:
        set_clarification_gate(ctx, stage_key)
        return False
    return result.revalidation_ok or result.open_blocking == 0


def assert_write_approval_itr_ok(ctx: Any, stage_key: str) -> None:
    if not triage_enabled():
        return
    from interview_mux.full_autopilot import full_autopilot_enabled
    from interview_mux.operator_decisions import pending_decision_count

    if full_autopilot_enabled() and pending_decision_count(ctx, stage_key) > 0:
        from interview_mux.write_staging import WriteApprovalBlockedError

        raise WriteApprovalBlockedError(
            stage_key,
            f"Stage {stage_key}: resolve pending decisions in the wizard before saving.",
        )
    ok, errors = revalidate_after_repair(ctx, stage_key, staged=True)
    blocking = open_blocking_count(ctx, stage_key)
    downstream_errors: list[str] = []
    propagation_plan: dict[str, Any] | None = None

    if stage_key in ("segment_classification", "boundary_detection"):
        downstream_errors = revalidate_downstream_on_segment_fix(ctx, stage_key)
        propagation_plan = get_propagation_plan(ctx, stage_key)
        require_prop = triage_cfg().get("require_propagation_before_segment_approve", True)
        if require_prop and propagation_plan.get("has_blocking"):
            blocking = max(blocking, 1)

    if blocking > 0 or not ok or downstream_errors:
        from interview_mux.write_staging import WriteApprovalBlockedError

        msg = (
            f"Stage {stage_key}: {blocking} open artifact issue(s) block save. "
            "Resolve in the clarification panel."
        )
        all_errors = errors + downstream_errors
        if all_errors:
            msg += f" Validation: {'; '.join(all_errors[:3])}"
        if propagation_plan and propagation_plan.get("has_blocking"):
            msg += " Downstream stages may be stale — use the propagation wizard."
        exc = WriteApprovalBlockedError(stage_key, msg)
        exc.propagation_plan = propagation_plan  # type: ignore[attr-defined]
        raise exc
