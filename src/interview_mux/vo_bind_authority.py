"""Seated VO bind authority — sha-bound WAV vs omit ledger (predicate family F2).

EDL must never own ``vo_pickup/`` bytes. Bind mismatch re-synthesizes into the
VO owner stage; if synth fails, the line is omitted (not re-bound to stale
EDL-promoted bytes).
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

REASON_SYNTH_FAILED = "seated_bind_synth_failed"


def heal_seated_bind_mismatch(
    ctx: RunContext,
    *,
    attempt_synth: bool = True,
) -> dict[str, list[str]]:
    """Restore seated bind: re-synth, else omit. Discard foreign pending VO.

    Returns ``{resynthesized, omitted, refused}`` line ids.
    """
    from interview_mux.write_staging import (
        discard_non_owner_pending_vo_pickup,
        promote_owner_vo_pickup,
    )

    discarded = discard_non_owner_pending_vo_pickup(ctx)
    out: dict[str, list[str]] = {
        "resynthesized": [],
        "omitted": [],
        "refused": [],
        "discarded_pending": discarded,
    }
    from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

    stale = list(compact_vo_coverage_stale_or_missing(ctx) or [])
    if not stale:
        return out
    gap_by = _gap_lines_by_id(ctx)
    for lid in stale:
        row = gap_by.get(lid)
        if not isinstance(row, dict):
            out["refused"].append(lid)
            continue
        if attempt_synth and _try_resynth_seated_line(ctx, row):
            promote_owner_vo_pickup(ctx)
            discard_non_owner_pending_vo_pickup(ctx)
            if _line_bind_ok(ctx, row):
                out["resynthesized"].append(lid)
                continue
        if _omit_bind_failed_line(ctx, lid, row):
            out["omitted"].append(lid)
        else:
            out["refused"].append(lid)
    discard_non_owner_pending_vo_pickup(ctx)
    return out


def _gap_lines_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return {}
    try:
        gap = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return {}
    by: dict[str, dict[str, Any]] = {}
    for row in (gap.get("interviewer_lines") or []) if isinstance(gap, dict) else []:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if lid:
            by[lid] = row
    return by


def _line_bind_ok(ctx: RunContext, line: dict[str, Any]) -> bool:
    from interview_mux.vo_synthesis_audit import synthesis_entry_matches_line

    try:
        matches, _reason = synthesis_entry_matches_line(ctx, line)
    except Exception:
        return False
    return bool(matches)


def _try_resynth_seated_line(ctx: RunContext, line: dict[str, Any]) -> bool:
    from interview_mux.write_staging import (
        VO_PICKUP_OWNER_STAGES,
        active_stage_id,
        enter_stage_staging,
        exit_stage_staging,
        promote_owner_vo_pickup,
    )

    parent = active_stage_id()
    nested = parent not in VO_PICKUP_OWNER_STAGES
    if nested:
        enter_stage_staging("vo_synthesize")
    try:
        from interview_mux import s2s_runner

        s2s_runner.synthesize_line(ctx, dict(line), mode="synthesize")
        promote_owner_vo_pickup(ctx)
        return True
    except Exception:
        return False
    finally:
        if nested:
            if parent:
                enter_stage_staging(parent)
            else:
                exit_stage_staging()


def _omit_bind_failed_line(
    ctx: RunContext, lid: str, line: dict[str, Any]
) -> bool:
    """Unseat + omit after synth failure. Never drop episode orientation (T0-4)."""
    from interview_mux.opening_orientation import is_episode_orientation
    from interview_mux.vo_contract import mark_gap_line_not_on_air

    if is_episode_orientation(line):
        return False
    try:
        from interview_mux.seat_authority import (
            bump_seat_rewrite_generation,
            seat_mutation_allowed,
        )

        allowed, _why = seat_mutation_allowed(
            ctx,
            reason="catastrophe_seated_bind_synth_failed",
            require_meta_gate=False,
        )
        if not allowed:
            return False
        bump_seat_rewrite_generation(ctx)
    except Exception:
        pass
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return False
    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return False
    rows: list[Any] = []
    found = False
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            rows.append(row)
            continue
        if str(row.get("line_id") or "").strip() == lid:
            rows.append(
                mark_gap_line_not_on_air(row, reason_code=REASON_SYNTH_FAILED)
            )
            found = True
        else:
            rows.append(dict(row))
    if not found:
        return False
    out = dict(gap)
    out["interviewer_lines"] = rows
    try:
        ctx.write_json("understanding/gap_report.json", out)
    except TypeError:
        ctx.write_json("understanding/gap_report.json", out, skip_handoff=True)
    except Exception:
        ctx.path("understanding", "gap_report.json").write_text(
            __import__("json").dumps(out), encoding="utf-8"
        )
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        try:
            from interview_mux.mastering_plan_loader import load_plan_raw, write_plan

            plan = dict(load_plan_raw(ctx) or {})
            script = dict(plan.get("air_script") or {})
            seats = dict(script.get("vo_seats") or {})
            seated = [
                str(x)
                for x in (seats.get("seated_line_ids") or [])
                if str(x) and str(x) != lid
            ]
            omitted = [
                str(x) for x in (seats.get("omitted_line_ids") or []) if str(x)
            ]
            if lid not in omitted:
                omitted.append(lid)
            seats["seated_line_ids"] = seated
            seats["omitted_line_ids"] = [x for x in omitted if x not in set(seated)]
            script["vo_seats"] = seats
            plan["air_script"] = script
            try:
                write_plan(ctx, plan)
            except Exception:
                ctx.write_json(
                    "mastering/mastering_plan.json", plan, skip_handoff=True
                )
        except Exception:
            pass
    try:
        from interview_mux.execution_contract import reconcile_execution_contract

        reconcile_execution_contract(ctx, reason="catastrophe_seated_bind_synth_failed")
    except Exception:
        pass
    return True
