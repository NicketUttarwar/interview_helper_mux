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


def test_listen_delight_pin_ignores_vo_wav_freshness(run_ctx, monkeypatch):
    """Cascade (MUX_FORENSICS=0): listen_delight must not ESR-wait on vo_wavs.

    exec_13165: pin=listen_delight_audit with fresh layup WAVs and no edl.json
    stayed in Producer-active wait forever while edl never ran.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import (
        _collect_progress_sources,
        should_wait_incomplete_after_conductor,
    )

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (False, ""),
    )
    synth = run_ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "vo_layup_seg_006.wav").write_bytes(b"RIFF" + b"\x00" * 100)

    sources, _newest = _collect_progress_sources(run_ctx, pin="listen_delight_audit")
    assert not any(s.startswith("vo_wavs") for s in sources)
    wait = should_wait_incomplete_after_conductor(run_ctx, pin="listen_delight_audit")
    assert wait is None or not str(wait.get("why") or "").startswith("fresh:vo_wavs")


def test_sound_design_vo_finalize_pin_ignores_vo_wav_freshness(
    run_ctx, monkeypatch
) -> None:
    """MUX_FORENSICS=0: sound_design_vo_finalize must not ESR-wait on vo_wavs.

    exec_13167: pin matched ``vo_`` substring → fresh:vo_wavs=3 stalled forever
    after finalize was already done; driver then leapfrogged to master_transcript.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import (
        _collect_progress_sources,
        should_wait_incomplete_after_conductor,
        stalled_expensive_can_advance,
        stalled_expensive_advance_stage,
    )

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (False, ""),
    )
    synth = run_ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "vo_layup_seg_005.wav").write_bytes(b"RIFF" + b"\x00" * 200)
    run_ctx.path(".stage_done").mkdir(parents=True, exist_ok=True)
    (run_ctx.path(".stage_done") / "sound_design_vo_finalize").write_text("1\n")

    sources, _ = _collect_progress_sources(run_ctx, pin="sound_design_vo_finalize")
    assert not any(s.startswith("vo_wavs") for s in sources)
    wait = should_wait_incomplete_after_conductor(
        run_ctx, pin="sound_design_vo_finalize"
    )
    assert wait is None
    # Pre-master done stall must not leapfrog into SHIP_AFTER_MASTER.
    assert stalled_expensive_can_advance(run_ctx, "sound_design_vo_finalize") is False
    assert stalled_expensive_advance_stage(run_ctx, "sound_design_vo_finalize") == ""


def _commit_master_and_finalize(run_ctx) -> None:
    import json

    from interview_mux.delivery_invariants import MIN_COMMITTED_MASTER_BYTES

    master_dir = run_ctx.final_path("master")
    master_dir.mkdir(parents=True, exist_ok=True)
    (master_dir / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    pmq = master_dir / "post_master_quality.json"
    pmq.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-09-21T00:00:00Z",
                "status": "pass",
                "publish_allowed": True,
                "failed_checks": [],
                "checks": {},
                "never_skipped": True,
            }
        ),
        encoding="utf-8",
    )
    done = run_ctx.final_path(".stage_done", "master_finalize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("")


def test_done_master_finalize_does_not_esr_wait_on_fresh_master(
    run_ctx, monkeypatch
) -> None:
    """Cascade (MUX_FORENSICS=0): completed finalize must not ESR-stall ship.

    exec_13165: master.wav + .stage_done/master_finalize existed, but fresh
    master/assembly mtimes kept should_wait → stalled, and driver never
    advanced to master_transcript_build / cover / publish.
    Done Authority: honest finalize also requires PMQ + integrity size floor.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import should_wait_incomplete_after_conductor

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (False, ""),
    )
    _commit_master_and_finalize(run_ctx)
    master_dir = run_ctx.final_path("master")
    (master_dir / "assembly.wav").write_bytes(b"RIFF" + b"\x00" * 2000)
    assert run_ctx.is_done("master_finalize")
    wait = should_wait_incomplete_after_conductor(run_ctx, pin="master_finalize")
    assert wait is None


def test_hollow_master_finalize_marker_still_esr_waits(run_ctx, monkeypatch) -> None:
    """B5 / Done Authority: bare .stage_done without PMQ must not clear wait."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import should_wait_incomplete_after_conductor

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (False, ""),
    )
    master_dir = run_ctx.final_path("master")
    master_dir.mkdir(parents=True, exist_ok=True)
    (master_dir / "master.wav").write_bytes(b"RIFF" + b"\x00" * 2000)
    done = run_ctx.final_path(".stage_done", "master_finalize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("")
    wait = should_wait_incomplete_after_conductor(run_ctx, pin="master_finalize")
    assert wait is not None
    assert wait.get("decision") == "wait"


def test_c1_post_master_family_never_waits(run_ctx, monkeypatch) -> None:
    """C1-1: mix / listen_delight_audit pins do not ESR-wait after master+finalize."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import should_wait_incomplete_after_conductor

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (False, ""),
    )
    _commit_master_and_finalize(run_ctx)
    for pin in ("mix", "listen_delight_audit", "junction_snip_qa"):
        wait = should_wait_incomplete_after_conductor(run_ctx, pin=pin)
        assert wait is None, pin


def test_pipeline_complete_is_ship_bar(run_ctx) -> None:
    """C5-2: DONE = committed master + cover + mp3 + package_ready (not bare markers)."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import pipeline_complete, ship_bar_complete

    assert pipeline_complete(run_ctx) is False
    _commit_master_and_finalize(run_ctx)
    assert pipeline_complete(run_ctx) is False
    done = run_ctx.final_path(".stage_done")
    (done / "podcast_publish").write_text("")
    (done / "episode_cover_generate").write_text("")
    pub = run_ctx.final_path("publish")
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "cover.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 32)
    assert pipeline_complete(run_ctx) is False
    (pub / "audio.mp3").write_bytes(b"ID3" + b"\x00" * 64)
    # Markers + files without package_ready → not DONE (hollow-marker resist).
    assert pipeline_complete(run_ctx) is False
    run_ctx.write_json(
        "publish/package_ready.json",
        {"ready": True, "version": 1},
        skip_handoff=True,
    )
    assert pipeline_complete(run_ctx) is True
    assert ship_bar_complete(run_ctx) is True


def test_c4_stalled_post_master_ignores_stale_vo_wav(run_ctx) -> None:
    """C4-1: stalled + post-master suppresses lease on *stale* VO wavs (not fresh)."""
    import os
    import time

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.thrash_hardening import expensive_stage_lease_active

    _commit_master_and_finalize(run_ctx)
    synth = run_ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    wav = synth / "ghost.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 200)
    old = time.time() - 600
    os.utime(wav, (old, old))
    run_ctx.write_json(
        "gui_job.json",
        {
            "status": "stalled",
            "stage": "master_finalize",
            "current_stage": "master_finalize",
            "message": "ESR wait after master",
        },
        skip_handoff=True,
    )
    active, lease_stage = expensive_stage_lease_active(run_ctx)
    assert active is False
    assert lease_stage == ""


def test_c4_running_still_holds_vo_mtime_lease(run_ctx) -> None:
    """C4-1: running/starting still holds the VO mtime lease."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.thrash_hardening import expensive_stage_lease_active

    _commit_master_and_finalize(run_ctx)
    synth = run_ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "live.wav").write_bytes(b"RIFF" + b"\x00" * 200)
    run_ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "vo_synthesize",
            "current_stage": "vo_synthesize",
            "message": "Chatterbox",
        },
        skip_handoff=True,
    )
    active, lease_stage = expensive_stage_lease_active(run_ctx)
    assert active is True
    assert lease_stage == "vo_synthesize"


def test_c2_stalled_advances_to_ship_from_stage(run_ctx, monkeypatch) -> None:
    """C2-1: stalled finalize with committed master advances to a ship stage."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import (
        stalled_expensive_advance_stage,
        stalled_expensive_can_advance,
    )
    from interview_mux.v2.config import SHIP_AFTER_MASTER

    _commit_master_and_finalize(run_ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _c: True,
    )
    assert stalled_expensive_can_advance(run_ctx, "master_finalize") is True
    pin = stalled_expensive_advance_stage(run_ctx, "master_finalize")
    assert pin in SHIP_AFTER_MASTER
    assert pin == "master_transcript_build"


def test_gui_heartbeat_does_not_block_hard_halt(run_ctx, monkeypatch):
    """Retry loops that stamp gui_job must not look like producer progress."""
    from interview_mux.execution_status import may_hard_halt, progress_stale

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (False, ""),
    )
    run_ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "edl",
            "message": "Homunculus selecting next delivery stage",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        },
        skip_handoff=True,
    )
    # Also stamp a stale wasted music_deferred event
    run_ctx.write_json(
        "operator/wasted_work.json",
        {
            "version": 1,
            "events": [
                {
                    "at": "2020-01-01T00:00:00+00:00",
                    "event": "music_deferred",
                    "stage": "music_palette_compose",
                    "detail": {"reason": "assembly_missing"},
                }
            ],
        },
        skip_handoff=True,
    )
    stale, why = progress_stale(run_ctx, pin="edl_narrative_audit")
    assert stale is True
    assert "fresh:" not in why
    assert may_hard_halt(run_ctx, pin="edl_narrative_audit") is True


def test_i6_esr_wait_skips_when_pin_not_remaining_head(
    run_ctx, monkeypatch
) -> None:
    """exec_13181: do not ESR-stall mix while listen_delight_audit is rem[0]."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.execution_status import should_wait_incomplete_after_conductor

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda ctx: (True, "mix"),
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.remaining_stages",
        lambda ctx, phase="delivery": ["listen_delight_audit", "music_palette_compose", "mix"],
    )
    wait = should_wait_incomplete_after_conductor(run_ctx, pin="mix")
    assert wait is None
