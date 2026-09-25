"""Delivery stage: smart per-line VO adjudication before synthesis (homunculus 0.1.0+)."""

from __future__ import annotations

from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark

STAGE_ID = "vo_line_adjudicate"


def _prep_opening_orientation(ctx: RunContext) -> None:
    """ALLOW stamp: orientation retarget/revive (writer = this stage)."""
    try:
        from interview_mux.omit_ledger import revive_required_opening_orientation
        from interview_mux.opening_orientation import retarget_orientation_to_open

        synced = retarget_orientation_to_open(ctx, stage_key=STAGE_ID)
        if synced:
            ctx.log(
                f"vo_line_adjudicate: orientation targets synced {synced}",
                stage=STAGE_ID,
            )
        revive_required_opening_orientation(ctx)
    except Exception as exc:
        ctx.log(
            f"vo_line_adjudicate: opening orientation prep incomplete: {exc}",
            level="warning",
            stage=STAGE_ID,
        )


def _maybe_full_auto_record_to_synth(ctx: RunContext) -> None:
    """S6: Full-auto record→synth delivery stamp as ``vo_line_adjudicate`` (no synth spoof)."""
    try:
        from interview_mux.gap_vo_gates import rewrite_full_auto_record_lines_to_synth

        rewritten = rewrite_full_auto_record_lines_to_synth(
            ctx, stage_key=STAGE_ID
        ) or []
        if rewritten:
            ctx.log(
                "vo_line_adjudicate: Full-auto record→synth "
                f"rewrote {len(rewritten)} line(s)",
                stage=STAGE_ID,
            )
    except Exception as exc:
        ctx.log(
            f"vo_line_adjudicate: Full-auto record→synth rewrite skipped: {exc}",
            level="warning",
            stage=STAGE_ID,
        )


def _pre_synth_gap_stamps(ctx: RunContext) -> None:
    """S7 fold: one readiness stamp suite (orientation + Full-auto delivery)."""
    _prep_opening_orientation(ctx)
    _maybe_full_auto_record_to_synth(ctx)


def run_vo_line_adjudicate(ctx: RunContext) -> None:
    from interview_mux.homunculus.runtime import has_homunculus_features
    from interview_mux.vo_line_adjudicate import (
        adjudicate_before_synth_enabled,
        run_vo_line_adjudicate_stage,
    )

    if not has_homunculus_features(ctx):
        ctx.log(
            "vo_line_adjudicate: skipped — homunculus 0.1.0+ only (4B)",
            level="info",
            stage=STAGE_ID,
        )
        from interview_mux.vo_line_adjudicate import persist_adjudication_skip_stub

        persist_adjudication_skip_stub(ctx, skip_reason="homunculus_features_off")
        _pre_synth_gap_stamps(ctx)
        heal_or_refuse_mark(ctx, STAGE_ID, force=True)
        return

    if not adjudicate_before_synth_enabled():
        ctx.log(
            "vo_line_adjudicate: skipped — analysis.gap_vo.adjudicate_before_synth=false",
            level="info",
            stage=STAGE_ID,
        )
        from interview_mux.vo_line_adjudicate import persist_adjudication_skip_stub

        persist_adjudication_skip_stub(ctx, skip_reason="adjudicate_before_synth_disabled")
        _pre_synth_gap_stamps(ctx)
        heal_or_refuse_mark(ctx, STAGE_ID)
        return

    with logged_step("vo_line_adjudicate/run", ctx=ctx, stage=STAGE_ID):
        try:
            from interview_mux.hosted_vo_authority import identify_hosted_vo_floor

            identify_hosted_vo_floor(ctx, stage_id=STAGE_ID, persist=True)
        except Exception:
            pass
        run_vo_line_adjudicate_stage(ctx)
        _pre_synth_gap_stamps(ctx)
        try:
            from interview_mux.hosted_vo_authority import identify_hosted_vo_floor

            identify_hosted_vo_floor(ctx, stage_id=STAGE_ID, persist=True)
        except Exception:
            pass
