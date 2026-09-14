"""HX-2: mix is complete only when mix_outputs_seated.

mtime-only freshness or a stale-flag clear must not stamp mix done.
HX-3 autopsy path stays later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_order import mix_outputs_seated
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.heal_routing import mix_assembly_seated
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    incompleteness_resume_stage,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_WAV = b"RIFF" + (b"\x00" * 2048)


def _edl(*, ids: list[str], gen: int | None = None) -> dict:
    clips = [
        {
            "type": "speech",
            "segment_id": sid,
            "source_start_ms": 0,
            "source_end_ms": 1000,
            "timeline_start_ms": i * 1000,
            "duration_ms": 1000,
        }
        for i, sid in enumerate(ids)
    ]
    out: dict = {
        "version": 1,
        "ordered_segment_ids": list(ids),
        "timeline_duration_ms": max(1000, 1000 * len(ids)),
        "clips": clips,
    }
    if gen is not None:
        out["air_order_generation"] = gen
    return out


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hx2_mix_unseated")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _write_wav(ctx: RunContext) -> None:
    dest = ctx.final_path("master", "assembly.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_WAV)


def _plant_seated(ctx: RunContext) -> None:
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_001"], "version": 1},
        source="hx2",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", _edl(ids=["seg_001"]), skip_handoff=True)
    _write_wav(ctx)


def test_hx2_wav_without_edl_is_unseated(ctx: RunContext) -> None:
    _write_wav(ctx)
    assert mix_outputs_seated(ctx) is False
    reason = stage_artifact_incompleteness(ctx, "mix")
    assert reason is not None
    assert "mix unseated" in reason
    assert incompleteness_resume_stage(ctx, "mix") == "mix"


def test_hx2_generation_mismatch_is_unseated(ctx: RunContext) -> None:
    ctx.write_json("master/air_order.json", {"generation": 2}, skip_handoff=True)
    ctx.write_json("master/edl.json", _edl(ids=["seg_001"], gen=1), skip_handoff=True)
    _write_wav(ctx)
    assert mix_outputs_seated(ctx) is False
    assert "mix unseated" in (stage_artifact_incompleteness(ctx, "mix") or "")


def test_hx2_order_lock_mismatch_is_unseated(ctx: RunContext) -> None:
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_001", "seg_002"], "version": 1},
        source="hx2",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", _edl(ids=["seg_001"]), skip_handoff=True)
    _write_wav(ctx)
    assert mix_outputs_seated(ctx) is False
    assert "mix unseated" in (stage_artifact_incompleteness(ctx, "mix") or "")


def test_hx2_raw_done_unmarked_while_unseated(ctx: RunContext) -> None:
    _write_wav(ctx)
    mark_done_raw(ctx, "mix")
    assert ctx.is_done("mix")
    assert seed_stage_complete(ctx, "mix") is False
    out = heal_or_refuse_mark(ctx, "mix")
    assert out.get("unmarked") is True
    assert not ctx.is_done("mix")
    assert out.get("marked") is not True


def test_hx2_mark_done_does_not_clear_stale_when_unseated(ctx: RunContext) -> None:
    _write_wav(ctx)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "assembly_seating_stale": True,
            "assembly_seating_stale_reason": "order_change:air_order",
        },
        skip_handoff=True,
    )
    ctx.mark_done("mix")
    assert not ctx.is_done("mix")
    meta = ctx.read_json("run_meta.json")
    assert meta.get("assembly_seating_stale") is True


def test_hx2_seated_mix_marks_and_clears_stale(ctx: RunContext) -> None:
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "assembly_seating_stale": True,
            "assembly_seating_stale_reason": "order_change:air_order",
        },
        skip_handoff=True,
    )
    _plant_seated(ctx)
    assert mix_outputs_seated(ctx) is True
    assert stage_artifact_incompleteness(ctx, "mix") is None
    out = heal_or_refuse_mark(ctx, "mix")
    assert out.get("marked") is True
    assert ctx.is_done("mix")
    assert seed_stage_complete(ctx, "mix") is True
    meta = ctx.read_json("run_meta.json")
    assert not meta.get("assembly_seating_stale")


def test_hx2_heal_files_exist_is_not_seated(ctx: RunContext) -> None:
    ctx.write_json(
        "master/air_order.json",
        {"generation": 4},
        skip_handoff=True,
    )
    ctx.write_json("master/edl.json", _edl(ids=["seg_001"], gen=1), skip_handoff=True)
    _write_wav(ctx)
    assert mix_assembly_seated(ctx) is False
    pin = producer_pin_for_token(
        "mix unseated — resume mix: mix_outputs_seated", ctx=ctx
    )
    assert pin == "mix"
