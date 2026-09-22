"""ESR_POST_MASTER family (DP-C1–C4) — post-master never-thrash-wait matrix.

MUX_FORENSICS=0. C5 ship-bar vocabulary is a separate family.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_invariants import MIN_COMMITTED_MASTER_BYTES
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "esr_post_master")


def _commit_master_and_finalize(run_ctx) -> None:
    master_dir = run_ctx.final_path("master")
    master_dir.mkdir(parents=True, exist_ok=True)
    (master_dir / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    (master_dir / "post_master_quality.json").write_text(
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


# --- C1: wrong-pin never-wait on fresh master ---


@pytest.mark.parametrize(
    "pin",
    [
        "mix",
        "listen_delight_audit",
        "junction_snip_qa",
        "master_finalize",
        "master_transcript_build",
        "episode_cover_generate",
        "podcast_publish",
    ],
)
def test_c1_post_family_never_waits_after_honest_finalize(
    ctx, monkeypatch: pytest.MonkeyPatch, pin: str
) -> None:
    from interview_mux.execution_status import (
        post_master_never_wait,
        should_wait_incomplete_after_conductor,
    )

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _c: (False, ""),
    )
    _commit_master_and_finalize(ctx)
    # Fresh assembly/master mtimes that used to stall ESR forever.
    master = ctx.final_path("master")
    (master / "assembly.wav").write_bytes(b"RIFF" + b"\x00" * 4000)
    (master / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    assert post_master_never_wait(ctx, pin) is True
    assert should_wait_incomplete_after_conductor(ctx, pin=pin) is None


def test_c1_wrong_pin_still_waits_without_honest_finalize(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.execution_status import (
        post_master_never_wait,
        should_wait_incomplete_after_conductor,
    )

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _c: (False, ""),
    )
    master = ctx.final_path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    # Hollow finalize marker only — no PMQ.
    done = ctx.final_path(".stage_done", "master_finalize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("")
    assert post_master_never_wait(ctx, "mix") is False
    wait = should_wait_incomplete_after_conductor(ctx, pin="mix")
    assert wait is not None
    assert wait.get("decision") == "wait"


# --- C2: stalled advance toward ship ---


def test_c2_stalled_finalize_advances_to_ship(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.execution_status import (
        stalled_expensive_advance_stage,
        stalled_expensive_can_advance,
    )
    from interview_mux.v2.config import SHIP_AFTER_MASTER

    _commit_master_and_finalize(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _c: True,
    )
    assert stalled_expensive_can_advance(ctx, "master_finalize") is True
    pin = stalled_expensive_advance_stage(ctx, "master_finalize")
    assert pin in SHIP_AFTER_MASTER


def test_c2_pre_master_done_does_not_leapfrog_ship(ctx) -> None:
    from interview_mux.execution_status import (
        stalled_expensive_advance_stage,
        stalled_expensive_can_advance,
    )

    done = ctx.final_path(".stage_done")
    done.mkdir(parents=True, exist_ok=True)
    (done / "sound_design_vo_finalize").write_text("1\n")
    assert stalled_expensive_can_advance(ctx, "sound_design_vo_finalize") is False
    assert stalled_expensive_advance_stage(ctx, "sound_design_vo_finalize") == ""


def test_c2_hollow_finalize_is_done_does_not_advance_without_seed(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Done Authority: bare is_done must not unlock C2 advance."""
    from interview_mux.execution_status import stalled_expensive_can_advance

    master = ctx.final_path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    done = ctx.final_path(".stage_done", "master_finalize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("")
    monkeypatch.setattr(
        "interview_mux.done_authority.may_clear_wait",
        lambda _c, sid: False,
    )
    # master_ok + ship remaining can still advance; clear remaining.
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.ship_after_master_remaining",
        lambda _c: [],
    )
    assert stalled_expensive_can_advance(ctx, "master_finalize") is False


# --- C3: driver parity — one wait helper ---


def test_c3_driver_uses_should_wait_not_raw_wait_vs_halt() -> None:
    import inspect
    from pathlib import Path

    src = Path("tools/full_auto_driver.py").read_text(encoding="utf-8")
    assert "should_wait_incomplete_after_conductor" in src
    # Incomplete-after-conductor path must not call wait_vs_halt directly.
    # (wait_vs_halt may still exist as import elsewhere — pin the incomplete block.)
    idx = src.find("incomplete-after-conductor")
    assert idx >= 0
    window = src[idx : idx + 2500]
    assert "should_wait_incomplete_after_conductor" in window
    assert "wait_vs_halt(" not in window


def test_c3_pipeline_agenda_runner_share_helper() -> None:
    import inspect
    from pathlib import Path

    from interview_mux.homunculus import agenda
    from interview_mux.web import runner

    for mod in (agenda, runner):
        src = inspect.getsource(mod)
        assert "should_wait_incomplete_after_conductor" in src
    pipe_src = Path("src/interview_mux/pipeline.py").read_text(encoding="utf-8")
    assert "should_wait_incomplete_after_conductor" in pipe_src


# --- C4: ghost mtime lease suppress ---


def test_c4_stalled_post_master_suppresses_vo_mtime_lease(ctx) -> None:
    import os
    import time

    from interview_mux.thrash_hardening import expensive_stage_lease_active

    _commit_master_and_finalize(ctx)
    synth = ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    wav = synth / "ghost.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 200)
    old = time.time() - 600
    os.utime(wav, (old, old))
    ctx.write_json(
        "gui_job.json",
        {
            "status": "stalled",
            "stage": "master_finalize",
            "current_stage": "master_finalize",
            "message": "ESR stall",
        },
        skip_handoff=True,
    )
    active, lease_stage = expensive_stage_lease_active(ctx)
    assert active is False
    assert lease_stage == ""


def test_c4_running_still_holds_vo_mtime_lease(ctx) -> None:
    from interview_mux.thrash_hardening import expensive_stage_lease_active

    _commit_master_and_finalize(ctx)
    synth = ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "live.wav").write_bytes(b"RIFF" + b"\x00" * 200)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "vo_synthesize",
            "current_stage": "vo_synthesize",
            "message": "Chatterbox",
        },
        skip_handoff=True,
    )
    active, lease_stage = expensive_stage_lease_active(ctx)
    assert active is True
    assert lease_stage == "vo_synthesize"


def test_c4_ssot_helper_matches_lease_gate(ctx) -> None:
    from interview_mux.execution_status import skip_post_master_mtime_lease

    _commit_master_and_finalize(ctx)
    assert (
        skip_post_master_mtime_lease(
            ctx, job_status="stalled", job_stage="mix"
        )
        is True
    )
    assert (
        skip_post_master_mtime_lease(
            ctx, job_status="running", job_stage="mix"
        )
        is False
    )


# --- Family cohesion ---


def test_esr_ssot_helpers_exported() -> None:
    from interview_mux import execution_status as es

    for name in (
        "pin_in_post_master_family",
        "committed_master_present",
        "post_master_finalize_honest",
        "post_master_never_wait",
        "skip_post_master_mtime_lease",
        "stalled_expensive_can_advance",
        "should_wait_incomplete_after_conductor",
    ):
        assert callable(getattr(es, name))
