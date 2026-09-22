"""Done Authority — hollow mark_done / ESR wait / finalize PMQ (MUX_FORENSICS=0)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.artifact_ownership import AuthorityDenied
from interview_mux.delivery_invariants import MIN_COMMITTED_MASTER_BYTES
from interview_mux.done_authority import (
    finalize_incompleteness,
    finalize_outputs_complete,
    finalize_ship_gate_open,
    honest_finalize_seeded,
    is_seed_complete,
    may_clear_wait,
    note_finalize_ship_gate_open,
    pmq_well_formed,
    require_seated_before_mix_mark,
    stamp_finalize_on_success,
    try_mark_done,
    unmark_finalize_after_ship_fail,
)
from interview_mux.execution_status import should_wait_incomplete_after_conductor
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "done_authority")


def _write_raw(ctx: RunContext, rel: str, data: object) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _pmq_doc(**overrides: object) -> dict:
    doc = {
        "version": 1,
        "generated_at": "2026-09-21T00:00:00Z",
        "status": "pass",
        "publish_allowed": True,
        "failed_checks": [],
        "checks": {},
        "never_skipped": True,
    }
    doc.update(overrides)
    return doc


def _honest_master(ctx: RunContext, *, with_pmq: bool = True) -> None:
    master_dir = ctx.final_path("master")
    master_dir.mkdir(parents=True, exist_ok=True)
    (master_dir / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    if with_pmq:
        _write_raw(ctx, "master/post_master_quality.json", _pmq_doc())


def test_hollow_is_done_does_not_clear_wait(ctx, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _c: (False, ""),
    )
    master_dir = ctx.final_path("master")
    master_dir.mkdir(parents=True, exist_ok=True)
    (master_dir / "master.wav").write_bytes(b"RIFF" + b"\x00" * 2000)
    done = ctx.final_path(".stage_done", "master_finalize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("")
    assert ctx.is_done("master_finalize")
    assert may_clear_wait(ctx, "master_finalize") is False
    assert honest_finalize_seeded(ctx) is False
    wait = should_wait_incomplete_after_conductor(ctx, pin="master_finalize")
    assert wait is not None
    assert wait.get("decision") == "wait"


def test_honest_finalize_clears_wait(ctx, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _c: (False, ""),
    )
    _honest_master(ctx, with_pmq=True)
    done = ctx.final_path(".stage_done", "master_finalize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("")
    assert finalize_outputs_complete(ctx) is True
    assert finalize_incompleteness(ctx) is None
    assert stage_artifact_incompleteness(ctx, "master_finalize") is None
    assert is_seed_complete(ctx, "master_finalize") is True
    assert may_clear_wait(ctx, "master_finalize") is True
    wait = should_wait_incomplete_after_conductor(ctx, pin="master_finalize")
    assert wait is None


def test_finalize_incompleteness_requires_pmq(ctx) -> None:
    _honest_master(ctx, with_pmq=False)
    inc = finalize_incompleteness(ctx)
    assert inc is not None
    assert "post_master_quality.json" in inc
    assert finalize_outputs_complete(ctx) is False


def test_malformed_pmq_not_complete(ctx) -> None:
    """Footgun #6: empty/partial PMQ JSON is not finalize-complete."""
    _honest_master(ctx, with_pmq=False)
    _write_raw(ctx, "master/post_master_quality.json", {"status": "pass"})
    assert pmq_well_formed(ctx) is False
    assert finalize_outputs_complete(ctx) is False
    inc = finalize_incompleteness(ctx)
    assert inc is not None
    assert "malformed" in inc


def test_ship_gate_blocks_seed_complete_after_fail(ctx) -> None:
    """Footgun #1: delight/structural fail leaves ship gate open → not seed-complete."""
    _honest_master(ctx, with_pmq=True)
    mark_done_raw(ctx, "master_finalize")
    assert ctx.is_done("master_finalize")
    unmark_finalize_after_ship_fail(ctx, reason="listen_delight")
    assert finalize_ship_gate_open(ctx) is True
    assert ctx.is_done("master_finalize") is False
    assert finalize_incompleteness(ctx) is not None
    assert "ship gate open" in (finalize_incompleteness(ctx) or "")
    assert honest_finalize_seeded(ctx) is False


def test_stamp_finalize_on_success_clears_ship_gate(ctx) -> None:
    """Footgun #1/#2: successful stamp clears gate and requires stuck marker."""
    _honest_master(ctx, with_pmq=True)
    note_finalize_ship_gate_open(ctx, reason="prior_fail")
    # stage_outputs_present needs both artifacts — plant via assert path using raw first
    # then unmark so stamp path can remake.
    mark_done_raw(ctx, "master_finalize")
    from interview_mux.homunculus.agenda import unmark_stage_only

    unmark_stage_only(ctx, "master_finalize")
    stamp_finalize_on_success(ctx)
    assert ctx.is_done("master_finalize")
    assert finalize_ship_gate_open(ctx) is False
    assert honest_finalize_seeded(ctx) is True


def test_require_seated_before_mix_mark_raises(ctx, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: False
    )
    with pytest.raises(RuntimeError, match="mix unseated"):
        require_seated_before_mix_mark(ctx)


def test_try_mark_done_false_on_hollow_mix(ctx, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: False
    )
    assert try_mark_done(ctx, "mix") is False
    assert ctx.is_done("mix") is False


def test_mark_done_raises_not_silent_on_hollow_guarded(ctx) -> None:
    """Footgun #3: RunContext.mark_done raises AuthorityDenied instead of silent return."""
    with pytest.raises(AuthorityDenied):
        ctx.mark_done("master_finalize")
    assert ctx.is_done("master_finalize") is False
