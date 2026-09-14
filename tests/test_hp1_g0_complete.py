"""HP-1: G0 complete only after transcript_review sign-off.

Missing queue, empty corrections.json, and sticky stored milestones are not
complete. Partial waits. Do not start a run. HP-2 hollow-build unmark stays open.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.execution_report import _g0_block
from interview_mux.journey_state import compute_milestones, compute_operator_phase
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hp1_g0")
    monkeypatch.setattr(driver, "RUN_ID", run.run_id)
    monkeypatch.setattr(driver, "MASTER", run.run_dir / "master" / "master.wav")
    monkeypatch.setattr(driver, "log", lambda *_a, **_k: None)
    return run


def test_hp1_build_done_without_queue_is_not_complete(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    ms = compute_milestones(ctx)
    assert ms["g0_complete"] is False
    assert compute_operator_phase(ctx, ms) == "prepare"
    assert driver.g0_complete() is False


def test_hp1_empty_corrections_without_signoff_is_not_complete(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    ctx.write_json("transcript/corrections.json", {"corrections": {}})
    ms = compute_milestones(ctx)
    assert ms["g0_complete"] is False
    assert driver.g0_complete() is False


def test_hp1_sticky_stored_milestone_does_not_complete(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    ctx.write_json(
        "run_meta.json",
        {"journey_milestones": {"g0_complete": True}, "homunculus_version": "0.1.0"},
    )
    ms = compute_milestones(ctx)
    assert ms["g0_complete"] is False
    assert driver.g0_complete() is False
    assert compute_operator_phase(ctx, ms) == "prepare"


def test_hp1_signoff_is_complete(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build", "transcript_review")
    ms = compute_milestones(ctx)
    assert ms["g0_complete"] is True
    assert driver.g0_complete() is True


def test_hp1_missing_queue_still_needs_operator(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    assert driver._transcript_review_needs_operator() is True
    mark_done_raw(ctx, "transcript_review")
    assert driver._transcript_review_needs_operator() is False


def test_hp1_queue_unsigned_needs_operator(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    ctx.write_json(
        "transcript/review_queue.json",
        {"version": 1, "chunk_count": 0, "chunks": []},
    )
    assert driver.g0_complete() is False
    assert driver._transcript_review_needs_operator() is True


def test_hp1_accepted_unreviewed_false_when_unsigned(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    meta = {"journey_milestones": {"g0_complete": True}}
    block = _g0_block(ctx, meta)
    assert block["accepted_unreviewed"] is False
    assert any("g0_complete" in h for h in block["stt_poison_hints"])
