"""Bulk auto-resolve for Artifact Issue Triage & Remediation (ITR)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from interview_mux.artifact_issue_triage import (
    blocking_issues_remaining,
    clear_clarification_gate,
    get_propagation_plan,
    revalidate_after_repair,
    revalidate_downstream_on_segment_fix,
    resolve_issue,
    run_triage_pipeline,
    triage_cfg,
    triage_enabled,
)
from interview_mux.operator_clarifications_store import items_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.write_staging import staged_path, write_pending_content

ITR_STAGE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "boundary_detection": {
        "tier": "full",
        "step_label": "Fix all & continue",
        "propagation_chain": ("segment_classification",),
        "auto_chain_downstream": True,
    },
    "segment_classification": {
        "tier": "full",
        "step_label": "Fix all & continue",
        "propagation_chain": (),
        "auto_chain_downstream": False,
    },
    "content_brief_reanchor": {"tier": "scaffold", "step_label": "Review issues", "propagation_chain": ()},
    "sonic_context_build": {"tier": "scaffold", "step_label": "Review issues", "propagation_chain": ()},
    "sound_design_palettes": {"tier": "scaffold", "step_label": "Review issues", "propagation_chain": ()},
    "missing_framing": {"tier": "scaffold", "step_label": "Review issues", "propagation_chain": ()},
    "optimal_questions": {"tier": "scaffold", "step_label": "Review issues", "propagation_chain": ()},
}


class AutoResolveOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    MANUAL_REQUIRED = "manual_required"
    BUSY = "busy"
    CAP_EXHAUSTED = "cap_exhausted"
    OSCILLATION_HALT = "oscillation_halt"
    NO_STAGED_ARTIFACT = "no_staged_artifact"
    STAGING_CORRUPT = "staging_corrupt"
    DESTRUCTIVE_BUDGET_EXCEEDED = "destructive_budget_exceeded"
    JOB_INTERRUPTED = "job_interrupted"


@dataclass
class AutoResolveResult:
    outcome: AutoResolveOutcome
    stage_key: str
    phase: str = "local_fix"
    open_blocking: int = 0
    resolved_count: int = 0
    resolved_ids: list[str] = field(default_factory=list)
    failed_at: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    can_advance_pipeline: bool = False
    downstream_job: dict[str, Any] | None = None
    preview: list[dict[str, Any]] = field(default_factory=list)
    attempt: int = 0
    propagation_plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "stage_key": self.stage_key,
            "phase": self.phase,
            "open_blocking": self.open_blocking,
            "resolved_count": self.resolved_count,
            "resolved_ids": self.resolved_ids,
            "failed_at": self.failed_at,
            "warnings": self.warnings,
            "errors": self.errors,
            "can_advance_pipeline": self.can_advance_pipeline,
            "downstream_job": self.downstream_job,
            "preview": self.preview,
            "attempt": self.attempt,
            "propagation_plan": self.propagation_plan,
        }


def stage_capabilities(stage_key: str) -> dict[str, Any]:
    return ITR_STAGE_CAPABILITIES.get(stage_key, {"tier": "manual", "step_label": "Review issues"})


def _orch_path() -> str:
    return "understanding/analysis_orchestration.json"


def _read_orch(ctx: Any) -> dict[str, Any]:
    if not ctx.artifact_exists(_orch_path()):
        return {}
    doc = ctx.read_json(_orch_path())
    return doc if isinstance(doc, dict) else {}


def _write_orch(ctx: Any, doc: dict[str, Any]) -> None:
    ctx.write_json(_orch_path(), doc, skip_handoff=True)


def _attempt_key(stage_key: str) -> str:
    return f"itr_auto_resolve_attempts_{stage_key}"


def _signature_key(stage_key: str) -> str:
    return f"itr_auto_resolve_signature_{stage_key}"


def _issue_signature(items: list[dict[str, Any]]) -> str:
    open_items = [
        (str(it.get("id")), str(it.get("message")))
        for it in items
        if it.get("status") == "open" and it.get("blocking") is not False
    ]
    payload = json.dumps(sorted(open_items), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _record_attempt(ctx: Any, stage_key: str, signature: str) -> tuple[int, bool]:
    cfg = triage_cfg()
    cap = int(cfg.get("max_auto_resolve_attempts_per_stage") or 2)
    doc = _read_orch(ctx)
    attempts = int(doc.get(_attempt_key(stage_key)) or 0) + 1
    prev_sig = str(doc.get(_signature_key(stage_key)) or "")
    oscillation = prev_sig == signature and attempts > 1
    doc[_attempt_key(stage_key)] = attempts
    doc[_signature_key(stage_key)] = signature
    _write_orch(ctx, doc)
    if attempts > cap:
        return attempts, True
    if oscillation and attempts >= cap:
        return attempts, True
    return attempts, False


def _reset_attempt_on_success(ctx: Any, stage_key: str) -> None:
    doc = _read_orch(ctx)
    doc.pop(_attempt_key(stage_key), None)
    doc.pop(_signature_key(stage_key), None)
    _write_orch(ctx, doc)


def pick_recommended_choice(item: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> Any | None:
    cfg = cfg or triage_cfg()
    min_conf = float(cfg.get("auto_resolve_min_confidence") or 0.70)
    gap = float(cfg.get("auto_resolve_confidence_gap") or 0.15)
    options = item.get("options") or []
    if not options:
        strategy = str(item.get("repair_strategy") or "")
        if strategy == "merge_overlap":
            return "accept_auto_repair"
        if strategy in ("infer_segment_types", "llm_pick"):
            return None
        return "accept_auto_repair"

    scored: list[tuple[float, Any]] = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        conf = opt.get("confidence")
        if conf is None:
            conf = opt.get("score")
        try:
            score = float(conf) if conf is not None else 0.5
        except (TypeError, ValueError):
            score = 0.5
        value = opt.get("value") if "value" in opt else opt.get("choice") or opt.get("label")
        scored.append((score, value))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_choice = scored[0]
    if best_score < min_conf:
        return None
    if len(scored) > 1 and (best_score - scored[1][0]) < gap:
        return None
    return best_choice


def can_auto_resolve_issue(item: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> bool:
    if item.get("status") != "open" or item.get("blocking") is False:
        return False
    if item.get("severity") == "critical" and not item.get("options") and not item.get("repair_strategy"):
        return False
    choice = pick_recommended_choice(item, cfg=cfg)
    return choice is not None


def can_auto_resolve_all(ctx: Any, stage_key: str) -> bool:
    if not triage_enabled():
        return False
    items = [
        it
        for it in items_for_stage(ctx, stage_key)
        if it.get("status") == "open" and it.get("blocking") is not False
    ]
    if not items:
        return True
    cfg = triage_cfg()
    return all(can_auto_resolve_issue(it, cfg=cfg) for it in items)


def build_resolution_preview(ctx: Any, stage_key: str) -> list[dict[str, Any]]:
    cfg = triage_cfg()
    preview: list[dict[str, Any]] = []
    cap = int(cfg.get("auto_resolve_max_issues_per_pass") or 50)
    for item in items_for_stage(ctx, stage_key):
        if item.get("status") != "open" or item.get("blocking") is False:
            continue
        choice = pick_recommended_choice(item, cfg=cfg)
        preview.append(
            {
                "issue_id": item.get("id"),
                "message": item.get("message"),
                "segment_id": item.get("segment_id"),
                "recommended_choice": choice,
                "auto_resolvable": choice is not None,
            }
        )
        if len(preview) >= cap:
            break
    return preview


def _snapshot_staging(ctx: Any, stage_key: str) -> dict[str, Any] | None:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return None
    try:
        p = staged_path(ctx, rel, stage_id=stage_key)
        if not p.is_file():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _restore_staging(ctx: Any, stage_key: str, snapshot: dict[str, Any]) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if rel:
        write_pending_content(ctx, stage_key, rel, data=snapshot)


def _segment_count(ctx: Any, stage_key: str) -> int:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return 0
    try:
        p = staged_path(ctx, rel, stage_id=stage_key)
        if not p.is_file():
            return 0
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return 0
        if rel.endswith("manifest.json"):
            segs = doc.get("segments")
            return len(segs) if isinstance(segs, list) else 0
        if rel.endswith("boundaries.json"):
            rows = doc.get("boundaries")
            return len(rows) if isinstance(rows, list) else 0
    except Exception:
        return 0
    return 0


def _destructive_choice(choice: Any) -> bool:
    if choice == "delete_segment":
        return True
    return isinstance(choice, dict) and choice.get("action") == "delete"


def _clear_propagation_investigations(ctx: Any, stage_key: str) -> None:
    from interview_mux.analysis_memory import mark_investigation_done

    path = "understanding/investigation_queue.json"
    if not ctx.artifact_exists(path):
        return
    doc = ctx.read_json(path)
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        return
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("kind")) != "manifest_propagation":
            continue
        if str(it.get("status") or "open") not in ("open", "pending"):
            continue
        inv_id = str(it.get("id") or "")
        if inv_id:
            mark_investigation_done(ctx, inv_id)


def revalidate_for_itr_gate(
    ctx: Any,
    stage_key: str,
    *,
    artifact_source: str = "staged",
) -> tuple[bool, list[str], list[str]]:
    """Gate exit validation: staged before save; committed after write approval."""
    staged = artifact_source != "committed"
    ok, errors = revalidate_after_repair(ctx, stage_key, staged=staged)
    downstream: list[str] = []
    if stage_key in ("segment_classification", "boundary_detection"):
        downstream = revalidate_downstream_on_segment_fix(ctx, stage_key)
    return ok and not downstream, errors, downstream


def get_stage_issues_summary(ctx: Any, stage_key: str) -> dict[str, Any]:
    caps = stage_capabilities(stage_key)
    open_blocking = blocking_issues_remaining(ctx, stage_key)
    preview = build_resolution_preview(ctx, stage_key) if triage_enabled() else []
    return {
        "tier": caps.get("tier", "manual"),
        "step_label": caps.get("step_label", "Review issues"),
        "can_fix_all": can_auto_resolve_all(ctx, stage_key) if open_blocking else True,
        "preview": preview,
        "open_blocking": open_blocking,
    }


def auto_resolve_stage(
    ctx: Any,
    stage_key: str,
    *,
    runner: Any | None = None,
    run_id: str | None = None,
) -> AutoResolveResult:
    """Resolve all auto-resolvable artifact issues for a stage."""
    result = AutoResolveResult(outcome=AutoResolveOutcome.SUCCESS, stage_key=stage_key)

    if not triage_enabled():
        result.phase = "complete"
        result.can_advance_pipeline = True
        return result

    open_before = blocking_issues_remaining(ctx, stage_key)
    if open_before == 0:
        result.phase = "complete"
        result.can_advance_pipeline = True
        clear_clarification_gate(ctx, stage_key)
        return result

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        result.outcome = AutoResolveOutcome.NO_STAGED_ARTIFACT
        result.phase = "failed"
        result.errors.append("No artifact path for stage")
        return result

    snapshot = _snapshot_staging(ctx, stage_key)
    if snapshot is None:
        result.outcome = AutoResolveOutcome.NO_STAGED_ARTIFACT
        result.phase = "failed"
        result.errors.append("No staged artifact to repair")
        return result

    items = [
        it
        for it in items_for_stage(ctx, stage_key)
        if it.get("status") == "open" and it.get("blocking") is not False
    ]
    signature = _issue_signature(items)
    attempt, cap_hit = _record_attempt(ctx, stage_key, signature)
    result.attempt = attempt
    if cap_hit:
        result.outcome = AutoResolveOutcome.CAP_EXHAUSTED
        result.phase = "failed"
        result.open_blocking = open_before
        result.errors.append("Auto-resolve attempt cap reached for this stage")
        return result

    cfg = triage_cfg()
    seg_before = _segment_count(ctx, stage_key)
    max_delete_ratio = float(cfg.get("max_segments_deleted_per_fix_all") or 0.10)
    min_segments = int(cfg.get("min_segments_after_auto_resolve") or 1)
    max_issues = int(cfg.get("auto_resolve_max_issues_per_pass") or 50)

    ctx.log(
        f"itr.auto_resolve.start stage={stage_key} open={open_before}",
        level="info",
        stage=stage_key,
    )

    triage_result = run_triage_pipeline(ctx, stage_key, staged=True)
    if triage_result.errors:
        result.warnings.extend(triage_result.errors[:3])

    open_after_triage = blocking_issues_remaining(ctx, stage_key)
    if open_after_triage == 0:
        ok, errors, downstream = revalidate_for_itr_gate(ctx, stage_key, artifact_source="staged")
        result.errors.extend(errors)
        if ok and not downstream:
            clear_clarification_gate(ctx, stage_key)
            _reset_attempt_on_success(ctx, stage_key)
            result.outcome = AutoResolveOutcome.SUCCESS
            result.phase = "awaiting_save"
            result.can_advance_pipeline = bool(cfg.get("auto_advance_after_itr_clear", True))
            return result

    deleted = 0
    resolved = 0
    cfg_caps = stage_capabilities(stage_key)

    for _ in range(max_issues):
        open_items = [
            it
            for it in items_for_stage(ctx, stage_key)
            if it.get("status") == "open" and it.get("blocking") is not False
        ]
        if not open_items:
            break

        progressed = False
        for item in open_items:
            choice = pick_recommended_choice(item, cfg=cfg)
            if choice is None:
                continue
            if _destructive_choice(choice):
                deleted += 1
                if seg_before and (deleted / seg_before) > max_delete_ratio:
                    _restore_staging(ctx, stage_key, snapshot)
                    result.outcome = AutoResolveOutcome.DESTRUCTIVE_BUDGET_EXCEEDED
                    result.phase = "failed"
                    result.errors.append("Destructive fix budget exceeded")
                    result.open_blocking = blocking_issues_remaining(ctx, stage_key)
                    return result

            issue_id = str(item.get("id") or "")
            try:
                ok, errors = resolve_issue(ctx, stage_key, issue_id, choice)
            except Exception as exc:
                result.failed_at = issue_id
                result.errors.append(str(exc))
                result.outcome = AutoResolveOutcome.PARTIAL
                result.phase = "failed"
                result.resolved_count = resolved
                result.resolved_ids = result.resolved_ids
                result.open_blocking = blocking_issues_remaining(ctx, stage_key)
                return result

            if not ok:
                result.failed_at = issue_id
                result.errors.extend(errors)
                result.outcome = AutoResolveOutcome.PARTIAL
                result.phase = "failed"
                result.resolved_count = resolved
                result.open_blocking = blocking_issues_remaining(ctx, stage_key)
                return result

            resolved += 1
            result.resolved_ids.append(issue_id)
            ctx.log(
                f"itr.auto_resolve.apply issue={issue_id} choice={choice!r}",
                level="info",
                stage=stage_key,
            )
            progressed = True
            break

        if not progressed:
            break

    seg_after = _segment_count(ctx, stage_key)
    if deleted > 0 and seg_after < min_segments:
        _restore_staging(ctx, stage_key, snapshot)
        result.outcome = AutoResolveOutcome.DESTRUCTIVE_BUDGET_EXCEEDED
        result.phase = "failed"
        result.errors.append(f"Would leave fewer than {min_segments} segment(s)")
        result.open_blocking = blocking_issues_remaining(ctx, stage_key)
        return result

    result.resolved_count = resolved
    ok, errors, downstream = revalidate_for_itr_gate(ctx, stage_key, artifact_source="staged")
    result.errors.extend(errors)
    result.warnings.extend([f"downstream: {e}" for e in downstream[:3]])
    result.propagation_plan = get_propagation_plan(ctx, stage_key)
    result.open_blocking = blocking_issues_remaining(ctx, stage_key)

    manual_left = [
        it
        for it in items_for_stage(ctx, stage_key)
        if it.get("status") == "open" and it.get("blocking") is not False
    ]

    if manual_left:
        result.outcome = AutoResolveOutcome.MANUAL_REQUIRED if resolved == 0 else AutoResolveOutcome.PARTIAL
        result.phase = "failed"
        result.preview = build_resolution_preview(ctx, stage_key)
        return result

    if not ok or downstream or result.propagation_plan.get("has_blocking"):
        result.outcome = AutoResolveOutcome.PARTIAL
        result.phase = "awaiting_save"
        return result

    clear_clarification_gate(ctx, stage_key)
    _clear_propagation_investigations(ctx, stage_key)
    _reset_attempt_on_success(ctx, stage_key)

    chain = cfg.get("auto_resolve_chain_downstream", True) and cfg_caps.get("auto_chain_downstream")
    if (
        chain
        and stage_key == "boundary_detection"
        and runner
        and run_id
    ):
        from interview_mux.artifact_root_cause import can_downstream_auto_continue, record_downstream_auto_continue

        if can_downstream_auto_continue(ctx):
            try:
                job = runner.start(
                    run_id,
                    mode="stage",
                    from_stage="segment_classification",
                    stage="segment_classification",
                )
                record_downstream_auto_continue(ctx)
                result.downstream_job = job
                result.phase = "downstream_job"
                result.outcome = AutoResolveOutcome.SUCCESS
                result.can_advance_pipeline = False
                result.warnings.append("Chained segment_classification re-run")
                return result
            except Exception as exc:
                result.warnings.append(f"Downstream chain skipped: {exc}")

    result.outcome = AutoResolveOutcome.SUCCESS
    result.phase = "awaiting_save"
    result.can_advance_pipeline = bool(cfg.get("auto_advance_after_itr_clear", True))
    ctx.log(
        f"itr.auto_resolve.complete stage={stage_key} resolved={resolved}",
        level="info",
        stage=stage_key,
    )
    return result
