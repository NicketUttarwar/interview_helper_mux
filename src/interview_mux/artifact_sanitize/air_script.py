"""Air-contract sanitizer — seats ↔ gap flags ↔ omit ledger (W3).

Sole authority surface for VO seating. Gap W1 must not clamp/seat.
"""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.halt import sanitize_refused_message
from interview_mux.artifact_sanitize.reentry import (
    in_sanitize_reentry,
    sanitize_reentry_guard,
    sanitary_content_hash,
    stamp_sanitize_meta,
)
from interview_mux.artifact_sanitize.types import SanitizeResult

PLAN_REL = "mastering/mastering_plan.json"
OMIT_REL = "understanding/omit_ledger.json"
GAP_REL = "understanding/gap_report.json"

_HOSTED_FLOOR_UNMET = (
    "hosted_vo_floor_unmet — resume nugget_layup_compose: "
    "G-Framing Yes requires synthetic host lines; hard freeze blocks floor reseat"
)
_HOSTED_FLOOR_UNSATISFIABLE = (
    "hosted_vo_floor_unsatisfiable — escalate once: "
    "G-Framing Yes floor unmet under hard freeze; do not invent or recompose"
)
_HOSTED_WAV_COVERAGE = (
    "hosted_vo_wav_coverage — resume vo_synthesize: "
    "G-Framing Yes has active host lines but WAV coverage below floor"
)

_AUTO_COMMIT_ACTIONS = frozenset(
    {
        "protect_orientation_from_omit",
        "stamp_gap_omit_flags",
        "drop_seated_missing_from_gap",
        "clamp_hosted_seats_to_rendered_wavs",
        "normalize_omit_ids",
        "dedupe_seated",
        "drop_seated_intersect_omitted",
        "reseated_active_hosted_vo_for_wav",
        "revive_pre_synth_floor_soft_omit",
    }
)

# Advisory-only actions: progress-floor continue / refuse notes. Never dirties
# air_contract_sanitary_errors or post-commit dry re-sanitize.
_ADVISORY_ONLY_ACTIONS = frozenset(
    {
        "hosted_vo_floor_aspirational_continue",
    }
)


def _strip_advisory_actions(
    actions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [
        a
        for a in (actions or [])
        if str(a.get("action") or "") not in _ADVISORY_ONLY_ACTIONS
        and not str(a.get("action") or "").endswith("_refused_hard_freeze")
    ]

_SYNTH_DELIVERIES = frozenset(
    {"synthesize", "record", "voice_clone", "chatterbox", ""}
)


def _air_script(plan: dict[str, Any]) -> dict[str, Any]:
    air = plan.get("air_script")
    return air if isinstance(air, dict) else {}


def _vo_seats(plan: dict[str, Any]) -> dict[str, Any]:
    air = _air_script(plan)
    seats = air.get("vo_seats")
    return seats if isinstance(seats, dict) else {}


def _load_artifact(
    ctx: Any,
    rel: str,
    *,
    supplied: dict[str, Any] | None,
    errors: list[str],
) -> dict[str, Any]:
    """Load JSON artifact; exist-but-unreadable → error (never invent empty)."""
    if isinstance(supplied, dict) and supplied:
        return dict(supplied)
    if not ctx.artifact_exists(rel):
        return {}
    try:
        loaded = ctx.read_json(rel)
    except Exception as exc:
        errors.append(f"artifact_unreadable:{rel}:{exc}")
        return {}
    if not isinstance(loaded, dict):
        errors.append(f"artifact_unreadable:{rel}:invalid_type")
        return {}
    return loaded


def _is_active_synth_row(row: dict[str, Any]) -> bool:
    if row.get("skipped_optional") or row.get("omit") or row.get("air_script_omit"):
        return False
    delivery = str(row.get("delivery") or "synthesize").strip().lower() or "synthesize"
    return delivery in _SYNTH_DELIVERIES


def _count_active_synth(lines: list[Any]) -> int:
    return sum(1 for row in lines if isinstance(row, dict) and _is_active_synth_row(row))


def _count_wav_backed_active(ctx: Any, lines: list[Any]) -> int:
    try:
        from interview_mux.opening_orientation import is_episode_orientation
        from interview_mux.vo_contract import _gap_row_has_pickup_stem
    except Exception:
        return 0
    n = 0
    for row in lines:
        if not isinstance(row, dict) or not _is_active_synth_row(row):
            continue
        try:
            if is_episode_orientation(row):
                continue
        except Exception:
            pass
        try:
            if _gap_row_has_pickup_stem(ctx, row):
                n += 1
        except Exception:
            pass
    return n


def _apply_seats(
    plan: dict[str, Any],
    seated: list[str],
    omitted: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    air = dict(_air_script(plan))
    seats = dict(_vo_seats(plan))
    seats["seated_line_ids"] = list(seated)
    seats["omitted_line_ids"] = [o for o in omitted if o not in set(seated)]
    air["vo_seats"] = seats
    plan = dict(plan)
    plan["air_script"] = air
    return plan, air, seats


def sanitize_air_contract(
    ctx: Any, docs: dict[str, dict[str, Any]] | None = None
) -> SanitizeResult:
    """Sanitize the seats/gap-flags/omit triple. docs may supply plan/gap/omit."""
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    supplied = docs or {}

    plan = _load_artifact(
        ctx, PLAN_REL, supplied=supplied.get("plan"), errors=errors
    )
    gap = _load_artifact(
        ctx, GAP_REL, supplied=supplied.get("gap"), errors=errors
    )
    omit = _load_artifact(
        ctx, OMIT_REL, supplied=supplied.get("omit"), errors=errors
    )
    if errors:
        return SanitizeResult(
            doc=plan or {},
            actions=actions,
            ok=False,
            errors=errors,
            artifact_rel=PLAN_REL,
            metrics={"actions": 0},
        )

    air = dict(_air_script(plan))
    seats = dict(_vo_seats(plan))
    seated = [str(x) for x in (seats.get("seated_line_ids") or []) if x]
    omitted = [str(x) for x in (seats.get("omitted_line_ids") or []) if x]

    # Dedupe seated/omitted; seated wins over omitted
    seen_s: set[str] = set()
    seated_u: list[str] = []
    for s in seated:
        if s in seen_s:
            actions.append({"action": "dedupe_seated", "line_id": s})
            continue
        seen_s.add(s)
        seated_u.append(s)
    seated = seated_u
    omitted = [o for o in omitted if o not in seen_s]
    both = set(seated) & set(omitted)
    if both:
        omitted = [o for o in omitted if o not in both]
        actions.append(
            {"action": "drop_seated_intersect_omitted", "ids": sorted(both)[:24]}
        )

    plan, air, seats = _apply_seats(plan, seated, omitted)

    lines = gap.get("interviewer_lines")
    if isinstance(lines, list) and omitted:
        omit_set = set(omitted)
        protect_floor: set[str] = set()
        try:
            from interview_mux.gap_fill_eligibility import (
                hosted_framing_requires_synthetic_vo,
                min_synthetic_vo_lines,
            )

            if hosted_framing_requires_synthetic_vo(ctx):
                need = min_synthetic_vo_lines(ctx)
                wav_backed = _count_wav_backed_active(ctx, lines)
                # WAV floor already met → clamp will shrink non-WAV; never reseat.
                if wav_backed >= need:
                    protect_floor = set()
                else:
                    active_now = _count_active_synth(lines)
                    would_stamp = [
                        str(row.get("line_id") or "")
                        for row in lines
                        if isinstance(row, dict)
                        and str(row.get("line_id") or "") in omit_set
                        and _is_active_synth_row(row)
                        and str(row.get("line_id") or "")
                    ]

                    def _protect_rank(lid: str) -> tuple[int, str]:
                        row = next(
                            (
                                r
                                for r in lines
                                if isinstance(r, dict)
                                and str(r.get("line_id") or "") == lid
                            ),
                            {},
                        )
                        orient = (
                            0
                            if (
                                row.get("episode_orientation")
                                or "orientation" in lid.lower()
                            )
                            else 1
                        )
                        return (orient, lid)

                    would_stamp_sorted = sorted(set(would_stamp), key=_protect_rank)
                    active_after = active_now - len(would_stamp_sorted)
                    if active_after < need or wav_backed < need:
                        # Prefer enough seats to close WAV floor when copy already
                        # exists on gap (exec_13177: active≥need but wav_backed=1).
                        protect_n = max(need - active_after, need - wav_backed)
                        protect_floor = set(would_stamp_sorted[:protect_n])
                if protect_floor:
                    refuse_reseat = False
                    try:
                        from interview_mux.seat_authority import (
                            hard_freeze_blocks_action,
                        )

                        refuse_reseat = hard_freeze_blocks_action(
                            ctx, "protect_hosted_vo_floor_reseat"
                        )
                    except Exception:
                        refuse_reseat = False
                    if refuse_reseat and active_now >= need:
                        # Hard freeze forbids inventing seats, but reseating
                        # already-active gap lines is WAV paperwork (End-A).
                        omitted = [o for o in omitted if o not in protect_floor]
                        for lid in sorted(protect_floor):
                            if lid not in seated:
                                seated.append(lid)
                        omit_set = set(omitted)
                        plan, air, seats = _apply_seats(plan, seated, omitted)
                        actions.append(
                            {
                                "action": "reseated_active_hosted_vo_for_wav",
                                "ids": sorted(protect_floor)[:24],
                                "wav_backed": wav_backed,
                                "active": active_now,
                                "need": need,
                            }
                        )
                        # Do not set errors here — commit_air_contract refuses
                        # writes when ok=False. Pin vo_synthesize via action.
                    elif refuse_reseat:
                        actions.append(
                            {
                                "action": (
                                    "protect_hosted_vo_floor_reseat_refused_hard_freeze"
                                ),
                                "ids": sorted(protect_floor)[:24],
                            }
                        )
                        # True shortage under hard freeze: progress floors →
                        # advisory-continue; legacy → unsatisfiable + sanitize error.
                        aspirational = False
                        try:
                            from interview_mux.hosted_vo_authority import (
                                may_aspirational_proceed,
                            )
                            from interview_mux.floor_progress import (
                                hosted_vo_aspirational,
                                proceed_on_floor_miss,
                            )

                            # Never aspirational at active==0; PARTIAL identity or
                            # config aspirational when local sanitize count >= 1.
                            if int(active_now or 0) >= 1 and (
                                may_aspirational_proceed(ctx)
                                or hosted_vo_aspirational(ctx)
                            ):
                                aspirational = True
                                proceed_on_floor_miss(
                                    ctx,
                                    gate_id="hosted_vo_floor",
                                    have=active_now,
                                    need=need,
                                    pool_exhausted=True,
                                    extra={
                                        "source": "sanitize_hard_freeze_shortage",
                                        "protect_ids": sorted(protect_floor)[:12],
                                    },
                                )
                                actions.append(
                                    {
                                        "action": "hosted_vo_floor_aspirational_continue",
                                        "need": need,
                                        "active": active_now,
                                    }
                                )
                        except Exception:
                            aspirational = False
                        if not aspirational:
                            try:
                                from interview_mux.nugget_layup import (
                                    stamp_hosted_vo_floor_unsatisfiable,
                                )

                                stamp_hosted_vo_floor_unsatisfiable(
                                    ctx, need=need, active=active_now
                                )
                            except Exception:
                                pass
                            errors.append(
                                f"{_HOSTED_FLOOR_UNSATISFIABLE} (need≥{need}, active={active_now})"
                            )
                        # Do not stamp omit on floor-protected ids — that would
                        # shrink active VO further under hard freeze.
                        omit_set -= protect_floor
                    else:
                        omitted = [o for o in omitted if o not in protect_floor]
                        for lid in sorted(protect_floor):
                            if lid not in seated:
                                seated.append(lid)
                        omit_set = set(omitted)
                        plan, air, seats = _apply_seats(plan, seated, omitted)
                        actions.append(
                            {
                                "action": "protect_hosted_vo_floor_reseat",
                                "ids": sorted(protect_floor)[:24],
                            }
                        )
        except Exception as exc:
            actions.append(
                {"action": "protect_hosted_vo_floor_failed", "error": str(exc)[:120]}
            )
            errors.append(f"protect_hosted_vo_floor_failed:{exc}")

        new_lines = []
        stamped = 0
        reseated_gate = 0
        for row in lines:
            if not isinstance(row, dict):
                continue
            lid = str(row.get("line_id") or "")
            if lid in omit_set and not (
                row.get("skipped_optional")
                or row.get("omit")
                or row.get("air_script_omit")
            ):
                from interview_mux.vo_contract import mark_gap_line_not_on_air

                stamped_row = mark_gap_line_not_on_air(
                    row,
                    reason_code=str(
                        row.get("skip_reason_code") or "air_script_omit_sync"
                    ),
                    ctx=ctx,
                    gap_report=gap,
                    peer_lines=lines,
                )
                if stamped_row.get("skipped_optional") and stamped_row.get(
                    "air_script_omit"
                ):
                    row = stamped_row
                    stamped += 1
                else:
                    # Pre-synth floor gate refused — keep on air / reseat.
                    if lid not in seated:
                        seated.append(lid)
                    omitted = [o for o in omitted if o != lid]
                    reseated_gate += 1
            new_lines.append(row)
        if stamped or reseated_gate:
            gap = dict(gap)
            gap["interviewer_lines"] = new_lines
            if stamped:
                actions.append({"action": "stamp_gap_omit_flags", "count": stamped})
            if reseated_gate:
                actions.append(
                    {
                        "action": "pre_synth_floor_gate_kept_on_air",
                        "count": reseated_gate,
                    }
                )
            omit_set = set(omitted)
            plan, air, seats = _apply_seats(plan, seated, omitted)

    # Orientation protect — never strip required orientation from omit ledger.
    try:
        from interview_mux.air_script import _orientation_line_waived
        from interview_mux.opening_orientation import is_episode_orientation

        orient_ids: set[str] = set()
        waived_orient: set[str] = set()
        for row in gap.get("interviewer_lines") or []:
            if not isinstance(row, dict):
                continue
            if not (
                row.get("episode_orientation")
                or is_episode_orientation(row)
                or "orientation" in str(row.get("line_id") or "").lower()
            ):
                continue
            lid = str(row.get("line_id") or "")
            if not lid:
                continue
            orient_ids.add(lid)
            try:
                if _orientation_line_waived(row, gap):
                    waived_orient.add(lid)
            except Exception:
                pass
        if seats.get("orientation_id"):
            orient_ids.add(str(seats.get("orientation_id")))
        orient_ids -= waived_orient
    except Exception:
        orient_ids = set()
        for row in gap.get("interviewer_lines") or []:
            if isinstance(row, dict) and row.get("episode_orientation"):
                lid = str(row.get("line_id") or "")
                if lid:
                    orient_ids.add(lid)

    entries = omit.get("entries")
    if isinstance(entries, list) and orient_ids:
        kept = []
        restored = 0
        for row in entries:
            if not isinstance(row, dict):
                kept.append(row)
                continue
            subj = str(
                row.get("subject_id") or row.get("segment_id") or row.get("id") or ""
            )
            active = str(row.get("status") or "active").lower() in {"", "active"}
            if (
                subj in orient_ids
                and active
                and str(row.get("kind") or "").startswith("gap")
            ):
                restored += 1
                actions.append(
                    {"action": "protect_orientation_from_omit", "subject_id": subj}
                )
                continue
            kept.append(row)
        if restored:
            omit = dict(omit)
            omit["entries"] = kept

    # In-memory clamp (no disk / reconcile) — W3 owns the write at commit.
    try:
        from interview_mux.vo_contract import clamp_hosted_seats_docs

        gap_clamped, unseated = clamp_hosted_seats_docs(
            ctx, gap, apply_freeze_gate=False
        )
        if unseated:
            gap = gap_clamped
            unseat_set = set(unseated)
            seated = [s for s in seated if s not in unseat_set]
            for lid in unseated:
                if lid not in omitted:
                    omitted.append(lid)
            plan, air, seats = _apply_seats(plan, seated, omitted)
            actions.append(
                {
                    "action": "clamp_hosted_seats_to_rendered_wavs",
                    "unseated": list(unseated)[:24],
                }
            )
            # Clamp may expand omitted after stamp_gap_omit_flags — sync gap flags
            # so vo_contract cannot thrash on omitted-without-flags (exec_13177).
            # Pre-synth floor: may_soft_omit_hosted_line refuses process omit below
            # need (exec_13196) — do not hollow-only band-aid.
            try:
                from interview_mux.vo_contract import mark_gap_line_not_on_air

                unseat_set = set(unseated)
                new_lines: list[Any] = []
                stamped_u = 0
                kept_gate = 0
                for row in gap.get("interviewer_lines") or []:
                    if not isinstance(row, dict):
                        new_lines.append(row)
                        continue
                    lid = str(row.get("line_id") or "")
                    if (
                        lid in unseat_set
                        and not (
                            row.get("skipped_optional")
                            or row.get("omit")
                            or row.get("air_script_omit")
                        )
                    ):
                        stamped_row = mark_gap_line_not_on_air(
                            row,
                            reason_code="air_script_omit_sync",
                            ctx=ctx,
                            gap_report=gap,
                            peer_lines=gap.get("interviewer_lines") or [],
                        )
                        if stamped_row.get("skipped_optional") and stamped_row.get(
                            "air_script_omit"
                        ):
                            new_lines.append(stamped_row)
                            stamped_u += 1
                        else:
                            new_lines.append(row)
                            kept_gate += 1
                            if lid not in seated:
                                seated.append(lid)
                            omitted = [o for o in omitted if o != lid]
                    else:
                        new_lines.append(row)
                if stamped_u or kept_gate:
                    gap = dict(gap)
                    gap["interviewer_lines"] = new_lines
                    if stamped_u:
                        actions.append(
                            {"action": "stamp_gap_omit_flags", "count": stamped_u}
                        )
                    if kept_gate:
                        actions.append(
                            {
                                "action": "protect_pre_synth_floor_from_omit_stamp",
                                "count": kept_gate,
                            }
                        )
                        plan, air, seats = _apply_seats(plan, seated, omitted)
            except Exception:
                pass
    except Exception as exc:
        actions.append({"action": "clamp_failed", "error": str(exc)[:120]})
        errors.append(f"clamp_failed:{exc}")

    # Revive soft-omit below floor before synth (SSOT full need, not hollow-only).
    try:
        from interview_mux.gap_fill_eligibility import (
            hosted_framing_requires_synthetic_vo,
            min_synthetic_vo_lines,
        )
        from interview_mux.hosted_vo_authority import vo_synth_era_complete
        from interview_mux.vo_contract import ensure_gap_line_on_air, omit_wins_skip_reason

        if (
            not vo_synth_era_complete(ctx)
            and hosted_framing_requires_synthetic_vo(ctx)
        ):
            active = _count_active_synth(gap.get("interviewer_lines") or [])
            need_n = int(min_synthetic_vo_lines(ctx) or 0)
            if need_n and active < need_n:
                revived: list[str] = []
                new_lines = []
                for row in gap.get("interviewer_lines") or []:
                    if not isinstance(row, dict):
                        new_lines.append(row)
                        continue
                    soft = bool(
                        row.get("skipped_optional")
                        or row.get("omit")
                        or row.get("air_script_omit")
                    )
                    text = str(row.get("text") or "").strip()
                    raw = row.get("delivery")
                    delivery = (
                        "synthesize" if raw is None else str(raw).strip().lower()
                    )
                    if (
                        soft
                        and text
                        and delivery
                        in {"synthesize", "chatterbox", "record", "mlx_audio"}
                        and active < need_n
                        and not omit_wins_skip_reason(row, gap_report=gap)
                    ):
                        row = ensure_gap_line_on_air(row, gap_report=gap)
                        revived.append(str(row.get("line_id") or ""))
                        lid = str(row.get("line_id") or "")
                        if lid and lid not in seated:
                            seated.append(lid)
                        if lid and lid in omitted:
                            omitted = [x for x in omitted if x != lid]
                        active = _count_active_synth(new_lines + [row])
                    new_lines.append(row)
                if revived:
                    gap = dict(gap)
                    gap["interviewer_lines"] = new_lines
                    plan, air, seats = _apply_seats(plan, seated, omitted)
                    actions.append(
                        {
                            "action": "revive_pre_synth_floor_soft_omit",
                            "ids": revived[:24],
                        }
                    )
    except Exception:
        pass

    # Drop seated synthesize lines missing from gap (orphan seats).
    gap_ids = {
        str(r.get("line_id") or "")
        for r in (gap.get("interviewer_lines") or [])
        if isinstance(r, dict)
    }
    if gap_ids:
        kept_seated: list[str] = []
        for sid in seated:
            if sid not in gap_ids:
                actions.append(
                    {"action": "drop_seated_missing_from_gap", "line_id": sid}
                )
                if sid not in omitted:
                    omitted.append(sid)
                continue
            kept_seated.append(sid)
        if len(kept_seated) != len(seated):
            seated = kept_seated
            plan, air, seats = _apply_seats(plan, seated, omitted)

    for sid in seated:
        if gap_ids and sid not in gap_ids:
            errors.append(f"seated_missing_from_gap:{sid}")

    # After mutations: if hosted floor still unmet → advisory or pin layup.
    try:
        from interview_mux.gap_fill_eligibility import (
            hosted_framing_requires_synthetic_vo,
            min_synthetic_vo_lines,
        )

        if hosted_framing_requires_synthetic_vo(ctx) and gap_ids:
            need = min_synthetic_vo_lines(ctx)
            active = _count_active_synth(gap.get("interviewer_lines") or [])
            if active < need and not any(
                "hosted_vo_floor_unmet" in e or "hosted_vo_floor_unsatisfiable" in e
                for e in errors
            ):
                aspirational = False
                try:
                    from interview_mux.hosted_vo_authority import may_aspirational_proceed
                    from interview_mux.floor_progress import (
                        hosted_vo_aspirational,
                        proceed_on_floor_miss,
                    )

                    if int(active or 0) >= 1 and (
                        may_aspirational_proceed(ctx) or hosted_vo_aspirational(ctx)
                    ):
                        aspirational = True
                        proceed_on_floor_miss(
                            ctx,
                            gate_id="hosted_vo_floor",
                            have=active,
                            need=need,
                            pool_exhausted=True,
                            extra={"source": "sanitize_post_mutation"},
                        )
                        actions.append(
                            {
                                "action": "hosted_vo_floor_aspirational_continue",
                                "need": need,
                                "active": active,
                            }
                        )
                except Exception:
                    aspirational = False
                if not aspirational:
                    errors.append(
                        "hosted_vo_floor_unmet — resume nugget_layup_compose: "
                        f"G-Framing Yes requires ≥{need} synthetic host "
                        f"line(s), gap_report has {active}"
                    )
    except Exception:
        pass

    # Normalize top-level omit_segment_ids if present (legacy field)
    omits = plan.get("omit_segment_ids") or plan.get("omitted_segment_ids")
    if isinstance(omits, list):
        cleaned = [str(s) for s in omits if str(s).strip()]
        if cleaned != list(omits):
            key = (
                "omit_segment_ids"
                if "omit_segment_ids" in plan
                else "omitted_segment_ids"
            )
            plan[key] = cleaned
            actions.append({"action": "normalize_omit_ids", "count": len(cleaned)})

    for a in actions:
        name = str(a.get("action") or "")
        if name.endswith("_failed"):
            err = f"{name}:{a.get('error') or 'failed'}"
            if err not in errors:
                errors.append(err)

    plan = stamp_sanitize_meta(
        plan,
        ok=not errors,
        source="artifact_sanitize.air_contract",
        actions_n=len(actions),
    )
    if omit:
        omit = stamp_sanitize_meta(
            omit,
            ok=not errors,
            source="artifact_sanitize.air_contract",
            actions_n=len(actions),
        )

    combined = dict(plan)
    combined["_air_contract_gap"] = gap
    combined["_air_contract_omit"] = omit

    return SanitizeResult(
        doc=combined,
        actions=actions,
        ok=not errors,
        errors=errors,
        artifact_rel=PLAN_REL,
        metrics={
            "actions": len(actions),
            "seated": len(seated),
            "omitted": len(omitted),
        },
    )


def sanitize_mastering_plan(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    """Registry entry for mastering_plan — delegates to air_contract."""
    result = sanitize_air_contract(ctx, {"plan": doc})
    plan = {
        k: v
        for k, v in result.doc.items()
        if not str(k).startswith("_air_contract_")
    }
    return SanitizeResult(
        doc=plan,
        actions=result.actions,
        ok=result.ok,
        errors=result.errors,
        artifact_rel=PLAN_REL,
        metrics=result.metrics,
    )


def sanitize_omit_ledger(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    result = sanitize_air_contract(ctx, {"omit": doc})
    omit = result.doc.get("_air_contract_omit")
    if not isinstance(omit, dict):
        omit = dict(doc)
    return SanitizeResult(
        doc=omit,
        actions=[
            a for a in result.actions if "omit" in str(a.get("action") or "")
        ],
        ok=result.ok,
        errors=result.errors,
        artifact_rel=OMIT_REL,
        metrics=result.metrics,
    )


def _floor_unmet_pin(
    errors: list[str],
    actions: list[dict[str, Any]],
    ctx: Any | None = None,
) -> str | None:
    # Progress-floors advisory continue — no heal pin for count shortfall.
    if any(
        str(a.get("action") or "") == "hosted_vo_floor_aspirational_continue"
        for a in actions
    ):
        return None
    for e in errors:
        if "hosted_vo_wav_coverage" in e:
            return e
        if "hosted_vo_floor_unsatisfiable" in e:
            return e
        if "hosted_vo_floor_unmet" in e:
            return e
    for a in actions:
        if str(a.get("action") or "") != "reseated_active_hosted_vo_for_wav":
            continue
        need = a.get("need")
        active = a.get("active")
        wav_backed = a.get("wav_backed")
        detail = ""
        if need is not None:
            detail = f" (active={active} wav_backed={wav_backed} need≥{need})"
        return f"{_HOSTED_WAV_COVERAGE}{detail}"
    names = {str(a.get("action") or "") for a in actions}
    if "protect_hosted_vo_floor_reseat" in names:
        return (
            "air_contract_needs_sanitize:protect_hosted_vo_floor_reseat"
        )
    if "protect_hosted_vo_floor_reseat_refused_hard_freeze" in names:
        try:
            from interview_mux.floor_progress import hosted_vo_aspirational

            if hosted_vo_aspirational(ctx):
                return None
        except Exception:
            pass
        return _HOSTED_FLOOR_UNSATISFIABLE
    return None


def air_contract_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary
    from interview_mux.artifact_sanitize.reentry import stamp_matches

    if not block_consumers_on_unsanitary():
        return []
    if not ctx.artifact_exists(PLAN_REL):
        return []
    try:
        plan = ctx.read_json(PLAN_REL)
    except Exception as exc:
        return [f"artifact_unreadable:{PLAN_REL}:{exc}"]
    if not isinstance(plan, dict):
        return [f"artifact_unreadable:{PLAN_REL}:invalid_type"]
    result = sanitize_air_contract(ctx)
    if stamp_matches(plan):
        names = {str(a.get("action") or "") for a in (result.actions or [])}
        if result.ok and "protect_hosted_vo_floor_reseat" not in names:
            return []
    if result.ok and not result.actions:
        return []
    if not result.ok:
        pin = _floor_unmet_pin(list(result.errors or []), list(result.actions or []), ctx)
        if pin:
            return [pin]
        return list(result.errors or ["air_contract sanitize refused"])

    actions = list(result.actions or [])
    # Refuse-notes are observational for expand-under-hard-freeze — map to layup pin.
    floor_pin = _floor_unmet_pin([], actions, ctx)
    actions = _strip_advisory_actions(actions)
    try:
        from interview_mux.seat_authority import (
            HARD_FREEZE_FORBIDDEN_ACTIONS,
            hard_freeze_active,
        )

        if hard_freeze_active(ctx):
            if any(
                str(a.get("action") or "") in HARD_FREEZE_FORBIDDEN_ACTIONS
                for a in result.actions or []
            ):
                return [floor_pin or _HOSTED_FLOOR_UNMET]
            actions = [
                a
                for a in actions
                if str(a.get("action") or "") not in HARD_FREEZE_FORBIDDEN_ACTIONS
            ]
    except Exception:
        pass

    # Expand reseat never auto-commits — needs stage (soft) or layup pin (hard).
    if any(
        str(a.get("action") or "") == "protect_hosted_vo_floor_reseat" for a in actions
    ):
        return [
            "air_contract_needs_sanitize:protect_hosted_vo_floor_reseat"
        ]

    if actions and all(
        str(a.get("action") or "") in _AUTO_COMMIT_ACTIONS for a in actions
    ):
        if in_sanitize_reentry(ctx):
            return [
                "air_contract_needs_sanitize:"
                + ",".join(str(a.get("action") or "") for a in actions[:6])
            ]
        committed = commit_air_contract(ctx, reason="auto_sanitary_heal")
        if committed.ok:
            # Wav reseat paperwork committed — still pin vo_synthesize for coverage.
            if floor_pin and "hosted_vo_wav_coverage" in floor_pin:
                return [floor_pin]
            return []
        return list(committed.errors or ["air_contract auto-commit failed"])
    if not actions:
        if floor_pin:
            return [floor_pin]
        return []
    return [
        "air_contract_needs_sanitize:"
        + ",".join(str(a.get("action") or "") for a in actions[:6])
    ]


def _read_hash(ctx: Any, rel: str) -> str:
    if not ctx.artifact_exists(rel):
        return "empty"
    try:
        loaded = ctx.read_json(rel)
    except Exception:
        return "unreadable"
    if not isinstance(loaded, dict):
        return "invalid"
    return sanitary_content_hash(loaded)


def commit_air_contract(ctx: Any, *, reason: str = "") -> SanitizeResult:
    """Sole mutator for seats + gap VO flags + omit ledger VO rows."""
    with sanitize_reentry_guard(ctx) as nested:
        if nested:
            return SanitizeResult(doc={}, ok=True, metrics={"skipped": "reentry"})

        cas_plan = _read_hash(ctx, PLAN_REL)
        cas_gap = _read_hash(ctx, GAP_REL)
        cas_omit = _read_hash(ctx, OMIT_REL)

        before_plan: dict[str, Any] = {}
        if ctx.artifact_exists(PLAN_REL):
            try:
                loaded = ctx.read_json(PLAN_REL)
                if isinstance(loaded, dict):
                    before_plan = loaded
            except Exception as exc:
                return SanitizeResult(
                    doc={},
                    ok=False,
                    errors=[f"artifact_unreadable:{PLAN_REL}:{exc}"],
                    artifact_rel=PLAN_REL,
                )
        before_hash = sanitary_content_hash(before_plan)
        result = sanitize_air_contract(ctx)
        from interview_mux.artifact_sanitize.audit import write_sanitize_audit

        write_sanitize_audit(
            ctx,
            result,
            stage_key="air_contract",
            mode=reason or "commit",
        )
        if not result.ok:
            return result

        # CAS: refuse if on-disk drifted since we started.
        if (
            _read_hash(ctx, PLAN_REL) != cas_plan
            or _read_hash(ctx, GAP_REL) != cas_gap
            or _read_hash(ctx, OMIT_REL) != cas_omit
        ):
            return SanitizeResult(
                doc=result.doc,
                actions=result.actions,
                ok=False,
                errors=["air_contract_cas_conflict"],
                artifact_rel=PLAN_REL,
                metrics=result.metrics,
            )

        plan = {
            k: v
            for k, v in result.doc.items()
            if not str(k).startswith("_air_contract_")
        }
        gap = result.doc.get("_air_contract_gap")
        omit = result.doc.get("_air_contract_omit")
        try:
            from interview_mux.information_packages import ensure_episode_close_on_plan

            plan = ensure_episode_close_on_plan(plan)
        except Exception:
            pass

        # Land Honesty: mastering_plan is air_contract_sanitize's shared primary.
        meta = dict(plan.get("_meta") or {}) if isinstance(plan.get("_meta"), dict) else {}
        meta["producer_stage"] = "air_contract_sanitize"
        plan["_meta"] = meta

        try:
            ctx.write_json(PLAN_REL, plan)
        except Exception as exc:
            return SanitizeResult(
                doc=result.doc,
                actions=result.actions,
                ok=False,
                errors=[f"air_contract_write_failed:{PLAN_REL}:{exc}"],
                artifact_rel=PLAN_REL,
                metrics=result.metrics,
            )
        if isinstance(gap, dict) and gap:
            try:
                ctx.write_json(GAP_REL, gap)
            except Exception as exc:
                return SanitizeResult(
                    doc=result.doc,
                    actions=result.actions,
                    ok=False,
                    errors=[f"air_contract_write_failed:{GAP_REL}:{exc}"],
                    artifact_rel=PLAN_REL,
                    metrics=result.metrics,
                )
        if isinstance(omit, dict) and omit:
            try:
                from interview_mux.omit_ledger import write_omit_ledger

                write_omit_ledger(ctx, omit)
            except Exception:
                try:
                    ctx.write_json(OMIT_REL, omit)
                except Exception as exc:
                    return SanitizeResult(
                        doc=result.doc,
                        actions=result.actions,
                        ok=False,
                        errors=[f"air_contract_write_failed:{OMIT_REL}:{exc}"],
                        artifact_rel=PLAN_REL,
                        metrics=result.metrics,
                    )

        # No terminal disk clamp — already applied in-memory and persisted above.
        after_hash = sanitary_content_hash(plan)
        try:
            from interview_mux.artifact_sanitize.invalidate import (
                maybe_invalidate_after_sanitize,
            )

            maybe_invalidate_after_sanitize(
                ctx,
                PLAN_REL,
                before_hash=before_hash,
                after_hash=after_hash,
                ok=result.ok,
                actions_n=len(result.actions or []),
            )
        except Exception:
            pass
        return result


def run_air_contract_sanitize(ctx: Any) -> None:
    # commit_air_contract already owns sanitize_reentry_guard. An outer wrap here
    # nested-skips the write (ok=True, skipped=reentry) so drop_seated_missing_from_gap
    # never lands and the stage finishes unsanitary / without a real commit.
    result = commit_air_contract(ctx, reason="air_contract_sanitize")
    if (result.metrics or {}).get("skipped") == "reentry":
        raise RuntimeError(
            "air_contract_sanitize: commit skipped via reentry guard (no write)"
        )
    if not result.ok:
        raise RuntimeError(
            sanitize_refused_message("air_contract", result.errors)
        )

    # Dry re-sanitize must be clean before heal / soft freeze.
    # Advisory-only actions (aspirational floor continue) are not dirt.
    dry = sanitize_air_contract(ctx)
    dry_actions = _strip_advisory_actions(list(dry.actions or []))
    if not dry.ok or dry_actions:
        detail = ",".join(
            list(dry.errors or [])[:4]
            or [str(a.get("action") or "") for a in dry_actions[:6]]
        )
        raise RuntimeError(
            f"air_contract_unsanitary — resume air_contract_sanitize: "
            f"post-commit drift ({detail})"
        )

    from interview_mux.stage_completion import heal_or_refuse_mark

    # Pay shared-path land when commit wrote seats but a later ALLOW writer
    # (IPP/layup) still owns producer_stage — restamp before mark_done.
    try:
        if ctx.artifact_exists(PLAN_REL):
            plan_pay = ctx.read_json(PLAN_REL)
            if isinstance(plan_pay, dict):
                meta_pay = (
                    dict(plan_pay.get("_meta") or {})
                    if isinstance(plan_pay.get("_meta"), dict)
                    else {}
                )
                if str(meta_pay.get("producer_stage") or "") != "air_contract_sanitize":
                    meta_pay["producer_stage"] = "air_contract_sanitize"
                    plan_pay["_meta"] = meta_pay
                    ctx.write_json(
                        PLAN_REL,
                        plan_pay,
                        stage_key="air_contract_sanitize",
                        skip_handoff=True,
                    )
    except Exception:
        pass

    out = heal_or_refuse_mark(ctx, "air_contract_sanitize")
    if out.get("refused") or not (
        out.get("marked")
        or (hasattr(ctx, "is_done") and ctx.is_done("air_contract_sanitize"))
    ):
        reason = str(out.get("reason") or "").strip()
        if not reason:
            from interview_mux.stage_completion import stage_artifact_incompleteness

            reason = stage_artifact_incompleteness(ctx, "air_contract_sanitize") or (
                "air_contract_unsanitary — resume air_contract_sanitize: heal refused"
            )
        raise RuntimeError(reason)
    try:
        from interview_mux.seat_authority import stamp_soft_seat_freeze

        stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    except Exception as exc:
        try:
            ctx.log(
                f"air_contract_sanitize: soft seat freeze stamp FAILED: {exc}",
                level="error",
                stage="air_contract_sanitize",
            )
        except Exception:
            pass
        raise
