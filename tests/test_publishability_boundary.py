"""Fixture-based tests for publishability_boundary checkpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.identical_failures import record_identical_failure
from interview_mux.publishability_boundary import (
    PublishabilityBlocked,
    checkpoint_publishability,
    commit_or_block,
    failure_in_active_repair_cascade,
    validate_publishability,
    violation_playbook,
    write_publishability_repair_plan,
)
from interview_mux.publishability_boundary import PublishabilityReport, PublishabilityViolation
from run_fixtures import isolated_run_ctx, write_fixture_vo_wav


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _speech_clip(
    sid: str,
    *,
    duration_ms: int = 1000,
    timeline_start_ms: int = 0,
    notes: list[str] | None = None,
) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": 0,
        "source_end_ms": duration_ms,
        "duration_ms": duration_ms,
        "timeline_start_ms": timeline_start_ms,
        **({"notes": notes} if notes else {}),
    }


def _write_edl(ctx, *, clips: list[dict], ordered: list[str] | None = None) -> None:
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ordered or [],
            "clips": clips,
            "timeline_duration_ms": sum(int(c.get("duration_ms") or 0) for c in clips),
        },
    )


def _orientation_gap_line() -> dict:
    return {
        "line_id": "vo_preface_episode_orientation",
        "delivery": "synthesize",
        "gap_type": "opening_orientation",
        "placement": "before_first_speech",
        "targets_segment_id": "seg_001",
        "orientation_missions": [
            "guest_identity",
            "conversation_topic",
            "listener_stakes",
        ],
        "text": "Welcome to the show. Today we explore cancer science with our guest.",
        "opening_sequence": "straight",
    }


def test_zero_keep_detected_post_edl(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_zero_keep")
    _write_edl(
        ctx,
        ordered=["seg_001"],
        clips=[
            _speech_clip(
                "seg_001",
                duration_ms=0,
                notes=["zeroed_inside_never_touch:seg_001"],
            )
        ],
    )
    report = validate_publishability(ctx, checkpoint="post_edl")
    assert not report.ok
    assert report.violations[0].error_class == "never_touch_zeroed_keep"


def test_phantom_vo_detected(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_phantom_vo")
    line = {
        "line_id": "vo_layup_seg_002",
        "delivery": "synthesize",
        "gap_type": "story_bridge",
        "placement": "before_segment",
        "targets_segment_id": "seg_002",
        "text": "Bridge line for the next beat.",
    }
    _write_raw(ctx, "understanding/gap_report.json", {"interviewer_lines": [line]})
    write_fixture_vo_wav(ctx.final_path("vo_pickup", "clean", "vo_layup_seg_002.wav"))
    _write_edl(
        ctx,
        ordered=["seg_001"],
        clips=[_speech_clip("seg_001", duration_ms=5000)],
    )
    report = validate_publishability(ctx, checkpoint="post_edl")
    classes = {v.error_class for v in report.violations}
    assert "vo_audibility_drift" in classes


def test_order_drift_detected(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_order_drift")
    _write_raw(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b"]},
    )
    _write_edl(
        ctx,
        ordered=["seg_a", "seg_b"],
        clips=[
            _speech_clip("seg_b", timeline_start_ms=0),
            _speech_clip("seg_a", timeline_start_ms=1000),
        ],
    )
    report = validate_publishability(ctx, checkpoint="post_edl")
    assert any(v.error_class == "selection_edl_order_drift" for v in report.violations)


def test_opening_orientation_inaudible(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_opening")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": [_orientation_gap_line()]},
    )
    write_fixture_vo_wav(
        ctx.final_path(
            "vo_pickup",
            "synthesized",
            "vo_preface_episode_orientation.wav",
        )
    )
    _write_edl(
        ctx,
        ordered=["seg_001"],
        clips=[_speech_clip("seg_001", duration_ms=5000)],
    )
    report = validate_publishability(ctx, checkpoint="post_edl")
    assert any(
        v.error_class == "opening_orientation_inaudible" for v in report.violations
    )


def test_pending_write_barrier_pre_mix(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_pending")
    pending = ctx.run_dir / ".pending_writes" / "edl" / "master"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "edl.json").write_text("{}", encoding="utf-8")
    _write_edl(
        ctx,
        ordered=["seg_001"],
        clips=[_speech_clip("seg_001", duration_ms=5000)],
    )
    report = validate_publishability(ctx, checkpoint="pre_mix")
    assert any(v.error_class == "pending_write_barrier" for v in report.violations)


def test_critical_junction_post_junction(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_junction")
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {
            "version": 1,
            "generated_at": "2026-08-29T00:00:00Z",
            "critical_residuals": 2,
            "blocking_reasons": ["critical_junction_residuals_after_two_runs"],
        },
    )
    report = validate_publishability(ctx, checkpoint="post_junction")
    assert any(v.error_class == "incomplete_cut_unresolved" for v in report.violations)


def test_commit_or_block_writes_repair_plan(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_repair_plan")
    violation = PublishabilityViolation(
        error_class="vo_audibility_drift",
        code="phantom_vo",
        detail="test",
        line_id="vo_x",
    )
    report = PublishabilityReport(
        checkpoint="post_edl",
        ok=False,
        violations=[violation],
    )
    commit_or_block(ctx, report, enforce=False)
    assert ctx.artifact_exists("operator/publishability_report.json")
    assert ctx.artifact_exists("operator/publishability_repair_plan.json")
    plan = ctx.read_json("operator/publishability_repair_plan.json")
    assert plan.get("error_class") == "vo_audibility_drift"
    assert plan.get("from_stage") == "edl"
    assert isinstance(plan.get("invalidate_set"), list)


def test_commit_or_block_raises_when_enforced(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_block")
    _write_edl(
        ctx,
        ordered=["seg_001"],
        clips=[_speech_clip("seg_001", duration_ms=0)],
    )
    report = validate_publishability(ctx, checkpoint="post_edl")
    with pytest.raises(PublishabilityBlocked) as excinfo:
        commit_or_block(ctx, report, enforce=True)
    assert excinfo.value.error_class == "never_touch_zeroed_keep"


def test_cascade_suppresses_identical_failure(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_cascade")
    report = PublishabilityReport(
        checkpoint="post_edl",
        ok=False,
        violations=[
            PublishabilityViolation(
                error_class="never_touch_zeroed_keep",
                code="zero_duration_speech",
                detail="seg_003a",
                segment_id="seg_003a",
            )
        ],
    )
    playbook = violation_playbook(report.violations[0])
    write_publishability_repair_plan(ctx, report, playbook=playbook)
    assert failure_in_active_repair_cascade(
        ctx, failed_stage="mix", producer="selection_edl_order_drift"
    )
    row = record_identical_failure(
        ctx,
        failed_stage="mix",
        producer="selection_edl_order_drift",
        reason="speech clip order diverges",
        resume_attempted="edl",
    )
    assert row.get("cascade_suppressed") is True
    assert row.get("halt") is False


def test_checkpoint_fail_open_by_default(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pub_fail_open")
    _write_edl(
        ctx,
        ordered=["seg_001"],
        clips=[_speech_clip("seg_001", duration_ms=0)],
    )
    report = checkpoint_publishability(ctx, checkpoint="post_edl")
    assert not report.ok
    assert ctx.artifact_exists("operator/publishability_report.json")
