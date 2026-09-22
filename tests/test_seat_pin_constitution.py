"""Complete seat + pin constitution (exec_13167 follow-through).

Laws (MUX_FORENSICS=0):
- Mix leave/done requires mtime **and** commitment (``mix_outputs_seated``).
- ``mix_seat_resume_stage`` is the only mix↔junction↔finalize resume SSOT.
- Producer pins are exact tokens only (no bare stage-id substring).
- ESR freshness uses exact pin→family maps (no ``vo_`` substring traps).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.air_order import (
    ensure_assembly_mtime_seats_edl,
    mix_outputs_seated,
    mix_seat_resume_stage,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import producer_pin_for_token
from interview_mux.thrash_hardening import path_to_master_pin
from run_fixtures import isolated_run_ctx, mark_done_raw

_WAV = b"RIFF" + (b"\x00" * 2048)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "seat_pin_constitution")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_assembly(ctx: RunContext, *, gen: int = 2, ledger_ok: bool = True) -> None:
    sel = bump_order_lock(
        {
            "ordered_segment_ids": ["seg_001"],
            "version": 1,
            "air_order_generation": gen,
        },
        source="seat_pin",
    )
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_001"],
        "air_order_generation": gen,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_001",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "timeline_start_ms": 0,
                "duration_ms": 1000,
            }
        ],
        "timeline_duration_ms": 1000,
    }
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", edl, skip_handoff=True, stage_key="edl")
    ctx.write_json(
        "master/air_order.json",
        {"generation": gen, "air_order_generation": gen},
        skip_handoff=True,
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(_WAV)
    from interview_mux.seam_autopsy import _file_fingerprint

    fp = _file_fingerprint(asm) if ledger_ok else {"sha256": "deadbeef", "size": 1}
    (ctx.final_path("master", "render_ledger.json")).write_text(
        json.dumps(
            {
                "version": 1,
                "assembly": fp,
                "air_order_generation": gen,
                "clips": [],
            }
        )
    )
    ensure_assembly_mtime_seats_edl(ctx)


def test_mtime_only_is_not_seated_when_ledger_mismatches(ctx: RunContext) -> None:
    _plant_assembly(ctx, ledger_ok=False)
    assert mix_outputs_seated(ctx) is False
    assert mix_seat_resume_stage(ctx) == "mix"


def test_hollow_is_done_does_not_advance_past_unseated_mix(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """is_done(mix) alone must not leave mix — commitment still required."""
    _plant_assembly(ctx, ledger_ok=False)
    mark_done_raw(ctx, "mix")
    assert ctx.is_done("mix")
    assert mix_outputs_seated(ctx) is False
    assert mix_seat_resume_stage(ctx) == "mix"
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: True,
    )
    for sid in (
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "edl",
        "edl_narrative_audit",
    ):
        mark_done_raw(ctx, sid)
    assert path_to_master_pin(ctx) == "mix"


def test_seated_ssot_advances_to_junction(ctx: RunContext) -> None:
    _plant_assembly(ctx, ledger_ok=True)
    mark_done_raw(ctx, "mix")
    assert mix_outputs_seated(ctx) is True
    assert mix_seat_resume_stage(ctx) == "junction_snip_qa"


def test_exact_pin_remix_does_not_match_mix(ctx: RunContext) -> None:
    assert producer_pin_for_token("remix bed failed", ctx=ctx, default="") != "mix"
    assert producer_pin_for_token("mix", ctx=ctx) == "mix"
    assert producer_pin_for_token("artifact_missing:mix", ctx=ctx) == "mix"


def test_esr_sound_design_pin_ignores_vo_substring(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.execution_status import _collect_progress_sources

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _c: (False, ""),
    )
    synth = ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "vo_layup_seg_009.wav").write_bytes(_WAV)
    sources, _ = _collect_progress_sources(ctx, pin="sound_design_vo_finalize")
    assert not any(s.startswith("vo_wavs") for s in sources)
    sources_vo, _ = _collect_progress_sources(ctx, pin="vo_synthesize")
    assert any(s.startswith("vo_wavs") for s in sources_vo)
