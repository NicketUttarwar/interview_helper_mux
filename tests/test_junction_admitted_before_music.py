"""junction_snip_qa may run before music when a pre-mix recut is owed (ISSUES 61)."""

from __future__ import annotations

import pytest

from interview_mux import delivery_guardrails as dg


def _ctx(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dg, "read_delivery_epoch", lambda c: {})
    monkeypatch.setattr(dg, "music_epoch_complete", lambda c: False)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl", lambda c: False
    )
    return object()


def test_junction_is_admitted_when_recut_precedes_mix(monkeypatch) -> None:
    ctx = _ctx(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix", lambda c: True
    )
    assert dg.mix_epoch_block(ctx, stage="junction_snip_qa") is None


def test_junction_still_waits_for_music_otherwise(monkeypatch) -> None:
    ctx = _ctx(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix", lambda c: False
    )
    assert dg.mix_epoch_block(ctx, stage="junction_snip_qa") == "music_incomplete"


def test_finalize_is_not_affected(monkeypatch) -> None:
    ctx = _ctx(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix", lambda c: True
    )
    assert dg.mix_epoch_block(ctx, stage="master_finalize") == "music_incomplete"


@pytest.mark.parametrize("earliest", ["mix", "music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"])
def test_seed_order_admits_junction_before_music_band(monkeypatch, earliest) -> None:
    from interview_mux.homunculus import runtime as rt

    class _Ctx:
        run_id = "x"

    monkeypatch.setattr("interview_mux.llm_flow_hardening._earliest_incomplete_seed_stage", lambda c, s: earliest)
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix", lambda c: True
    )
    ctx = _Ctx()
    ctx.log = lambda *a, **k: None
    assert rt._seed_prereq_block(ctx, "junction_snip_qa") is None


def test_junction_admitted_during_speech_first_remaster(monkeypatch) -> None:
    """exec_052: after music, junction was refused on speech_first_remaster_pending
    while the remaster mix refused until junction recut its residuals."""
    monkeypatch.setattr(dg, "read_delivery_epoch", lambda c: {"music_complete_at": "t"})
    monkeypatch.setattr(dg, "music_epoch_complete", lambda c: True)
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.ensure_speech_first_remaster", lambda c: True
    )
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix", lambda c: True
    )
    assert dg.mix_epoch_block(object(), stage="junction_snip_qa") is None
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix", lambda c: False
    )
    assert dg.mix_epoch_block(object(), stage="junction_snip_qa") == "speech_first_remaster_pending"
    assert dg.mix_epoch_block(object(), stage="master_finalize") == "speech_first_remaster_pending"
