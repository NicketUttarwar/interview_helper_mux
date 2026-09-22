from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner
from run_fixtures import init_run_meta_for_test, patch_executions_root, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run_id = "exec_nle_apply"
    c = RunContext(run_id, create=True)
    init_run_meta_for_test(c)
    c.write_json(
        "segments/nle_edits.json",
        {
            "segment_overrides": {"seg_a": {"start_ms": 100, "end_ms": 4000}},
        },
    )
    return c


def test_nle_apply_stages_trim_only(ctx: RunContext) -> None:
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=False)
    # Trim-only still reseats VO before EDL/assembly.
    assert stages == ["vo_synthesize", "edl", "assembly_preview"]


def test_nle_apply_stages_structural(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "sequence_order": ["seg_b", "seg_a"],
            "segment_overrides": {"seg_a": {"excluded": True}},
        },
    )
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=False)
    assert "full_master_ranking" in stages
    assert "selection_framing_apply" in stages
    assert "transitions" in stages
    assert stages[-2:] == ["edl", "assembly_preview"]


def test_nle_apply_stages_empty_without_edits(ctx: RunContext) -> None:
    ctx.write_json("segments/nle_edits.json", {"playhead_ms": 0})
    runner = JobRunner()
    assert runner._nle_apply_stages(ctx, full_refresh=False) == []


def test_nle_apply_stages_trim_only_mode_skips_ranking(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "sequence_order": ["seg_b", "seg_a"],
            "segment_overrides": {"seg_a": {"excluded": True}},
        },
    )
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=False, apply_mode="trim_only")
    assert stages == ["edl", "assembly_preview"]
    assert "full_master_ranking" not in stages


def test_nle_apply_stages_full_refresh_mode(ctx: RunContext) -> None:
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=True, apply_mode="full_refresh")
    assert "transitions" in stages
    assert "edl_narrative_audit" in stages


def test_delivery_skips_master_qa_until_master_exists(ctx: RunContext) -> None:
    runner = JobRunner()
    assert runner._should_verify_master_after_delivery(ctx) is False
    mark_done_raw(ctx, "master_finalize")
    assert runner._should_verify_master_after_delivery(ctx) is True


def test_delivery_runs_master_qa_when_master_wav_exists(ctx: RunContext) -> None:
    runner = JobRunner()
    master = ctx.path("master/master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 40)
    assert runner._should_verify_master_after_delivery(ctx) is True


def test_delivery_incomplete_raises_when_ship_remaining(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.pipeline import run_delivery

    ctx.mutate_run_meta(
        lambda m: m.update({"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"})
    )
    master = ctx.path("master/master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 40)
    mark_done_raw(ctx, "master_finalize")

    def _phase(_ctx, phase, remaining, **_kwargs):
        return {"conductor": {"ok": True}, "remaining_after": remaining}

    monkeypatch.setattr("interview_mux.homunculus.agenda.run_homunculus_phase", _phase)
    monkeypatch.setattr("interview_mux.pipeline.require_g1_clear", lambda _c: None)
    monkeypatch.setattr("interview_mux.pipeline.require_analysis_artifacts_complete", lambda _c: None)
    monkeypatch.setattr("interview_mux.pipeline.require_delivery_gates", lambda _c, **_k: None)
    with pytest.raises(RuntimeError, match="not publishable|remaining ship|walk_failed"):
        run_delivery(ctx, from_stage="episode_meta_build")
