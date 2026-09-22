"""HAU footgun harden — close gate / bare epoch / speech-first none / remaster / preview-era / gui-only."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import mix_epoch_block
from interview_mux.mix_junction_seat import (
    allow_speech_first_mix,
    begin_remaster,
    close_preview_music_gate,
    junction_precedes_mix,
    may_admit_music,
    maybe_remaster_after_music_epoch,
    note_preview_era_music,
    note_speech_first_mix,
    open_preview_music_gate,
    preview_music_gate_open,
    remaster_in_flight,
    remaster_owner,
    who_runs_next,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hau_footguns")


def _write_preview(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly_preview.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


def _write_assembly(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


# --- FG1: close must clear preview_music_at ---


def test_fg1_close_preview_music_clears_at_stamp(ctx: RunContext) -> None:
    _write_preview(ctx)
    assert open_preview_music_gate(ctx, source="gui") is True
    assert preview_music_gate_open(ctx) is True
    close_preview_music_gate(ctx)
    assert preview_music_gate_open(ctx) is False
    assert may_admit_music(ctx) is False


# --- FG2: bare mix_epoch_block must not speech-first ---


def test_fg2_bare_mix_epoch_block_stays_music_incomplete(ctx: RunContext) -> None:
    _write_preview(ctx)
    assert allow_speech_first_mix(ctx) is True
    assert mix_epoch_block(ctx, stage="mix") is None
    assert mix_epoch_block(ctx) == "music_incomplete"
    assert mix_epoch_block(ctx, stage="") == "music_incomplete"


# --- FG3: speech-first refuses assembly_kind none ---


def test_fg3_speech_first_requires_preview_or_unseated(ctx: RunContext) -> None:
    assert allow_speech_first_mix(ctx) is False
    assert mix_epoch_block(ctx, stage="mix") == "music_incomplete"
    _write_preview(ctx)
    assert allow_speech_first_mix(ctx) is True


# --- FG4: music_epoch remaster lands on mix, not junction ---


def test_fg4_music_epoch_remaster_does_not_precede_junction(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.live_incomplete_cuts", lambda _c: False
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.assembly_stale", lambda _c: False
    )
    _write_preview(ctx)
    note_speech_first_mix(ctx)
    marker = ctx.final_path(".stage_done", "mix")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done")
    assert maybe_remaster_after_music_epoch(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert remaster_in_flight(ctx) is True
    assert junction_precedes_mix(ctx) is False
    assert who_runs_next(ctx) == "mix"
    assert not ctx.is_done("mix")
    # Junction remaster owner still precedes.
    begin_remaster(ctx, owner="junction")
    assert junction_precedes_mix(ctx) is True


# --- FG5: preview-era music stamps remaster when seat predated beds ---


def test_fg5_preview_era_remaster_when_seat_exists(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_preview(ctx)
    assert open_preview_music_gate(ctx, source="gui") is True
    note_preview_era_music(ctx)
    _write_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    # Seated after preview-era spend → remaster required.
    assert maybe_remaster_after_music_epoch(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"


def test_fg5_preview_era_no_remaster_before_first_seat(ctx: RunContext) -> None:
    _write_preview(ctx)
    assert open_preview_music_gate(ctx, source="gui") is True
    # No speech_first, kind=preview only → first mix folds beds; no sticky remaster.
    assert maybe_remaster_after_music_epoch(ctx) is False
    assert remaster_in_flight(ctx) is False


# --- FG6: only gui may open preview_music ---


def test_fg6_forged_operator_refused(ctx: RunContext) -> None:
    _write_preview(ctx)
    for src in ("operator", "auto", "homunculus", "", "cli"):
        assert open_preview_music_gate(ctx, source=src) is False
    assert preview_music_gate_open(ctx) is False
    assert open_preview_music_gate(ctx, source="gui") is True
