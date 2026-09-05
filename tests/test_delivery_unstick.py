"""Operator delivery unstick + dual-driver singleton."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_mux.driver_singleton import (
    claim_driver_run,
    live_foreign_driver_claim,
    read_driver_claim,
    release_driver_run,
)
from interview_mux.delivery_unstick import run_delivery_unstick
from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import record_thrash_hit, thrash_summary
from run_fixtures import isolated_run_ctx


def _ctx(tmp_path: Path, name: str) -> RunContext:
    return isolated_run_ctx(tmp_path, name)


def test_delivery_unstick_clears_thrash_and_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "unstick")
    ctx.write_json(
        "run_meta.json",
        {
            "needs_operator": True,
            "needs_operator_stage": "music_palette_compose",
            "needs_operator_reason": "thrash",
        },
        skip_handoff=True,
    )
    for _ in range(6):
        record_thrash_hit(
            ctx,
            fail_class="music_epoch",
            pin="music_palette_compose",
            stage="music_palette_compose",
        )
    assert thrash_summary(ctx) is not None

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.promote_complete_orphan_stage_done",
        lambda *_a, **_k: ["edl"],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.reconcile_orphan_artifacts",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seal_phase_a_if_stable",
        lambda *_a, **_k: {"phase": "A_sealed"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.heal_navigate",
        lambda *_a, **_k: {
            "intent": "delivery_blocked",
            "from_stage": "mix",
            "mode": "delivery",
        },
    )

    out = run_delivery_unstick(ctx, execute_resume=True)
    assert out["ok"] is True
    assert out["from_stage"] == "mix"
    assert out["thrash_cleared"] is True
    assert thrash_summary(ctx) is None
    assert out["needs_operator_cleared"] is True
    meta = ctx.read_json("run_meta.json")
    assert not meta.get("needs_operator")
    assert out["execute"] == {"mode": "delivery", "from_stage": "mix"}
    assert "edl" in (out.get("promoted") or [])


def test_driver_claim_refuses_second_live_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "claim")
    ctx.write_json("run_meta.json", {}, skip_handoff=True)

    claim = claim_driver_run(ctx, force=False)
    assert int(claim["pid"]) == os.getpid()
    loaded = read_driver_claim(ctx)
    assert loaded and int(loaded["pid"]) == os.getpid()

    # Same PID re-claim is fine.
    claim2 = claim_driver_run(ctx, force=False)
    assert int(claim2["pid"]) == os.getpid()

    # Simulate another live PID holding the claim.
    ctx.write_json(
        "operator/driver_claim.json",
        {"version": 1, "run_id": ctx.run_id, "pid": 1, "claimed_at": "t0"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.driver_singleton._pid_alive",
        lambda pid: int(pid) == 1,
    )
    with pytest.raises(RuntimeError, match="driver already active"):
        claim_driver_run(ctx, force=False)

    existing = live_foreign_driver_claim(ctx, force=False)
    assert existing and int(existing["pid"]) == 1

    # force=True replaces.
    claim3 = claim_driver_run(ctx, force=True)
    assert int(claim3["pid"]) == os.getpid()


def test_driver_release_and_stale_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "release")
    ctx.write_json("run_meta.json", {}, skip_handoff=True)
    claim_driver_run(ctx, force=True)
    assert release_driver_run(ctx) is True
    claim = read_driver_claim(ctx)
    assert claim is not None
    assert claim.get("pid") is None

    # Dead foreign PID: bind is free.
    ctx.write_json(
        "operator/driver_claim.json",
        {"version": 1, "run_id": ctx.run_id, "pid": 999999, "claimed_at": "t0"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.driver_singleton._pid_alive",
        lambda _pid: False,
    )
    assert live_foreign_driver_claim(ctx, force=False) is None


def test_release_is_idempotent_for_self_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "release2")
    ctx.write_json("run_meta.json", {}, skip_handoff=True)
    claim_driver_run(ctx, force=True)
    assert release_driver_run(ctx) is True
    # Second release after pid cleared still succeeds (stale/self).
    assert release_driver_run(ctx) is True
