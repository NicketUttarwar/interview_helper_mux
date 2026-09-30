"""VO air contract — seated/synthesize/omit alignment (execution-flow hardening R2/R10)."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

# Durable policy omits — never revived by hosted floor or WAV reseat.
# Process failures (seated_bind_synth_failed) are NOT policy; bind/WAV wins.
POLICY_OMIT_REASON_CODES = frozenset(
    {
        "media_ip_cta_hole",
        "never_touch_cta",
        # Tier-D logged waive must survive hosted-floor / keep-on-air un-omit
        # (exec_13170: vo_context_seg_011 omit_notes kept, flags cleared → thrash).
        "execution_contract_waive",
    }
)

# Floor / intentional-skip sync: policy + skip_omit_unseat. Process bind-fail
# stamps are excluded so a false-fail omit cannot thrash-lock delivery.
OMIT_WINS_REASON_CODES = POLICY_OMIT_REASON_CODES | frozenset({"skip_omit_unseat"})


def _waive_markers_present(row: dict[str, Any]) -> bool:
    path = str(row.get("compensating_path") or "").strip().lower()
    if path in {"tier_d_logged_waive", "execution_contract_waive"}:
        return True
    notes = row.get("omit_notes") or []
    if isinstance(notes, list):
        for note in notes:
            s = str(note or "").strip().lower()
            if "execution_contract_waive" in s:
                return True
    return False


def _orphan_orientation_waive(
    row: dict[str, Any] | None,
    gap_report: dict[str, Any] | None,
) -> bool:
    """True when tier-D/waive stamps sit on a still-required orientation.

    Orphan stamps are not durable policy — required orientation must stay clearable
    onto air (exec_13177 / orientation waive constitution).
    """
    if not isinstance(row, dict) or not isinstance(gap_report, dict):
        return False
    try:
        from interview_mux.opening_orientation import (
            is_episode_orientation,
            orientation_omitted,
        )

        if orientation_omitted(gap_report):
            return False
        meta = gap_report.get("opening_orientation")
        if not (isinstance(meta, dict) and meta.get("required")):
            return False
        oid = str(meta.get("line_id") or "").strip()
        lid = str(row.get("line_id") or "").strip()
        if is_episode_orientation(row):
            return True
        return bool(oid and lid and lid == oid)
    except Exception:
        return False


def policy_omit_skip_reason(
    row: dict[str, Any] | None,
    gap_report: dict[str, Any] | None = None,
) -> bool:
    """True for durable CTA/waive policy — WAV/bind must not reseat these.

    Orphan ``execution_contract_waive`` / ``tier_d_logged_waive`` on a still-required
    orientation are **not** policy (pass ``gap_report`` so consumers can clear).
    """
    if not isinstance(row, dict):
        return False
    if _orphan_orientation_waive(row, gap_report):
        return False
    reason = str(row.get("skip_reason_code") or "").strip().lower()
    if reason in POLICY_OMIT_REASON_CODES:
        return True
    return _waive_markers_present(row)


def omit_wins_skip_reason(
    row: dict[str, Any] | None,
    gap_report: dict[str, Any] | None = None,
) -> bool:
    """True when hosted-floor must not revive this skip (policy or intentional unseat).

    Process omit ``seated_bind_synth_failed`` is never omit-wins — bind/WAV ladder
    clears it. Callers that must refuse WAV reseat of CTA/waive use
    ``policy_omit_skip_reason`` instead.
    """
    if not isinstance(row, dict):
        return False
    if policy_omit_skip_reason(row, gap_report=gap_report):
        return True
    reason = str(row.get("skip_reason_code") or "").strip().lower()
    return reason == "skip_omit_unseat"


def _load_seated_omitted(ctx: RunContext) -> tuple[set[str], set[str]]:
    from interview_mux.air_script import omitted_vo_line_ids, seated_vo_line_ids
    from interview_mux.mastering_plan_loader import load_plan_raw

    plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
    return seated_vo_line_ids(plan), omitted_vo_line_ids(plan)


def mark_gap_line_not_on_air(
    line: dict[str, Any],
    *,
    reason_code: str,
    compensating_path: str | None = None,
    ctx: RunContext | None = None,
    gap_report: dict[str, Any] | None = None,
    peer_lines: list[Any] | None = None,
) -> dict[str, Any]:
    """Atomically mark a gap line as not on air (skip + omit flags).

    Fills gap_report.schema.json required fields when absent so omit stamps
    cannot fail pre-flush commit (tier-D mint / incomplete LLM rows).

    When ``ctx`` is provided, pre-synth hosted floor gate
    (``may_soft_omit_hosted_line``) may refuse process soft-omit and return the
    line unchanged (exec_13196).
    """
    if ctx is not None:
        try:
            from interview_mux.hosted_vo_authority import may_soft_omit_hosted_line

            if not may_soft_omit_hosted_line(
                ctx,
                line,
                gap_report=gap_report,
                reason_code=reason_code,
                peer_lines=peer_lines,
            ):
                return dict(line)
        except Exception:
            pass
    row = dict(line)
    row["skipped_optional"] = True
    row["air_script_omit"] = True
    row["blocking"] = False
    row["skip_reason_code"] = str(reason_code or "not_on_air")
    if compensating_path:
        row["compensating_path"] = compensating_path
    notes = list(row.get("omit_notes") or [])
    note = f"vo_contract:{reason_code}"
    if note not in notes:
        notes.append(note)
    row["omit_notes"] = notes
    # Schema requires these on every interviewer_lines item (incl. omitted).
    if not str(row.get("gap_type") or "").strip():
        row["gap_type"] = "missing_setup"
    if "text" not in row or row.get("text") is None:
        row["text"] = ""
    if not str(row.get("targets_segment_id") or "").strip():
        tgt = (
            row.get("target_segment_id")
            or row.get("after_segment_id")
            or row.get("segment_id")
            or ""
        )
        row["targets_segment_id"] = str(tgt or "seg_omitted")
    if str(row.get("placement") or "") not in {"before", "after"}:
        row["placement"] = "before"
    if str(row.get("delivery") or "").strip().lower() not in {"record", "synthesize"}:
        row["delivery"] = "synthesize"
    return row


def ensure_gap_line_on_air(
    line: dict[str, Any],
    *,
    force_bind_synth_failed: bool = False,
    gap_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Clear skip/omit flags so a seated synthesize line stays on air.

    Durable policy omits (CTA / waive) stay locked. Process stamps such as
    ``seated_bind_synth_failed`` and intentional ``skip_omit_unseat`` clear when
    bind/WAV success forces the line on air (``force_bind_synth_failed`` or
    any non-policy caller that already gated on WAV).

    Pass ``gap_report`` so orphan orientation waive stamps are not treated as
    durable policy.
    """
    if policy_omit_skip_reason(line, gap_report=gap_report):
        return dict(line)
    reason = str((line or {}).get("skip_reason_code") or "").strip().lower()
    # Hosted floor must not strip skip_omit_unseat without an explicit force
    # (WAV reseat / bind heal passes force_bind_synth_failed=True).
    if reason == "skip_omit_unseat" and not force_bind_synth_failed:
        if omit_wins_skip_reason(line, gap_report=gap_report):
            return dict(line)
    row = dict(line)
    orphan = _orphan_orientation_waive(line, gap_report)
    # Orphan orientation waive: scrub stamps fully when clearing onto air.
    if orphan:
        try:
            from interview_mux.opening_orientation import clear_stale_orientation_waive_stamps

            row, _ = clear_stale_orientation_waive_stamps(row)
        except Exception:
            pass
    row.pop("skipped_optional", None)
    row.pop("air_script_omit", None)
    row.pop("skip", None)
    row.pop("skip_reason_code", None)
    if orphan:
        row.pop("compensating_path", None)
    row["blocking"] = bool(row.get("required"))
    return row


def gap_line_requires_synthesis(
    line: dict[str, Any],
    seated: set[str],
    gap_report: dict[str, Any] | None = None,
) -> bool:
    """True when a gap line must have a synthesize WAV (synth_always policy)."""
    if not isinstance(line, dict):
        return False
    if str(line.get("delivery") or "").lower() != "synthesize":
        return False
    lid = str(line.get("line_id") or "").strip()
    if not lid:
        return False
    from interview_mux.air_script import gap_line_air_eligible

    # Waived / omitted lines never require synthesis — even if stale seats linger.
    if not gap_line_air_eligible(line, gap_report=gap_report):
        return False
    if lid in seated:
        return True
    from interview_mux.opening_orientation import is_episode_orientation

    return is_episode_orientation(line) or bool(line.get("required"))


def seated_vo_missing_ids(ctx: RunContext) -> list[str]:
    """Seated synthesize line_ids with no matching WAV on disk."""
    from interview_mux.vo_synthesis_audit import synthesis_entry_matches_line
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    seated, omitted = _load_seated_omitted(ctx)
    missing: list[str] = []
    for line in gap.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        lid = str(line.get("line_id") or "")
        # Plan omit wins even when gap skip flags drifted off.
        if lid and lid in omitted:
            continue
        if not gap_line_requires_synthesis(line, seated, gap_report=gap):
            continue
        path = resolve_vo_pickup_path(ctx, line)
        matches, _reason = synthesis_entry_matches_line(ctx, line)
        if path is None or not path.is_file() or not matches:
            missing.append(lid)
    return [x for x in missing if x]


def assert_seated_vo_rendered(ctx: RunContext) -> None:
    """Fail closed when seated synthesize lines lack WAV."""
    missing = seated_vo_missing_ids(ctx)
    if missing:
        raise RuntimeError(
            "vo_synthesize: seated synthesize VO not rendered: "
            + ", ".join(missing[:8])
        )


def vo_synthesize_render_incompleteness(ctx: RunContext) -> str | None:
    """S4 SSOT: pairs / G1 / seated WAV / bind sanitary+stale — one readiness stack.

    Does not cover gap/air sanitary preconditions or hollow-seat HV-4 (caller).
    """
    if not ctx.artifact_exists("master/transitions.json"):
        return "master/transitions.json is pending"
    try:
        from interview_mux.transition_vo import vo_synthesize_pair_incompleteness

        pair_reason = vo_synthesize_pair_incompleteness(ctx)
    except Exception:
        pair_reason = None
    if pair_reason:
        return pair_reason
    try:
        from interview_mux.gates import check_g1_vo

        missing_g1 = check_g1_vo(ctx)
        if missing_g1:
            return f"G1 VO pickups missing: {', '.join(missing_g1[:4])}"
    except Exception:
        pass
    try:
        missing_seated = seated_vo_missing_ids(ctx)
        if missing_seated:
            return (
                "seated synthesize VO missing WAV: "
                + ", ".join(missing_seated[:4])
            )
    except Exception:
        pass
    try:
        from interview_mux.artifact_sanitize.registry import vo_sanitary_errors

        vo_errs = vo_sanitary_errors(ctx)
        if vo_errs:
            return "vo_unsanitary — resume vo_synthesize: " + "; ".join(vo_errs[:3])
    except Exception:
        pass
    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        stale = compact_vo_coverage_stale_or_missing(ctx)
        if stale:
            return (
                "seated synthesize VO script/WAV stale: "
                + ", ".join(stale[:4])
            )
    except Exception:
        pass
    return None


def validate_vo_contract(ctx: RunContext) -> list[str]:
    """Return human-readable contract violations (empty = pass)."""
    issues: list[str] = []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return issues
    gap = ctx.read_json("understanding/gap_report.json")
    seated, omitted = _load_seated_omitted(ctx)
    by_line: dict[str, dict] = {}
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if lid:
            by_line[lid] = row
    for lid in sorted(seated):
        row = by_line.get(lid)
        if row is None:
            issues.append(f"seated line {lid} missing from gap_report")
            continue
        if str(row.get("delivery") or "").lower() != "synthesize":
            continue
        if row.get("skipped_optional") or row.get("air_script_omit"):
            issues.append(f"seated synthesize {lid} has skip/omit flags")
    for lid in sorted(omitted):
        row = by_line.get(lid)
        if row is None:
            continue
        if lid in seated:
            issues.append(f"line {lid} is both seated and omitted")
        elif not _gap_row_has_omit_flags(row):
            issues.append(f"omitted {lid} lacks skip/omit flags in gap_report")
    missing = seated_vo_missing_ids(ctx)
    for lid in missing:
        issues.append(f"seated synthesize {lid} missing WAV")
    return issues


def _gap_row_has_omit_flags(row: dict[str, Any]) -> bool:
    """True when gap row is durably off-air (flags or omit-sync notes)."""
    if row.get("skipped_optional") or row.get("air_script_omit"):
        return True
    notes = row.get("omit_notes") or []
    return any("air_script_omit_sync" in str(n) for n in notes if n)


def _count_active_hosted_synth(rows: list[dict[str, Any]]) -> int:
    n = 0
    for ln in rows:
        if (
            ln.get("skipped_optional")
            or ln.get("air_script_omit")
            or not str(ln.get("text") or "").strip()
        ):
            continue
        delivery = str(ln.get("delivery") or "synthesize").strip().lower() or "synthesize"
        if delivery in {"synthesize", "record", "voice_clone", "chatterbox"}:
            n += 1
    return n


def revive_discarded_floor_candidates(
    ctx: RunContext,
    lines_in: list[dict[str, Any]],
    *,
    need: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Reactivate soft-omitted / discarded host lines until need or pool empty.

    Never invents text or line ids — only clears soft omit flags on existing
    synthesize rows that are not omit-wins / CTA / orientation-protected.
    End-A allowlisted as ``revive_discarded_floor_candidate``.
    """
    from interview_mux.opening_orientation import is_episode_orientation

    changed: list[str] = []
    rows = [dict(r) for r in lines_in if isinstance(r, dict)]
    seated_now: set[str] = set()
    try:
        seated_now, _om = _load_seated_omitted(ctx)
    except Exception:
        seated_now = set()

    while _count_active_hosted_synth(rows) < need:
        picked = None
        best_rank = 99
        for i, row in enumerate(rows):
            if not (row.get("skipped_optional") or row.get("air_script_omit")):
                continue
            delivery = str(row.get("delivery") or "").strip().lower() or "synthesize"
            if delivery not in {"synthesize", "record", "voice_clone", "chatterbox"}:
                continue
            if is_episode_orientation(row):
                continue
            lid = str(row.get("line_id") or "").strip()
            if not lid or not str(row.get("text") or "").strip():
                continue
            if lid in seated_now or omit_wins_skip_reason(row):
                continue
            # Prefer soft air_script_omit_sync / optional over policy omit.
            soft = 0 if (
                row.get("air_script_omit_sync")
                or str(row.get("skip_reason_code") or "").startswith("soft")
            ) else 1
            sev = str(row.get("severity") or "medium").lower()
            wav_bonus = 0 if _gap_row_has_pickup_stem(ctx, row) else 2
            rank = soft + (0 if sev in {"high", "critical", "blocking"} else 1) + wav_bonus
            if rank < best_rank:
                best_rank = rank
                picked = i
        if picked is None:
            break
        rows[picked] = ensure_gap_line_on_air(rows[picked])
        lid = str(rows[picked].get("line_id") or "")
        if lid:
            changed.append(lid)
            seated_now.add(lid)
    return rows, [x for x in dict.fromkeys(changed) if x]


def ensure_hosted_framing_vo_seats(ctx: RunContext) -> list[str]:
    """Keep already-on-air hosted framing seats; reseat only when unfrozen.

    Under **hard freeze**: never invent new seats or CTA holes (no
    ``catastrophe_hosted_vo_floor`` bypass). May revive existing soft-omitted
    host lines (``revive_discarded_floor_candidate``). If the G-Framing floor is
    still unmet under progress_floors → advisory-continue (no sticky halt).

    Soft/unfrozen: eligible synthesize layups may still reseat (i4).
    """
    from interview_mux.gap_fill_eligibility import (
        hosted_framing_requires_synthetic_vo,
        min_synthetic_vo_lines,
    )
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID, is_episode_orientation

    if not hosted_framing_requires_synthetic_vo(ctx):
        return []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return []
    need = min_synthetic_vo_lines(ctx)
    lines_in = [dict(r) for r in (gap.get("interviewer_lines") or []) if isinstance(r, dict)]
    changed_ids: list[str] = []

    def _active_count(rows: list[dict[str, Any]]) -> int:
        return _count_active_hosted_synth(rows)

    hard = False
    soft = False
    try:
        from interview_mux.seat_authority import hard_freeze_active, soft_freeze_active

        hard = bool(hard_freeze_active(ctx))
        soft = bool(soft_freeze_active(ctx))
    except Exception:
        hard = True  # fail-closed when freeze state unknown

    # Keep-on-air: un-omit non-waived orientation that should stay audible.
    for i, row in enumerate(lines_in):
        if not is_episode_orientation(row):
            continue
        try:
            from interview_mux.air_script import _orientation_line_waived

            if _orientation_line_waived(row, gap):
                continue
        except Exception:
            pass
        cleared = ensure_gap_line_on_air(row, gap_report=gap)
        if cleared.get("skipped_optional") or cleared.get("air_script_omit"):
            continue
        if row.get("skipped_optional") or row.get("air_script_omit"):
            changed_ids.append(str(cleared.get("line_id") or ""))
        lines_in[i] = cleared

    floor_unmet = _active_count(lines_in) < need

    # Hard freeze: never invent. Stretch may revive existing soft-omitted copy.
    if hard:
        if floor_unmet:
            try:
                from interview_mux.seat_authority import hard_freeze_action_permitted

                if hard_freeze_action_permitted("revive_discarded_floor_candidate", ctx):
                    lines_in, revived = revive_discarded_floor_candidates(
                        ctx, lines_in, need=need
                    )
                    changed_ids.extend(revived)
            except Exception:
                pass
            if _active_count(lines_in) < need:
                _record_hosted_floor_unmet(ctx, need=need, active=_active_count(lines_in))
            if changed_ids:
                return _commit_hosted_floor_gap(ctx, gap, lines_in, changed_ids)
            return []
        if changed_ids:
            return _commit_hosted_floor_gap(ctx, gap, lines_in, changed_ids)
        return []

    # Soft freeze: require seat_mutation_allowed (meta-gate) — no catastrophe token.
    if soft and floor_unmet:
        try:
            from interview_mux.seat_authority import (
                bump_seat_rewrite_generation,
                seat_mutation_allowed,
            )

            allowed, _why = seat_mutation_allowed(
                ctx,
                reason="ensure_hosted_framing",
                require_meta_gate=True,
            )
            if not allowed:
                _record_hosted_floor_unmet(ctx, need=need, active=_active_count(lines_in))
                return []
            bump_seat_rewrite_generation(ctx)
        except Exception:
            _record_hosted_floor_unmet(ctx, need=need, active=_active_count(lines_in))
            return []

    def _has_pickup_wav(row: dict[str, Any]) -> bool:
        return _gap_row_has_pickup_stem(ctx, row)

    seated_now: set[str] = set()
    try:
        seated_now, _omitted_now = _load_seated_omitted(ctx)
    except Exception:
        seated_now = set()

    cta_only_leftovers = True
    while _active_count(lines_in) < need:
        picked = None
        best_rank = 99
        for i, row in enumerate(lines_in):
            if not (row.get("skipped_optional") or row.get("air_script_omit")):
                continue
            if str(row.get("delivery") or "").lower() != "synthesize":
                continue
            if is_episode_orientation(row):
                continue
            lid = str(row.get("line_id") or "").strip()
            if not lid or not str(row.get("text") or "").strip():
                continue
            if lid in seated_now or omit_wins_skip_reason(row):
                continue
            cta_only_leftovers = False
            sev = str(row.get("severity") or "medium").lower()
            wav_bonus = 0 if _has_pickup_wav(row) else 2
            rank = (0 if sev in {"high", "critical", "blocking"} else 1) + wav_bonus
            if rank < best_rank:
                best_rank = rank
                picked = i
        if picked is None:
            break
        lines_in[picked] = ensure_gap_line_on_air(lines_in[picked])
        changed_ids.append(str(lines_in[picked].get("line_id") or ""))

    changed_ids = [x for x in dict.fromkeys(changed_ids) if x]
    if _active_count(lines_in) < need:
        _record_hosted_floor_unmet(
            ctx,
            need=need,
            active=_active_count(lines_in),
            cta_only=cta_only_leftovers and not changed_ids,
        )
        if not changed_ids:
            return []

    if not changed_ids:
        return []

    return _commit_hosted_floor_gap(ctx, gap, lines_in, changed_ids)


def _record_hosted_floor_unmet(
    ctx: RunContext,
    *,
    need: int,
    active: int,
    cta_only: bool = False,
) -> None:
    """Record floor miss — advisory-continue under progress_floors; else legacy thrash pins.

    Under hard freeze with a true shortage and progress floors off, escalate to
    ``hosted_vo_floor_unsatisfiable`` (empty heal pin). When progress floors are
    on, always advisory-continue with whatever active count exists.
    """
    try:
        from interview_mux.floor_progress import hosted_vo_aspirational, proceed_on_floor_miss

        # Zero active seats is catastrophic — Gap VO synth refuses no_synthesize_lines.
        # Aspirational stretch covers partial floors (e.g. 1–2 of 3), never hollow zero.
        # Cluster C: may_aspirational_proceed gates PARTIAL only.
        try:
            from interview_mux.hosted_vo_authority import may_aspirational_proceed

            if may_aspirational_proceed(ctx) and int(active) >= 1:
                proceed_on_floor_miss(
                    ctx,
                    gate_id="hosted_vo_floor",
                    have=int(active),
                    need=int(need),
                    pool_exhausted=True,
                    extra={"cta_only": bool(cta_only), "mode": "aspirational"},
                )
                return
        except Exception:
            if hosted_vo_aspirational(ctx) and int(active) >= 1:
                proceed_on_floor_miss(
                    ctx,
                    gate_id="hosted_vo_floor",
                    have=int(active),
                    need=int(need),
                    pool_exhausted=True,
                    extra={"cta_only": bool(cta_only), "mode": "aspirational"},
                )
                return
    except Exception:
        pass
    try:
        from interview_mux.seat_authority import hard_freeze_active

        if hard_freeze_active(ctx) and int(active) < int(need):
            from interview_mux.nugget_layup import stamp_hosted_vo_floor_unsatisfiable

            stamp_hosted_vo_floor_unsatisfiable(ctx, need=need, active=active)
            try:
                from interview_mux.identical_failures import record_identical_failure

                record_identical_failure(
                    ctx,
                    failed_stage="nugget_layup_compose",
                    producer="nugget_layup_compose",
                    reason="hosted_vo_floor_unsatisfiable",
                )
            except Exception:
                pass
            return
    except Exception:
        pass
    prose = (
        f"hosted_vo_floor_unmet: need={need} active={active} "
        f"— resume nugget_layup_compose: keep-on-air floor short"
        + ("; cta_only_leftovers needs_operator" if cta_only else "")
    )
    layup_is_front = False
    try:
        from interview_mux.v2.config import DELIVERY_ORDER
        from interview_mux.delivery_guardrails import seed_stage_complete

        layup_is_front = True
        for sid in DELIVERY_ORDER:
            if sid == "nugget_layup_compose":
                break
            if not seed_stage_complete(ctx, sid):
                layup_is_front = False
                break
    except Exception:
        # Prefer advisory over operator thrash when seed-front is unknown.
        layup_is_front = False

    try:
        ctx.log(
            prose if layup_is_front else prose + " (advisory: seed-front before layup)",
            level="warning",
            stage="vo_contract",
        )
    except Exception:
        pass
    try:

        def _mut(meta: dict[str, Any]) -> None:
            meta["hosted_vo_floor_unmet"] = True
            meta["hosted_vo_floor_unmet_prose"] = prose
            # Full-auto / forensics: never stamp needs_operator for floor before
            # layup is seed-front (G1-style wait honesty).
            if cta_only and layup_is_front:
                from interview_mux.operator_gates import should_stamp_needs_operator

                meta_now = {}
                try:
                    meta_now = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
                except Exception:
                    meta_now = {}
                if should_stamp_needs_operator(
                    "nugget_layup_compose",
                    "hosted_vo_floor_unmet",
                    meta=meta_now if isinstance(meta_now, dict) else None,
                ):
                    meta["needs_operator"] = True
                    meta["needs_operator_stage"] = "nugget_layup_compose"
                    meta["needs_operator_reason"] = prose
                else:
                    meta.pop("needs_operator", None)
                    meta["hosted_vo_floor_wait"] = True

        ctx.mutate_run_meta(_mut)
    except Exception:
        pass
    if not layup_is_front:
        return
    try:
        from interview_mux.identical_failures import record_identical_failure

        record_identical_failure(
            ctx,
            failed_stage="nugget_layup_compose",
            producer="nugget_layup_compose",
            reason="hosted_vo_floor_unmet",
        )
    except Exception:
        pass


def _commit_hosted_floor_gap(
    ctx: RunContext,
    gap: dict[str, Any],
    lines_in: list[dict[str, Any]],
    changed_ids: list[str],
) -> list[str]:
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID, is_episode_orientation

    out = dict(gap)
    out["interviewer_lines"] = lines_in
    gap_dest = ctx.write_json(
        "understanding/gap_report.json",
        out,
        stage_key="nugget_layup_compose",
    )

    plan_dest = None
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = dict(load_plan_raw(ctx) or {})
        script = dict(plan.get("air_script") or {})
        seats = dict(script.get("vo_seats") or {})
        seated = {
            str(r.get("line_id") or "")
            for r in lines_in
            if not r.get("skipped_optional") and r.get("line_id")
        }
        omitted = {
            str(r.get("line_id") or "")
            for r in lines_in
            if (r.get("skipped_optional") or r.get("air_script_omit")) and r.get("line_id")
        }
        beats = [dict(b) for b in (script.get("beats") or []) if isinstance(b, dict)]
        beat_lids = {str(b.get("line_id") or "") for b in beats if b.get("line_id")}
        by_id = {str(r.get("line_id") or ""): r for r in lines_in if r.get("line_id")}
        for lid in seated:
            if lid in beat_lids:
                continue
            row = by_id.get(lid) or {}
            beats.append(
                {
                    "segment_id": str(row.get("targets_segment_id") or "").strip(),
                    "line_id": lid,
                    "montage_move": "vo_then_clip",
                    "role": "hosted_framing_reseat",
                }
            )
            beat_lids.add(lid)
        orient = next(
            (lid for lid in seated if is_episode_orientation(by_id.get(lid) or {})),
            None,
        )
        seats["seated_line_ids"] = sorted(seated)
        seats["omitted_line_ids"] = sorted(omitted - seated)
        seats["orientation_id"] = orient or (
            seats.get("orientation_id") if seats.get("orientation_id") in seated else None
        )
        if seats["orientation_id"] is None and orient is None and ORIENTATION_LINE_ID in seated:
            seats["orientation_id"] = ORIENTATION_LINE_ID
        script["vo_seats"] = seats
        script["beats"] = beats
        plan["air_script"] = script
        plan_dest = ctx.write_json(
            "mastering/mastering_plan.json",
            plan,
            stage_key="air_contract_sanitize",
        )
    try:
        import shutil

        pending_root = ctx.run_dir / ".pending_writes"
        if pending_root.is_dir():
            for stage_dir in pending_root.iterdir():
                if not stage_dir.is_dir():
                    continue
                for rel, src in (
                    (("understanding", "gap_report.json"), gap_dest),
                    (("mastering", "mastering_plan.json"), plan_dest),
                ):
                    if src is None:
                        continue
                    candidate = stage_dir.joinpath(*rel)
                    if candidate.is_file():
                        shutil.copy2(src, candidate)
    except Exception:
        pass
    return [x for x in dict.fromkeys(changed_ids) if x]




def _gap_row_has_pickup_stem(ctx: RunContext, row: dict[str, Any]) -> bool:
    """True when a vo_pickup stem exists (committed or owner pending).

    Clamp / hosted-floor / bind-heal use stem presence. Pending under
    ``vo_synthesize`` counts so chatterbox false-fail before promote still
    registers as success. Script freshness is ``line_vo_wav_fresh``.
    """
    lid = str(row.get("line_id") or "").strip()
    seg = str(row.get("targets_segment_id") or "").strip()
    if not lid and not seg:
        return False
    roots: list[Any] = [ctx.final_path("vo_pickup")]
    try:
        from interview_mux.write_staging import staging_root

        pending = staging_root(ctx, "vo_synthesize") / "vo_pickup"
        roots.append(pending)
    except Exception:
        pass
    for pickup in roots:
        for base in (
            pickup / "matched",
            pickup / "synthesized",
            pickup / "clean",
            pickup / "normalized",
            pickup,
        ):
            try:
                if not base.is_dir():
                    continue
            except OSError:
                continue
            for key in (lid, seg):
                if key and (base / f"{key}.wav").is_file():
                    return True
    return False


def clamp_hosted_seats_docs(
    ctx: RunContext,
    gap: dict[str, Any],
    *,
    apply_freeze_gate: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """In-memory WAV-floor clamp: return (updated_gap, unseated_ids) with no disk I/O.

    When ``apply_freeze_gate`` is True (default disk path), soft/hard freeze requires
    a seat-mutation gate. Sanitize passes set False — W3 is the seat authority.
    """
    if apply_freeze_gate:
        try:
            from interview_mux.seat_authority import (
                gate_seat_mutation,
                hard_freeze_active,
                soft_freeze_active,
            )

            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                if not gate_seat_mutation(
                    ctx,
                    reason="clamp_hosted_seats_to_rendered_wavs",
                    symptoms=["clamp"],
                ):
                    return gap, []
        except Exception:
            try:
                from interview_mux.seat_authority import (
                    hard_freeze_active,
                    soft_freeze_active,
                )

                frozen = bool(soft_freeze_active(ctx) or hard_freeze_active(ctx))
            except Exception:
                frozen = True
            if frozen:
                return gap, []
    from interview_mux.gap_fill_eligibility import (
        hosted_framing_requires_synthetic_vo,
        min_synthetic_vo_lines,
    )
    from interview_mux.opening_orientation import is_episode_orientation

    if not hosted_framing_requires_synthetic_vo(ctx):
        return gap, []
    if not isinstance(gap, dict):
        return gap, []
    # Pre-synth (exec_13196): never WAV-prefer omit — no rendered floor yet.
    try:
        from interview_mux.hosted_vo_authority import vo_synth_era_complete

        if not vo_synth_era_complete(ctx):
            return gap, []
    except Exception:
        pass
    need = min_synthetic_vo_lines(ctx)
    rows = [dict(r) for r in (gap.get("interviewer_lines") or []) if isinstance(r, dict)]
    with_wav: list[dict[str, Any]] = []
    without_wav: list[dict[str, Any]] = []
    for row in rows:
        if row.get("skipped_optional") or row.get("air_script_omit"):
            continue
        if is_episode_orientation(row):
            continue
        delivery = str(row.get("delivery") or "synthesize").strip().lower() or "synthesize"
        if delivery not in {"synthesize", "record", "voice_clone", "chatterbox"}:
            continue
        if _gap_row_has_pickup_stem(ctx, row):
            with_wav.append(row)
        else:
            without_wav.append(row)
    if len(with_wav) < need or not without_wav:
        return gap, []
    unseated: list[str] = []
    by_id = {
        str(r.get("line_id") or ""): i for i, r in enumerate(rows) if r.get("line_id")
    }
    for row in without_wav:
        lid = str(row.get("line_id") or "").strip()
        if not lid:
            continue
        idx = by_id.get(lid)
        if idx is None:
            continue
        stamped = mark_gap_line_not_on_air(
            row,
            reason_code="rendered_floor_prefer_wav",
            ctx=ctx,
            gap_report=gap,
            peer_lines=rows,
        )
        if not (
            stamped.get("skipped_optional") and stamped.get("air_script_omit")
        ):
            continue
        rows[idx] = stamped
        unseated.append(lid)
    if not unseated:
        return gap, []
    out = dict(gap)
    out["interviewer_lines"] = rows
    return out, unseated


def clamp_hosted_seats_to_rendered_wavs(ctx: RunContext) -> list[str]:
    """When a rendered WAV floor already exists, omit seated lines without pickup.

    Heals and air-script passes can revive high-severity omitted lines into seats.
    Once enough pickup stems exist to meet ``min_synthetic_vo_lines``, prefer those
    and unseat the rest so G1/EDL do not demand fresh Chatterbox mid-delivery.

    Under soft/hard freeze, clamp is a seat mutation — require gate / one-shot token.
    """
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    try:
        gap = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return []
    if not isinstance(gap, dict):
        return []
    out, unseated = clamp_hosted_seats_docs(ctx, gap, apply_freeze_gate=True)
    if not unseated:
        return []
    ctx.write_json("understanding/gap_report.json", out, stage_key=_gap_report_owner(ctx))
    try:
        from interview_mux.execution_contract import reconcile_execution_contract

        reconcile_execution_contract(ctx, reason="clamp_hosted_seats_to_rendered_wavs")
    except Exception:
        pass
    # Mirror into pending shadows so stale incomplete stages cannot re-expand seats.
    try:
        import shutil

        gap_dest = ctx.path("understanding/gap_report.json")
        plan_dest = (
            ctx.path("mastering/mastering_plan.json")
            if ctx.artifact_exists("mastering/mastering_plan.json")
            else None
        )
        pending_root = ctx.run_dir / ".pending_writes"
        if pending_root.is_dir():
            for stage_dir in pending_root.iterdir():
                if not stage_dir.is_dir():
                    continue
                for rel, src in (
                    (("understanding", "gap_report.json"), gap_dest),
                    (("mastering", "mastering_plan.json"), plan_dest),
                ):
                    if src is None or not src.is_file():
                        continue
                    candidate = stage_dir.joinpath(*rel)
                    if candidate.is_file():
                        shutil.copy2(src, candidate)
    except Exception:
        pass
    return unseated


def _is_skip_omit_violation(issue: str) -> bool:
    text = str(issue or "")
    return "skip/omit" in text or "both seated and omitted" in text


def seams_contract_remaining(ctx: RunContext) -> list[str]:
    """Post-seams drift that must refuse done (not missing WAV, not F3 skip/omit)."""
    violations = validate_vo_contract(ctx)
    return [
        v
        for v in violations
        if "missing WAV" not in v
        and "missing wav" not in v.lower()
        and not _is_skip_omit_violation(v)
    ]


def sync_vo_contract_after_layup(ctx: RunContext) -> list[str]:
    """R10c: align gap_report, vo_seats, and omit ledger after layup/seams.

    Missing WAVs are expected here — ``vo_synthesize`` renders them. Post-layup
    only fails closed on seat/omit flag drift. When a rendered floor already
    exists, clamp away non-WAV seats so delivery heals cannot expand G1.

    F3: omit-wins unseat happens before hosted-floor reseat. Leftover seated
    skip/omit is omitted again and does not block layup (3C proceed).
    """
    from interview_mux.air_script import persist_air_script_omits_on_gap_report

    try:
        from interview_mux.media_ip_cta import omit_locked_degraded_cta_scraps

        dropped = omit_locked_degraded_cta_scraps(ctx)
        if dropped:
            ctx.log(
                "layup producer omitted locked CTA scrap(s): " + ",".join(dropped[:8]),
                level="info",
                stage="nugget_layup_compose",
            )
    except Exception:
        pass
    persist_air_script_omits_on_gap_report(ctx)
    # Stamp skip_omit_unseat + unseat before floor reseat so omit-wins sticks.
    repair_vo_contract_drift(ctx)
    reseated = ensure_hosted_framing_vo_seats(ctx)
    if reseated:
        ctx.log(
            f"hosted framing reseated {len(reseated)} VO line(s) to meet floor: "
            f"{reseated[:6]}",
            level="info",
            stage="nugget_layup_compose",
        )
    clamped = clamp_hosted_seats_to_rendered_wavs(ctx)
    if clamped:
        ctx.log(
            f"hosted framing clamped {len(clamped)} non-WAV seat(s) after rendered floor: "
            f"{clamped[:6]}",
            level="info",
            stage="nugget_layup_compose",
        )
    violations = validate_vo_contract(ctx)
    if violations:
        # Omit/skip on gap wins over stale seats — unseat, do not force-synth.
        repair_vo_contract_drift(ctx)
        # Floor may reseat *new* lines; omit-wins reasons stay omitted.
        ensure_hosted_framing_vo_seats(ctx)
        clamp_hosted_seats_to_rendered_wavs(ctx)
        violations = validate_vo_contract(ctx)
    leftover = [v for v in violations if _is_skip_omit_violation(v)]
    if leftover:
        repair_vo_contract_drift(ctx)
        violations = [
            v for v in validate_vo_contract(ctx) if not _is_skip_omit_violation(v)
        ]
    return [
        v
        for v in violations
        if "missing WAV" not in v and "missing wav" not in v.lower()
    ]


def _unseat_ineligible_plan_seats(ctx: RunContext) -> list[str]:
    """Write vo_seats even when reconcile freeze-blocks (1A omit-wins)."""
    if not ctx.artifact_exists("mastering/mastering_plan.json"):
        return []
    from interview_mux.air_script import gap_line_air_eligible
    from interview_mux.mastering_plan_loader import load_plan_raw

    by_line: dict[str, dict[str, Any]] = {}
    gap_doc: dict[str, Any] | None = None
    if ctx.artifact_exists("understanding/gap_report.json"):
        gap = ctx.read_json("understanding/gap_report.json")
        if isinstance(gap, dict):
            gap_doc = gap
        for row in (gap.get("interviewer_lines") or []) if isinstance(gap, dict) else []:
            if not isinstance(row, dict):
                continue
            lid = str(row.get("line_id") or "").strip()
            if lid:
                by_line[lid] = row
    plan = dict(load_plan_raw(ctx) or {})
    script = dict(plan.get("air_script") or {})
    seats = dict(script.get("vo_seats") or {})
    seated = [str(x) for x in (seats.get("seated_line_ids") or []) if x]
    omitted = [str(x) for x in (seats.get("omitted_line_ids") or []) if x]
    drop: list[str] = []
    for lid in seated:
        row = by_line.get(lid)
        if row is None or not gap_line_air_eligible(row, gap_report=gap_doc):
            drop.append(lid)
    if not drop:
        return []
    drop_set = set(drop)
    new_seated = [x for x in seated if x not in drop_set]
    for lid in drop:
        if lid not in omitted:
            omitted.append(lid)
    seats["seated_line_ids"] = new_seated
    seats["omitted_line_ids"] = [o for o in omitted if o not in set(new_seated)]
    script["vo_seats"] = seats
    plan["air_script"] = script
    _persist_seat_repair(ctx, plan, reason="air_script_gap_omit_sync")
    return drop


def _persist_seat_repair(ctx: RunContext, plan: dict[str, Any], *, reason: str) -> bool:
    """Land a seat repair on the mastering plan under the seat owner's key.

    Seat truth is required state: adjudicate and synthesis compare it with
    the gap report and refuse a mismatch (ISSUES 101). A repair from a
    consumer stage therefore presents the seat owner's key
    (`air_contract_sanitize`, the precedent in `_commit_hosted_floor_gap`) and its
    End-A reason, so neither the ownership table nor the seat freeze turns
    it into a silent skip. Returns False only when the freeze refuses.
    """
    from interview_mux.seat_authority import persist_frozen_seat_doc

    landed = persist_frozen_seat_doc(
        ctx,
        "mastering/mastering_plan.json",
        plan,
        reason=reason,
        skip_handoff=True,
        stage_key="air_contract_sanitize",
    )
    if not landed:
        ctx.log(
            f"vo_contract: seat repair {reason} held by the seat freeze (not End-A)",
            level="warning",
            stage="vo_contract",
        )
    return bool(landed)


def repair_vo_contract_drift(ctx: RunContext) -> list[str]:
    """Align seats with gap omit/skip — policy omit stays; WAV/bind beats process omit.

    Ladder: policy CTA/waive stay off air; omitted + stem present reseats unless
    policy; seated + skip without WAV stamps ``skip_omit_unseat`` so floor cannot
    revive intentional skips. Process ``seated_bind_synth_failed`` never blocks
    WAV reseat.
    """
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    from interview_mux.air_script import gap_line_air_eligible
    from interview_mux.execution_contract import reconcile_execution_contract
    from interview_mux.opening_orientation import is_episode_orientation

    gap = ctx.read_json("understanding/gap_report.json")
    seated, omitted = _load_seated_omitted(ctx)
    changed: list[str] = []
    reseat_wav: list[str] = []
    lines: list[dict[str, Any]] = []
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if not gap_line_air_eligible(row, gap_report=gap):
            kept = dict(row)
            # Omitted + rendered WAV: reseat unless durable policy omit.
            reason = str(kept.get("skip_reason_code") or "").strip().lower()
            allow_wav_reseat = not policy_omit_skip_reason(kept, gap_report=gap)
            if (
                lid
                and lid in omitted
                and lid not in seated
                and _gap_row_has_pickup_stem(ctx, row)
                and allow_wav_reseat
            ):
                kept = ensure_gap_line_on_air(
                    kept, force_bind_synth_failed=True, gap_report=gap
                )
                reseat_wav.append(lid)
                lines.append(kept)
                changed.append(lid)
                continue
            if lid and lid in seated:
                # Seated + ineligible without WAV: stamp intentional unseat.
                # If WAV is present and not policy, reseat instead (bind-first).
                if _gap_row_has_pickup_stem(ctx, row) and not policy_omit_skip_reason(
                    kept, gap_report=gap
                ):
                    kept = ensure_gap_line_on_air(
                        kept, force_bind_synth_failed=True, gap_report=gap
                    )
                    reseat_wav.append(lid)
                    lines.append(kept)
                    changed.append(lid)
                    continue
                if reason not in OMIT_WINS_REASON_CODES and reason not in {
                    "seated_bind_synth_failed"
                }:
                    reason = "skip_omit_unseat"
                if reason == "seated_bind_synth_failed":
                    reason = "skip_omit_unseat"
                kept = mark_gap_line_not_on_air(
                    kept,
                    reason_code=reason,
                    ctx=ctx,
                    gap_report=gap,
                    peer_lines=list(gap.get("interviewer_lines") or []),
                )
                if kept.get("skipped_optional") and kept.get("air_script_omit"):
                    changed.append(lid)
            elif not (kept.get("skipped_optional") and kept.get("air_script_omit")):
                kept = mark_gap_line_not_on_air(
                    kept,
                    reason_code=str(
                        kept.get("skip_reason_code") or "air_script_omit_sync"
                    ),
                    ctx=ctx,
                    gap_report=gap,
                    peer_lines=list(gap.get("interviewer_lines") or []),
                )
                if lid and kept.get("skipped_optional") and kept.get("air_script_omit"):
                    changed.append(lid)
            lines.append(kept)
            continue
        if lid in omitted and lid not in seated:
            # WAV already on disk → reseat unless policy (omit seat lagged synth).
            if (
                lid
                and _gap_row_has_pickup_stem(ctx, row)
                and not policy_omit_skip_reason(row, gap_report=gap)
            ):
                reseat_wav.append(lid)
                lines.append(
                    ensure_gap_line_on_air(
                        row, force_bind_synth_failed=True, gap_report=gap
                    )
                )
                changed.append(lid)
                continue
            stamped = mark_gap_line_not_on_air(
                row,
                reason_code="air_script_omit_sync",
                ctx=ctx,
                gap_report=gap,
                peer_lines=list(gap.get("interviewer_lines") or []),
            )
            lines.append(stamped)
            if stamped.get("skipped_optional") and stamped.get("air_script_omit"):
                changed.append(lid)
            continue
        if lid in seated and str(row.get("delivery") or "").lower() == "synthesize":
            # On-air seat with no omit flags — leave as-is.
            lines.append(dict(row))
        elif is_episode_orientation(row) and lid in seated:
            lines.append(dict(row))
        elif lid in omitted or lid not in seated:
            if not row.get("skipped_optional"):
                stamped = mark_gap_line_not_on_air(
                    row,
                    reason_code="air_script_omit_sync",
                    ctx=ctx,
                    gap_report=gap,
                    peer_lines=list(gap.get("interviewer_lines") or []),
                )
                lines.append(stamped)
                if stamped.get("skipped_optional") and stamped.get("air_script_omit"):
                    changed.append(lid)
            else:
                lines.append(dict(row))
        else:
            lines.append(dict(row))
    if changed or lines:
        out = dict(gap)
        out["interviewer_lines"] = lines
        try:
            from interview_mux.seat_authority import persist_frozen_seat_doc

            if not persist_frozen_seat_doc(
                ctx,
                "understanding/gap_report.json",
                out,
                reason="stamp_gap_omit_flags",
                skip_handoff=True,
                stage_key=_gap_report_owner(ctx),
            ):
                ctx.write_json(
                    "understanding/gap_report.json", out, stage_key=_gap_report_owner(ctx)
                )
        except Exception:
            ctx.write_json("understanding/gap_report.json", out, stage_key=_gap_report_owner(ctx))
    if reseat_wav and ctx.artifact_exists("mastering/mastering_plan.json"):
        from interview_mux.mastering_plan_loader import load_plan_raw
        from interview_mux.seat_authority import persist_frozen_seat_doc

        plan = dict(load_plan_raw(ctx) or {})
        script = dict(plan.get("air_script") or {})
        seats = dict(script.get("vo_seats") or {})
        cur_seated = [str(x) for x in (seats.get("seated_line_ids") or []) if x]
        cur_omitted = [str(x) for x in (seats.get("omitted_line_ids") or []) if x]
        for lid in reseat_wav:
            if lid not in cur_seated:
                cur_seated.append(lid)
            cur_omitted = [o for o in cur_omitted if o != lid]
        seats["seated_line_ids"] = cur_seated
        seats["omitted_line_ids"] = cur_omitted
        script["vo_seats"] = seats
        plan["air_script"] = script
        persist_frozen_seat_doc(
            ctx,
            "mastering/mastering_plan.json",
            plan,
            reason="reseated_active_hosted_vo_for_wav",
            skip_handoff=True,
        )
    # Unseat orphan ids that seats still cite but gap_report no longer has.
    gap_ids = {
        str(r.get("line_id") or "").strip()
        for r in lines
        if isinstance(r, dict) and r.get("line_id")
    }
    orphan_seated = sorted(lid for lid in seated if lid and lid not in gap_ids)
    if orphan_seated and ctx.artifact_exists("mastering/mastering_plan.json"):
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = dict(load_plan_raw(ctx) or {})
        script = dict(plan.get("air_script") or {})
        seats = dict(script.get("vo_seats") or {})
        cur_seated = [str(x) for x in (seats.get("seated_line_ids") or []) if x]
        cur_omitted = [str(x) for x in (seats.get("omitted_line_ids") or []) if x]
        new_seated = [x for x in cur_seated if x not in set(orphan_seated)]
        for lid in orphan_seated:
            if lid not in cur_omitted:
                cur_omitted.append(lid)
            changed.append(lid)
        seats["seated_line_ids"] = new_seated
        seats["omitted_line_ids"] = [o for o in cur_omitted if o not in set(new_seated)]
        script["vo_seats"] = seats
        plan["air_script"] = script
        _persist_seat_repair(ctx, plan, reason="drop_seated_missing_from_gap")
    # Rebuild vo_seats from gap so omitted lines are not synthesized downstream.
    # Catastrophe reason unlocks freeze; explicit unseat covers freeze fail-closed.
    try:
        reconcile_execution_contract(ctx, reason="catastrophe_skip_omit_unseat")
    except Exception:
        pass
    changed.extend(_unseat_ineligible_plan_seats(ctx))
    # After omit stamps, demote high gaps that no longer have audible covers so
    # high_gap_unframed cannot thrash compose while omit-wins holds (exec_13170).
    try:
        from interview_mux.high_gap_vo import demote_uncovered_high_gaps

        demote_uncovered_high_gaps(ctx, origin="post_commit_uncovered_high")
    except Exception:
        pass
    return list(dict.fromkeys(x for x in changed if x))


def _gap_report_owner(ctx: RunContext) -> str:
    """Stage key the gap report accepts for a repair write right now (see entry 36)."""
    from interview_mux.artifact_ownership import gap_report_body_owner

    try:
        prior = ctx.read_json("understanding/gap_report.json") if ctx.artifact_exists("understanding/gap_report.json") else None
    except Exception:
        prior = None
    return gap_report_body_owner(prior)
