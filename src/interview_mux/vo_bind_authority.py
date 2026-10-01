"""Seated VO bind authority — sha-bound WAV vs omit ledger (predicate family F2).

EDL must never own ``vo_pickup/`` bytes. Bind mismatch re-synthesizes into the
VO owner stage. Ladder: promote → accept on-disk (committed or pending) →
resynth → omit only when no stem exists anywhere. Process omit never beats WAV.
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
    """Restore seated bind: promote, accept WAV, resynth; else refuse incomplete.

    Returns ``{resynthesized, omitted, refused}`` line ids.
    S2: never omit seated synth fail as success — leave refused for incompleteness.
    Process omit helper remains for catastrophe call sites only.
    """
    from interview_mux.write_staging import (
        discard_non_owner_pending_vo_pickup,
        promote_owner_vo_pickup,
    )

    # Bind-first: land owner pending stems before any presence / omit decision.
    try:
        promote_owner_vo_pickup(ctx)
    except Exception:
        pass
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
        # WAV already on disk (committed or pending) → accept; never omit.
        if _line_wav_present(ctx, row):
            try:
                promote_owner_vo_pickup(ctx)
            except Exception:
                pass
            if _line_bind_ok(ctx, row) or _ensure_audit_for_present_wav(ctx, row):
                out["resynthesized"].append(lid)
                continue
            # Stem present even if audit backfill failed — still keep on air.
            out["resynthesized"].append(lid)
            continue
        if attempt_synth and _try_resynth_seated_line(ctx, row):
            try:
                promote_owner_vo_pickup(ctx)
            except Exception:
                pass
            discard_non_owner_pending_vo_pickup(ctx)
            if _line_bind_ok(ctx, row) or _line_wav_present(ctx, row):
                out["resynthesized"].append(lid)
                continue
        # Never omit a hosted line that already has pickup bytes on disk.
        if _line_wav_present(ctx, row):
            out["resynthesized"].append(lid)
            continue
        # A seat whose copy the guard refuses with no grounded fallback can
        # never be rendered by any retry: the contract then demands a WAV the
        # guard forbids, and the run dies on "seated synthesize VO not
        # rendered" (maintainer's exec_010, ISSUES 123). Release the seat
        # under the synth-fail End-A action, with the reason recorded, so the
        # content hole stays visible instead of fatal.
        if _copy_unspeakable(ctx, row):
            if _omit_bind_failed_line(ctx, lid, row):
                ctx.log(
                    f"vo bind heal: unseated {lid}: its copy is refused by the "
                    "spoken-copy guard with no grounded fallback",
                    level="warning",
                    stage="vo_synthesize",
                    detail={"line_id": lid, "reason": "spoken_copy_guard_block"},
                )
                out["omitted"].append(lid)
                continue
        # S2: seated synth fail → refuse incomplete (no omit-as-success / plan unseat).
        out["refused"].append(lid)
    discard_non_owner_pending_vo_pickup(ctx)
    return out


def _copy_unspeakable(ctx: RunContext, line: dict[str, Any]) -> bool:
    """True when the guard blocks the line's own copy and offers no fallback."""
    try:
        from interview_mux.spoken_copy_guard import (
            enrich_evidence_from_run,
            evidence_for_line,
            guard_spoken_copy,
        )

        text = str(line.get("text") or "").strip()
        if not text:
            return False
        evidence = enrich_evidence_from_run(ctx, evidence_for_line(line))
        decision = guard_spoken_copy(
            text, evidence=evidence, required=True, purpose=f"vo[{line.get('line_id')}]"
        )
        return str(decision.get("action") or "") == "block"
    except Exception:
        return False


def _line_wav_present(ctx: RunContext, line: dict[str, Any]) -> bool:
    """Stem presence on disk (audit not required) — chatterbox may write before JSON OK."""
    try:
        from interview_mux.vo_contract import _gap_row_has_pickup_stem

        return bool(_gap_row_has_pickup_stem(ctx, line))
    except Exception:
        return False


def _ensure_audit_for_present_wav(ctx: RunContext, line: dict[str, Any]) -> bool:
    """Record synthesis audit when WAV exists but chatterbox JSON parse failed."""
    try:
        from interview_mux.vo_contract import _gap_row_has_pickup_stem
        from interview_mux.vo_synthesis_audit import (
            record_synthesis,
            synthesis_entry_matches_line,
        )
        from interview_mux.write_staging import staging_root

        if not _gap_row_has_pickup_stem(ctx, line):
            return False
        lid = str(line.get("line_id") or "").strip()
        path = None
        roots = [ctx.final_path("vo_pickup")]
        try:
            roots.append(staging_root(ctx, "vo_synthesize") / "vo_pickup")
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
                candidate = base / f"{lid}.wav"
                if candidate.is_file():
                    path = candidate
                    break
            if path is not None:
                break
        if path is None:
            return False
        matches, _reason = synthesis_entry_matches_line(ctx, line)
        if matches:
            return True
        record_synthesis(
            ctx,
            dict(line),
            backend="chatterbox",
            out_wav=path,
        )
        matches, _reason = synthesis_entry_matches_line(ctx, line)
        return bool(matches) or path.is_file()
    except Exception:
        return _line_wav_present(ctx, line)


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
        from interview_mux.gap_vo_gates import (
            framing_requires_nested_synth_gate,
            vo_synth_mint_allowed,
        )

        # Footgun #3: nested bind heal must honor Partial mint SSOT (not only runners).
        if framing_requires_nested_synth_gate(ctx):
            ok, reason = vo_synth_mint_allowed(ctx, for_synthesize=False)
            if not ok:
                return False

        s2s_runner.synthesize_line(ctx, dict(line), mode="synthesize")
        promote_owner_vo_pickup(ctx)
        return True
    except Exception:
        # Chatterbox may write WAV then fail JSON parse (pkg_resources warning on
        # stdout). Accept durable pickup bytes as success; promote pending first.
        try:
            promote_owner_vo_pickup(ctx)
        except Exception:
            pass
        return _line_wav_present(ctx, line)
    finally:
        if nested:
            if parent:
                enter_stage_staging(parent)
            else:
                exit_stage_staging()


def _omit_bind_failed_line(
    ctx: RunContext, lid: str, line: dict[str, Any]
) -> bool:
    """Unseat + omit after synth failure. Never drop episode orientation (T0-4).

    Only call when no stem exists anywhere. Process stamp is not policy omit-wins.
    """
    from interview_mux.opening_orientation import is_episode_orientation
    from interview_mux.vo_contract import mark_gap_line_not_on_air

    if is_episode_orientation(line):
        return False
    # Final guard: never omit when bytes landed mid-heal.
    if _line_wav_present(ctx, line):
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
    from interview_mux.seat_authority import persist_frozen_seat_doc

    if not persist_frozen_seat_doc(
        ctx, "understanding/gap_report.json", out, reason="catastrophe_seated_bind_synth_failed"
    ):
        return False
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
                write_plan(ctx, plan, seat_reason="catastrophe_seated_bind_synth_failed")
            except Exception:
                from interview_mux.seat_authority import persist_frozen_seat_doc

                persist_frozen_seat_doc(
                    ctx,
                    "mastering/mastering_plan.json",
                    plan,
                    reason="catastrophe_seated_bind_synth_failed",
                    skip_handoff=True,
                    stage_key="air_contract_sanitize",
                )
        except Exception:
            pass
    try:
        from interview_mux.execution_contract import reconcile_execution_contract

        reconcile_execution_contract(ctx, reason="catastrophe_seated_bind_synth_failed")
    except Exception:
        pass
    return True
