from __future__ import annotations

import pytest

from interview_mux.artifact_completeness import (
    artifact_status,
    compute_gaps,
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


def test_validate_artifact_write_content_brief_registered():
    errors = validate_artifact_write(
        "understanding/content_brief.json",
        {"thesis": "ok", "topics": [{"name": "n", "summary": "s"}]},
    )
    assert errors == []
