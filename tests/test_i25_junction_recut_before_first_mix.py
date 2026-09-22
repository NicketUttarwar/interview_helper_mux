"""i25: live incomplete-cut residuals must be recut before the first mix.

exec_11871 hard-looped (class_failure junction_snip_qa/incomplete_cut_unresolved
x3/3 halt=True): run_mix refused with
``incomplete_cut_unresolved: … recut/fuse/omit at junction_snip_qa first`` while
seed order refused junction_snip_qa with ``seed order: complete mix before
running junction_snip_qa`` — so the recut owner could never run. The junction
ladder owns recut/fuse/omit on the EDL and drives its own remaster, so it is
allowed ahead of the first mix while those residuals are live.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.runtime import _seed_prereq_block
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i25_junction_before_mix")


def _sdp_doc(crossfade_ms: int) -> dict:
    """Schema-valid sound_design_plan with one podcast cue."""
    return {
        "version": 1,
        "flow_plans": {
            "podcast": {
                "profile": "podcast",
                "cues": [
                    {
                        "cue_id": "cue_theme_a",
                        "asset_id": "theme_a",
                        "crossfade_ms": crossfade_ms,
                        "placement": "before_segment",
                        "segment_id": "seg_001",
                    }
                ],
            }
        },
    }


def _pin_earliest_incomplete(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening._earliest_incomplete_seed_stage",
        lambda _ctx, _stage: stage,
    )


def test_i25_live_incomplete_cuts_unblock_junction_before_mix(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSQ-B2 / MIX-B2: junction_recut_precedes_mix golden — live residuals → junction first."""
    _pin_earliest_incomplete(monkeypatch, "mix")
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    assert _seed_prereq_block(ctx, "junction_snip_qa") is None, (
        "junction recut owner must run before first mix while residuals are live"
    )


def test_jsq_b2_mix_refuse_and_junction_first_handshake(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSQ-B2: thrash handshake — mix refuses live incompletes; junction owns recut first."""
    from interview_mux.junction_snip_qa import (
        junction_recut_precedes_mix,
        refuse_mix_if_live_incomplete_cuts,
    )
    from interview_mux.loud_fail import LoudStageFailure

    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    assert junction_recut_precedes_mix(ctx) is True
    with pytest.raises(LoudStageFailure, match="incomplete_cut_unresolved"):
        refuse_mix_if_live_incomplete_cuts(ctx)
    _pin_earliest_incomplete(monkeypatch, "mix")
    assert _seed_prereq_block(ctx, "junction_snip_qa") is None
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    assert junction_recut_precedes_mix(ctx) is False


def test_i25_clean_edl_keeps_mix_first(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_earliest_incomplete(monkeypatch, "mix")
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    assert _seed_prereq_block(ctx, "junction_snip_qa") == "mix", (
        "without live residuals junction must stay behind mix in seed order"
    )


def test_i25_other_stages_still_seed_blocked(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_earliest_incomplete(monkeypatch, "mix")
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    assert _seed_prereq_block(ctx, "master_finalize") == "mix", (
        "the exemption is junction-only — finalize must never jump the mix seat"
    )


def test_i25_input_check_allows_junction_recut_without_assembly(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The GUI/driver preflight must not require assembly.wav for the pre-mix recut."""
    from interview_mux.stage_input_checks import collect_stage_input_issues

    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "clips": [],
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
        },
        stage_key="edl",
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "chapter_bleed_incomplete", "severity": "critical", "segment_id": "seg_014"}
        ],
    )
    msgs = [i.message for i in collect_stage_input_issues(ctx, "junction_snip_qa")]
    assert not any("assembly.wav" in m for m in msgs), msgs


def test_i25_input_check_still_requires_assembly_when_clean(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stage_input_checks import collect_stage_input_issues

    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "clips": [],
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
        },
        stage_key="edl",
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    msgs = [i.message for i in collect_stage_input_issues(ctx, "junction_snip_qa")]
    assert any("assembly.wav" in m for m in msgs), msgs


def test_i25_hardening_gate_lets_junction_recut_run(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """maybe_require_upstream_llm_progress must not SystemExit the pre-mix recut."""
    from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

    _pin_earliest_incomplete(monkeypatch, "mix")
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.flow_hardening_enabled", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    maybe_require_upstream_llm_progress(ctx, "junction_snip_qa")


def test_i25_hardening_gate_still_blocks_when_clean(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

    _pin_earliest_incomplete(monkeypatch, "mix")
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.flow_hardening_enabled", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    with pytest.raises(SystemExit):
        maybe_require_upstream_llm_progress(ctx, "junction_snip_qa")


def _stamp_mix_done(ctx: RunContext) -> None:
    done = ctx.final_path(".stage_done", "mix")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("done")


def test_i25_helper_is_false_once_mix_landed(ctx: RunContext) -> None:
    from interview_mux.junction_snip_qa import junction_recut_precedes_mix

    path = ctx.final_path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF")
    assert junction_recut_precedes_mix(ctx) is False
    _stamp_mix_done(ctx)
    assert junction_recut_precedes_mix(ctx) is False


def test_i41_stale_assembly_does_not_strand_the_recut(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """i41: mix ⇄ junction_snip_qa ping-pong on a stale assembly.wav.

    exec_11871: an early mix left ``master/assembly.wav`` behind, then a later EDL
    rebuild re-opened ``chapter_bleed_incomplete`` on seg_014. mix refused (residual
    live, mix not done) and the seed-order gate refused junction because "mix is not
    complete" — a 5-minute loop with no owner. A stale assembly must not count as a
    landed mix.
    """
    from interview_mux.junction_snip_qa import junction_recut_precedes_mix
    from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

    path = ctx.final_path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF")
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {
                "kind": "chapter_bleed_incomplete",
                "severity": "critical",
                "segment_id": "seg_014",
                "detail": {"unrecoverable_within_clip": True},
            }
        ],
    )
    assert junction_recut_precedes_mix(ctx) is True
    # …and the seed-order hardening gate lets the ladder run.
    _pin_earliest_incomplete(monkeypatch, "mix")
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.flow_hardening_enabled", lambda *a, **k: True
    )
    maybe_require_upstream_llm_progress(ctx, "junction_snip_qa")
    # Once live residuals clear and mix has landed, the ladder goes back behind mix.
    _stamp_mix_done(ctx)
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_stale_versus_live",
        lambda _ctx: False,
    )
    assert junction_recut_precedes_mix(ctx) is False


def test_i25_conductor_pins_junction_instead_of_mix(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delivery conductor must not pin mix while the recut is owed."""
    from interview_mux.homunculus import agenda

    monkeypatch.setattr(
        agenda, "earliest_incomplete_seed_stage", lambda *a, **k: "mix"
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.filter_delivery_candidates",
        lambda _c, remaining: list(remaining),
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    pinned = agenda.constrain_conductor_to_seed_front(
        ctx, "delivery", ["mix", "junction_snip_qa", "master_finalize"]
    )
    assert pinned == ["junction_snip_qa"], pinned


def test_i25_conductor_keeps_mix_front_when_edl_clean(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.homunculus import agenda

    monkeypatch.setattr(
        agenda, "earliest_incomplete_seed_stage", lambda *a, **k: "mix"
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.filter_delivery_candidates",
        lambda _c, remaining: list(remaining),
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    pinned = agenda.constrain_conductor_to_seed_front(
        ctx, "delivery", ["mix", "junction_snip_qa"]
    )
    assert pinned == ["mix"], pinned


def test_i25_assert_consumer_allows_pre_mix_recut(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """assert_consumer must not refuse the recut for a missing/stale assembly."""
    from interview_mux.air_order import assert_consumer

    ctx.write_json(
        "master/selection.json",
        {"version": 1, "ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []},
        stage_key="selection_order_sanitize",
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "clips": [],
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
        },
        stage_key="edl",
    )
    monkeypatch.setattr(
        "interview_mux.order_hash.order_drift_heal_action", lambda *a, **k: "none"
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    assert_consumer(ctx, "junction_snip_qa")


def test_i25_assert_consumer_still_refuses_finalize(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.air_order import assert_consumer

    ctx.write_json(
        "master/selection.json",
        {"version": 1, "ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []},
        stage_key="selection_order_sanitize",
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "clips": [],
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
        },
        stage_key="edl",
    )
    monkeypatch.setattr(
        "interview_mux.order_hash.order_drift_heal_action", lambda *a, **k: "none"
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    with pytest.raises(SystemExit):
        assert_consumer(ctx, "master_finalize")


def test_i26_junction_does_not_rewrite_sealed_sdp(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Music-fade repair keeps the sealed SDP intact (fade lives in placement_adjustments)."""
    from interview_mux.junction_snip_qa import _patch_sdp_cue_crossfade

    sealed = _sdp_doc(0)
    ctx.write_json(
        "understanding/sound_design_plan.json", sealed, stage_key="sound_design_plan"
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "not_allow:owner=sound_design_vo_finalize"),
    )

    _patch_sdp_cue_crossfade(ctx, "theme_a", 180)
    doc = ctx.read_json("understanding/sound_design_plan.json")
    assert doc["flow_plans"]["podcast"]["cues"][0]["crossfade_ms"] == 0, doc


def test_i26_junction_patches_sdp_when_permitted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.junction_snip_qa import _patch_sdp_cue_crossfade

    ctx.write_json(
        "understanding/sound_design_plan.json",
        _sdp_doc(0),
        stage_key="sound_design_plan",
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted", lambda *a, **k: (True, "")
    )

    _patch_sdp_cue_crossfade(ctx, "theme_a", 180)
    doc = ctx.read_json("understanding/sound_design_plan.json")
    assert doc["flow_plans"]["podcast"]["cues"][0]["crossfade_ms"] == 180, doc
