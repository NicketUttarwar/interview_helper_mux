"""Tests for first-try reliability helpers and gates."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from interview_mux.first_try import (
    first_try_mode_enabled,
    line_requires_vo,
    line_severity,
    should_pause_for_write_approval,
    write_approval_deferred,
)
from interview_mux.gates import check_g1_vo
from interview_mux.run_context import RunContext
from interview_mux.selection_auto_pack import auto_pack_selection_to_brief
from interview_mux.source_readiness import compute_source_readiness, maybe_auto_dismiss_preclean
from interview_mux.custom_run_handoff import handoff_between_stages_enabled
from interview_mux.stage_execution_reuse import stage_reuse_blocks_execute
from interview_mux.mix_completeness import enforce_mix_completeness


def test_first_try_defaults_enabled():
    assert first_try_mode_enabled() is True
    assert write_approval_deferred() is True
    assert should_pause_for_write_approval("ingest") is False
    assert handoff_between_stages_enabled() is False
    assert stage_reuse_blocks_execute() is False


def test_line_severity_defaults_record_to_high():
    assert line_severity({"delivery": "record"}) == "high"
    assert line_severity({"delivery": "record", "severity": "low"}) == "low"
    assert line_requires_vo({"delivery": "record"}) is True
    assert line_requires_vo({"delivery": "record", "severity": "low"}) is False
    assert line_requires_vo({"delivery": "record", "severity": "medium", "blocking": True}) is True
    assert line_requires_vo({"delivery": "record", "severity": "high", "skipped_optional": True}) is False


def test_check_g1_vo_filters_severity(tmp_path: Path):
    run = tmp_path / "exec_test"
    run.mkdir()
    (run / "understanding").mkdir()
    (run / "vo_pickup").mkdir()
    gap = {
        "interviewer_lines": [
            {
                "line_id": "hi",
                "gap_type": "question",
                "text": "Q?",
                "targets_segment_id": "s1",
                "placement": "before",
                "delivery": "record",
                "severity": "high",
            },
            {
                "line_id": "lo",
                "gap_type": "question",
                "text": "Optional?",
                "targets_segment_id": "s2",
                "placement": "before",
                "delivery": "record",
                "severity": "low",
            },
        ]
    }
    (run / "understanding" / "gap_report.json").write_text(json.dumps(gap), encoding="utf-8")
    ctx = RunContext(str(run))
    missing = check_g1_vo(ctx)
    assert missing == ["hi"]


def test_source_readiness_missing_wav(tmp_path: Path):
    run = tmp_path / "exec_ready"
    run.mkdir()
    (run / "run_meta.json").write_text("{}", encoding="utf-8")
    ctx = RunContext(str(run))
    doc = compute_source_readiness(ctx)
    assert doc["band"] in {"green", "yellow", "red"}
    assert "reasons" in doc


def test_auto_pack_drops_to_brief_max(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run = tmp_path / "exec_pack"
    run.mkdir()
    (run / "understanding").mkdir()
    (run / "segments").mkdir()
    (run / "master").mkdir()
    brief = {
        "target_duration_sec": {"min": 10, "ideal": 20, "max": 30},
    }
    (run / "understanding" / "delivery_brief.json").write_text(json.dumps(brief), encoding="utf-8")
    segs = {
        "segments": [
            {"segment_id": "a", "start_ms": 0, "end_ms": 20_000},
            {"segment_id": "b", "start_ms": 20_000, "end_ms": 40_000},
            {"segment_id": "c", "start_ms": 40_000, "end_ms": 60_000},
        ]
    }
    (run / "segments" / "manifest.json").write_text(json.dumps(segs), encoding="utf-8")
    ctx = RunContext(str(run))
    monkeypatch.setattr("interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: True)
    sel = {
        "ordered_segment_ids": ["a", "b", "c"],
        "segment_ranks": {"a": 1, "b": 2, "c": 3},
    }
    out = auto_pack_selection_to_brief(ctx, sel)
    assert len(out["ordered_segment_ids"]) < 3
    assert "c" in (out.get("excluded_segment_ids") or [])


def test_g0_auto_complete_when_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from interview_mux.stages.transcript_review import maybe_auto_complete_transcript_review

    run = tmp_path / "exec_g0"
    run.mkdir()
    (run / "transcript").mkdir()
    (run / ".stage_done").mkdir()
    queue = {
        "version": 1,
        "low_confidence_threshold": 0.85,
        "chunk_count": 1,
        "chunks": [
            {
                "chunk_id": "c1",
                "rank": 1,
                "start_ms": 0,
                "end_ms": 1000,
                "text": "hello",
                "confidence": 0.99,
                "needs_review": False,
                "reviewed": False,
            }
        ],
    }
    (run / "transcript" / "review_queue.json").write_text(json.dumps(queue), encoding="utf-8")
    (run / "transcript" / "full.json").write_text(json.dumps({"words": [], "text": ""}), encoding="utf-8")
    (run / "transcript" / "corrections.json").write_text(json.dumps({"corrections": {}}), encoding="utf-8")
    ctx = RunContext(str(run))
    monkeypatch.setattr(
        "interview_mux.stages.transcript_review.materialize_transcript",
        lambda c, source="x": None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.transcript_review.apply_corrections",
        lambda c: None,
    )
    assert maybe_auto_complete_transcript_review(ctx) is True
    assert ctx.is_done("transcript_review")


def test_deferred_write_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from interview_mux.write_staging import after_stage_write_check, WriteApprovalPending

    run = tmp_path / "exec_wa"
    run.mkdir()
    (run / ".pending_writes" / "ingest").mkdir(parents=True)
    (run / ".pending_writes" / "ingest" / "ingest").mkdir(parents=True)
    (run / ".pending_writes" / "ingest" / "ingest" / "normalized.wav").write_bytes(b"RIFF")
    ctx = RunContext(str(run))
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: True)
    monkeypatch.setattr("interview_mux.write_staging.has_pending_writes", lambda c, s: True)
    monkeypatch.setattr(
        "interview_mux.write_staging.list_pending_paths",
        lambda c, s: ["ingest/normalized.wav"],
    )
    monkeypatch.setattr("interview_mux.write_staging.record_pending_approval", lambda c, s: None)
    # Should not raise under deferred mode
    after_stage_write_check(ctx, "ingest")

    monkeypatch.setattr("interview_mux.first_try.write_approval_deferred", lambda cfg=None: False)
    monkeypatch.setattr("interview_mux.first_try.should_pause_for_write_approval", lambda sid, cfg=None: True)
    with pytest.raises(WriteApprovalPending):
        after_stage_write_check(ctx, "ingest")


def test_preclean_auto_dismiss_green_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run = tmp_path / "exec_pc"
    run.mkdir()
    (run / "understanding").mkdir()
    readiness = {
        "version": 1,
        "band": "green",
        "score": 0.9,
        "reasons": ["ok"],
        "recommended": {"preclean": False},
        "updated_at": "t",
    }
    (run / "understanding" / "source_readiness.json").write_text(json.dumps(readiness), encoding="utf-8")
    (run / "run_meta.json").write_text("{}", encoding="utf-8")
    ctx = RunContext(str(run))
    monkeypatch.setattr("interview_mux.first_try.preclean_auto_dismiss_when_green", lambda cfg=None: True)
    assert maybe_auto_dismiss_preclean(ctx) is True
    meta = json.loads((run / "run_meta.json").read_text(encoding="utf-8"))
    decisions = (meta.get("audio_preclean") or {}).get("decisions") or []
    assert any(d.get("action") == "dismiss" and d.get("reason") == "auto_clean_enough" for d in decisions)
    # Never accept
    assert all(d.get("action") != "accept" for d in decisions)


def test_mix_warns_sfx_blocks_vo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run = tmp_path / "exec_mix"
    run.mkdir()
    ctx = RunContext(str(run))
    logs: list[tuple] = []
    ctx.log = lambda *a, **k: logs.append((a, k))  # type: ignore[method-assign]
    monkeypatch.setattr("interview_mux.mix_completeness.completeness_gate_enabled", lambda: True)
    monkeypatch.setattr("interview_mux.mix_completeness.completeness_gate_mode", lambda: "warn")
    monkeypatch.setattr(
        "interview_mux.mix_completeness._missing_sfx_from_mmaudio_qa",
        lambda c: {"bed_1"},
    )
    monkeypatch.setattr("interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: True)
    monkeypatch.setattr("interview_mux.first_try.allow_placeholder_mix", lambda cfg=None: True)
    # SFX only — warn, no raise
    enforce_mix_completeness(ctx, flow="podcast", stage="mix", missing_sfx=["bed_1"])
    with pytest.raises(RuntimeError, match="empty speech"):
        enforce_mix_completeness(ctx, flow="podcast", stage="mix", empty_speech=True)
    with pytest.raises(RuntimeError, match="missing VO"):
        enforce_mix_completeness(ctx, flow="podcast", stage="mix", missing_vo=["line_1"])


def test_g15_auto_approve_when_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from interview_mux.sfx_prompt_review import maybe_auto_approve_prompt_review

    run = tmp_path / "exec_g15"
    run.mkdir()
    (run / "sound_design").mkdir()
    (run / "understanding").mkdir()
    prompts = {
        "prompts": [
            {
                "asset_id": "a1",
                "sfx_prompt": "soft pad",
                "negative_prompt": "noise",
                "duration_seconds": 2.0,
            }
        ]
    }
    (run / "sound_design" / "sfx_prompts.json").write_text(json.dumps(prompts), encoding="utf-8")
    (run / "understanding" / "sound_design_plan.json").write_text(
        json.dumps({"assets": [{"asset_id": "a1"}], "flow_plans": {"podcast": {"cues": []}}}),
        encoding="utf-8",
    )
    (run / "run_meta.json").write_text("{}", encoding="utf-8")
    ctx = RunContext(str(run))
    monkeypatch.setattr("interview_mux.sfx_prompt_review.g15_required", lambda cfg=None: True)
    monkeypatch.setattr("interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: True)
    assert maybe_auto_approve_prompt_review(ctx) is True
    meta = json.loads((run / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["sfx_prompt_review"]["approved"] is True
    assert meta["sfx_prompt_review"]["approved_by"] == "auto_qa_green"
