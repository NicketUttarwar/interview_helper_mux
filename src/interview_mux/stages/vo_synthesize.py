"""Delivery stage: synthesize current-pair transition WAVs and remaining gap VO."""

from __future__ import annotations

from datetime import datetime, timezone

from interview_mux.run_context import RunContext

STAGE_ID = "vo_synthesize"
REPORT_REL = "mastering/vo_synthesize.json"


def run_vo_synthesize(ctx: RunContext) -> None:
    """Generate current-pair transition audio, then fail-open remaining synthesize gap lines."""
    from interview_mux.stages.assembly import resync_required_synthesize_wavs
    from interview_mux.transition_vo import (
        current_transition_pairs_missing,
        restamp_edl_transition_source_paths,
        synthesize_spoken_transitions,
    )
    from interview_mux.write_staging import promote_staged_side_effects

    attempted: list[str] = []
    if ctx.artifact_exists("master/transitions.json"):
        try:
            synthesize_spoken_transitions(ctx)
        except Exception as exc:
            ctx.log(
                f"vo_synthesize: transition synth failed open: {exc}",
                level="warning",
                stage=STAGE_ID,
            )
        attempted = current_transition_pairs_missing(ctx)

    gap_notes: list[str] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        try:
            gap = ctx.read_json("understanding/gap_report.json")
        except Exception:
            gap = None
        if isinstance(gap, dict):
            gap_notes = resync_required_synthesize_wavs(ctx, gap)

    try:
        restamp_edl_transition_source_paths(ctx)
    except Exception:
        pass
    try:
        promote_staged_side_effects(ctx, ("master/transitions/",), stage_id=STAGE_ID)
    except Exception:
        pass

    still = current_transition_pairs_missing(ctx)
    from interview_mux.transition_vo import persist_vo_pair_gap

    persist_vo_pair_gap(
        ctx,
        still,
        source="vo_synthesize",
        extra={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "attempted_missing_before": attempted,
            "gap_lines_synthesized": gap_notes,
        },
        skip_handoff=False,
        stage_key=STAGE_ID,
    )
    if still:
        ctx.log(
            "vo_synthesize: current pairs still missing WAV: " + ", ".join(still[:8]),
            level="warning",
            stage=STAGE_ID,
        )
    else:
        ctx.log("vo_synthesize: current-pair transition WAVs ready", stage=STAGE_ID)

    from interview_mux.vo_contract import assert_seated_vo_rendered

    assert_seated_vo_rendered(ctx)
