"""HAU — Heard-Assembly Unification (DP-BUILD-ASSEMBLY-FRESHNESS).

Federal: preview WAV alone never admits music; seated or operator preview_music;
optional_beds_until_remaster (speech-first mix) for Partial + Full-auto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    delivery_stable_for_music,
    mix_epoch_block,
    music_assembly_ready,
)
from interview_mux.homunculus.agenda import stage_outputs_present
from interview_mux.mix_junction_seat import (
    BEDS_POLICY,
    allow_speech_first_mix,
    heard_assembly,
    may_admit_music,
    music_admit_block_reason,
    note_speech_first_mix,
    open_preview_music_gate,
    maybe_remaster_after_music_epoch,
    remaster_in_flight,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hau_assembly")


def _write_preview(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly_preview.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


def _write_assembly(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


def _set_mode(ctx: RunContext, *, partial: bool) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    if partial:
        meta["run_mode"] = "partially-accelerated"
        meta["partial_auto"] = True
        meta.pop("full_auto", None)
    else:
        meta["run_mode"] = "full-auto"
        meta["full_auto"] = True
        meta.pop("partial_auto", None)
    ctx.write_json("run_meta.json", meta, skip_handoff=True)


@pytest.mark.parametrize("partial", [True, False])
def test_hau_preview_alone_blocks_music_admit(
    ctx: RunContext, partial: bool
) -> None:
    _set_mode(ctx, partial=partial)
    _write_preview(ctx)
    assert may_admit_music(ctx) is False
    assert music_assembly_ready(ctx) is False
    assert music_admit_block_reason(ctx) == "assembly_preview_only"
    assert stage_outputs_present(ctx, "music_palette_compose") is False
    assert stage_outputs_present(ctx, "mmaudio_sfx") is False


@pytest.mark.parametrize("partial", [True, False])
def test_hau_seated_admits_music(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch, partial: bool
) -> None:
    _set_mode(ctx, partial=partial)
    _write_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    assert may_admit_music(ctx) is True
    assert music_assembly_ready(ctx) is True
    assert music_admit_block_reason(ctx) == ""
    hau = heard_assembly(ctx)
    assert hau["seated"] is True
    assert hau["light"] is False
    assert hau["beds_policy"] == BEDS_POLICY


@pytest.mark.parametrize("partial", [True, False])
def test_hau_speech_first_mix_unblocks_mix_epoch(
    ctx: RunContext, partial: bool
) -> None:
    _set_mode(ctx, partial=partial)
    _write_preview(ctx)
    assert allow_speech_first_mix(ctx) is True
    assert mix_epoch_block(ctx, stage="mix") is None
    assert mix_epoch_block(ctx, stage="junction_snip_qa") == "music_incomplete"


def test_hau_delivery_stable_blocks_preview_only(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Federal delivery_stable_for_music — not Partial-only."""
    _set_mode(ctx, partial=False)
    _write_preview(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid
        in {
            "nugget_layup_compose",
            "vo_line_adjudicate",
            "edl",
            "assembly_preview",
            "listen_delight_audit",
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.listen_delight_cleared_for_progress",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda _c, _s: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._layup_escalation_blocking",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.read_checkpoint",
        lambda _c: {"ok": True},
    )
    ok, reason = delivery_stable_for_music(ctx)
    assert ok is False
    assert reason == "assembly_preview_only"


def test_hau_preview_music_gate_then_remaster(ctx: RunContext) -> None:
    _set_mode(ctx, partial=True)
    _write_preview(ctx)
    assert open_preview_music_gate(ctx, source="driver") is False
    assert open_preview_music_gate(ctx, source="operator") is False
    assert open_preview_music_gate(ctx, source="gui") is True
    assert may_admit_music(ctx) is True
    note_speech_first_mix(ctx)
    # With gate open, speech-first is off; remaster still fires after music epoch.
    assert allow_speech_first_mix(ctx) is False
    assert maybe_remaster_after_music_epoch(ctx) is True
    assert remaster_in_flight(ctx) is True
