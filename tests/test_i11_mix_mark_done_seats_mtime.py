"""i11: mix mark_done must seat assembly mtime after EDL skew (hollow remaster).

Forensics exec_13167: mix rendered assembly.wav + QC passed, then
authority_denied:mark_done:hollow:mix because edl.json was newer than the wav.
Junction remaster then failed with the same hollow deny.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from interview_mux.air_order import (
    ensure_assembly_mtime_seats_edl,
    mix_outputs_seated,
    mix_wav_fresh_versus_edl,
)
from interview_mux.artifact_ownership import AuthorityDenied, assert_may_mark_done
from interview_mux.homunculus.agenda import stage_outputs_present
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from interview_mux import sound_design as sound_design_mod
from run_fixtures import isolated_run_ctx

_WAV = b"RIFF" + (b"\x00" * 2048)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i11_mix_seat_mtime")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _seat_mix_artifacts(ctx: RunContext, *, gen: int = 2) -> None:
    sel = bump_order_lock(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "version": 1,
            "air_order_generation": gen,
        },
        source="i11_test",
    )
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "air_order_generation": gen,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_001",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "timeline_start_ms": 0,
                "duration_ms": 1000,
            },
            {
                "type": "speech",
                "segment_id": "seg_002",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "timeline_start_ms": 1000,
                "duration_ms": 1000,
            },
        ],
        "timeline_duration_ms": 2000,
    }
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    ctx.write_json(
        "master/air_order.json",
        {"generation": gen, "air_order_generation": gen},
        skip_handoff=True,
        stage_key="edl",
    )
    import json

    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(_WAV)
    from interview_mux.seam_autopsy import _file_fingerprint

    fp = _file_fingerprint(asm)
    dest_rl = ctx.final_path("master", "render_ledger.json")
    dest_rl.parent.mkdir(parents=True, exist_ok=True)
    dest_rl.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "edl_hash": "x",
                "assembly": fp,
                "clips": [],
                "air_order_generation": gen,
            }
        )
    )


def test_i11_mix_source_seats_mtime_before_mark_done() -> None:
    src = inspect.getsource(sound_design_mod.mix)
    assert "ensure_assembly_mtime_seats_edl" in src
    seat_idx = src.index("ensure_assembly_mtime_seats_edl")
    done_idx = src.index("try_mark_done")
    assert seat_idx < done_idx
    assert "require_seated_before_mix_mark" in src


def test_i11_skewed_assembly_refuses_hollow_until_seated(ctx: RunContext) -> None:
    import os
    import time

    _seat_mix_artifacts(ctx)
    asm = ctx.final_path("master", "assembly.wav")
    edl = ctx.final_path("master", "edl.json")
    # Make EDL strictly newer than assembly (post-render write_live_edl skew).
    older = time.time() - 30.0
    os.utime(asm, (older, older))
    os.utime(edl, (older + 10.0, older + 10.0))
    assert mix_wav_fresh_versus_edl(ctx) is False
    assert mix_outputs_seated(ctx) is False
    assert stage_outputs_present(ctx, "mix") is False
    with pytest.raises(AuthorityDenied) as exc:
        assert_may_mark_done(ctx, "mix")
    assert "hollow:mix" in str(exc.value)

    ensure_assembly_mtime_seats_edl(ctx)
    assert mix_wav_fresh_versus_edl(ctx) is True
    assert mix_outputs_seated(ctx) is True
    assert stage_outputs_present(ctx, "mix") is True
    assert_may_mark_done(ctx, "mix")


def test_i11_assembly_stale_resume_pins_mix_not_junction(ctx: RunContext) -> None:
    """mtime-seated assembly must not resume junction when commitment diverged."""
    from interview_mux.delivery_guardrails import resolve_assembly_stale_resume

    _seat_mix_artifacts(ctx)
    # Seated by mtime/gen, but pretend commitment says diverged via stale live.
    assert resolve_assembly_stale_resume(ctx) == "mix"
    # Even when mix_assembly_seated would have been true:
    from interview_mux.heal_routing import mix_assembly_seated

    # Without diverged commitment, outputs_seated may be true — resume still mix.
    ensure_assembly_mtime_seats_edl(ctx)
    # Force seated path; resolve must still prefer mix (no junction pin).
    if mix_assembly_seated(ctx):
        assert resolve_assembly_stale_resume(ctx) == "mix"
    else:
        assert resolve_assembly_stale_resume(ctx) == "mix"


def test_i11_write_render_ledger_fingerprints_final_not_pending(
    ctx: RunContext, tmp_path: Path
) -> None:
    from interview_mux.seam_autopsy import write_render_ledger, _file_fingerprint

    _seat_mix_artifacts(ctx)
    final = ctx.final_path("master", "assembly.wav")
    pending_root = ctx.run_dir / ".pending_writes" / "mix" / "master"
    pending_root.mkdir(parents=True, exist_ok=True)
    pending = pending_root / "assembly.wav"
    # Different content in pending must not poison the ledger.
    pending.write_bytes(_WAV + b"PENDING_DIFF")
    led = write_render_ledger(ctx)
    assert led["assembly"]["sha256_edges"] == _file_fingerprint(final)["sha256_edges"]
    assert led["assembly"]["sha256_edges"] != _file_fingerprint(pending)["sha256_edges"]


def test_i11_mix_outputs_seated_false_when_ledger_sha_mismatches(ctx: RunContext) -> None:
    import json

    _seat_mix_artifacts(ctx)
    ensure_assembly_mtime_seats_edl(ctx)
    # Poison ledger SHA while keeping mtime seat.
    rl = ctx.final_path("master", "render_ledger.json")
    doc = json.loads(rl.read_text())
    doc["assembly"]["sha256_edges"] = "deadbeef" * 8
    rl.write_text(json.dumps(doc))
    assert mix_outputs_seated(ctx) is False


def test_i11_path_to_master_pins_mix_when_assembly_stale(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.thrash_hardening import path_to_master_pin

    _seat_mix_artifacts(ctx)
    ensure_assembly_mtime_seats_edl(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.heal_routing.mix_assembly_seated",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: True,
    )
    assert path_to_master_pin(ctx) == "mix"


def test_i11_mix_not_blocked_by_assembly_stale_upstream(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import upstream_stale_blockers

    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: True,
    )
    assert "assembly_stale_versus_edl" not in upstream_stale_blockers(ctx, "mix")
    assert "assembly_stale_versus_edl" in upstream_stale_blockers(ctx, "junction_snip_qa")
    assert "assembly_stale_versus_edl" in upstream_stale_blockers(ctx, "master_finalize")


def test_i11_remaster_mix_only_uses_nested_mix_staging(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remaster under junction must nest mix staging (else assembly lands in pending junction)."""
    import json

    from interview_mux.junction_snip_qa import remaster_mix_only

    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
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

    nested: list[str] = []

    def _spy_nested(ctx_, stage_id, fn):
        nested.append(stage_id)
        fn()

    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.refuse_mix_if_live_incomplete_cuts",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.assembly.run_mix",
        lambda _ctx: _ctx.final_path("master", "assembly.wav"),
    )
    monkeypatch.setattr(
        "interview_mux.assembly_ledger.write_assembly_ledger",
        lambda _ctx: {"complete": True, "naked_seam_count": 0},
    )
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.write_render_ledger",
        lambda _ctx: {"assembly": {"sha256_edges": "x"}},
    )
    monkeypatch.setattr(
        "interview_mux.air_order.ensure_assembly_mtime_seats_edl",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.promote_staged_side_effects",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.run_nested_staged_stage",
        _spy_nested,
    )

    remaster_mix_only(ctx)
    assert nested == ["mix"], f"expected nested mix staging, got {nested!r}"
