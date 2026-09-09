"""Delivery stage: smart per-line VO adjudication before synthesis (homunculus 0.1.0+)."""

from __future__ import annotations

from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark

STAGE_ID = "vo_line_adjudicate"


def run_vo_line_adjudicate(ctx: RunContext) -> None:
    from interview_mux.homunculus.runtime import is_homunculus_run
    from interview_mux.vo_line_adjudicate import (
        adjudicate_before_synth_enabled,
        run_vo_line_adjudicate_stage,
    )

    if not is_homunculus_run(ctx):
        ctx.log(
            "vo_line_adjudicate: skipped — homunculus 0.1.0+ only (4B)",
            level="info",
            stage=STAGE_ID,
        )
        heal_or_refuse_mark(ctx, STAGE_ID, force=True)
        return

    if not adjudicate_before_synth_enabled():
        ctx.log(
            "vo_line_adjudicate: skipped — analysis.gap_vo.adjudicate_before_synth=false",
            level="info",
            stage=STAGE_ID,
        )
        heal_or_refuse_mark(ctx, STAGE_ID, force=True)
        return

    with logged_step("vo_line_adjudicate/run", ctx=ctx, stage=STAGE_ID):
        run_vo_line_adjudicate_stage(ctx)
