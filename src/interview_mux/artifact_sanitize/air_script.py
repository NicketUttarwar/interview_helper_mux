"""Air-contract sanitizer — seats ↔ gap flags ↔ omit ledger (W3).

Sole authority surface for VO seating. Gap W1 must not clamp/seat.
"""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.halt import sanitize_refused_message
from interview_mux.artifact_sanitize.reentry import (
    sanitize_reentry_guard,
    stamp_sanitize_meta,
)
from interview_mux.artifact_sanitize.types import SanitizeResult

PLAN_REL = "mastering/mastering_plan.json"
OMIT_REL = "understanding/omit_ledger.json"
GAP_REL = "understanding/gap_report.json"


def _air_script(plan: dict[str, Any]) -> dict[str, Any]:
    air = plan.get("air_script")
    return air if isinstance(air, dict) else {}


def _vo_seats(plan: dict[str, Any]) -> dict[str, Any]:
    air = _air_script(plan)
    seats = air.get("vo_seats")
    return seats if isinstance(seats, dict) else {}


def sanitize_air_contract(ctx: Any, docs: dict[str, dict[str, Any]] | None = None) -> SanitizeResult:
    """Sanitize the seats/gap-flags/omit triple. docs may supply plan/gap/omit."""
    actions: list[dict[str, Any]] = []
    errors: list[str] = []

    plan = dict((docs or {}).get("plan") or {})
    if not plan and ctx.artifact_exists(PLAN_REL):
        try:
            loaded = ctx.read_json(PLAN_REL)
            if isinstance(loaded, dict):
                plan = loaded
        except Exception:
            plan = {}
    gap = dict((docs or {}).get("gap") or {})
    if not gap and ctx.artifact_exists(GAP_REL):
        try:
            loaded = ctx.read_json(GAP_REL)
            if isinstance(loaded, dict):
                gap = loaded
        except Exception:
            gap = {}
    omit = dict((docs or {}).get("omit") or {})
    if not omit and ctx.artifact_exists(OMIT_REL):
        try:
            loaded = ctx.read_json(OMIT_REL)
            if isinstance(loaded, dict):
                omit = loaded
        except Exception:
            omit = {}

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
        actions.append({"action": "drop_seated_intersect_omitted", "ids": sorted(both)[:24]})

    seats["seated_line_ids"] = seated
    seats["omitted_line_ids"] = omitted
    air["vo_seats"] = seats
    plan = dict(plan)
    plan["air_script"] = air

    # Sync omit flags onto gap lines for omitted seats — but never stamp an omit
    # that would drop active synthetic VO below the G-Framing floor. Prefer
    # reseating those ids so sanitize cannot thrash under soft/hard freeze.
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
                synth = {
                    "synthesize",
                    "record",
                    "voice_clone",
                    "chatterbox",
                }

                def _is_active(row: dict[str, Any]) -> bool:
                    if row.get("skipped_optional") or row.get("omit") or row.get(
                        "air_script_omit"
                    ):
                        return False
                    delivery = (
                        str(row.get("delivery") or "synthesize").strip().lower()
                        or "synthesize"
                    )
                    return delivery in synth

                active_now = sum(
                    1 for row in lines if isinstance(row, dict) and _is_active(row)
                )
                would_stamp = [
                    str(row.get("line_id") or "")
                    for row in lines
                    if isinstance(row, dict)
                    and str(row.get("line_id") or "") in omit_set
                    and _is_active(row)
                    and str(row.get("line_id") or "")
                ]
                # Prefer keeping orientation + any WAV-backed lines on air.
                def _protect_rank(lid: str) -> tuple[int, str]:
                    row = next(
                        (
                            r
                            for r in lines
                            if isinstance(r, dict) and str(r.get("line_id") or "") == lid
                        ),
                        {},
                    )
                    orient = 0 if (
                        row.get("episode_orientation")
                        or "orientation" in lid.lower()
                    ) else 1
                    return (orient, lid)

                would_stamp_sorted = sorted(set(would_stamp), key=_protect_rank)
                active_after = active_now - len(would_stamp_sorted)
                if active_after < need:
                    protect_n = need - active_after
                    protect_floor = set(would_stamp_sorted[:protect_n])
                if protect_floor:
                    omitted = [o for o in omitted if o not in protect_floor]
                    for lid in sorted(protect_floor):
                        if lid not in seated:
                            seated.append(lid)
                    omit_set = set(omitted)
                    seats["seated_line_ids"] = seated
                    seats["omitted_line_ids"] = omitted
                    air["vo_seats"] = seats
                    plan = dict(plan)
                    plan["air_script"] = air
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

        new_lines = []
        stamped = 0
        for row in lines:
            if not isinstance(row, dict):
                continue
            lid = str(row.get("line_id") or "")
            if lid in omit_set and not (
                row.get("skipped_optional")
                or row.get("omit")
                or row.get("air_script_omit")
            ):
                row = dict(row)
                row["skipped_optional"] = True
                row["omit"] = True
                row["air_script_omit"] = True
                row["skip_reason"] = row.get("skip_reason") or "air_contract_omit"
                row["skip_reason_code"] = (
                    row.get("skip_reason_code") or "air_script_omit_sync"
                )
                stamped += 1
            new_lines.append(row)
        if stamped:
            gap = dict(gap)
            gap["interviewer_lines"] = new_lines
            actions.append({"action": "stamp_gap_omit_flags", "count": stamped})

    # Orientation protect — never strip required orientation from omit ledger.
    # Durably waived orientation (air_script_omit / omit meta) must stay omitable
    # so sanitize does not thrash protect_orientation_from_omit forever (exec_10066).
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
            subj = str(row.get("subject_id") or row.get("segment_id") or row.get("id") or "")
            active = str(row.get("status") or "active").lower() in {"", "active"}
            if subj in orient_ids and active and str(row.get("kind") or "").startswith("gap"):
                # supersede by skipping active orientation-fighting omit
                restored += 1
                actions.append({"action": "protect_orientation_from_omit", "subject_id": subj})
                continue
            kept.append(row)
        if restored:
            omit = dict(omit)
            omit["entries"] = kept

    # Clamp seats to rendered WAVs (in-memory then persist via commit)
    try:
        from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

        unseated = clamp_hosted_seats_to_rendered_wavs(ctx) or []
        if unseated:
            actions.append(
                {
                    "action": "clamp_hosted_seats_to_rendered_wavs",
                    "unseated": list(unseated)[:24],
                }
            )
            # Re-read seats after clamp
            if ctx.artifact_exists(PLAN_REL):
                refreshed = ctx.read_json(PLAN_REL)
                if isinstance(refreshed, dict):
                    plan = refreshed
                    seats = dict(_vo_seats(plan))
                    seated = [str(x) for x in (seats.get("seated_line_ids") or []) if x]
            if ctx.artifact_exists(GAP_REL):
                refreshed_gap = ctx.read_json(GAP_REL)
                if isinstance(refreshed_gap, dict):
                    gap = refreshed_gap
    except Exception as exc:
        actions.append({"action": "clamp_failed", "error": str(exc)[:120]})

    # Drop seated synthesize lines missing from gap (orphan seats after layup
    # recompose) instead of refusing — resume VO synth for remaining seats.
    gap_ids = {
        str(r.get("line_id") or "")
        for r in (gap.get("interviewer_lines") or [])
        if isinstance(r, dict)
    }
    if gap_ids:
        kept_seated: list[str] = []
        for sid in seated:
            if sid not in gap_ids:
                actions.append({"action": "drop_seated_missing_from_gap", "line_id": sid})
                if sid not in omitted:
                    omitted.append(sid)
                continue
            kept_seated.append(sid)
        if len(kept_seated) != len(seated):
            seated = kept_seated
            seats["seated_line_ids"] = seated
            seats["omitted_line_ids"] = [o for o in omitted if o not in set(seated)]
            air["vo_seats"] = seats
            plan = dict(plan)
            plan["air_script"] = air

    # Refuse only if seats still cite ids absent from an empty gap (no lines at all).
    for sid in seated:
        if gap_ids and sid not in gap_ids:
            errors.append(f"seated_missing_from_gap:{sid}")

    # Normalize top-level omit_segment_ids if present (legacy field)
    omits = plan.get("omit_segment_ids") or plan.get("omitted_segment_ids")
    if isinstance(omits, list):
        cleaned = [str(s) for s in omits if str(s).strip()]
        if cleaned != list(omits):
            key = "omit_segment_ids" if "omit_segment_ids" in plan else "omitted_segment_ids"
            plan[key] = cleaned
            actions.append({"action": "normalize_omit_ids", "count": len(cleaned)})

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

    # Combined doc for registry (plan is primary)
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
    # Strip helper keys before return doc for plan write
    plan = {k: v for k, v in result.doc.items() if not str(k).startswith("_air_contract_")}
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
        actions=[a for a in result.actions if "omit" in str(a.get("action") or "")],
        ok=result.ok,
        errors=result.errors,
        artifact_rel=OMIT_REL,
        metrics=result.metrics,
    )


def air_contract_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary
    from interview_mux.artifact_sanitize.reentry import stamp_matches

    if not block_consumers_on_unsanitary():
        return []
    if not ctx.artifact_exists(PLAN_REL):
        # No plan yet — not an air-contract consumer problem
        return []
    try:
        plan = ctx.read_json(PLAN_REL)
    except Exception as exc:
        return [f"{PLAN_REL} unreadable: {exc}"]
    if not isinstance(plan, dict):
        return [f"{PLAN_REL} invalid"]
    if stamp_matches(plan):
        return []
    result = sanitize_air_contract(ctx)
    if result.ok and not result.actions:
        return []
    if not result.ok:
        return list(result.errors or ["air_contract sanitize refused"])
    # Would change — needs stage commit
    return [
        "air_contract_needs_sanitize:"
        + ",".join(str(a.get("action") or "") for a in (result.actions or [])[:6])
    ]


def commit_air_contract(ctx: Any, *, reason: str = "") -> SanitizeResult:
    """Sole mutator for seats + gap VO flags + omit ledger VO rows."""
    from interview_mux.artifact_sanitize.reentry import sanitary_content_hash

    with sanitize_reentry_guard(ctx) as nested:
        if nested:
            return SanitizeResult(doc={}, ok=True, metrics={"skipped": "reentry"})
        before_plan = {}
        if ctx.artifact_exists(PLAN_REL):
            try:
                loaded = ctx.read_json(PLAN_REL)
                if isinstance(loaded, dict):
                    before_plan = loaded
            except Exception:
                before_plan = {}
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
        plan = {k: v for k, v in result.doc.items() if not str(k).startswith("_air_contract_")}
        gap = result.doc.get("_air_contract_gap")
        omit = result.doc.get("_air_contract_omit")
        try:
            from interview_mux.information_packages import ensure_episode_close_on_plan

            plan = ensure_episode_close_on_plan(plan)
        except Exception:
            pass
        # Direct write — write_plan would recurse into commit_air_contract.
        ctx.write_json(PLAN_REL, plan)
        if isinstance(gap, dict) and gap:
            try:
                ctx.write_json(GAP_REL, gap)
            except Exception:
                pass
        if isinstance(omit, dict) and omit:
            try:
                from interview_mux.omit_ledger import write_omit_ledger

                write_omit_ledger(ctx, omit)
            except Exception:
                try:
                    ctx.write_json(OMIT_REL, omit)
                except Exception:
                    pass
        # Terminal clamp again after writes (nested reentry skips commit)
        try:
            from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

            clamp_hosted_seats_to_rendered_wavs(ctx)
        except Exception:
            pass
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
    try:
        from interview_mux.stage_completion import heal_or_refuse_mark

        heal_or_refuse_mark(ctx, "air_contract_sanitize")
    except Exception:
        try:
            ctx.mark_done("air_contract_sanitize")
        except Exception:
            pass
    try:
        from interview_mux.seat_authority import stamp_soft_seat_freeze

        stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    except Exception as exc:
        # Soft freeze is load-bearing for Pillar B — never continue ungated.
        try:
            ctx.log(
                f"air_contract_sanitize: soft seat freeze stamp FAILED: {exc}",
                level="error",
                stage="air_contract_sanitize",
            )
        except Exception:
            pass
        raise
