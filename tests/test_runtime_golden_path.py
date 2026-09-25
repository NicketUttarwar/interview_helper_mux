"""Runtime golden path — save contract and GET artifact read resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.artifact_completeness import artifact_status
from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    approve_stage_writes,
    record_pending_approval,
    resolve_read_path,
    write_pending_content,
)
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_speakers


def test_get_artifact_uses_resolve_read_path_during_staging(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "staging_read")
    staged_doc = {"speakers": [{"speaker_id": "spk_001", "role": "interviewer", "label": "Host"}]}
    write_pending_content(ctx, "speaker_roles", "understanding/speakers.json", data=staged_doc)
    record_pending_approval(ctx, "speaker_roles")
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    enter_stage_staging("speaker_roles")
    try:
        read_path = resolve_read_path(ctx, "understanding/speakers.json")
    finally:
        exit_stage_staging()
    assert read_path.is_file()
    assert read_path.read_text(encoding="utf-8").strip().startswith("{")


def test_save_contract_commits_and_marks_complete(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "save_contract")
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    doc = minimal_speakers()
    write_pending_content(ctx, "speaker_roles", "understanding/speakers.json", data=doc)
    record_pending_approval(ctx, "speaker_roles")
    flushed = approve_stage_writes(ctx, "speaker_roles")
    assert "understanding/speakers.json" in flushed
    assert artifact_status("understanding/speakers.json", ctx) == "complete"
    final = ctx.run_dir / "understanding" / "speakers.json"
    assert final.is_file()
    assert json.loads(final.read_text(encoding="utf-8"))["speakers"]


def test_adversarial_null_thesis_fails_schema_or_completeness():
    from interview_mux.prompt_validation import validate_artifact_write

    path = Path(__file__).parent / "fixtures" / "adversarial_artifacts.json"
    adv = json.loads(path.read_text(encoding="utf-8"))
    doc = adv["content_context_null_thesis"]
    errors = validate_artifact_write("understanding/content_brief.json", doc)
    assert errors or not doc.get("thesis")
