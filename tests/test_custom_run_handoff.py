"""Custom-run artifact handoff checkpoints."""

from __future__ import annotations

import pytest

from interview_mux.custom_run_handoff import (
    handoff_acknowledged,
    is_custom_run_artifact,
    pending_handoff_stage,
    record_custom_run_write,
    require_handoff_clear,
)
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root

COMPLETE_SPEAKERS = {
    "speakers": [
        {
            "speaker_id": "spk_0",
            "role": "interviewer",
            "confidence": 0.95,
        },
        {
            "speaker_id": "spk_1",
            "role": "interviewee",
            "confidence": 0.92,
        },
    ]
}


def test_is_custom_run_artifact() -> None:
    assert is_custom_run_artifact("understanding/content_brief.json")
    assert not is_custom_run_artifact("ingest/checksums.json")


def test_record_custom_run_write_clears_ack(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    init_run_meta_for_test(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["handoff_ack"] = {"speaker_roles": "2026-01-01T00:00:00Z"}
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    ctx.write_json("understanding/speakers.json", COMPLETE_SPEAKERS, stage_key="speaker_roles")
    record_custom_run_write(ctx, "understanding/speakers.json", stage_key="speaker_roles")
    assert not handoff_acknowledged(ctx, "speaker_roles")


def test_pending_handoff_not_triggered_for_empty_artifact(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    ctx.path("understanding/speakers.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/speakers.json").write_text("{}", encoding="utf-8")
    ctx.mark_done("speaker_roles")
    assert pending_handoff_stage(ctx) is None


def test_pending_handoff_after_mark_done_with_complete_artifact(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    monkeypatch.setattr("interview_mux.full_autopilot.full_autopilot_enabled", lambda cfg=None: False)
    ctx = RunContext(create=True)
    ctx.write_json("understanding/speakers.json", COMPLETE_SPEAKERS, stage_key="speaker_roles")
    ctx.mark_done("speaker_roles")
    assert pending_handoff_stage(ctx) == "speaker_roles"


def test_require_handoff_clear_raises(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    monkeypatch.setattr("interview_mux.full_autopilot.full_autopilot_enabled", lambda cfg=None: False)
    ctx = RunContext(create=True)
    ctx.write_json("understanding/speakers.json", COMPLETE_SPEAKERS, stage_key="speaker_roles")
    ctx.mark_done("speaker_roles")
    with pytest.raises(SystemExit):
        require_handoff_clear(ctx)
