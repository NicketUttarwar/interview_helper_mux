"""Execution contract — reconciled VO seating truth + recovery ladder (Phases 1–3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.run_context import RunContext

EXECUTION_CONTRACT_REL = "operator/execution_contract.json"
VO_CONTRACT_REPAIR_PLAN_REL = "operator/vo_contract_repair_plan.json"
REMEDIATION_PLAN_REL = "operator/remediation_plan.json"

VoViolationKind = Literal[
    "missing_from_gap",
    "skip_omit_on_seated",
    "seated_and_omitted",
    "omitted_without_flags",
    "missing_wav",
    "implicit_orientation_seat",
    "unknown",
]

LADDER_TIERS: tuple[str, ...] = (
    "tier_a_publish_orientation",
    "tier_b_gap_recompose",
    "tier_c_opening_omit_unseat",
    "tier_d_logged_waive",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class VoViolation:
    kind: VoViolationKind
    line_id: str = ""
    detail: str = ""


@dataclass
class LadderResult:
    tier: str
    recovered: bool
    contract_ok: bool
    violations: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    detail: str = ""
    resume_stage: str = ""


def ladder_enabled() -> bool:
    try:
        from interview_mux.config import merged_config

        root = merged_config()
        mastering = root.get("mastering") if isinstance(root, dict) else {}
        resilience = (mastering or {}).get("resilience") if isinstance(mastering, dict) else {}
        if isinstance(resilience, dict):
            return bool(resilience.get("execution_contract_ladder_enabled", True))
    except Exception:
        pass
    return True


def snapshot_execution_contract(ctx: RunContext) -> dict[str, Any]:
    """Read-only contract snapshot from gap_report + mastering_plan vo_seats."""
    from interview_mux.air_script import load_air_script, seated_vo_line_ids, omitted_vo_line_ids
    from interview_mux.mastering_plan_loader import load_plan_raw
    from interview_mux.opening_orientation import is_episode_orientation, orientation_omitted
    from interview_mux.vo_contract import validate_vo_contract

    plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
    script = load_air_script(plan if isinstance(plan, dict) else {})
    seats = script.get("vo_seats") if isinstance(script, dict) else {}
    seated = seated_vo_line_ids(plan if isinstance(plan, dict) else {})
    omitted = omitted_vo_line_ids(plan if isinstance(plan, dict) else {})

    gap_lines: dict[str, dict[str, Any]] = {}
    opening_omit = False
    if ctx.artifact_exists("understanding/gap_report.json"):
        gap = ctx.read_json("understanding/gap_report.json")
        if isinstance(gap, dict):
            opening_omit = orientation_omitted(gap)
            for row in gap.get("interviewer_lines") or []:
                if isinstance(row, dict):
                    lid = str(row.get("line_id") or "").strip()
                    if lid:
                        gap_lines[lid] = row

    vo_lines: dict[str, Any] = {}
    for lid in sorted(set(seated) | set(omitted) | set(gap_lines)):
        row = gap_lines.get(lid)
        vo_lines[lid] = {
            "seated": lid in seated,
            "omitted": lid in omitted,
            "in_gap_report": lid in gap_lines,
            "delivery": str((row or {}).get("delivery") or ""),
            "skipped_optional": bool((row or {}).get("skipped_optional")),
            "air_script_omit": bool((row or {}).get("air_script_omit")),
            "is_orientation": bool(row and is_episode_orientation(row)),
        }

    violations = validate_vo_contract(ctx)
    return {
        "version": 1,
        "snapshot_at": _utc_now(),
        "contract_ok": not violations,
        "violations": violations,
        "opening_orientation_omitted": opening_omit,
        "vo_seats": seats if isinstance(seats, dict) else {},
        "vo_lines": vo_lines,
        "seated_count": len(seated),
        "omitted_count": len(omitted),
    }


def classify_vo_violation(message: str) -> VoViolation:
    low = str(message or "").lower()
    lid = ""
    if "seated line " in low and "missing from gap_report" in low:
        start = low.find("seated line ") + len("seated line ")
        lid = message[start:].split(" missing")[0].strip()
        return VoViolation("missing_from_gap", line_id=lid, detail=message)
    if "missing from gap_report" in low:
        return VoViolation("missing_from_gap", detail=message)
    if "skip/omit" in low or "skipped_optional" in low:
        return VoViolation("skip_omit_on_seated", detail=message)
    if "both seated and omitted" in low:
        return VoViolation("seated_and_omitted", detail=message)
    if "lacks skip/omit" in low:
        return VoViolation("omitted_without_flags", detail=message)
    if "missing wav" in low:
        return VoViolation("missing_wav", detail=message)
    return VoViolation("unknown", detail=message)


def reconcile_execution_contract(ctx: RunContext, *, reason: str = "") -> dict[str, Any]:
    """Sync vo_seats on mastering_plan from gap_report; persist execution_contract.json."""
    from interview_mux.air_script import build_vo_seats, load_air_script
    from interview_mux.mastering_plan_loader import load_plan_raw, write_plan

    changed: list[str] = []
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        plan = load_plan_raw(ctx)
        if isinstance(plan, dict):
            script = load_air_script(plan) or {}
            gap = (
                ctx.read_json("understanding/gap_report.json")
                if ctx.artifact_exists("understanding/gap_report.json")
                else None
            )
            new_seats = build_vo_seats(plan, gap if isinstance(gap, dict) else None)
            old_seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
            if new_seats != old_seats:
                script = dict(script)
                script["vo_seats"] = new_seats
                plan = dict(plan)
                plan["air_script"] = script
                write_plan(ctx, plan)
                changed.append("mastering/mastering_plan.json")

    snapshot = snapshot_execution_contract(ctx)
    snapshot["last_reconciled_at"] = _utc_now()
    snapshot["reconcile_reason"] = str(reason or "")
    snapshot["reconcile_changed"] = changed
    ctx.write_json(EXECUTION_CONTRACT_REL, snapshot, skip_handoff=True)
    return snapshot


def _tier_a_publish_orientation(ctx: RunContext) -> list[str]:
    from interview_mux.nugget_layup import PLAN_REL, publish_layup_plan_to_gap_report

    written: list[str] = []
    plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    publish_layup_plan_to_gap_report(ctx, plan if isinstance(plan, dict) else None)
    written.append("understanding/gap_report.json")
    if ctx.artifact_exists(PLAN_REL):
        written.append(PLAN_REL)
    reconcile_execution_contract(ctx, reason="tier_a_publish_orientation")
    return written


def _tier_b_gap_recompose(ctx: RunContext) -> list[str]:
    from interview_mux.refinement_passes import run_gap_framing_recompose

    run_gap_framing_recompose(ctx)
    reconcile_execution_contract(ctx, reason="tier_b_gap_recompose")
    written = ["understanding/gap_report.json"]
    if ctx.artifact_exists("understanding/gap_framing_recompose.json"):
        written.append("understanding/gap_framing_recompose.json")
    return written


def _tier_c_opening_omit_unseat(ctx: RunContext) -> list[str]:
    from interview_mux.recovery_controller import (
        playbook_opening_slot_conflict,
        playbook_stamp_air_script_omits,
    )

    written: list[str] = []
    written.extend(playbook_opening_slot_conflict(ctx))
    written.extend(playbook_stamp_air_script_omits(ctx))
    reconcile_execution_contract(ctx, reason="tier_c_opening_omit_unseat")
    return list(dict.fromkeys(written))


def _tier_d_logged_waive(ctx: RunContext, violation: VoViolation | None) -> list[str]:
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID, is_episode_orientation
    from interview_mux.vo_contract import mark_gap_line_not_on_air

    lid = (
        str(violation.line_id or "").strip()
        if violation and violation.line_id
        else ORIENTATION_LINE_ID
    )
    written: list[str] = []

    if ctx.artifact_exists("mastering/mastering_plan.json"):
        from interview_mux.air_script import load_air_script
        from interview_mux.mastering_plan_loader import load_plan_raw, write_plan

        plan = load_plan_raw(ctx)
        if isinstance(plan, dict):
            script = load_air_script(plan) or {}
            script = dict(script)
            seats = dict(script.get("vo_seats") or {})
            seated_ids = [
                str(x)
                for x in (seats.get("seated_line_ids") or [])
                if str(x) and str(x) != lid
            ]
            seats["seated_line_ids"] = seated_ids
            if str(seats.get("orientation_id") or "") == lid:
                seats["orientation_id"] = None
            script["vo_seats"] = seats
            beats = script.get("beats")
            if isinstance(beats, list) and lid:
                script["beats"] = [
                    b
                    for b in beats
                    if not isinstance(b, dict) or str(b.get("line_id") or "") != lid
                ]
            plan = dict(plan)
            plan["air_script"] = script
            write_plan(ctx, plan)
            written.append("mastering/mastering_plan.json")

    if not ctx.artifact_exists("understanding/gap_report.json"):
        return written
    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return written
    lines_out: list[dict[str, Any]] = []
    found = False
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        row_lid = str(row.get("line_id") or "").strip()
        if row_lid == lid or (not found and lid == ORIENTATION_LINE_ID and is_episode_orientation(row)):
            lines_out.append(
                mark_gap_line_not_on_air(
                    row,
                    reason_code="execution_contract_waive",
                    compensating_path="tier_d_logged_waive",
                )
            )
            found = True
            continue
        lines_out.append(dict(row))
    if not found and lid and violation and violation.kind == "missing_from_gap":
        # Do not mint a seated line into gap — unseat-only waive for missing_from_gap.
        pass
    elif not found and lid:
        lines_out.append(
            mark_gap_line_not_on_air(
                {"line_id": lid, "delivery": "synthesize"},
                reason_code="execution_contract_waive",
                compensating_path="tier_d_logged_waive",
            )
        )
    out = dict(gap)
    out["interviewer_lines"] = lines_out
    ctx.write_json("understanding/gap_report.json", out)
    written.append("understanding/gap_report.json")
    reconcile_execution_contract(ctx, reason="tier_d_logged_waive")
    try:
        from interview_mux.recovery_controller import append_remediation_log

        append_remediation_log(
            ctx,
            action="vo_contract_tier_d_waive",
            detail=lid or "orientation",
        )
    except Exception:
        pass
    return written


def _write_vo_repair_plan(
    ctx: RunContext,
    *,
    tier: str,
    violations: list[str],
    consumer_stage: str = "",
) -> None:
    plan = {
        "version": 1,
        "active": True,
        "error_class": "vo_contract_repair",
        "started_at": _utc_now(),
        "current_tier": tier,
        "violations": violations[:12],
        "consumer_stage": consumer_stage,
        "invalidate_set": [
            "vo_line_adjudicate",
            "vo_synthesize",
            "nugget_layup_compose",
        ],
        "cascade_error_classes": [
            "vo_contract_repair",
            "vo_seated_coverage",
            "opening_slot_conflict",
            "air_script_omit_sync",
        ],
    }
    ctx.write_json(VO_CONTRACT_REPAIR_PLAN_REL, plan, skip_handoff=True)


def mark_vo_repair_plan_completed(ctx: RunContext) -> None:
    if not ctx.artifact_exists(VO_CONTRACT_REPAIR_PLAN_REL):
        return
    try:
        plan = ctx.read_json(VO_CONTRACT_REPAIR_PLAN_REL)
        if isinstance(plan, dict):
            plan = dict(plan)
            plan["active"] = False
            plan["completed"] = True
            plan["completed_at"] = _utc_now()
            ctx.write_json(VO_CONTRACT_REPAIR_PLAN_REL, plan, skip_handoff=True)
    except Exception:
        pass


def read_active_vo_repair_plan(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(VO_CONTRACT_REPAIR_PLAN_REL):
        return None
    try:
        doc = ctx.read_json(VO_CONTRACT_REPAIR_PLAN_REL)
    except Exception:
        return None
    if not isinstance(doc, dict) or doc.get("completed") or not doc.get("active"):
        return None
    return doc


def failure_in_active_policy_cascade(
    ctx: RunContext,
    *,
    failed_stage: str,
    producer: str,
) -> bool:
    """True when failure is expected during active VO contract / remediation plan."""
    plan = read_active_vo_repair_plan(ctx)
    if plan:
        root = str(plan.get("error_class") or "")
        if producer and producer == root:
            return True
        cascade = {str(c) for c in (plan.get("cascade_error_classes") or [])}
        if producer in cascade:
            return True
        invalidate = {str(s) for s in (plan.get("invalidate_set") or [])}
        if failed_stage in invalidate:
            return True
    if ctx.artifact_exists("operator/vo_coverage_repair_plan.json"):
        try:
            vc = ctx.read_json("operator/vo_coverage_repair_plan.json")
            if isinstance(vc, dict) and vc.get("active"):
                if producer in {"vo_seated_coverage", "edl_vo_coverage_repair", "edl_vo_coverage_ladder"}:
                    return True
                if failed_stage in {
                    "vo_synthesize",
                    "edl_narrative_audit",
                    "edl",
                    "assembly_preview",
                }:
                    return True
        except Exception:
            pass
    try:
        from interview_mux.remediation_framework import failure_in_active_remediation

        return failure_in_active_remediation(ctx, failed_stage=failed_stage, producer=producer)
    except Exception:
        return False


def run_vo_contract_ladder(
    ctx: RunContext,
    *,
    consumer_stage: str = "",
    start_tier: str | None = None,
) -> LadderResult:
    """Run tier A→D until validate_vo_contract passes or tiers exhausted."""
    from interview_mux.vo_contract import validate_vo_contract

    if not ladder_enabled():
        violations = validate_vo_contract(ctx)
        return LadderResult(
            tier="disabled",
            recovered=False,
            contract_ok=not violations,
            violations=violations,
            detail="ladder_disabled",
        )

    violations = validate_vo_contract(ctx)
    if not violations:
        mark_vo_repair_plan_completed(ctx)
        return LadderResult(
            tier="none",
            recovered=True,
            contract_ok=True,
            detail="already_ok",
        )

    _write_vo_repair_plan(ctx, tier=start_tier or LADDER_TIERS[0], violations=violations, consumer_stage=consumer_stage)

    tier_index = 0
    if start_tier:
        try:
            tier_index = LADDER_TIERS.index(start_tier)
        except ValueError:
            tier_index = 0

    primary_violation = classify_vo_violation(violations[0])
    last_tier = ""
    artifacts: list[str] = []

    for tier in LADDER_TIERS[tier_index:]:
        last_tier = tier
        try:
            if tier == "tier_a_publish_orientation":
                artifacts = _tier_a_publish_orientation(ctx)
            elif tier == "tier_b_gap_recompose":
                artifacts = _tier_b_gap_recompose(ctx)
            elif tier == "tier_c_opening_omit_unseat":
                artifacts = _tier_c_opening_omit_unseat(ctx)
            elif tier == "tier_d_logged_waive":
                artifacts = _tier_d_logged_waive(ctx, primary_violation)
        except Exception as exc:
            ctx.log(
                f"vo_contract ladder {tier} failed: {exc}",
                level="warning",
                stage=consumer_stage or "execution_contract",
                detail={"tier": tier, "error": str(exc)[:240]},
            )

        violations = validate_vo_contract(ctx)
        if not violations:
            mark_vo_repair_plan_completed(ctx)
            _log_ladder_action(ctx, tier=tier, status="recovered", consumer_stage=consumer_stage)
            return LadderResult(
                tier=tier,
                recovered=True,
                contract_ok=True,
                artifacts=list(dict.fromkeys(artifacts)),
                resume_stage=_resume_after_ladder(consumer_stage),
            )

    mark_vo_repair_plan_completed(ctx)
    _log_ladder_action(
        ctx,
        tier=last_tier or "tier_d_logged_waive",
        status="escalate",
        consumer_stage=consumer_stage,
        detail=violations[0] if violations else "",
    )
    return LadderResult(
        tier=last_tier or "tier_d_logged_waive",
        recovered=False,
        contract_ok=False,
        violations=violations,
        artifacts=list(dict.fromkeys(artifacts)),
        detail=violations[0] if violations else "tiers_exhausted",
        resume_stage=_resume_after_ladder(consumer_stage),
    )


def _resume_after_ladder(consumer_stage: str) -> str:
    stage = str(consumer_stage or "").strip()
    if stage in {"vo_synthesize", "vo_line_adjudicate"}:
        return stage
    if stage in {"nugget_layup_compose", "air_script_seams"}:
        return "nugget_layup_compose"
    return stage or "vo_line_adjudicate"


def _log_ladder_action(
    ctx: RunContext,
    *,
    tier: str,
    status: str,
    consumer_stage: str,
    detail: str = "",
) -> None:
    try:
        from interview_mux.recovery_controller import _append_action

        _append_action(
            ctx,
            {
                "ts": _utc_now(),
                "signature": f"vo_contract_ladder:{consumer_stage or 'unknown'}",
                "playbook_id": "vo_contract_ladder",
                "status": status,
                "detail": detail or tier,
                "tier": tier,
            },
        )
    except Exception:
        pass


VO_COVERAGE_LADDER_TIERS: tuple[str, ...] = (
    "tier_a_backfill",
    "tier_b_vo_seated",
    "tier_c_adjudicate_heal",
    "tier_d_operator",
)


@dataclass
class VoCoverageLadderResult:
    tier: str
    recovered: bool
    detail: str = ""
    artifacts: list[str] = field(default_factory=list)
    resume_stage: str = ""


def _vo_coverage_clear(ctx: RunContext, *, reason: str) -> list[str]:
    from interview_mux.execution_invalidation_profiles import apply_bounded_invalidation

    result = apply_bounded_invalidation(ctx, "vo_coverage_heal", reason=reason)
    return list(result.get("cleared") or [])


def _tier_a_vo_coverage_backfill(ctx: RunContext) -> list[str]:
    from interview_mux.vo_synthesis_audit import backfill_missing_synthesis_entries

    written: list[str] = []
    backfilled = backfill_missing_synthesis_entries(ctx)
    if backfilled:
        written.append("mastering/vo_synthesis_report.json")
    return written


def _tier_b_vo_seated_coverage(ctx: RunContext) -> list[str]:
    from interview_mux.recovery_controller import playbook_vo_seated_coverage

    artifacts = playbook_vo_seated_coverage(ctx)
    cleared = _vo_coverage_clear(ctx, reason="tier_b_vo_seated")
    return list(dict.fromkeys(list(artifacts) + cleared))


def _tier_c_vo_adjudicate_heal(ctx: RunContext) -> list[str]:
    from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

    stale = compact_vo_coverage_stale_or_missing(ctx)
    if not stale:
        return []
    (ctx.run_dir / ".stage_done" / "vo_line_adjudicate").unlink(missing_ok=True)
    cleared = _vo_coverage_clear(ctx, reason="tier_c_adjudicate_heal")
    return [".stage_done/vo_line_adjudicate"] + cleared


def _hosted_topology_requires_orientation(ctx: RunContext) -> bool:
    try:
        if not ctx.artifact_exists("understanding/source_topology.json"):
            return False
        topo = ctx.read_json("understanding/source_topology.json")
        if not isinstance(topo, dict):
            return False
        speakers = topo.get("speakers") or topo.get("speaker_count")
        if isinstance(speakers, list) and len(speakers) >= 2:
            return True
        if isinstance(speakers, int) and speakers >= 2:
            return True
    except Exception:
        pass
    return False


def run_edl_vo_coverage_ladder(
    ctx: RunContext,
    *,
    consumer_stage: str = "edl_narrative_audit",
) -> VoCoverageLadderResult:
    """Tiered ladder for VO coverage not rendered — no edl_narrative_remutate."""
    from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

    if not ladder_enabled():
        missing = compact_vo_coverage_stale_or_missing(ctx)
        return VoCoverageLadderResult(
            tier="disabled",
            recovered=not missing,
            detail="ladder_disabled",
        )

    missing = compact_vo_coverage_stale_or_missing(ctx)
    if not missing:
        mark_remediation_plan_completed_vo_coverage(ctx)
        return VoCoverageLadderResult(
            tier="none",
            recovered=True,
            detail="already_ok",
            resume_stage=consumer_stage or "edl_narrative_audit",
        )

    write_remediation_plan_vo_coverage(ctx, consumer_stage=consumer_stage, missing=missing)

    last_tier = ""
    artifacts: list[str] = []
    for tier in VO_COVERAGE_LADDER_TIERS:
        last_tier = tier
        try:
            if tier == "tier_a_backfill":
                artifacts = _tier_a_vo_coverage_backfill(ctx)
            elif tier == "tier_b_vo_seated":
                artifacts = _tier_b_vo_seated_coverage(ctx)
            elif tier == "tier_c_adjudicate_heal":
                artifacts = _tier_c_adjudicate_heal(ctx)
            elif tier == "tier_d_operator":
                if _hosted_topology_requires_orientation(ctx):
                    mark_remediation_plan_completed_vo_coverage(ctx)
                    return VoCoverageLadderResult(
                        tier=tier,
                        recovered=False,
                        detail=f"needs_operator: {missing[:6]}",
                        resume_stage=consumer_stage,
                    )
        except Exception as exc:
            ctx.log(
                f"vo_coverage ladder {tier} failed: {exc}",
                level="warning",
                stage=consumer_stage,
                detail={"tier": tier, "error": str(exc)[:240]},
            )

        missing = compact_vo_coverage_stale_or_missing(ctx)
        if not missing:
            mark_remediation_plan_completed_vo_coverage(ctx)
            _log_vo_coverage_ladder(ctx, tier=tier, status="recovered", consumer_stage=consumer_stage)
            resume = "edl"
            if tier in {"tier_b_vo_seated", "tier_c_adjudicate_heal"}:
                resume = "vo_synthesize"
            return VoCoverageLadderResult(
                tier=tier,
                recovered=True,
                artifacts=list(dict.fromkeys(artifacts)),
                resume_stage=resume,
            )

    mark_remediation_plan_completed_vo_coverage(ctx)
    _log_vo_coverage_ladder(
        ctx,
        tier=last_tier,
        status="escalate",
        consumer_stage=consumer_stage,
        detail=str(missing[:4]),
    )
    return VoCoverageLadderResult(
        tier=last_tier or "tier_d_operator",
        recovered=False,
        detail=f"still_missing: {missing[:6]}",
        artifacts=list(dict.fromkeys(artifacts)),
        resume_stage=consumer_stage,
    )


def write_remediation_plan_vo_coverage(
    ctx: RunContext,
    *,
    consumer_stage: str,
    missing: list[str],
) -> None:
    from interview_mux.remediation_framework import RemediationPlan, write_remediation_plan
    from interview_mux.execution_invalidation_profiles import VO_COVERAGE_HEAL_STAGES

    write_remediation_plan(
        ctx,
        RemediationPlan(
            error_class="vo_seated_coverage",
            consumer_stage=consumer_stage,
            allowed_rerun_stages=list(VO_COVERAGE_HEAL_STAGES),
            cascade_error_classes=["vo_seated_coverage", "edl_vo_coverage_repair"],
        ),
    )
    try:
        ctx.write_json(
            "operator/vo_coverage_repair_plan.json",
            {
                "version": 1,
                "active": True,
                "missing_line_ids": missing[:24],
                "consumer_stage": consumer_stage,
                "started_at": _utc_now(),
            },
            skip_handoff=True,
        )
    except Exception:
        pass


def mark_remediation_plan_completed_vo_coverage(ctx: RunContext) -> None:
    from interview_mux.remediation_framework import mark_remediation_plan_completed

    mark_remediation_plan_completed(ctx)
    if ctx.artifact_exists("operator/vo_coverage_repair_plan.json"):
        try:
            doc = ctx.read_json("operator/vo_coverage_repair_plan.json")
            if isinstance(doc, dict):
                doc = dict(doc)
                doc["active"] = False
                doc["completed_at"] = _utc_now()
                ctx.write_json("operator/vo_coverage_repair_plan.json", doc, skip_handoff=True)
        except Exception:
            pass


def _log_vo_coverage_ladder(
    ctx: RunContext,
    *,
    tier: str,
    status: str,
    consumer_stage: str,
    detail: str = "",
) -> None:
    try:
        from interview_mux.recovery_controller import _append_action

        _append_action(
            ctx,
            {
                "ts": _utc_now(),
                "signature": f"vo_coverage_ladder:{consumer_stage}",
                "playbook_id": "edl_vo_coverage_ladder",
                "status": status,
                "detail": detail or tier,
                "tier": tier,
            },
        )
    except Exception:
        pass
