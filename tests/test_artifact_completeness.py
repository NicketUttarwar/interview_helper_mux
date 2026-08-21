from __future__ import annotations

import pytest

from interview_mux.artifact_completeness import (
    artifact_status,
    compute_gaps,
    compute_staged_write_gaps,
    merge_artifact,
    should_run_stage_for_artifact,
)
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.prompt_validation import validate_artifact_write
from interview_mux.run_context import RunContext


def test_compute_gaps_empty_content_brief():
    gaps = compute_gaps("understanding/content_brief.json", {})
    paths = {g.path for g in gaps}
    assert "thesis" in paths
    assert "topics" in paths


def test_compute_gaps_complete_content_brief():
    data = {
        "thesis": "Main takeaway from the interview.",
        "topics": [{"name": "Topic A", "summary": "Summary here."}],
    }
    assert compute_gaps("understanding/content_brief.json", data) == []


def test_compute_staged_write_gaps_relax_analysis_state_for_speaker_roles():
    from interview_mux.analysis_memory import default_analysis_state

    state = default_analysis_state("exec_test")
    state["speakers"] = [
        {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.8},
        {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.7},
    ]
    assert compute_gaps("understanding/analysis_state.json", state, stage_key="speaker_roles")
    assert not compute_staged_write_gaps(
        "understanding/analysis_state.json",
        state,
        stage_id="speaker_roles",
    )


def test_merge_artifact_preserves_operator_verified_themes():
    existing = {
        "meta": {"operator_verified": True},
        "themes": [{"id": "t1", "label": "Operator theme"}],
        "narrative": {"thesis": "old"},
    }
    patch = {
        "themes": [{"id": "t2", "label": "LLM theme"}],
        "narrative": {"thesis": "new"},
    }
    merged = merge_artifact(
        "understanding/analysis_state.json",
        existing,
        patch,
        preserve_operator=True,
    )
    assert merged["themes"] == existing["themes"]
    assert merged["narrative"]["thesis"] == "old"


def test_write_validated_artifact_rejects_invalid_brief(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    with pytest.raises(ValueError, match="schema validation failed"):
        write_validated_artifact(
            ctx,
            "understanding/content_brief.json",
            {"thesis": "", "topics": []},
            merge_from_disk=False,
            stage_key="content_context",
        )


def test_artifact_status_pending_and_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    assert artifact_status("understanding/content_brief.json", ctx) == "pending"
    write_validated_artifact(
        ctx,
        "understanding/content_brief.json",
        {
            "thesis": "A clear thesis.",
            "topics": [{"name": "A", "summary": "B"}],
        },
        merge_from_disk=False,
        stage_key="content_context",
    )
    assert artifact_status("understanding/content_brief.json", ctx) == "complete"


def test_preferred_fill_stage_uses_reanchor_after_manifest(tmp_path, monkeypatch):
    from interview_mux.artifact_completeness import preferred_fill_stage

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    assert preferred_fill_stage("understanding/content_brief.json", ctx) == "content_context"
    manifest = ctx.path("segments", "manifest.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"segments":[{"segment_id":"seg_001"}]}', encoding="utf-8")
    assert preferred_fill_stage("understanding/content_brief.json", ctx) == "content_brief_reanchor"


def test_should_run_stage_when_gaps_remain(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    brief_path = ctx.path("understanding", "content_brief.json")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps({"thesis": "", "topics": []}),
        encoding="utf-8",
    )
    assert should_run_stage_for_artifact(ctx, "content_context") is True


def test_analysis_profile_ready_requires_complete_artifacts(tmp_path, monkeypatch):
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review
    from run_fixtures import isolated_run_ctx, patch_merged_config, populated_analysis_state

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "ready_gate")
    ctx.mark_done("optimal_questions")
    state = populated_analysis_state(ctx.run_id, verified=True)
    ctx.write_json("understanding/analysis_state.json", state)
    assert analysis_profile_ready_for_review(ctx) is False


def test_validate_artifact_write_content_brief_registered():
    errors = validate_artifact_write(
        "understanding/content_brief.json",
        {"thesis": "ok", "topics": [{"name": "n", "summary": "s"}]},
    )
    assert errors == []


def test_gap_report_empty_interviewer_lines_is_complete(tmp_path, monkeypatch):
    from run_fixtures import minimal_gap_report

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    write_validated_artifact(
        ctx,
        "understanding/gap_report.json",
        minimal_gap_report(),
        merge_from_disk=False,
        stage_key="optimal_questions",
    )
    assert artifact_status("understanding/gap_report.json", ctx) == "complete"


def test_seed_analysis_ready_with_empty_gap_report(tmp_path, monkeypatch):
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review
    from run_fixtures import isolated_run_ctx, patch_merged_config, seed_analysis_ready_artifacts

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "seed_ready")
    seed_analysis_ready_artifacts(ctx, verified=True)
    assert artifact_status("understanding/gap_report.json", ctx) == "complete"
    assert analysis_profile_ready_for_review(ctx) is True


def test_artifact_status_partial_when_resilience_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    write_validated_artifact(
        ctx,
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.8},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.7},
            ],
            "_meta": {
                "resilience": {
                    "partial": True,
                    "summary": "saved after arbiter failure",
                }
            },
        },
        merge_from_disk=False,
        stage_key="speaker_roles",
    )
    assert artifact_status("understanding/speakers.json", ctx) == "partial"
    assert should_run_stage_for_artifact(ctx, "speaker_roles") is True
