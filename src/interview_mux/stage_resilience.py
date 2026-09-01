"""Stage-lifecycle resilience: contract evaluation, commit barrier, escalations.

Composes existing stage_contract / stage_acceptance / completeness. Leaves LLM
envelope sanitize/partial persist to ``llm_output_resilience``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

Action = Literal["pass", "retry", "halt", "skip", "reconcile", "escalate"]

RESILIENCE_REPORT_REL = "operator/resilience_report.json"
ESCALATIONS_DIR = "operator/escalations"
WAIVERS_DIR = "operator/waivers"


@dataclass
class StageResilienceDecision:
    action: Action
    reasons: list[str] = field(default_factory=list)
    remediation: list[str] = field(default_factory=list)
    acceptance_ok: bool | None = None
    family: str | None = None
    escalation: dict[str, Any] | None = None


def all_pipeline_stage_ids() -> tuple[str, ...]:
    return ANALYSIS_ORDER + DELIVERY_ORDER


def stage_resilience_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from interview_mux.config import merged_config

    root = cfg if isinstance(cfg, dict) else merged_config()
    raw = (root.get("resilience") or {}) if isinstance(root, dict) else {}
    return raw if isinstance(raw, dict) else {}


def unattended_defaults_enabled(ctx: RunContext | None = None) -> bool:
    """True for Full-auto / partially-accelerated / explicit config — never force_publish."""
    from interview_mux.automation_run import automation_driver_env_enabled, automation_driver_run

    cfg = stage_resilience_cfg().get("unattended_defaults") or {}
    if isinstance(cfg, dict) and cfg.get("enabled"):
        return True
    if automation_driver_env_enabled():
        return True
    if ctx is not None and ctx.artifact_exists("run_meta.json"):
        try:
            meta = ctx.read_json("run_meta.json") or {}
        except Exception:
            meta = {}
        if automation_driver_run(meta if isinstance(meta, dict) else None):
            return True
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evaluate_stage_resilience(
    ctx: RunContext,
    stage_id: str,
    *,
    staged: bool = True,
    phase: str | None = None,
) -> StageResilienceDecision:
    """Compose contract + acceptance + family remediation into a decision."""
    from interview_mux.stage_families import family_for_stage, remediation_for_stage
    from interview_mux.stage_contract import load_contract

    family = family_for_stage(stage_id)
    remediation = remediation_for_stage(stage_id)
    reasons: list[str] = []
    acceptance_ok: bool | None = None

    try:
        contract = load_contract(stage_id)
        if contract and contract.remediation:
            for r in contract.remediation:
                if r not in remediation:
                    remediation.append(r)
    except Exception as exc:
        reasons.append(f"contract_load:{exc}")

    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
        from interview_mux.stage_acceptance import stage_acceptance_ok

        # Stages without a registered primary artifact soft-pass acceptance.
        if stage_id not in STAGE_ARTIFACT_DISK_PATHS:
            acceptance_ok = True
        else:
            result = stage_acceptance_ok(
                ctx,
                stage_id,
                staged=staged,
                include_cross_validate=True,
            )
            acceptance_ok = bool(result.ok)
            if not acceptance_ok:
                errs = list(result.all_errors or result.errors or [])
                # Missing artifact during pre-flush of a stage that writes elsewhere
                # (side-effect heavy) should not always halt — callers use
                # staged_artifacts_acceptable for the hard gate.
                if errs == ["no_staged_artifact"] or errs == ["no_committed_artifact"]:
                    acceptance_ok = True
                    reasons.append(errs[0])
                else:
                    reasons.extend(str(e) for e in errs[:8])
                    if not reasons:
                        reasons.append("stage_acceptance_failed")
    except Exception as exc:
        # Some stages have no acceptance rules; treat missing as soft pass.
        msg = str(exc)
        if "unknown" in msg.lower() or "no acceptance" in msg.lower():
            acceptance_ok = True
        else:
            acceptance_ok = False
            reasons.append(f"acceptance_error:{exc}")

    if acceptance_ok is False:
        if "operator_escalate" in remediation or phase == "exhausted":
            try:
                from interview_mux.homunculus.issues import ingest_catch

                ingest_catch(
                    ctx,
                    kind="resilience_escalate",
                    source="stage_resilience",
                    stage_id=stage_id,
                    implicated=[stage_id],
                    evidence={"reasons": reasons[:8]},
                )
            except Exception:
                pass
            return StageResilienceDecision(
                action="escalate",
                reasons=reasons,
                remediation=remediation,
                acceptance_ok=False,
                family=family,
            )
        return StageResilienceDecision(
            action="retry",
            reasons=reasons,
            remediation=remediation,
            acceptance_ok=False,
            family=family,
        )

    return StageResilienceDecision(
        action="pass",
        reasons=reasons,
        remediation=remediation,
        acceptance_ok=True if acceptance_ok is None else acceptance_ok,
        family=family,
    )


def before_mark_done(ctx: RunContext, stage_id: str) -> StageResilienceDecision:
    """Refuse mark_done when staged outputs are incomplete / unacceptable."""
    from interview_mux.stage_completion import staged_artifacts_acceptable
    from interview_mux.write_staging import has_pending_writes

    if has_pending_writes(ctx, stage_id):
        ok, reason = staged_artifacts_acceptable(ctx, stage_id)
        if not ok:
            return StageResilienceDecision(
                action="halt",
                reasons=[reason or "staged_artifacts_unacceptable"],
                remediation=["repair_outputs", "operator_escalate"],
                acceptance_ok=False,
            )
        # Pending writes must flush before durable done — reconcile path.
        return StageResilienceDecision(
            action="reconcile",
            reasons=["pending_writes_unflushed"],
            remediation=["flush_then_mark_done"],
            acceptance_ok=True,
        )
    decision = evaluate_stage_resilience(ctx, stage_id, staged=False)
    if decision.action in ("retry", "escalate", "halt") and decision.acceptance_ok is False:
        decision.action = "halt"
    return decision


def after_flush_resilience(
    ctx: RunContext,
    stage_id: str,
    flushed: list[str],
) -> StageResilienceDecision:
    decision = evaluate_stage_resilience(ctx, stage_id, staged=False, phase="post_flush")
    record_resilience_event(
        ctx,
        stage_id,
        event="after_flush",
        action=decision.action,
        reasons=decision.reasons,
        detail={"flushed": list(flushed)[:40]},
    )
    return decision


def validate_staged_before_flush(ctx: RunContext, stage_id: str) -> StageResilienceDecision:
    """Pre-flush commit barrier: validate staged overlay before promoting files."""
    from interview_mux.stage_completion import staged_artifacts_acceptable
    from interview_mux.write_staging import has_pending_writes, list_pending_paths

    if not has_pending_writes(ctx, stage_id):
        return StageResilienceDecision(action="pass", reasons=["no_pending_writes"])

    ok, reason = staged_artifacts_acceptable(ctx, stage_id)
    if not ok:
        reason_s = reason or "staged_unacceptable"
        # Incomplete/empty staged files mid-write: log and let post_commit validate
        # after flush rather than blocking promotion of sibling good outputs.
        soft = any(
            token in reason_s.lower()
            for token in (
                "cannot read",
                "expecting value",
                "empty",
                "no_staged_artifact",
                "not found",
            )
        )
        decision = StageResilienceDecision(
            action="pass" if soft else "halt",
            reasons=[reason_s],
            remediation=["repair_outputs", "discard_staged", "operator_escalate"],
            acceptance_ok=soft,
        )
        record_resilience_event(
            ctx,
            stage_id,
            event="pre_flush_validate",
            action=decision.action,
            reasons=decision.reasons,
            detail={"pending": list_pending_paths(ctx, stage_id)[:40], "soft": soft},
        )
        return decision

    decision = evaluate_stage_resilience(ctx, stage_id, staged=True, phase="pre_flush")
    if decision.action in ("retry", "escalate") and decision.acceptance_ok is False:
        # Soft: do not hard-halt pre-flush solely on registry acceptance soft-fails.
        decision = StageResilienceDecision(
            action="pass",
            reasons=decision.reasons or ["pre_flush_soft_pass"],
            remediation=decision.remediation,
            acceptance_ok=True,
            family=decision.family,
        )
    record_resilience_event(
        ctx,
        stage_id,
        event="pre_flush_validate",
        action=decision.action,
        reasons=decision.reasons,
    )
    return decision


def reconcile_stage_if_stale(ctx: RunContext, stage_id: str) -> bool:
    from interview_mux.stage_completion import reconcile_stage_done_marker

    return bool(reconcile_stage_done_marker(ctx, stage_id))


def _read_report(ctx: RunContext) -> dict[str, Any]:
    path = Path(ctx.run_dir) / RESILIENCE_REPORT_REL
    if not path.is_file():
        return {"version": 1, "events": [], "stages": {}, "active_escalations": []}
    try:
        data = ctx.read_json(RESILIENCE_REPORT_REL)
        return data if isinstance(data, dict) else {
            "version": 1,
            "events": [],
            "stages": {},
            "active_escalations": [],
        }
    except Exception:
        return {"version": 1, "events": [], "stages": {}, "active_escalations": []}


def record_resilience_event(
    ctx: RunContext,
    stage_id: str,
    *,
    event: str,
    action: str | None = None,
    reasons: list[str] | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    report = _read_report(ctx)
    events = list(report.get("events") or [])
    entry = {
        "ts": _utc_now(),
        "stage_id": stage_id,
        "event": event,
        "action": action,
        "reasons": list(reasons or [])[:12],
        "detail": detail or {},
    }
    events.append(entry)
    # Cap history to keep artifact bounded.
    report["events"] = events[-500:]
    stages = dict(report.get("stages") or {})
    prev = dict(stages.get(stage_id) or {})
    attempts = int(prev.get("attempts") or 0)
    if event in ("retry", "pre_flush_validate", "after_flush", "stage_fail"):
        attempts += 1
    stages[stage_id] = {
        "last_action": action or prev.get("last_action"),
        "attempts": attempts,
        "status": event,
        "last_reasons": list(reasons or [])[:8],
    }
    report["stages"] = stages
    report["updated_at"] = _utc_now()
    report["version"] = 1
    dest = Path(ctx.run_dir) / RESILIENCE_REPORT_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(dest, report)


def write_escalation(
    ctx: RunContext,
    stage_id: str,
    *,
    failed_invariant: str,
    evidence: dict[str, Any] | None = None,
    preserved_work: list[str] | None = None,
    recommended_option: str,
    options: list[dict[str, Any]],
    resume_stage: str | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    """Write a quality-first operator escalation card (never auto-waives ship)."""
    try:
        from interview_mux.homunculus.issues import ingest_catch

        ingest_catch(
            ctx,
            kind="resilience_escalation",
            source="stage_resilience",
            stage_id=stage_id,
            implicated=[stage_id],
            evidence={"failed_invariant": failed_invariant[:400]},
        )
    except Exception:
        pass
    from interview_mux.stage_families import family_for_stage

    doc = {
        "version": 1,
        "stage_id": stage_id,
        "status": "open",
        "failed_invariant": failed_invariant,
        "evidence": evidence or {},
        "preserved_work": list(preserved_work or []),
        "recommended_option": recommended_option,
        "options": options,
        "resume_stage": resume_stage or stage_id,
        "created_at": _utc_now(),
        "resolved_at": None,
        "chosen_option": None,
        "family": family or family_for_stage(stage_id),
        "quality_first": True,
    }
    rel = f"{ESCALATIONS_DIR}/{stage_id}.json"
    dest = Path(ctx.run_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(dest, doc)
    report = _read_report(ctx)
    active = [str(s) for s in (report.get("active_escalations") or []) if s]
    if stage_id not in active:
        active.append(stage_id)
    report["active_escalations"] = active
    report["updated_at"] = _utc_now()
    dest_r = Path(ctx.run_dir) / RESILIENCE_REPORT_REL
    dest_r.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest_r, report)
    record_resilience_event(
        ctx,
        stage_id,
        event="escalation_open",
        action="escalate",
        reasons=[failed_invariant],
        detail={"recommended_option": recommended_option},
    )
    return doc


def resolve_escalation(
    ctx: RunContext,
    stage_id: str,
    *,
    chosen_option: str,
    unattended: bool = False,
) -> dict[str, Any]:
    rel = f"{ESCALATIONS_DIR}/{stage_id}.json"
    path = Path(ctx.run_dir) / rel
    if not path.is_file():
        raise FileNotFoundError(rel)
    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        raise ValueError(f"invalid escalation: {rel}")
    option_ids = {str(o.get("id")) for o in (doc.get("options") or []) if isinstance(o, dict)}
    if chosen_option not in option_ids:
        raise ValueError(f"unknown escalation option: {chosen_option}")
    # Quality-first: never mark a publish waiver via this path.
    if chosen_option in ("waive_quality", "force_publish", "soft_ship"):
        raise ValueError("quality_first policy forbids waived publish via escalation")
    doc["status"] = "waived_unattended" if unattended else "resolved"
    doc["chosen_option"] = chosen_option
    doc["resolved_at"] = _utc_now()
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(path, doc)
    if unattended:
        waiver_rel = f"{WAIVERS_DIR}/{stage_id}.json"
        wdest = Path(ctx.run_dir) / waiver_rel
        wdest.parent.mkdir(parents=True, exist_ok=True)
        fs_write_json(
            wdest,
            {
                "version": 1,
                "stage_id": stage_id,
                "chosen_option": chosen_option,
                "created_at": _utc_now(),
                "note": "unattended_default_decision",
                "quality_first": True,
                "publishes_waived_master": False,
            },
        )
    report = _read_report(ctx)
    active = [str(s) for s in (report.get("active_escalations") or []) if s and s != stage_id]
    report["active_escalations"] = active
    report["updated_at"] = _utc_now()
    fs_write_json(Path(ctx.run_dir) / RESILIENCE_REPORT_REL, report)
    record_resilience_event(
        ctx,
        stage_id,
        event="escalation_resolved",
        action="pass",
        reasons=[f"chose:{chosen_option}"],
        detail={"unattended": unattended},
    )
    return doc


def read_escalation(ctx: RunContext, stage_id: str) -> dict[str, Any] | None:
    rel = f"{ESCALATIONS_DIR}/{stage_id}.json"
    path = Path(ctx.run_dir) / rel
    if not path.is_file():
        return None
    try:
        data = ctx.read_json(rel)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def list_open_escalations(ctx: RunContext) -> list[dict[str, Any]]:
    root = Path(ctx.run_dir) / ESCALATIONS_DIR
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            from interview_mux.file_store import read_json as fs_read_json

            doc = fs_read_json(path)
        except Exception:
            continue
        if isinstance(doc, dict) and doc.get("status") == "open":
            out.append(doc)
    return out


def registry_coverage() -> dict[str, Any]:
    """Assert every pipeline stage has a family mapping (and preferably a YAML contract)."""
    from interview_mux.stage_families import FAMILY_BY_STAGE, family_for_stage
    from interview_mux.stage_contract import all_contract_stage_ids

    ids = list(all_pipeline_stage_ids())
    missing_family = [s for s in ids if s not in FAMILY_BY_STAGE]
    try:
        contracts = set(all_contract_stage_ids())
    except Exception:
        contracts = set()
    missing_contract = [s for s in ids if s not in contracts]
    return {
        "stage_count": len(ids),
        "missing_family": missing_family,
        "missing_contract": missing_contract,
        "ok": not missing_family,
        "families": {s: family_for_stage(s) for s in ids},
    }


def escalate_stage_failure(
    ctx: RunContext,
    stage_id: str,
    *,
    failed_invariant: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard escalation card for exhausted repairs."""
    from interview_mux.stage_families import default_escalation_options, family_for_stage

    family = family_for_stage(stage_id)
    options = default_escalation_options(stage_id)
    recommended = str(options[0]["id"]) if options else "retry_stage"
    preserved: list[str] = []
    for rel in (
        "master/selection.json",
        "master/edl.json",
        "master/assembly.wav",
        "master/master.wav",
        "understanding/gap_report.json",
        "understanding/nugget_layup_plan.json",
        "sound_design/mmaudio_qa.json",
    ):
        if ctx.artifact_exists(rel):
            preserved.append(rel)
    try:
        from interview_mux.identical_failures import record_identical_failure

        record_identical_failure(
            ctx,
            failed_stage=stage_id,
            producer=str((evidence or {}).get("path") or ""),
            reason=failed_invariant,
            resume_attempted=stage_id,
        )
    except Exception:
        pass
    doc = write_escalation(
        ctx,
        stage_id,
        failed_invariant=failed_invariant,
        evidence=evidence or {},
        preserved_work=preserved,
        recommended_option=recommended,
        options=options,
        resume_stage=stage_id,
        family=family,
    )
    if unattended_defaults_enabled(ctx) and recommended not in {
        "force_publish",
        "soft_ship",
        "waive_quality",
    }:
        try:
            doc = resolve_escalation(
                ctx,
                stage_id,
                chosen_option=recommended,
                unattended=True,
            )
        except Exception:
            pass
    return doc
