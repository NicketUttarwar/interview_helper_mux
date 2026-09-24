"""Delivery stage: synthesize current-pair transition WAVs and remaining gap VO."""

from __future__ import annotations

from datetime import datetime, timezone

from interview_mux.run_context import RunContext

STAGE_ID = "vo_synthesize"
REPORT_REL = "mastering/vo_synthesize.json"


def run_vo_synthesize(ctx: RunContext) -> None:
    """Generate current-pair transition audio, then fail-open remaining synthesize gap lines."""
    from interview_mux.gap_vo_gates import (
        gap_framing_enabled,
        require_vo_path_ready,
        rewrite_full_auto_record_lines_to_synth,
    )
    from interview_mux.stages.assembly import resync_required_synthesize_wavs
    from interview_mux.transition_vo import (
        current_transition_pairs_missing,
        restamp_edl_transition_source_paths,
        synthesize_spoken_transitions,
    )
    from interview_mux.write_staging import promote_staged_side_effects

    if gap_framing_enabled(ctx):
        try:
            require_vo_path_ready(ctx, for_synthesize=True, auto_accept=True)
        except SystemExit as exc:
            msg = str(exc)
            if "no synthesize lines" in msg.lower():
                try:
                    from interview_mux.hosted_vo_authority import identify_hosted_vo_floor

                    ident = identify_hosted_vo_floor(
                        ctx, stage_id=STAGE_ID, persist=True
                    )
                    ctx.log(
                        f"vo_synthesize refused: {msg} ({ident.prose})",
                        level="warning",
                        stage=STAGE_ID,
                    )
                except Exception:
                    pass
            raise

    # VS-B3: unattended Full-auto owns formerly record-required lines via synth.
    rewrite_full_auto_record_lines_to_synth(ctx)

    # Align gap skipped_optional with omit ledger before G1 / resync (End-A under
    # freeze). Without this, ledger-omitted layups stay G1-red while synth no-ops.
    try:
        from interview_mux.omit_ledger import stamp_gap_report_omit_skips

        stamped = stamp_gap_report_omit_skips(ctx)
        if stamped:
            ctx.log(
                f"vo_synthesize: stamped {stamped} omit-ledger skip(s) onto gap_report",
                stage=STAGE_ID,
            )
    except Exception as exc:
        ctx.log(
            f"vo_synthesize: omit-ledger gap stamp incomplete: {exc}",
            level="warning",
            stage=STAGE_ID,
        )

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
            try:
                gap_notes = resync_required_synthesize_wavs(ctx, gap)
            except Exception as exc:
                ctx.log(
                    f"vo_synthesize: resync incomplete: {exc}",
                    level="warning",
                    stage=STAGE_ID,
                )
                gap_notes = []
            # Bind-first: promote pending stems before heal so stem checks see them.
            try:
                promote_staged_side_effects(
                    ctx, ("master/transitions/", "vo_pickup/"), stage_id=STAGE_ID
                )
            except Exception:
                pass
            from interview_mux.vo_bind_authority import heal_seated_bind_mismatch

            heal = heal_seated_bind_mismatch(ctx, attempt_synth=True)
            if heal.get("omitted") or heal.get("resynthesized"):
                ctx.log(
                    "vo_synthesize: seated bind heal "
                    f"resynth={heal.get('resynthesized')} omit={heal.get('omitted')}",
                    stage=STAGE_ID,
                )

    try:
        restamp_edl_transition_source_paths(ctx)
    except Exception:
        pass
    try:
        from interview_mux.stages.assembly import restamp_edl_vo_pickup_source_paths

        restamp_edl_vo_pickup_source_paths(ctx)
    except Exception as exc:
        ctx.log(
            f"vo_synthesize: VO bind restamp incomplete: {exc}",
            level="warning",
            stage=STAGE_ID,
        )
    try:
        promote_staged_side_effects(
            ctx, ("master/transitions/", "vo_pickup/"), stage_id=STAGE_ID
        )
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
    try:
        from interview_mux.seat_authority import stamp_hard_seat_freeze

        stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    except Exception as exc:
        # Hard freeze is load-bearing for Pillar B — never mark synth complete ungated.
        ctx.log(
            f"vo_synthesize: hard seat freeze stamp FAILED: {exc}",
            level="error",
            stage=STAGE_ID,
        )
        raise
