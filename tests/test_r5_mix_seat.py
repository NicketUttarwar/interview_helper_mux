"""R5 residual closures (#24) under MUX_FORENSICS=0.

write_live_edl content unseats · commitment remaster cousin · music-complete
unseat classifies mix_seat · no mtime-fake seat when render gen drifted.
i24 / End-D / HX-2 remain importable cousins.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.air_order import (
    ensure_assembly_mtime_seats_edl,
    live_render_generation_matches,
    mix_outputs_seated,
    mix_wav_fresh_versus_edl,
    write_live_edl,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import (
    FAIL_CLASS_MIX_SEAT,
    FAIL_CLASS_MUSIC_EPOCH,
    fail_class_for_failure,
    premature_fail_class,
)
from run_fixtures import isolated_run_ctx

_WAV = b"RIFF" + (b"\x00" * 2048)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    run = isolated_run_ctx(tmp_path, "r5_mix_seat")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _write_raw(ctx: RunContext, rel: str, doc: dict) -> None:
    path = ctx.final_path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _plant_seated(ctx: RunContext, *, gen: int = 1) -> dict:
    sel = bump_order_lock(
        {
            "ordered_segment_ids": ["seg_001"],
            "version": 1,
            "air_order_generation": gen,
        },
        source="r5",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_001"],
        "air_order_generation": gen,
        "timeline_duration_ms": 1000,
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
    }
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    _write_raw(
        ctx,
        "master/air_order.json",
        {"generation": gen, "air_order_generation": gen},
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(_WAV)
    from interview_mux.seam_autopsy import _file_fingerprint

    fp = _file_fingerprint(asm)
    _write_raw(
        ctx,
        "master/render_ledger.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "edl_hash": "x",
            "assembly": fp,
            "clips": [],
            "air_order_generation": gen,
        },
    )
    ensure_assembly_mtime_seats_edl(ctx)
    assert mix_outputs_seated(ctx) is True
    return edl


def test_r5a_write_live_edl_content_change_unseats(ctx: RunContext) -> None:
    """#24: write_live_edl content change → mix_outputs_seated false."""
    edl = _plant_seated(ctx, gen=1)
    edl2 = {
        **edl,
        "timeline_duration_ms": 2000,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_001",
                "source_start_ms": 0,
                "source_end_ms": 2000,
                "timeline_start_ms": 0,
                "duration_ms": 2000,
            }
        ],
    }
    live = write_live_edl(ctx, edl2, source="edl")
    assert int(live.get("generation") or 0) >= 2
    assert mix_outputs_seated(ctx) is False


def test_r5b_commitment_remaster_bypasses_low_gain(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#24 / i24 cousin: path=commitment remasters; feel still refuses."""
    from interview_mux import junction_snip_qa

    calls: list[str] = []
    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        lambda *_a, **_k: {"allow": False, "refuse_reason": "low_gain_test"},
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

    ok_feel, _ = junction_snip_qa._budgeted_remaster_mix(ctx, path="feel")
    assert ok_feel is False
    assert calls == []
    ok_commit, used = junction_snip_qa._budgeted_remaster_mix(ctx, path="commitment")
    assert ok_commit is True
    assert used == 1
    assert calls == ["remaster"]


def test_r5c_music_complete_unseated_is_mix_seat_not_music(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#24: music_epoch_complete + unseated → fail_class mix_seat (not music)."""
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    reason = "mix unseated — resume mix: mix_outputs_seated"
    assert fail_class_for_failure(stage="mix", reason=reason) == FAIL_CLASS_MIX_SEAT
    assert fail_class_for_failure(resume="mix") == FAIL_CLASS_MIX_SEAT
    assert premature_fail_class("mix") == FAIL_CLASS_MIX_SEAT
    # Music-incomplete prose still maps to music_epoch (HX-1 cousin).
    assert (
        fail_class_for_failure(stage="mix", reason="music incomplete")
        == FAIL_CLASS_MUSIC_EPOCH
    )

    from interview_mux.delivery_guardrails import premature_cap_hard_pin

    ctx.write_json(
        "gui_job.json",
        {"status": "running", "current_stage": "mix"},
        skip_handoff=True,
    )
    assert premature_cap_hard_pin(ctx, "mix") == "mix"


def test_r5d_mtime_alone_does_not_seat_when_gen_drifted(ctx: RunContext) -> None:
    """#24: ensure_assembly_mtime_seats_edl cannot fake-seat drifted render gen."""
    _plant_seated(ctx, gen=3)
    # Drift render ledger gen while keeping wav mtime fresh vs EDL.
    _write_raw(
        ctx,
        "master/render_ledger.json",
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
        },
    )
    ensure_assembly_mtime_seats_edl(ctx)
    assert mix_wav_fresh_versus_edl(ctx) is True
    assert live_render_generation_matches(ctx) is False
    assert mix_outputs_seated(ctx) is False


def test_r5_i24_endd_hx_cousins_importable() -> None:
    import test_endd_commitment_seating as endd
    import test_hx1_mix_epoch_unsealed as hx1
    import test_hx2_mix_unseated as hx2
    import test_hx4_mix_lease_pin as hx4
    import test_i24_commitment_remaster as i24

    assert callable(i24.test_i24_render_ledger_gen_mismatch_unseats)
    assert callable(endd.test_endd_commitment_bypasses_budget_and_low_gain)
    assert callable(hx2.test_hx2_generation_mismatch_is_unseated)
    assert callable(hx1.test_hx1_unsealed_unstable_is_music_incomplete)
    assert callable(hx4.test_hx4_mix_lease_holds_after_music_complete)
