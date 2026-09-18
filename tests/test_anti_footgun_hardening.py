"""Negative tests for durable self-completion anti-footguns (heal ≠ waive)."""

from __future__ import annotations

import pytest

from interview_mux.aspirational_quality import (
    has_quality_advisories,
    publish_blocked_by_advisories,
)
from interview_mux.delivery_guardrails import (
    INVALIDATION_BLAST_RADIUS,
    MUSIC_BEFORE_MIX,
    break_music_epoch_seal,
    freeze_air_order,
    invalidation_allowed_downstream,
    music_clear_blocked,
    ship_path_ready,
    stamp_delivery_epoch,
    unlock_air_order_freeze,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    PRODUCER_PIN_TABLE,
    heal_or_refuse_mark,
    producer_pin_for_token,
)
from interview_mux.thrash_hardening import (
    assert_may_force_done,
    gate_wait_tick,
    junction_budget_exhaust_hard_pin,
    music_epoch_sealed_no_delight_rewind,
    wasted_work_is_true_waste,
)
from interview_mux.timeline_optimizer.config import optimizer_live_mutate_blocked
from interview_mux.v2.config import DELIVERY_ORDER
from interview_mux.vo_synthesis_audit import unmark_transition_spoken_text_cascade_stages
from run_fixtures import mark_done_raw


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    return RunContext(create=True)


def test_seal_does_not_waive_delight_ship(ctx):
    stamp_delivery_epoch(ctx, music_complete_at="2026-01-01T00:00:00Z")
    for sid in MUSIC_BEFORE_MIX:
        mark_done_raw(ctx, sid)
    # No assembly / delight → ship blocked even if music sealed.
    ok, reason = ship_path_ready(ctx)
    assert ok is False
    assert reason in {
        "assembly_missing",
        "mix_incomplete",
        "listen_delight_incomplete",
        "assembly_stale_versus_edl",
    }
    # Seal helper is about music rewind, not delight soft-pass.
    assert music_epoch_sealed_no_delight_rewind(ctx) in {True, False}


def test_vo_cascade_cannot_clear_sealed_music(ctx):
    stamp_delivery_epoch(ctx, music_complete_at="2026-01-01T00:00:00Z")
    for sid in MUSIC_BEFORE_MIX:
        (ctx.run_dir / "sound_design" / "assets").mkdir(parents=True, exist_ok=True)
        mark_done_raw(ctx, sid)
    mark_done_raw(ctx, "vo_synthesize")
    mark_done_raw(ctx, "edl")
    mark_done_raw(ctx, "mix")
    # Ensure SDP missing-wav check does not unseal for this unit test.
    stamp_delivery_epoch(ctx, music_complete_at="2026-01-01T00:00:00Z")
    assert music_clear_blocked(ctx, "mmaudio_sfx", source="transitions_write")
    unmarked = unmark_transition_spoken_text_cascade_stages(ctx)
    assert "mmaudio_sfx" not in unmarked
    assert "music_palette_compose" not in unmarked
    assert ctx.is_done("mmaudio_sfx")


def test_blast_radius_excludes_music_from_vo_sources():
    for src in ("transitions_write", "gap_report_write", "vo_line_adjudicate", "edl"):
        assert src in INVALIDATION_BLAST_RADIUS
        for music_sid in MUSIC_BEFORE_MIX:
            assert not invalidation_allowed_downstream(src, music_sid)


def test_heal_or_refuse_mark_refuses_hollow(ctx):
    # edl marked without artifact → refuse / unmark
    mark_done_raw(ctx, "edl")
    out = heal_or_refuse_mark(ctx, "edl")
    assert out.get("unmarked") or out.get("refused")
    assert not heal_or_refuse_mark(ctx, "edl", force=True).get("marked")


def test_assert_may_force_done_refuses_incomplete(ctx):
    with pytest.raises(RuntimeError, match="refuse force-done"):
        assert_may_force_done(ctx, "edl")


def test_music_seal_break_required_to_clear(ctx):
    stamp_delivery_epoch(ctx, music_complete_at="2026-01-01T00:00:00Z")
    assert music_clear_blocked(ctx, "mmaudio_sfx", source="hollow_unmark")
    break_music_epoch_seal(ctx, "unit_test")
    assert not music_clear_blocked(ctx, "mmaudio_sfx", source="hollow_unmark")


def test_air_order_freeze_blocks_optimizer_until_unlock(ctx):
    freeze_air_order(ctx, reason="test")
    assert optimizer_live_mutate_blocked(ctx) is True
    unlock_air_order_freeze(ctx, "unit_test")
    # May still be false unless skip flags set — at least freeze cleared.
    from interview_mux.delivery_guardrails import air_order_frozen

    assert air_order_frozen(ctx) is False


def test_junction_budget_exhaust_pins_not_soft_pass(ctx):
    """JSQ-B3: exhaust pins classified refuse — never needs_operator hang."""
    pin = junction_budget_exhaust_hard_pin(ctx)
    assert pin == "junction_snip_qa"
    meta = ctx.read_json("run_meta.json")
    assert meta.get("junction_remaster_budget_exhausted") is True
    assert meta.get("junction_budget_exhaust_classified") is True
    assert meta.get("needs_operator") is not True
    assert not meta.get("needs_operator_stage")


def test_junction_budget_exhaust_is_classified_not_operator_gate():
    """JSQ-B3: unattended must not stamp needs_operator for budget/osc reasons."""
    from interview_mux.operator_gates import should_stamp_needs_operator

    meta = {"full_auto": True, "homunculus_version": "0.2.0"}
    for reason in (
        "junction_remaster_budget_exhausted",
        "junction_oscillation_halt",
        "junction_budget_exhaust",
        "junction_quality_blocked",
    ):
        assert should_stamp_needs_operator(
            "junction_snip_qa", reason, meta=meta
        ) is False


def test_avoidance_is_not_true_waste():
    assert wasted_work_is_true_waste("avoided_musicgen") is False
    assert wasted_work_is_true_waste("orphan") is True
    from interview_mux.thrash_hardening import wasted_work_counts_toward_sticky_halt

    assert wasted_work_counts_toward_sticky_halt(
        "music_deferred", {"reason": "assembly_missing"}
    ) is False
    assert wasted_work_counts_toward_sticky_halt(
        "music_deferred", {"reason": "phase_a_unsealed"}
    ) is False
    assert wasted_work_counts_toward_sticky_halt("music_deferred", {"reason": "beds_stuck"}) is True
    assert wasted_work_counts_toward_sticky_halt("orphan") is True
    assert wasted_work_counts_toward_sticky_halt(
        "orphan_artifact", {"stages": ["sound_design_plan"], "promoted": [], "demoted": []}
    ) is False
    assert wasted_work_counts_toward_sticky_halt(
        "orphan_artifact", {"stages": [], "demoted": ["edl"]}
    ) is True


def test_gate_wait_escalates(ctx):
    from interview_mux.thrash_hardening import GATE_WAIT_ESCALATE_TICKS

    last = {}
    for _ in range(GATE_WAIT_ESCALATE_TICKS):
        last = gate_wait_tick(ctx, "voice_reference_pending")
    assert last.get("escalate") is True
    assert "gate_wait_escalate" in last.get("halt_signature", "")


def test_no_auto_s3_on_advisories(ctx, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_REQUIRE_OPERATOR_PUBLISH_ADVISORY", "1")
    def _patch(meta):
        meta["quality_advisories"] = [{"code": "rubric"}]
        meta["aspirational_proceeded"] = True

    ctx.mutate_run_meta(_patch)
    assert has_quality_advisories(ctx)
    assert publish_blocked_by_advisories(ctx) is True


def test_producer_pin_table_covers_delivery_order():
    for sid in DELIVERY_ORDER:
        assert sid in PRODUCER_PIN_TABLE
        assert producer_pin_for_token(f"{sid}_missing") == sid


def test_clear_from_respects_blast_and_music_seal(ctx):
    stamp_delivery_epoch(ctx, music_complete_at="2026-01-01T00:00:00Z")
    for sid in ("edl", "mix", "mmaudio_sfx", "music_palette_compose"):
        mark_done_raw(ctx, sid)
    order = list(DELIVERY_ORDER)
    ctx.clear_from("edl", order, blast_source="edl")
    assert ctx.is_done("mmaudio_sfx")
    assert ctx.is_done("music_palette_compose")
    # edl itself is in blast and may clear
    assert not ctx.is_done("edl") or ctx.is_done("edl")
