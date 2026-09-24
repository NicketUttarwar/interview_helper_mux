"""exec_13170: sealed vo_synthesize must not hold expensive lease forever."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import premature_cap_hard_pin
from interview_mux.thrash_hardening import expensive_stage_lease_active
from run_fixtures import isolated_run_ctx, mark_done_raw


def test_sealed_vo_synthesize_releases_expensive_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i5_vo_lease")
    # Minimal VO synth seal
    ctx.path("mastering").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "mastering/vo_synthesize.json",
        {"status": "complete", "synthesized": ["vo_a"], "wavs": 1},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "vo_synthesize")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid == "vo_synthesize",
    )
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "current_stage": "vo_synthesize",
            "message": "Finished: Synthesize spoken VO",
        },
        skip_handoff=True,
    )
    # Stale pending residue must not keep lease
    pending = ctx.run_dir / ".pending_writes" / "vo_synthesize" / "vo_pickup"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "orphan.wav").write_bytes(b"RIFF" + b"\0" * 20)

    leased, stage = expensive_stage_lease_active(ctx)
    assert leased is False
    assert stage == ""
    pin = premature_cap_hard_pin(
        ctx, "edl", message="premature complete drift=rebuild but edl.json missing"
    )
    assert pin != "vo_synthesize"
