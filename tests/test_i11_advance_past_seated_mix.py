"""i11g: after seated mix, resume must advance to junction (not re-pin mix).

exec_13167: Finished Mix assembly → premature_complete:mix_seat thrash because
delivery_resume_stage / safe_mix_resume_stage always returned mix once music
epoch was complete.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.air_order import ensure_assembly_mtime_seats_edl, mix_outputs_seated
from interview_mux.delivery_guardrails import safe_mix_resume_stage
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw

_WAV = b"RIFF" + (b"\x00" * 2048)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i11g_advance_past_mix")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _seat_mix(ctx: RunContext) -> None:
    sel = bump_order_lock(
        {
            "ordered_segment_ids": ["seg_001"],
            "version": 1,
            "air_order_generation": 2,
        },
        source="i11g",
    )
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_001"],
        "air_order_generation": 2,
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
        {"generation": 2, "air_order_generation": 2},
        skip_handoff=True,
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(_WAV)
    from interview_mux.seam_autopsy import _file_fingerprint

    fp = _file_fingerprint(asm)
    (ctx.final_path("master", "render_ledger.json")).write_text(
        json.dumps(
            {
                "version": 1,
                "assembly": fp,
                "air_order_generation": 2,
                "clips": [],
            }
        )
    )
    ensure_assembly_mtime_seats_edl(ctx)
    mark_done_raw(ctx, "mix")
    for sid in (
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "edl_narrative_audit",
        "edl",
    ):
        mark_done_raw(ctx, sid)


def test_i11_safe_mix_resume_advances_when_seated(ctx: RunContext, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.critical_residual_view",
        lambda _ctx: type("V", (), {"count": 0, "kinds": ()})(),
    )
    _seat_mix(ctx)
    assert mix_outputs_seated(ctx) is True
    assert safe_mix_resume_stage(ctx) == "junction_snip_qa"
