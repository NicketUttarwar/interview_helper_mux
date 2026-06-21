from __future__ import annotations

import json

import pytest

from interview_mux.operator_trace import (
    StageSubstepError,
    failure_detail,
    log_stage_error,
    log_step,
    logged_step,
    resolve_ctx,
    resolve_stage,
)


def test_log_step_writes_when_context_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    from interview_mux.run_context import RunContext
    from interview_mux.session_log import read_log

    ctx = RunContext("exec_030_20260101T000030Z")
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))

    from interview_mux.operator_trace import active_run_context

    token = active_run_context.set(ctx)
    try:
        log_step("Substep alpha", stage="ingest")
    finally:
        active_run_context.reset(token)

    entries = read_log(ctx.run_dir, tail=10)
    assert any(e.get("message") == "Substep alpha" for e in entries)


def test_logged_step_success_and_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    from interview_mux.run_context import RunContext
    from interview_mux.session_log import read_log

    ctx = RunContext("exec_031_20260101T000031Z")
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))

    with logged_step("beta work", ctx=ctx, stage="transcribe"):
        pass

    entries = read_log(ctx.run_dir, tail=10)
    messages = [e.get("message") for e in entries]
    assert "Start: beta work" in messages
    assert "Done: beta work" in messages


def test_logged_step_failure_includes_trace_detail(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    from interview_mux.run_context import RunContext
    from interview_mux.session_log import read_log

    ctx = RunContext("exec_032_20260101T000032Z")
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))

    with pytest.raises(ValueError, match="boom"):
        with logged_step("gamma work", ctx=ctx, stage="ingest"):
            raise ValueError("boom")

    entries = read_log(ctx.run_dir, tail=10)
    fail = next(e for e in entries if e.get("message") == "Failed: gamma work")
    detail = json.loads(fail["detail"])
    assert detail["event"] == "substep_fail"
    assert detail["error_class"] == "ValueError"
    assert "boom" in detail["traceback"]


def test_log_failure_and_stage_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    from interview_mux.run_context import RunContext
    from interview_mux.session_log import read_log

    ctx = RunContext("exec_033_20260101T000033Z")
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))

    try:
        raise RuntimeError("stage broke")
    except RuntimeError as exc:
        log_stage_error("ingest", exc, ctx=ctx)

    entries = read_log(ctx.run_dir, tail=5)
    fail = next(e for e in entries if "Failed: Stage ingest" in e.get("message", ""))
    detail = json.loads(fail["detail"])
    assert detail["error_class"] == "RuntimeError"
    assert detail["event"] == "substep_fail"


def test_stage_substep_error_carries_stage() -> None:
    err = StageSubstepError("bad substep", stage="transcribe")
    assert err.stage == "transcribe"
    assert str(err) == "bad substep"


def test_failure_detail_from_exc() -> None:
    try:
        raise TypeError("nope")
    except TypeError as exc:
        detail = failure_detail(exc)
    assert detail["error_class"] == "TypeError"
    assert detail["event"] == "substep_fail"
    assert "TypeError" in detail["traceback"]
