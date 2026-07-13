from __future__ import annotations

import json
import shutil
from pathlib import Path

from interview_mux.operator_quality import qc_summary, record_qc_summary
from interview_mux.prompt_validation import (
    validate_coherence_report,
    validate_interview_spine,
    validate_nle_edits,
    validate_source_acoustic_profile,
    validate_transcript_review_queue,
)
from interview_mux.run_context import RunContext

FIXTURE = Path(__file__).parent / "fixtures" / "runs" / "gap_closure_smoke"


def _load(rel: str) -> dict:
    return json.loads((FIXTURE / rel).read_text(encoding="utf-8"))


def test_fixture_nle_edits_valid():
    assert validate_nle_edits(_load("segments/nle_edits.json")) == []


def test_fixture_nle_edits_invalid():
    errors = validate_nle_edits(_load("segments/nle_edits_invalid.json"))
    assert errors
    assert any("segment_overrides" in e for e in errors)


def test_fixture_review_queue_invalid():
    errors = validate_transcript_review_queue(_load("transcript/review_queue.json"))
    assert errors
    assert any("chunks" in e for e in errors)


def test_fixture_source_acoustic_profile_valid():
    assert validate_source_acoustic_profile(_load("understanding/source_acoustic_profile.json")) == []


def test_fixture_interview_spine_valid():
    assert validate_interview_spine(_load("understanding/interview_spine.json")) == []


def test_coherence_report_from_planted_fixture(tmp_path, monkeypatch):
    from interview_mux.coherence.analyze import build_coherence_report

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    planted = Path(__file__).parent / "fixtures" / "runs" / "coherence_30m_planted_drift"
    run_dir = tmp_path / "coherence_planted"
    shutil.copytree(planted, run_dir)
    ctx = RunContext("coherence_planted", create=False)
    ctx.run_dir = run_dir
    report = build_coherence_report(ctx, phase="post_reanchor")
    assert validate_coherence_report(report) == []


def test_record_qc_summary_merge_on_fixture_run_meta(tmp_path):
    run_dir = tmp_path / "gap_closure_smoke"
    shutil.copytree(FIXTURE, run_dir)
    ctx = RunContext("gap_closure_smoke", create=False)
    ctx.run_dir = run_dir

    meta = ctx.read_json("run_meta.json")
    assert meta["execution_id"] == "gap_closure_smoke"
    assert qc_summary(meta, "narrative_qc")["passed"] is True

    record_qc_summary(ctx, "show_notes_qc", {"passed": False, "errors": ["too short"]})
    updated = ctx.read_json("run_meta.json")
    assert updated["qc_summaries"]["narrative_qc"]["passed"] is True
    assert updated["qc_summaries"]["show_notes_qc"]["passed"] is False
    assert "recorded_at" in updated["qc_summaries"]["show_notes_qc"]
