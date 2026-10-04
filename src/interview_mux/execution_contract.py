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

# Plan-mutating tiers write mastering_plan under air_contract_sanitize ownership.
# Analysis-era consumers (esp. gap_framing_compose) must not run them — live
# AuthorityDenied on mastering_plan (exec_13167/13168/13170/13174).
_PLAN_MUTATING_LADDER_TIERS: frozenset[str] = frozenset(
    {
        "tier_c_opening_omit_unseat",
        "tier_d_logged_waive",
    }
)


def _consumer_is_analysis_era(consumer_stage: str) -> bool:
    stage = str(consumer_stage or "").strip()
    if not stage:
        return False
    try:
        from interview_mux.v2.config import ANALYSIS_ORDER

        return stage in ANALYSIS_ORDER or stage == "optimal_questions"
    except Exception:
        return stage in {
            "missing_framing",
            "gap_framing_compose",
            "optimal_questions",
            "mastering_plan_confirm",
            "delivery_brief_build",
            "soundscape_policy_build",
            "episode_structure_compose",
        }


def _vo_ladder_id_sets(ctx: RunContext) -> tuple[list[str], list[str], list[str]]:
    """Seated / omitted / skip IDs for a size-independent ladder fingerprint."""
    seated: list[str] = []
    omitted: list[str] = []
    try:
        from interview_mux.air_script import omitted_vo_line_ids, seated_vo_line_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
        if isinstance(plan, dict):
            seated = sorted({str(x) for x in seated_vo_line_ids(plan) if x})
            omitted = sorted({str(x) for x in omitted_vo_line_ids(plan) if x})
    except Exception:
        pass
    skip: list[str] = []
    try:
        if ctx.artifact_exists("understanding/gap_report.json"):
            gap = ctx.read_json("understanding/gap_report.json")
            if isinstance(gap, dict):
                for row in gap.get("interviewer_lines") or []:
                    if not isinstance(row, dict):
                        continue
                    if not (row.get("skipped_optional") or row.get("air_script_omit")):
                        continue
                    lid = str(row.get("line_id") or "").strip()
                    if lid:
                        skip.append(lid)
    except Exception:
        pass
    return seated, omitted, sorted(set(skip))


def _vo_ladder_fingerprint(ctx: RunContext, violations: list[Any]) -> str:
    """Stable fingerprint of the VO contract hole — not artifact file sizes."""
    import hashlib

    parts: list[str] = [str(v)[:80] for v in (violations or [])[:8]]
    seated, omitted, skip = _vo_ladder_id_sets(ctx)
    parts.append("seated:" + ",".join(seated))
    parts.append("omitted:" + ",".join(omitted))
    parts.append("skip:" + ",".join(skip))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


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
    if "seated synthesize " in low and ("skip/omit" in low or "skipped_optional" in low):
        start = low.find("seated synthesize ") + len("seated synthesize ")
        rest = message[start:]
        lid = rest.split(" has ")[0].strip() if " has " in rest else rest.split()[0].strip()
        return VoViolation("skip_omit_on_seated", line_id=lid, detail=message)
    if "skip/omit" in low or "skipped_optional" in low:
        return VoViolation("skip_omit_on_seated", detail=message)
    if "both seated and omitted" in low:
        return VoViolation("seated_and_omitted", detail=message)
    if "lacks skip/omit" in low:
        return VoViolation("omitted_without_flags", detail=message)
    if "missing wav" in low:
        if "seated synthesize " in low:
            start = low.find("seated synthesize ") + len("seated synthesize ")
            rest = message[start:]
            lid = rest.split(" missing")[0].strip() if " missing" in rest else ""
        return VoViolation("missing_wav", line_id=lid, detail=message)
    return VoViolation("unknown", detail=message)


def _plan_write_permitted(ctx: RunContext) -> bool:
    """True when the active stage may persist mastering/mastering_plan.json.

    Reconcile runs from every delivery stage (``delivery_batch``). Once the plan
    owner sealed it, the seat sync must stay a read-side observation instead of
    an authority_denied write (exec_11871 junction remaster).
    """
    try:
        from interview_mux.artifact_ownership import write_permitted
        from interview_mux.write_staging import active_stage_id

        stage_now = str(active_stage_id() or "")
        if not stage_now:
            # No active stage (CLI / ladder helpers) — ownership cannot resolve a
            # writer, so keep legacy behaviour instead of silently dropping seats.
            return True
        allowed, reason = write_permitted(
            ctx,
            "mastering/mastering_plan.json",
            stage_now,
            role="producer",
            verb="persist",
        )
    except Exception:
        return True
    if not allowed:
        try:
            ctx.log(
                "execution contract: mastering_plan sealed — seat sync stays read-only "
                f"(stage={stage_now or 'unknown'}, {reason})",
                level="info",
                stage=stage_now or None,
            )
        except Exception:
            pass
        return False
    return True


def reconcile_execution_contract(ctx: RunContext, *, reason: str = "") -> dict[str, Any]:
    """Sync vo_seats on mastering_plan from gap_report; persist execution_contract.json.

    Clamp is N/A here: ``clamp_hosted_seats_to_rendered_wavs`` already calls this
    after omit/seat mutations; calling clamp from reconcile would recurse.
    """
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
                # B16: after soft freeze, seat rewrite needs meta-gate allow.
                try:
                    from interview_mux.seat_authority import (
                        gate_seat_mutation,
                        soft_freeze_active,
                    )

                    if soft_freeze_active(ctx) and not gate_seat_mutation(
                        ctx,
                        reason=f"reconcile_execution_contract:{reason or 'sync'}",
                        symptoms=["exec_contract_reconcile"],
                        proposed_delta={"ops": [], "from": "reconcile_execution_contract"},
                    ):
                        new_seats = old_seats
                except Exception:
                    # b16 fail-closed under freeze: keep old seats
                    try:
                        from interview_mux.seat_authority import soft_freeze_active

                        if soft_freeze_active(ctx):
                            new_seats = old_seats
                    except Exception:
                        pass
            if new_seats != old_seats and _plan_write_permitted(ctx):
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
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="tier_a_publish_orientation",
            symptoms=["exec_contract_ladder", "orientation"],
        ):
            return []
    except Exception:
        try:
            from interview_mux.seat_authority import soft_freeze_active, hard_freeze_active

            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                return []
        except Exception:
            return []
    from interview_mux.nugget_layup import PLAN_REL, publish_layup_plan_to_gap_report

    written: list[str] = []
    if not ctx.artifact_exists(PLAN_REL):
        # Before nugget_layup_compose has run there is no plan to publish; an
        # empty publish can never meet the hosted VO floor and raised
        # hosted_vo_floor_unsatisfiable at error level from the invariant
        # ladder (exec_015, ISSUES 156). The next tier handles this state.
        return written
    plan = ctx.read_json(PLAN_REL)
    publish_layup_plan_to_gap_report(ctx, plan if isinstance(plan, dict) else None)
    written.append("understanding/gap_report.json")
    if ctx.artifact_exists(PLAN_REL):
        written.append(PLAN_REL)
    reconcile_execution_contract(ctx, reason="tier_a_publish_orientation")
    return written


def _tier_b_gap_recompose(ctx: RunContext) -> list[str]:
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="tier_b_gap_recompose",
            symptoms=["exec_contract_ladder", "gap_recompose"],
        ):
            return []
    except Exception:
        try:
            from interview_mux.seat_authority import soft_freeze_active, hard_freeze_active
            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                return []
        except Exception:
            return []
    from interview_mux.refinement_passes import run_gap_framing_recompose

    run_gap_framing_recompose(ctx)
    reconcile_execution_contract(ctx, reason="tier_b_gap_recompose")
    written = ["understanding/gap_report.json"]
    if ctx.artifact_exists("understanding/gap_framing_recompose.json"):
        written.append("understanding/gap_framing_recompose.json")
    return written


def _tier_c_opening_omit_unseat(ctx: RunContext) -> list[str]:
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="tier_c_opening_omit_unseat",
            symptoms=["opening_adjacency", "exec_contract_ladder"],
        ):
            return []
    except Exception:
        try:
            from interview_mux.seat_authority import soft_freeze_active, hard_freeze_active
            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                return []
        except Exception:
            return []
    from interview_mux.recovery_controller import (
        playbook_opening_slot_conflict,
        playbook_stamp_air_script_omits,
    )

    written: list[str] = []
    written.extend(playbook_opening_slot_conflict(ctx))
    written.extend(playbook_stamp_air_script_omits(ctx))
    reconcile_execution_contract(ctx, reason="tier_c_opening_omit_unseat")
    return list(dict.fromkeys(written))


def _tier_d_target_is_required_orientation(
    gap: dict[str, Any] | None,
    lid: str,
) -> bool:
    """True when VO ladder must not waive a still-required opening orientation."""
    if not isinstance(gap, dict):
        return False
    meta = gap.get("opening_orientation")
    if not isinstance(meta, dict) or not meta.get("required"):
        return False
    # Still required: never ladder-waive orientation (even with omitted half-state).
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID, is_episode_orientation

    oid = str(meta.get("line_id") or "").strip()
    if lid and oid and lid == oid:
        return True
    if lid and lid == ORIENTATION_LINE_ID:
        return True
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("line_id") or "").strip() != lid:
            continue
        return bool(is_episode_orientation(row))
    # No matching line but lid names orientation — refuse meta-only flip.
    return bool(lid) and (lid == oid or lid == ORIENTATION_LINE_ID)


def _tier_d_would_hollow_hosted_floor(
    ctx: RunContext,
    gap: dict[str, Any] | None,
    lid: str,
) -> bool:
    """True when waiving ``lid`` would leave a hosted show with no live host line.

    Zero active lines is the catastrophic floor state; no later stage can
    recover it, so layup is pinned and the ladder waives its line again
    (exec_016, ISSUES 160). Like a required orientation, the last line is
    not waivable; the miss escalates to its producer instead.
    """
    if not isinstance(gap, dict) or not lid:
        return False
    try:
        from interview_mux.gap_fill_eligibility import hosted_framing_requires_synthetic_vo
        from interview_mux.vo_contract import _count_active_hosted_synth

        if not hosted_framing_requires_synthetic_vo(ctx):
            return False
        rows = [r for r in (gap.get("interviewer_lines") or []) if isinstance(r, dict)]
        target = [r for r in rows if str(r.get("line_id") or "").strip() == lid]
        if not target or _count_active_hosted_synth(target) < 1:
            return False
        rest = [r for r in rows if str(r.get("line_id") or "").strip() != lid]
        return _count_active_hosted_synth(rest) < 1
    except Exception:
        return False


def _tier_d_logged_waive(ctx: RunContext, violation: VoViolation | None) -> list[str]:
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="tier_d_logged_waive",
            symptoms=["exec_contract_ladder", "waive"],
        ):
            return []
    except Exception:
        try:
            from interview_mux.seat_authority import soft_freeze_active, hard_freeze_active
            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                return []
        except Exception:
            return []
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID, is_episode_orientation
    from interview_mux.vo_contract import mark_gap_line_not_on_air

    lid = (
        str(violation.line_id or "").strip()
        if violation and violation.line_id
        else ORIENTATION_LINE_ID
    )
    written: list[str] = []

    gap_early: dict[str, Any] | None = None
    if ctx.artifact_exists("understanding/gap_report.json"):
        try:
            raw = ctx.read_json("understanding/gap_report.json")
            if isinstance(raw, dict):
                gap_early = raw
        except Exception:
            gap_early = None

    # Constitution: required opening orientation is non-waivable by VO ladder
    # (publishability T0-4). Escalate via ladder exhaust → vo_synthesize heal.
    if _tier_d_target_is_required_orientation(gap_early, lid):
        try:
            ctx.log(
                "tier_d_refused_required_orientation",
                level="warning",
                stage="execution_contract",
                detail={"line_id": lid or "orientation"},
            )
        except Exception:
            pass
        try:
            from interview_mux.recovery_controller import append_remediation_log

            append_remediation_log(
                ctx,
                action="tier_d_refused_required_orientation",
                detail=lid or "orientation",
            )
        except Exception:
            pass
        return []

    if _tier_d_would_hollow_hosted_floor(ctx, gap_early, lid):
        try:
            ctx.log(
                "tier_d_refused_last_host_line",
                level="warning",
                stage="execution_contract",
                detail={"line_id": lid},
            )
        except Exception:
            pass
        return []

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
            # Unseating mirrors the gap line's not-on-air mark below. Unkeyed,
            # the ladder's host stage (gap_framing_compose) wrote it as a
            # foreign side effect and it was skipped, so the plan kept seating a
            # line the gap report waived (ISSUES 140). Present the seat owner
            # with the omit-stamp reason, as stamp_gap_omit_flags does.
            write_plan(
                ctx, plan, seat_reason="stamp_gap_omit_flags", stage_key="air_contract_sanitize"
            )
            written.append("mastering/mastering_plan.json")

    if not ctx.artifact_exists("understanding/gap_report.json"):
        return written
    gap = gap_early if isinstance(gap_early, dict) else ctx.read_json("understanding/gap_report.json")
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
                    ctx=ctx,
                    gap_report=gap,
                    peer_lines=list(gap.get("interviewer_lines") or []),
                )
            )
            found = True
            continue
        lines_out.append(dict(row))
    if not found and lid:
        # Never mint a schema-incomplete omit stub into interviewer_lines.
        # opening_orientation.omitted (below) is the durable waive record;
        # a stub with only line_id/delivery fails gap_report.schema.json and
        # blocks gap_framing_compose pre-flush (exec_11165 class).
        pass
    out = dict(gap)
    out["interviewer_lines"] = lines_out
    # Persist omit meta so filter_gap_lines / ORIENTATION_ALWAYS cannot un-omit.
    # Only when not still-required (gated above). Require both omitted+required=false.
    # CRITICAL: only touch opening_orientation meta when the waived *line* is
    # orientation — waiving vo_question_* must not mark orientation omitted
    # (exec_13181: waived_line_id=vo_question_seg_009 flipped required=false →
    # preface omit-sync → hosted_vo_floor 2<3 thrash).
    waived_row = next(
        (
            r
            for r in lines_out
            if isinstance(r, dict) and str(r.get("line_id") or "").strip() == lid
        ),
        None,
    )
    waive_is_orientation = bool(
        lid
        and (
            lid == ORIENTATION_LINE_ID
            or (isinstance(waived_row, dict) and is_episode_orientation(waived_row))
            or (
                isinstance(gap_early, dict)
                and str((gap_early.get("opening_orientation") or {}).get("line_id") or "").strip()
                == lid
            )
        )
    )
    if waive_is_orientation and (found or lid):
        meta = out.get("opening_orientation")
        meta = dict(meta) if isinstance(meta, dict) else {}
        meta["omitted"] = True
        meta["required"] = False
        meta["omit_reason"] = str(meta.get("omit_reason") or "execution_contract_waive")
        if lid:
            meta["waived_line_id"] = lid
        meta["compensating_path"] = "tier_d_logged_waive"
        out["opening_orientation"] = meta
    # A waive is a flag stamp on a report another stage owns (ISSUES 101).
    from interview_mux.seat_authority import persist_gap_report_stamp

    persist_gap_report_stamp(ctx, out, reason="stamp_gap_omit_flags")
    written.append("understanding/gap_report.json")
    # Omit removed audible cover — demote leftover high gaps so compose lint
    # cannot stay dirty while omit-wins holds (exec_13170 seg_007).
    try:
        from interview_mux.high_gap_vo import demote_uncovered_high_gaps

        demote_uncovered_high_gaps(
            ctx, gap_report=out, origin="post_commit_uncovered_high"
        )
    except Exception:
        pass
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
    fingerprint: str = "",
    last_outcome: str = "",
    detail: str = "",
) -> None:
    plan = {
        "version": 1,
        "active": True,
        "completed": False,
        "error_class": "vo_contract_repair",
        "started_at": _utc_now(),
        "current_tier": tier,
        "violations": violations[:12],
        "consumer_stage": consumer_stage,
        "fingerprint": str(fingerprint or ""),
        "last_outcome": str(last_outcome or ""),
        "detail": str(detail or ""),
        "resume_stage": "vo_synthesize" if last_outcome else "",
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


def _cached_unrecovered_vo_ladder(
    ctx: RunContext, fingerprint: str
) -> LadderResult | None:
    """HV-1: same contract hole after stall/exhaust must not re-enter A→D."""
    plan = read_active_vo_repair_plan(ctx)
    if not plan:
        return None
    if str(plan.get("fingerprint") or "") != str(fingerprint or ""):
        return None
    outcome = str(plan.get("last_outcome") or "")
    if outcome not in {"stall_cap", "tiers_exhausted"}:
        return None
    violations = [str(v) for v in (plan.get("violations") or []) if v]
    return LadderResult(
        tier="stall_cap" if outcome == "stall_cap" else str(plan.get("current_tier") or "tier_d_logged_waive"),
        recovered=False,
        contract_ok=False,
        violations=violations,
        detail=str(plan.get("detail") or "")
        or (
            "vo_ladder_fingerprint_stall"
            if outcome == "stall_cap"
            else "tiers_exhausted"
        ),
        resume_stage="vo_synthesize",
    )


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

    fp = _vo_ladder_fingerprint(ctx, violations)
    cached = _cached_unrecovered_vo_ladder(ctx, fp)
    if cached is not None:
        return cached

    # Cap identical ladder resumes when the contract hole is unchanged.
    try:
        from interview_mux.delivery_invariants import (
            count_identical_seed_resumes,
            note_seed_resume,
            record_invariant_heal,
        )

        note_seed_resume(
            ctx,
            from_stage="vo_contract_ladder",
            because_of=consumer_stage or "vo_contract",
            fingerprint=fp,
        )
        if count_identical_seed_resumes(
            ctx, from_stage="vo_contract_ladder", fingerprint=fp, window=12
        ) >= 6:
            record_invariant_heal(
                ctx,
                kind="vo_ladder_fingerprint_stall",
                stage=consumer_stage or "vo_synthesize",
                detail={"fingerprint": fp},
            )
            _write_vo_repair_plan(
                ctx,
                tier="stall_cap",
                violations=list(violations or []),
                consumer_stage=consumer_stage,
                fingerprint=fp,
                last_outcome="stall_cap",
                detail="vo_ladder_fingerprint_stall",
            )
            return LadderResult(
                tier="stall_cap",
                recovered=False,
                contract_ok=False,
                violations=list(violations or []),
                detail="vo_ladder_fingerprint_stall",
                resume_stage="vo_synthesize",
            )
    except Exception:
        pass

    _write_vo_repair_plan(
        ctx,
        tier=start_tier or LADDER_TIERS[0],
        violations=violations,
        consumer_stage=consumer_stage,
        fingerprint=fp,
    )

    tier_index = 0
    if start_tier:
        try:
            tier_index = LADDER_TIERS.index(start_tier)
        except ValueError:
            tier_index = 0

    primary_violation = classify_vo_violation(violations[0])
    last_tier = ""
    artifacts: list[str] = []
    analysis_era = _consumer_is_analysis_era(consumer_stage)
    if analysis_era:
        ctx.log(
            "vo_contract ladder: analysis-era consumer — skipping plan-mutating "
            f"tiers ({', '.join(sorted(_PLAN_MUTATING_LADDER_TIERS))})",
            level="warning",
            stage=consumer_stage or "execution_contract",
            detail={"consumer_stage": consumer_stage, "violations": violations[:4]},
        )

    for tier in LADDER_TIERS[tier_index:]:
        if analysis_era and tier in _PLAN_MUTATING_LADDER_TIERS:
            ctx.log(
                f"vo_contract ladder skip {tier} under analysis consumer "
                f"{consumer_stage} (mastering_plan owned by air_contract_sanitize)",
                level="info",
                stage=consumer_stage or "execution_contract",
                detail={"tier": tier},
            )
            continue
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

    # Analysis-era: do not escalate through plan-mutate; pin compose/high-gap fill.
    if analysis_era and violations:
        pin = "gap_framing_compose"
        if str(consumer_stage or "").strip() in {"missing_framing", "optimal_questions"}:
            pin = str(consumer_stage).strip()
        _write_vo_repair_plan(
            ctx,
            tier="analysis_era_skip_plan_mutate",
            violations=list(violations or []),
            consumer_stage=consumer_stage,
            fingerprint=fp,
            last_outcome="analysis_era_skip",
            detail="plan_mutating_tiers_skipped",
        )
        _log_ladder_action(
            ctx,
            tier="analysis_era_skip_plan_mutate",
            status="escalate",
            consumer_stage=consumer_stage,
        )
        return LadderResult(
            tier="analysis_era_skip_plan_mutate",
            recovered=False,
            contract_ok=False,
            violations=list(violations or []),
            detail="plan_mutating_tiers_skipped_for_analysis_consumer",
            resume_stage=pin,
        )

    # HV-1: exhaust keeps the repair plan open and pins vo_synthesize.
    fp_end = _vo_ladder_fingerprint(ctx, violations)
    _write_vo_repair_plan(
        ctx,
        tier=last_tier or "tier_d_logged_waive",
        violations=violations,
        consumer_stage=consumer_stage,
        fingerprint=fp_end,
        last_outcome="tiers_exhausted",
        detail=violations[0] if violations else "tiers_exhausted",
    )
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
        resume_stage="vo_synthesize",
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


def _pin_unrecovered_coverage_to_vo_synthesize(ctx: RunContext) -> None:
    """HV-2: missing seated WAV is a vo_synthesize hole — unmark the producer."""
    (ctx.run_dir / ".stage_done" / "vo_synthesize").unlink(missing_ok=True)


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
                artifacts = _tier_c_vo_adjudicate_heal(ctx)
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

    # HV-2: exhaust / hosted 2-speaker still pin vo_synthesize. Do not stamp
    # the repair plan complete or resume the EDL consumer.
    _pin_unrecovered_coverage_to_vo_synthesize(ctx)
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
        resume_stage="vo_synthesize",
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
