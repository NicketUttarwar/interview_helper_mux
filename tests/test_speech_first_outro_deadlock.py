"""exec_062: the outro rule and the speech-first rule handed mix and music to each other (ISSUES 85).

With only a preview assembly, music_palette_compose may not run (HAU: mix seats
the assembly first). But the sound design plan already names a theme_outro asset
with no close cue, and the candidate filter answered ``filter([mix])`` with
``[music_palette_compose]`` so that compose could place the cue. The walk then
refused compose, walked mix again, got compose again, and ended with nothing run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from run_fixtures import isolated_run_ctx, mark_done_raw

from interview_mux.delivery_guardrails import (
    defer_until_producers_ready,
    filter_delivery_candidates,
)
from interview_mux.mix_junction_seat import allow_speech_first_mix

OUTRO_MISSING = "music_palette_compose missing theme_outro cue"


def _preview_ctx(tmp_path: Path, run_id: str):
    ctx = isolated_run_ctx(tmp_path, run_id)
    preview = ctx.path("master/assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\0" * 64)
    mark_done_raw(ctx, "assembly_preview")
    mark_done_raw(ctx, "edl")
    return ctx


def _quiet_other_gates(monkeypatch: pytest.MonkeyPatch, *, outro_missing: bool) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr("interview_mux.delivery_guardrails.edl_ready", lambda _c: True)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.earliest_incomplete_must_precede",
        lambda _c, _s: "",
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion._music_palette_missing_outro_incompleteness",
        lambda _c: OUTRO_MISSING if outro_missing else None,
    )
    monkeypatch.setattr(
        "interview_mux.heal_pin_authority.admit_schedule",
        lambda _c, s: (True, s, "ok"),
    )


def test_speech_first_mix_is_not_handed_to_music_for_the_outro_cue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _preview_ctx(tmp_path, "outro_speech_first")
    _quiet_other_gates(monkeypatch, outro_missing=True)
    assert allow_speech_first_mix(ctx) is True

    out: list[str] = []
    deferred: list[str] = []
    assert defer_until_producers_ready(ctx, "mix", out, deferred) is False
    assert out == [] and deferred == []


def test_outro_rule_still_reinjects_compose_once_music_may_admit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _preview_ctx(tmp_path, "outro_music_admits")
    _quiet_other_gates(monkeypatch, outro_missing=True)
    # A seated assembly: music may admit, so mix waits for compose as before.
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.may_admit_music", lambda _c: True
    )
    assert allow_speech_first_mix(ctx) is False

    out: list[str] = []
    deferred: list[str] = []
    assert defer_until_producers_ready(ctx, "mix", out, deferred) is True
    assert out == ["music_palette_compose"] and deferred == ["mix"]


def test_filter_of_mix_alone_keeps_mix_under_speech_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exec_062 shape end to end: filter([mix]) must not come back as [compose]."""
    ctx = _preview_ctx(tmp_path, "outro_filter_mix")
    _quiet_other_gates(monkeypatch, outro_missing=True)
    monkeypatch.setattr("interview_mux.delivery_guardrails.phase_a_sealed", lambda _c: True)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready", lambda _c: (False, "no_master")
    )
    monkeypatch.setattr("interview_mux.delivery_guardrails._g1_open", lambda _c: False)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers", lambda _c, _s: []
    )

    filtered = filter_delivery_candidates(ctx, ["mix"])
    assert "music_palette_compose" not in filtered
    assert filtered == ["mix"]
