"""Mix–Junction Seat Authority (Partial Zero DP-MIX-JUNCTION-SEAT-AUTHORITY)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.mix_junction_seat import (
    abandon_remaster,
    allow_speech_first_mix,
    begin_remaster,
    clear_remaster,
    demote_hollow_mix_done,
    junction_precedes_mix,
    may_admit_music,
    maybe_remaster_after_music_epoch,
    music_admit_block_reason,
    must_verify_commitment,
    note_speech_first_mix,
    remaster_in_flight,
    remaster_session,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "mix_junction_seat")


def _write_preview(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly_preview.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


def _write_assembly(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


def _set_partial(ctx: RunContext) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    meta["run_mode"] = "partially-accelerated"
    meta["partial_auto"] = True
    ctx.write_json("run_meta.json", meta, skip_handoff=True)


def test_must_verify_commitment_only_when_assembly_exists(ctx: RunContext) -> None:
    """DP-A5 Option A: commitment required iff assembly.wav is present."""
    assert must_verify_commitment(ctx) is False
    _write_assembly(ctx)
    assert must_verify_commitment(ctx) is True


def test_remaster_owner_gates_precede(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.live_incomplete_cuts", lambda _c: False
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.assembly_stale", lambda _c: False
    )
    _write_assembly(ctx)
    clear_remaster(ctx)
    assert remaster_in_flight(ctx) is False
    assert junction_precedes_mix(ctx) is False
    begin_remaster(ctx, owner="junction")
    assert remaster_in_flight(ctx) is True
    assert junction_precedes_mix(ctx) is True
    clear_remaster(ctx)
    assert junction_precedes_mix(ctx) is False


def test_partial_music_requires_seated_not_preview(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_partial(ctx)
    _write_preview(ctx)
    assert may_admit_music(ctx) is False
    assert allow_speech_first_mix(ctx) is True
    _write_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: False
    )
    assert may_admit_music(ctx) is False
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    assert may_admit_music(ctx) is True
    assert allow_speech_first_mix(ctx) is False


def test_full_auto_preview_alone_does_not_admit(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HAU federal: Full-auto has no dual-admit carve-out for preview WAV."""
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    meta["run_mode"] = "full-auto"
    meta.pop("partial_auto", None)
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    _write_preview(ctx)
    assert may_admit_music(ctx) is False
    assert allow_speech_first_mix(ctx) is True
    assert music_admit_block_reason(ctx) == "assembly_preview_only"


def test_preview_music_gate_admits_when_gui_opens(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.mix_junction_seat import (
        open_preview_music_gate,
        preview_music_gate_open,
    )

    _set_partial(ctx)
    _write_preview(ctx)
    assert may_admit_music(ctx) is False
    assert open_preview_music_gate(ctx, source="auto") is False
    assert open_preview_music_gate(ctx, source="operator") is False
    assert preview_music_gate_open(ctx) is False
    assert open_preview_music_gate(ctx, source="gui") is True
    assert preview_music_gate_open(ctx) is True
    assert may_admit_music(ctx) is True
    assert allow_speech_first_mix(ctx) is False


def test_heard_assembly_ssot_light_preview(ctx: RunContext) -> None:
    from interview_mux.mix_junction_seat import BEDS_POLICY, heard_assembly

    snap = heard_assembly(ctx)
    assert snap["kind"] == "none"
    assert snap["beds_policy"] == BEDS_POLICY
    _write_preview(ctx)
    snap = heard_assembly(ctx)
    assert snap["kind"] == "preview"
    assert snap["light"] is True
    assert snap["seated"] is False
    assert snap["may_admit_music"] is False
    assert snap["path"] == "master/assembly_preview.wav"


def test_abandon_remaster_clears_sticky(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.live_incomplete_cuts", lambda _c: False
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.assembly_stale", lambda _c: False
    )
    _write_assembly(ctx)
    begin_remaster(ctx, owner="junction")
    assert remaster_in_flight(ctx) is True
    abandon_remaster(ctx, reason="budget_exhaust")
    assert remaster_in_flight(ctx) is False
    assert junction_precedes_mix(ctx) is False


def test_remaster_session_clears_when_seated(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    with remaster_session(ctx, owner="junction"):
        assert remaster_in_flight(ctx) is True
    assert remaster_in_flight(ctx) is False


def test_speech_first_then_music_epoch_remaster(ctx: RunContext) -> None:
    _set_partial(ctx)
    note_speech_first_mix(ctx)
    assert maybe_remaster_after_music_epoch(ctx) is True
    assert remaster_in_flight(ctx) is True
    # Idempotent — do not double-stamp.
    assert maybe_remaster_after_music_epoch(ctx) is False


def test_unseated_music_block_reason(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_partial(ctx)
    _write_preview(ctx)
    assert music_admit_block_reason(ctx) == "assembly_preview_only"
    _write_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: False
    )
    assert music_admit_block_reason(ctx) == "assembly_not_seated_for_music"


def test_demote_hollow_mix_done(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_assembly(ctx)
    marker = ctx.final_path(".stage_done", "mix")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done")
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: False
    )
    assert demote_hollow_mix_done(ctx) is True
    assert not ctx.is_done("mix")
