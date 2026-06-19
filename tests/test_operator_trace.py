from __future__ import annotations

from interview_mux.operator_trace import log_step, logged_step, resolve_ctx, resolve_stage


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
