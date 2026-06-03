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


def test_is_custom_run_artifact() -> None:
    assert is_custom_run_artifact("understanding/content_brief.json")
    assert not is_custom_run_artifact("ingest/checksums.json")


def test_record_custom_run_write_clears_ack(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ASSETS" / "executions").mkdir(parents=True)
    ctx = RunContext(create=True)
    ctx.init_run_meta("ASSETS/input/interview.wav")
    meta = ctx.read_json("run_meta.json")
    meta["handoff_ack"] = {"speaker_roles": "2026-01-01T00:00:00Z"}
    ctx.write_json("run_meta.json", meta)
    ctx.path("understanding/speakers.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/speakers.json").write_text("{}", encoding="utf-8")
    record_custom_run_write(ctx, "understanding/speakers.json", stage_key="speaker_roles")
    assert not handoff_acknowledged(ctx, "speaker_roles")


def test_pending_handoff_after_mark_done(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ASSETS" / "executions").mkdir(parents=True)
    ctx = RunContext(create=True)
    ctx.path("understanding/speakers.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/speakers.json").write_text("{}", encoding="utf-8")
    ctx.mark_done("speaker_roles")
    assert pending_handoff_stage(ctx) == "speaker_roles"


def test_require_handoff_clear_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ASSETS" / "executions").mkdir(parents=True)
    ctx = RunContext(create=True)
    ctx.path("understanding/speakers.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/speakers.json").write_text("{}", encoding="utf-8")
    ctx.mark_done("speaker_roles")
    with pytest.raises(SystemExit):
        require_handoff_clear(ctx)
