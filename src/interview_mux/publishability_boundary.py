"""Publishability boundary — Tier 0/1 invariants at producer checkpoints."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.run_context import RunContext

CheckpointName = Literal[
    "post_cta_prune",
    "post_edl",
    "post_junction",
    "pre_mix",
    "pre_finalize",
]

PUBLISHABILITY_REPORT_REL = "operator/publishability_report.json"
REPAIR_PLAN_REL = "operator/publishability_repair_plan.json"

_MIN_SPEECH_MS = 400
_PENDING_WRITE_STAGES = frozenset({"edl", "junction_snip_qa", "mix", "master_finalize"})


@dataclass
class PublishabilityViolation:
    error_class: str
    code: str
    detail: str
    segment_id: str = ""
    line_id: str = ""


@dataclass
class PublishabilityReport:
    checkpoint: str
    ok: bool
    violations: list[PublishabilityViolation] = field(default_factory=list)
    selection_hash: str = ""
    edl_hash: str = ""
    producer_stage: str = ""


class PublishabilityBlocked(Exception):
    """Raised when a checkpoint cannot commit downstream work."""

    def __init__(
        self,
        report: PublishabilityReport,
        *,
        error_class: str,
        message: str = "",
    ) -> None:
        self.report = report
        self.error_class = error_class
        super().__init__(message or f"publishability blocked: {error_class}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def publishability_enforce(ctx: RunContext) -> bool:
    """Block on violation when homunculus or resilience.publishability_enforce."""
    try:
        from interview_mux.homunculus.runtime import is_homunculus_run

        if is_homunculus_run(ctx):
            return True
    except Exception:
        pass
    try:
        from interview_mux.config import merged_config

        root = merged_config()
        resilience = root.get("resilience") if isinstance(root, dict) else {}
        if isinstance(resilience, dict) and resilience.get("publishability_enforce"):
            return True
    except Exception:
        pass
    return False


def _selection_hash(ctx: RunContext) -> str:
    if not ctx.artifact_exists("master/selection.json"):
        return ""
    try:
        from interview_mux.order_hash import ordered_segment_ids_hash

        sel = ctx.read_json("master/selection.json")
        ids = [
            str(s)
            for s in ((sel or {}).get("ordered_segment_ids") or [])
            if s
        ]
        return ordered_segment_ids_hash(ids) if ids else ""
    except Exception:
        return ""


def _edl_hash(ctx: RunContext) -> str:
    if not ctx.artifact_exists("master/edl.json"):
        return ""
    try:
        edl = ctx.read_json("master/edl.json")
        if isinstance(edl, dict):
            return str(edl.get("order_content_hash") or "")
    except Exception:
        pass
    return ""


def _load_selection(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("master/selection.json"):
        return None
    doc = ctx.read_json("master/selection.json")
    return dict(doc) if isinstance(doc, dict) else None


def _load_edl(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("master/edl.json"):
        return None
    doc = ctx.read_json("master/edl.json")
    return dict(doc) if isinstance(doc, dict) else None


def _load_gap_report(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return None
    doc = ctx.read_json("understanding/gap_report.json")
    return dict(doc) if isinstance(doc, dict) else None


def _gap_report_aligned_with_edl(
    ctx: RunContext,
    gap_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Apply the same air_script VO filter ``run_edl`` uses before building clips."""
    if not isinstance(gap_report, dict):
        return gap_report
    try:
        from interview_mux.air_script import filter_gap_lines_for_air_script
        from interview_mux.mastering_plan_loader import load_plan_raw

        filtered = filter_gap_lines_for_air_script(gap_report, load_plan_raw(ctx))
        return filtered if isinstance(filtered, dict) else gap_report
    except Exception:
        return gap_report


def _check_zero_keeps(ctx: RunContext, edl: dict[str, Any] | None) -> list[PublishabilityViolation]:
    if not isinstance(edl, dict):
        return []
    out: list[PublishabilityViolation] = []
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or str(clip.get("type") or "") != "speech":
            continue
        sid = str(clip.get("segment_id") or "")
        try:
            dur = int(clip.get("duration_ms") or 0)
            ss = int(clip.get("source_start_ms") or 0)
            se = int(clip.get("source_end_ms") or ss)
        except (TypeError, ValueError):
            dur = 0
            ss = se = 0
        notes = clip.get("notes") or []
        note_blob = " ".join(str(n) for n in notes) if isinstance(notes, list) else str(notes)
        zeroed = (
            dur < _MIN_SPEECH_MS
            or se <= ss
            or "zeroed_inside_never_touch" in note_blob
        )
        if zeroed:
            out.append(
                PublishabilityViolation(
                    error_class="never_touch_zeroed_keep",
                    code="zero_duration_speech",
                    detail=f"speech clip {sid} duration_ms={dur}",
                    segment_id=sid,
                )
            )
    return out


def _check_phantom_vo(
    ctx: RunContext,
    edl: dict[str, Any] | None,
    gap_report: dict[str, Any] | None,
) -> list[PublishabilityViolation]:
    if not isinstance(edl, dict):
        return []
    edl_line_ids = {
        str(c.get("line_id") or "")
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and c.get("type") == "vo_pickup" and c.get("line_id")
    }
    out: list[PublishabilityViolation] = []
    for line in (gap_report or {}).get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        delivery = str(line.get("delivery") or "").lower()
        if delivery not in {"record", "synthesize"}:
            continue
        if line.get("skipped_optional") or line.get("air_script_omit"):
            continue
        lid = str(line.get("line_id") or "")
        if not lid or lid in edl_line_ids:
            continue
        try:
            from interview_mux.stages.assembly import resolve_vo_pickup_path

            wav = resolve_vo_pickup_path(ctx, line)
        except Exception:
            wav = None
        if wav is not None and wav.is_file():
            out.append(
                PublishabilityViolation(
                    error_class="vo_audibility_drift",
                    code="phantom_vo",
                    detail=f"WAV exists without EDL vo_pickup for {lid}",
                    line_id=lid,
                    segment_id=str(line.get("targets_segment_id") or ""),
                )
            )
    return out


def _check_unseated_required_vo(
    ctx: RunContext,
    edl: dict[str, Any] | None,
    gap_report: dict[str, Any] | None,
) -> list[PublishabilityViolation]:
    """Required synthesize lines must appear on EDL or have omit-ledger compensation."""
    if not isinstance(gap_report, dict):
        return []
    edl_line_ids = {
        str(c.get("line_id") or "")
        for c in ((edl or {}).get("clips") or [])
        if isinstance(c, dict) and c.get("type") == "vo_pickup" and c.get("line_id")
    }
    out: list[PublishabilityViolation] = []
    try:
        from interview_mux.air_script import gap_line_air_eligible
        from interview_mux.omit_ledger import active_entries, line_is_omitted

        ledger = ctx.read_json("master/omit_ledger.json") if ctx.artifact_exists(
            "master/omit_ledger.json"
        ) else {}
    except Exception:
        gap_line_air_eligible = None  # type: ignore[assignment,misc]
        active_entries = None  # type: ignore[assignment,misc]
        line_is_omitted = None  # type: ignore[assignment,misc]
        ledger = {}
    compensated: set[str] = set()
    if active_entries is not None and isinstance(ledger, dict):
        try:
            for row in active_entries(ledger):
                if isinstance(row, dict) and row.get("line_id"):
                    compensated.add(str(row["line_id"]))
        except Exception:
            pass
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if gap_line_air_eligible is not None and not gap_line_air_eligible(line):
            continue
        if str(line.get("delivery") or "").lower() != "synthesize":
            continue
        if not line.get("required", True):
            continue
        lid = str(line.get("line_id") or "")
        if not lid or lid in edl_line_ids or lid in compensated:
            continue
        out.append(
            PublishabilityViolation(
                error_class="omit_collateral_vo_strip",
                code="unseated_required_vo",
                detail=f"required synthesize line not seated on EDL: {lid}",
                line_id=lid,
            )
        )
    return out


def _check_order_drift(
    selection: dict[str, Any] | None,
    edl: dict[str, Any] | None,
) -> list[PublishabilityViolation]:
    if not isinstance(selection, dict) or not isinstance(edl, dict):
        return []
    try:
        from interview_mux.order_hash import order_drift_heal_action

        action = order_drift_heal_action(selection, edl)
    except Exception:
        return []
    if action != "rebuild":
        return []
    return [
        PublishabilityViolation(
            error_class="selection_edl_order_drift",
            code="speech_order_drift",
            detail="speech clip order diverges from ordered_segment_ids",
        )
    ]


def _check_opening_orientation(
    gap_report: dict[str, Any] | None,
    edl: dict[str, Any] | None,
) -> list[PublishabilityViolation]:
    try:
        from interview_mux.opening_orientation import validate_opening_orientation

        errors = validate_opening_orientation(gap_report=gap_report, edl=edl)
    except Exception:
        return []
    if not errors:
        return []
    audible = any("opening_orientation_audible_count" in e for e in errors)
    error_class = (
        "opening_orientation_inaudible"
        if audible
        else "opening_orientation_inaudible"
    )
    return [
        PublishabilityViolation(
            error_class=error_class,
            code="opening_orientation_contract",
            detail="; ".join(errors[:4]),
        )
    ]


def _check_pending_writes(ctx: RunContext) -> list[PublishabilityViolation]:
    try:
        from interview_mux.write_staging import stages_with_pending_writes

        pending = [
            s for s in stages_with_pending_writes(ctx) if s in _PENDING_WRITE_STAGES
        ]
    except Exception:
        return []
    if not pending:
        return []
    return [
        PublishabilityViolation(
            error_class="pending_write_barrier",
            code="staging_ghost",
            detail="pending writes: " + ", ".join(sorted(pending)),
        )
    ]


def _check_critical_junction(ctx: RunContext) -> list[PublishabilityViolation]:
    out: list[PublishabilityViolation] = []
    qa_rel = "master/junction_snip_qa.json"
    if ctx.artifact_exists(qa_rel):
        try:
            report = ctx.read_json(qa_rel)
            if isinstance(report, dict):
                critical = int(report.get("critical_residuals") or 0)
                blocking = list(report.get("blocking_reasons") or [])
                if critical > 0 or any(
                    "critical" in str(b).lower() for b in blocking
                ):
                    out.append(
                        PublishabilityViolation(
                            error_class="incomplete_cut_unresolved",
                            code="critical_junction_residual",
                            detail=f"critical_residuals={critical} blocking={blocking[:3]}",
                        )
                    )
        except Exception:
            pass
    autopsy_rel = "mastering/seam_autopsy.json"
    if not out and ctx.artifact_exists(autopsy_rel):
        try:
            autopsy = ctx.read_json(autopsy_rel)
            if isinstance(autopsy, dict):
                reasons = list(autopsy.get("blocking_reasons") or [])
                if reasons:
                    out.append(
                        PublishabilityViolation(
                            error_class="incomplete_cut_unresolved",
                            code="seam_autopsy_blocking",
                            detail="; ".join(str(r) for r in reasons[:4]),
                        )
                    )
        except Exception:
            pass
    return out


def _check_pmq_envelope(ctx: RunContext) -> list[PublishabilityViolation]:
    rel = "master/post_master_quality.json"
    if not ctx.artifact_exists(rel):
        return [
            PublishabilityViolation(
                error_class="post_master_quality_missing",
                code="pmq_missing",
                detail="post_master_quality.json missing at finalize",
            )
        ]
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return [
            PublishabilityViolation(
                error_class="post_master_quality_missing",
                code="pmq_unreadable",
                detail="post_master_quality.json unreadable",
            )
        ]
    if not isinstance(doc, dict):
        return [
            PublishabilityViolation(
                error_class="post_master_quality_missing",
                code="pmq_invalid",
                detail="post_master_quality.json not a dict",
            )
        ]
    if not doc.get("publish_allowed"):
        failed = list(doc.get("failed_checks") or [])
        detail = "publish_allowed=false"
        if failed:
            detail += " failed=" + ",".join(str(x) for x in failed[:6])
        return [
            PublishabilityViolation(
                error_class="pmq_incomplete_ship_walk",
                code="pmq_not_publishable",
                detail=detail,
            )
        ]
    if doc.get("status") == "advisory_fail":
        from interview_mux.aspirational_quality import is_aspirational_enabled

        if is_aspirational_enabled(ctx):
            failed = list(doc.get("rubric_failed_checks") or doc.get("failed_checks") or [])
            if failed:
                return [
                    PublishabilityViolation(
                        error_class="quality_advisory",
                        code="pmq_advisory",
                        detail="advisory_fail: " + ",".join(str(x) for x in failed[:6]),
                    )
                ]
    return []


_CHECKPOINT_CHECKS: dict[str, tuple[str, ...]] = {
    "post_cta_prune": ("zero_keeps",),
    "post_edl": (
        "zero_keeps",
        "phantom_vo",
        "order_drift",
        "opening_orientation",
    ),
    "post_junction": (
        "zero_keeps",
        "order_drift",
        "critical_junction",
    ),
    "pre_mix": (
        "zero_keeps",
        "phantom_vo",
        "unseated_required_vo",
        "order_drift",
        "opening_orientation",
        "pending_writes",
        "critical_junction",
    ),
    "pre_finalize": ("pmq_envelope",),
}


def validate_publishability(
    ctx: RunContext,
    *,
    checkpoint: str,
) -> PublishabilityReport:
    """Run checkpoint-scoped publishability checks."""
    checks = _CHECKPOINT_CHECKS.get(str(checkpoint or ""), ())
    selection = _load_selection(ctx)
    edl = _load_edl(ctx)
    gap_report = _load_gap_report(ctx)
    edl_gap_report = _gap_report_aligned_with_edl(ctx, gap_report)
    violations: list[PublishabilityViolation] = []

    for name in checks:
        if name == "zero_keeps":
            violations.extend(_check_zero_keeps(ctx, edl))
        elif name == "phantom_vo":
            violations.extend(_check_phantom_vo(ctx, edl, edl_gap_report))
        elif name == "unseated_required_vo":
            violations.extend(_check_unseated_required_vo(ctx, edl, edl_gap_report))
        elif name == "order_drift":
            violations.extend(_check_order_drift(selection, edl))
        elif name == "opening_orientation":
            violations.extend(_check_opening_orientation(gap_report, edl))
        elif name == "pending_writes":
            violations.extend(_check_pending_writes(ctx))
        elif name == "critical_junction":
            violations.extend(_check_critical_junction(ctx))
        elif name == "pmq_envelope":
            violations.extend(_check_pmq_envelope(ctx))

    producer = ""
    if violations:
        producer = violation_playbook(violations[0]).resume_stage

    return PublishabilityReport(
        checkpoint=str(checkpoint or ""),
        ok=not violations,
        violations=violations,
        selection_hash=_selection_hash(ctx),
        edl_hash=_edl_hash(ctx),
        producer_stage=producer,
    )


def violation_playbook(v: PublishabilityViolation):
    """Map a violation to registry playbook spec."""
    from interview_mux.heal_routing import PLAYBOOK_REGISTRY, PlaybookSpec

    spec = PLAYBOOK_REGISTRY.get(v.error_class)
    if spec is not None:
        return spec
    return PlaybookSpec(resume_stage="edl", action="rebuild_edl")


def write_publishability_report(ctx: RunContext, report: PublishabilityReport) -> None:
    primary = report.violations[0] if report.violations else None
    playbook = violation_playbook(primary) if primary else None
    doc: dict[str, Any] = {
        "version": 1,
        "updated_at": _utc_now(),
        "checkpoint": report.checkpoint,
        "ok": report.ok,
        "selection_hash": report.selection_hash,
        "edl_hash": report.edl_hash,
        "producer_stage": report.producer_stage,
        "violations": [
            {
                "error_class": v.error_class,
                "code": v.code,
                "detail": v.detail,
                "segment_id": v.segment_id,
                "line_id": v.line_id,
            }
            for v in report.violations
        ],
    }
    if playbook is not None and primary is not None:
        doc["playbook"] = {
            "error_class": primary.error_class,
            "resume_stage": playbook.resume_stage,
            "action": playbook.action,
        }
    ctx.write_json(PUBLISHABILITY_REPORT_REL, doc, skip_handoff=True)


def _snapshot_edl_ledger(ctx: RunContext) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    edl = _load_edl(ctx)
    ledger: dict[str, Any] | None = None
    if ctx.artifact_exists("master/assembly_ledger.json"):
        try:
            doc = ctx.read_json("master/assembly_ledger.json")
            ledger = dict(doc) if isinstance(doc, dict) else None
        except Exception:
            ledger = None
    return edl, ledger


def _reemit_edl_ledger(
    ctx: RunContext,
    edl: dict[str, Any] | None,
    ledger: dict[str, Any] | None,
) -> None:
    """Restore just-committed EDL/ledger after a hard invalidate that archived them."""
    from interview_mux.file_store import write_json as fs_write_json

    if isinstance(edl, dict) and edl:
        dest = ctx.final_path("master", "edl.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Bypass schema re-validate — bytes were already committed this turn.
        fs_write_json(dest, edl)
    if isinstance(ledger, dict) and ledger:
        dest = ctx.final_path("master", "assembly_ledger.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        fs_write_json(dest, ledger)
    elif isinstance(edl, dict) and edl:
        try:
            from interview_mux.assembly_ledger import write_assembly_ledger

            write_assembly_ledger(ctx, edl=edl)
        except Exception:
            pass


def write_publishability_repair_plan(
    ctx: RunContext,
    report: PublishabilityReport,
    *,
    playbook,
    soft: bool = False,
) -> dict[str, Any]:
    """Persist cascade repair plan with invalidate_set for downstream failures.

    Soft/advisory: write the plan only — never ``clear_from(edl)`` / archive live EDL.
    Hard: may invalidate, but re-emits EDL+ledger in the same call so finalize keeps a ledger.
    """
    from interview_mux.artifact_dependency_graph import transitive_invalidate

    primary = report.violations[0]
    resume_stage = playbook.resume_stage
    invalidate_set = transitive_invalidate(resume_stage)
    plan_id_src = "|".join(
        [
            report.checkpoint,
            primary.error_class,
            report.selection_hash,
            report.edl_hash,
        ]
    )
    repair_plan_id = hashlib.sha256(plan_id_src.encode("utf-8")).hexdigest()[:16]
    plan: dict[str, Any] = {
        "version": 1,
        "repair_plan_id": repair_plan_id,
        "error_class": primary.error_class,
        "from_stage": resume_stage,
        "checkpoint": report.checkpoint,
        "invalidate_set": invalidate_set,
        "cascade_error_classes": sorted({v.error_class for v in report.violations}),
        "completed": False,
        "soft": bool(soft),
        "created_at": _utc_now(),
    }
    ctx.write_json(REPAIR_PLAN_REL, plan, skip_handoff=True)
    if soft:
        # Soft/advisory: plan only. Archive downstream of mix at most (never live EDL).
        if resume_stage in {"mix", "junction_snip_qa", "master_finalize"}:
            try:
                from interview_mux.homunculus.agenda import invalidate_downstream

                invalidate_downstream(ctx, "mix")
                plan["cleared_from"] = "mix"
                plan["soft_clear_mode"] = "downstream_of_mix"
            except Exception:
                pass
        else:
            plan["cleared_from"] = None
            plan["soft_clear_mode"] = "plan_only"
        ctx.write_json(REPAIR_PLAN_REL, plan, skip_handoff=True)
        return plan

    edl_snap, ledger_snap = _snapshot_edl_ledger(ctx)
    try:
        from interview_mux.homunculus.agenda import invalidate_downstream

        invalidate_downstream(ctx, resume_stage)
        plan["cleared_from"] = resume_stage
    except Exception:
        try:
            from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER

            ctx.clear_from(resume_stage, list(ANALYSIS_ORDER) + list(DELIVERY_ORDER))
            plan["cleared_from"] = resume_stage
        except Exception:
            pass
    # Hard invalidate must not leave finalize without the just-committed EDL/ledger.
    if resume_stage in {"edl", "mix", "junction_snip_qa"} or report.checkpoint in {
        "post_edl",
        "post_junction",
        "pre_mix",
    }:
        _reemit_edl_ledger(ctx, edl_snap, ledger_snap)
        plan["edl_ledger_reemitted"] = True
    ctx.write_json(REPAIR_PLAN_REL, plan, skip_handoff=True)
    return plan


def commit_or_block(
    ctx: RunContext,
    report: PublishabilityReport,
    *,
    enforce: bool | None = None,
) -> None:
    """Raise PublishabilityBlocked when violations exist and enforcement is on."""
    write_publishability_report(ctx, report)
    if report.ok:
        return
    primary = report.violations[0]
    playbook = violation_playbook(primary)
    should_block = publishability_enforce(ctx) if enforce is None else bool(enforce)
    advisory_only = (
        report.violations
        and all(v.error_class == "quality_advisory" for v in report.violations)
    )
    soft = advisory_only or not should_block
    write_publishability_repair_plan(ctx, report, playbook=playbook, soft=soft)
    if advisory_only:
        try:
            from interview_mux.aspirational_quality import is_aspirational_enabled

            if is_aspirational_enabled(ctx):
                ctx.log(
                    f"publishability {report.checkpoint}: quality advisory only "
                    f"({len(report.violations)}) — not blocking",
                    level="warning",
                    stage=playbook.resume_stage,
                )
                return
        except Exception:
            pass
    if not should_block:
        try:
            ctx.log(
                f"publishability {report.checkpoint}: {len(report.violations)} violation(s) "
                f"(fail-open error_class={primary.error_class})",
                level="warning",
                stage=playbook.resume_stage,
            )
        except Exception:
            pass
        return
    raise PublishabilityBlocked(
        report,
        error_class=primary.error_class,
        message=(
            f"publishability blocked at {report.checkpoint}: "
            f"{primary.error_class} — {primary.detail}"
        ),
    )


def checkpoint_publishability(
    ctx: RunContext,
    *,
    checkpoint: str,
    enforce: bool | None = None,
) -> PublishabilityReport:
    """Validate, persist report, and optionally block."""
    report = validate_publishability(ctx, checkpoint=checkpoint)
    commit_or_block(ctx, report, enforce=enforce)
    return report


def read_active_repair_plan(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(REPAIR_PLAN_REL):
        return None
    try:
        doc = ctx.read_json(REPAIR_PLAN_REL)
    except Exception:
        return None
    return doc if isinstance(doc, dict) and not doc.get("completed") else None


def failure_in_active_repair_cascade(
    ctx: RunContext,
    *,
    failed_stage: str,
    producer: str,
) -> bool:
    """True when failure is expected downstream of an active publishability repair plan."""
    plan = read_active_repair_plan(ctx)
    if not plan:
        return False
    root_class = str(plan.get("error_class") or "")
    if producer and producer == root_class:
        return True
    cascade = {str(c) for c in (plan.get("cascade_error_classes") or [])}
    if producer in cascade:
        return True
    invalidate_set = {str(s) for s in (plan.get("invalidate_set") or [])}
    stage = str(failed_stage or "").strip()
    if stage and stage in invalidate_set:
        return True
    return False


def mark_repair_plan_completed(ctx: RunContext) -> None:
    plan = read_active_repair_plan(ctx)
    if not plan:
        return
    plan = dict(plan)
    plan["completed"] = True
    plan["completed_at"] = _utc_now()
    ctx.write_json(REPAIR_PLAN_REL, plan, skip_handoff=True)
