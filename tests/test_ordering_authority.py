"""One authority decides delivery ordering exceptions (ISSUES 62)."""

from __future__ import annotations

import pytest

from interview_mux import ordering_authority as oa


@pytest.mark.parametrize("pre", ["mix", "music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx", None])
def test_junction_ahead_of_mix_and_music_when_recut_owed(monkeypatch, pre) -> None:
    monkeypatch.setattr(oa, "_junction_recut_precedes_mix", lambda c: True)
    assert oa.ordering_exempt(object(), "junction_snip_qa", pre) == "junction_recut_precedes_mix"


def test_junction_not_exempt_without_owed_recut(monkeypatch) -> None:
    monkeypatch.setattr(oa, "_junction_recut_precedes_mix", lambda c: False)
    assert oa.ordering_exempt(object(), "junction_snip_qa", "mix") is None


def test_junction_never_skips_edl(monkeypatch) -> None:
    monkeypatch.setattr(oa, "_junction_recut_precedes_mix", lambda c: True)
    assert oa.ordering_exempt(object(), "junction_snip_qa", "edl") is None


def test_speech_first_mix_ahead_of_music(monkeypatch) -> None:
    monkeypatch.setattr(oa, "_beds_deferred_for_mix", lambda c: True)
    assert oa.ordering_exempt(object(), "mix", "mmaudio_sfx") == "speech_first_beds_deferred"
    assert oa.ordering_exempt(object(), "mix", "edl") is None


def test_every_ordering_check_consults_the_authority() -> None:
    """Guard against a check growing its own copy of an exception again."""
    import inspect

    from interview_mux import air_order, delivery_guardrails, llm_flow_hardening
    from interview_mux.homunculus import runtime

    for fn in (
        runtime._seed_prereq_block,
        llm_flow_hardening.maybe_require_upstream_llm_progress,
        delivery_guardrails.mix_epoch_block,
        delivery_guardrails.upstream_stale_blockers,
        air_order.assert_consumer,
    ):
        src = inspect.getsource(fn)
        assert "ordering_exempt" in src, fn.__qualname__
        assert "junction_recut_precedes_mix(" not in src, fn.__qualname__


def test_mix_seats_before_music_when_music_needs_a_seated_assembly(monkeypatch) -> None:
    """exec_052: after a re-cut, mix waited for music and music for a seated assembly."""
    monkeypatch.setattr(oa, "_beds_deferred_for_mix", lambda c: False)
    monkeypatch.setattr(oa, "_speech_first_mix_allowed", lambda c: True)
    assert oa.ordering_exempt(object(), "mix", "music_palette_compose") == "assembly_seat_before_music"
    monkeypatch.setattr(oa, "_speech_first_mix_allowed", lambda c: False)
    assert oa.ordering_exempt(object(), "mix", "music_palette_compose") is None
