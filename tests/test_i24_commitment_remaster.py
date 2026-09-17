"""i24: junction commitment remaster must not refuse low_gain / hollow-done.

When write_live_edl leaves assembly older than EDL, path=commitment remasters
even if the timeline-reopen meta-gate would refuse a cosmetic remaster.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_order import (
    ensure_assembly_mtime_seats_edl,
    live_render_generation_matches,
    mix_outputs_seated,
    mix_wav_fresh_versus_edl,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx

_WAV = b"RIFF" + (b"\x00" * 2048)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i24_commitment_remaster")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_i24_commitment_path_bypasses_low_gain(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import junction_snip_qa

    calls: list[str] = []

    def _refuse_gain(*_a, **_k):
        return {"allow": False, "refuse_reason": "low_gain_test"}

    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        _refuse_gain,
    )
    monkeypatch.setattr(
        junction_snip_qa,
        "remaster_mix_only",
        lambda _ctx: calls.append("remaster"),
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.junction_remaster_budget_ok",
        lambda _ctx: (True, 0),
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.note_junction_remaster",
        lambda _ctx: 1,
    )

    # Cosmetic path still refuses.
    ok_feel, _ = junction_snip_qa._budgeted_remaster_mix(ctx, path="feel")
    assert ok_feel is False
    assert calls == []

    # Commitment path must remaster anyway (assembly seat).
    ok_commit, used = junction_snip_qa._budgeted_remaster_mix(ctx, path="commitment")
    assert ok_commit is True
    assert used == 1
    assert calls == ["remaster"]


def test_i24_render_ledger_gen_mismatch_unseats(ctx: RunContext) -> None:
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_001"], "version": 1, "air_order_generation": 3},
        source="i24",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "air_order_generation": 3,
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
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/air_order.json",
        {"generation": 3, "air_order_generation": 3},
        skip_handoff=True,
        stage_key="edl",
    )
    import json

    dest_rl = ctx.final_path("master", "render_ledger.json")
    dest_rl.parent.mkdir(parents=True, exist_ok=True)
    dest_rl.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "edl_hash": "x",
                "assembly": {
                    "path": "master/assembly.wav",
                    "exists": True,
                    "size": len(_WAV),
                    "sha256_edges": "ab",
                },
                "clips": [],
                "air_order_generation": 2,
            }
        ),
        encoding="utf-8",
    )
    dest = ctx.final_path("master", "assembly.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_WAV)
    # Make wav fresher than EDL so only render-gen gate fails.
    ensure_assembly_mtime_seats_edl(ctx)
    assert mix_wav_fresh_versus_edl(ctx) is True
    assert live_render_generation_matches(ctx) is False
    assert mix_outputs_seated(ctx) is False


def test_i24_ensure_assembly_mtime_seats_edl(ctx: RunContext) -> None:
    import os
    import time

    edl = ctx.final_path("master", "edl.json")
    edl.parent.mkdir(parents=True, exist_ok=True)
    edl.write_text("{}", encoding="utf-8")
    asm = ctx.final_path("master", "assembly.wav")
    asm.write_bytes(_WAV)
    older = time.time() - 30
    os.utime(asm, (older, older))
    newer = time.time()
    os.utime(edl, (newer, newer))
    assert mix_wav_fresh_versus_edl(ctx) is False
    ensure_assembly_mtime_seats_edl(ctx)
    assert mix_wav_fresh_versus_edl(ctx) is True
