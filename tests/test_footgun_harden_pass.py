"""Footgun harden pass — LAYUP clamp / C5 Skip / C2 mix seat / NESTED framing / C4 lease."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from interview_mux.delivery_invariants import MIN_COMMITTED_MASTER_BYTES
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "footgun_harden")


def _commit_master_finalize(run_ctx) -> None:
    master = run_ctx.final_path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    (master / "post_master_quality.json").write_text(
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


# --- #1 LAYUP: downstream pin clamps when VO hole open ---


def test_fg1_music_pin_clamps_to_layup_when_vo_hole_open(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import clamp_resume_through_order
    from interview_mux.thrash_hardening import resume_producer

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid != "nugget_layup_compose",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    assert clamp_resume_through_order(ctx, "music_palette_compose") == (
        "nugget_layup_compose"
    )
    assert resume_producer(ctx, "mix") == "nugget_layup_compose"


def test_fg1_music_pin_not_clamped_when_vo_chain_sealed(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not reopen premature_cap music→narrative thrash when VO is ready."""
    from interview_mux.delivery_guardrails import clamp_resume_through_order

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.vo_synthesize_stability_block",
        lambda _c, allow_rewrite=False: None,
    )
    master = ctx.path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "transitions.json").write_text("{}", encoding="utf-8")
    assert clamp_resume_through_order(ctx, "music_palette_compose") == (
        "music_palette_compose"
    )


# --- #2 C5: Skip is not Partial DONE ---


def test_fg2_skipped_package_is_not_pipeline_complete(ctx) -> None:
    from interview_mux.execution_status import pipeline_complete

    _commit_master_finalize(ctx)
    pub = ctx.final_path("publish")
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "cover.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 32)
    (pub / "audio.mp3").write_bytes(b"ID3" + b"\x00" * 64)
    ctx.write_json(
        "publish/package_ready.json",
        {"ready": False, "skipped": True, "version": 1},
        skip_handoff=True,
    )
    assert pipeline_complete(ctx) is False
    ctx.write_json(
        "publish/package_ready.json",
        {"ready": True, "version": 1},
        skip_handoff=True,
    )
    # ready:true alone is still not DONE: the package stage must be done (ISSUES 111).
    assert pipeline_complete(ctx) is False
    marker = ctx.final_path(".stage_done", "podcast_publish")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")
    assert pipeline_complete(ctx) is True


# --- #3 C2: unseated mix before ship ---


def test_fg3_stalled_advance_pins_mix_when_unseated(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.execution_status import stalled_expensive_advance_stage

    _commit_master_finalize(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.ship_after_master_remaining",
        lambda _c: ["master_transcript_build", "podcast_publish"],
    )
    assert stalled_expensive_advance_stage(ctx, "master_finalize") == "mix"


def test_fg3_stalled_advance_ship_when_mix_seated(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.execution_status import stalled_expensive_advance_stage

    _commit_master_finalize(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.ship_after_master_remaining",
        lambda _c: ["master_transcript_build"],
    )
    assert stalled_expensive_advance_stage(ctx, "master_finalize") == (
        "master_transcript_build"
    )


# --- #4 NESTED: framing probe fail-closed all modes ---


def test_fg4_framing_probe_error_skips_full_auto(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_vo_gates import nested_synth_may_mint

    ctx.write_json(
        "run_meta.json",
        {"full_auto": True, "run_mode": "full-auto", "gap_framing_enabled": True},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _c: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    ok, note = nested_synth_may_mint(ctx)
    assert ok is False
    assert "framing_probe_error" in note


# --- #5 C4: fresh wav holds lease despite stalled post-master ---


def test_fg5_fresh_vo_wav_blocks_mtime_lease_skip(ctx) -> None:
    from interview_mux.execution_status import skip_post_master_mtime_lease
    from interview_mux.thrash_hardening import expensive_stage_lease_active

    _commit_master_finalize(ctx)
    synth = ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    wav = synth / "live.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 200)
    # Ensure mtime is "now"
    wav.touch()
    assert (
        skip_post_master_mtime_lease(
            ctx, job_status="stalled", job_stage="master_finalize"
        )
        is False
    )
    ctx.write_json(
        "gui_job.json",
        {
            "status": "stalled",
            "stage": "master_finalize",
            "current_stage": "master_finalize",
        },
        skip_handoff=True,
    )
    active, lease = expensive_stage_lease_active(ctx)
    assert active is True
    assert lease == "vo_synthesize"


def test_fg5_stale_vo_allows_skip_when_post_master(ctx) -> None:
    from interview_mux.execution_status import skip_post_master_mtime_lease

    _commit_master_finalize(ctx)
    synth = ctx.final_path("vo_pickup", "synthesized")
    synth.mkdir(parents=True, exist_ok=True)
    wav = synth / "old.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 200)
    old = time.time() - 600
    import os

    os.utime(wav, (old, old))
    assert (
        skip_post_master_mtime_lease(
            ctx, job_status="stalled", job_stage="master_finalize"
        )
        is True
    )
