"""Tests for Pillar A execution status + sticky progress honesty."""

from __future__ import annotations

import time
from pathlib import Path

import pytest


@pytest.fixture()
def run_ctx(tmp_path: Path):
    from interview_mux.run_context import RunContext

    run = tmp_path / "exec_test_esr_001"
    run.mkdir()
    (run / "run_meta.json").write_text('{"version":1}\n', encoding="utf-8")
    (run / ".stage_done").mkdir()
    (run / "vo_pickup").mkdir()
    return RunContext(str(run), create=False)


def test_vo_wav_growth_flips_predicate_and_blocks_sticky_halt(run_ctx):
    from interview_mux import thrash_hardening as th
    from interview_mux.execution_status import may_hard_halt, sync_execution_status

    synth = run_ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "a.wav").write_bytes(b"RIFF" + b"\x00" * 100)
    tok1 = th.stage_predicate_token(run_ctx, "vo_synthesize")
    time.sleep(0.05)
    (synth / "b.wav").write_bytes(b"RIFF" + b"\x00" * 120)
    tok2 = th.stage_predicate_token(run_ctx, "vo_synthesize")
    assert tok1 != tok2
    assert "wavs=" in tok2

    sync_execution_status(run_ctx, pin="vo_synthesize", predicate_token=tok2)
    assert may_hard_halt(run_ctx, pin="vo_synthesize", predicate_token=tok2) is False

    for _ in range(4):
        sticky = th.note_sticky_heal_attempt(
            run_ctx,
            kind="incomplete_after_conductor",
            pin="vo_synthesize",
            intent="delivery_blocked",
            predicate_token=tok2,
            halt_after=3,
        )
    assert sticky.get("halt") is False or sticky.get("progress_stale") is False


def test_sfx_mtime_in_predicate(run_ctx):
    from interview_mux.thrash_hardening import stage_predicate_token

    assets = run_ctx.final_path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "theme.wav").write_bytes(b"RIFF" + b"\x00" * 80)
    tok = stage_predicate_token(run_ctx, "mmaudio_sfx")
    assert "sfx=" in tok


def test_hollow_done_does_not_count_as_done_in_token(run_ctx, monkeypatch):
    from interview_mux.thrash_hardening import stage_predicate_token

    done = run_ctx.final_path(".stage_done", "mix")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("1\n", encoding="utf-8")

    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda ctx, sid: "assembly.wav missing",
    )
    tok = stage_predicate_token(run_ctx, "mix")
    assert tok.startswith("mix:0:")


def test_wait_vs_halt_lease(run_ctx, monkeypatch):
    from interview_mux.execution_status import wait_vs_halt

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (True, "vo_synthesize"),
    )
    row = wait_vs_halt(run_ctx, pin="vo_synthesize", intent="test")
    assert row["decision"] == "wait"


def test_true_waste_sticky_respects_esr(run_ctx, monkeypatch):
    from interview_mux.delivery_guardrails import record_wasted_work
    from interview_mux.thrash_hardening import TRUE_WASTE_STICKY_HALT_AFTER

    monkeypatch.setattr(
        "interview_mux.execution_status.may_hard_halt",
        lambda *a, **k: False,
    )
    for _ in range(TRUE_WASTE_STICKY_HALT_AFTER + 1):
        record_wasted_work(
            run_ctx,
            event="orphan_artifact",
            stage="delivery",
            detail={"stages": ["sound_design_plan"]},
        )
    meta = run_ctx.read_json("run_meta.json")
    assert not meta.get("needs_operator")


def test_forensics_stall_resets_on_predicate_progress(run_ctx, monkeypatch):
    from interview_mux import forensics_stall as fs

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.stage_predicate_token",
        lambda ctx, stage: "tok_v1",
    )
    monkeypatch.setattr(
        "interview_mux.execution_status.may_hard_halt",
        lambda *a, **k: True,
    )
    r1 = fs.record_stall(run_ctx, stage="edl", reason="seed order", error_class="seed")
    assert r1["count"] == 1
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.stage_predicate_token",
        lambda ctx, stage: "tok_v2",
    )
    r2 = fs.record_stall(run_ctx, stage="edl", reason="seed order", error_class="seed")
    assert r2["count"] == 1
    assert r2.get("esr_progress_reset") is True


def test_pin_scoped_progress_ignores_unrelated_vo_mtime(run_ctx, monkeypatch):
    """EDL thrash pin must not inherit freshness from VO wav mtimes."""
    from interview_mux.execution_status import _collect_progress_sources, may_hard_halt

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (False, ""),
    )

    synth = run_ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "fresh.wav").write_bytes(b"RIFF" + b"\x00" * 100)

    edl = run_ctx.final_path("master", "edl.json")
    edl.parent.mkdir(parents=True, exist_ok=True)
    # Stale EDL (old mtime) vs fresh VO
    edl.write_text('{"clips":[]}\n', encoding="utf-8")
    old = time.time() - 10_000
    import os

    os.utime(edl, (old, old))

    sources, newest = _collect_progress_sources(run_ctx, pin="edl")
    assert not any(s.startswith("vo_wavs") for s in sources)
    assert "edl.json" in sources
    # newest is EDL clock, not VO
    assert newest < time.time() - 1000

    # Unpinned sees VO
    all_src, all_new = _collect_progress_sources(run_ctx, pin="")
    assert any(s.startswith("vo_wavs") for s in all_src)
    assert all_new > newest

    # Stale EDL pin → HARD allowed (lease mocked off)
    assert may_hard_halt(run_ctx, pin="edl") is True
