from __future__ import annotations

from unittest.mock import patch

import pytest

from interview_mux.operator_subprocess import format_command, run_logged_command
from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log


def test_format_command_quotes_args() -> None:
    assert format_command(["ffmpeg", "-i", "my file.wav", "out.wav"]) == (
        "ffmpeg -i 'my file.wav' out.wav"
    )


def test_run_logged_command_streams_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    ctx = RunContext("exec_020_20260101T000020Z")
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))

    with patch("interview_mux.operator_subprocess.subprocess.Popen") as popen:
        class _Proc:
            returncode = 0

            def __init__(self) -> None:
                import io

                self.stdout = io.StringIO("line-one\n")
                self.stderr = io.StringIO("err-two\n")

            def wait(self, timeout=None):
                return 0

        popen.return_value = _Proc()
        run_logged_command(
            ctx,
            ["echo", "hello"],
            stage="ingest",
            label="echo hello",
        )

    entries = read_log(ctx.run_dir, tail=50)
    messages = [e["message"] for e in entries]
    assert any(m.startswith("$ echo hello") for m in messages)
    assert "line-one" in messages
    assert "err-two" in messages
    assert any("Command finished" in m for m in messages)


def test_run_logged_command_raises_on_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    ctx = RunContext("exec_021_20260101T000021Z")
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))

    with patch("interview_mux.operator_subprocess.subprocess.Popen") as popen:
        class _Proc:
            returncode = 1

            def __init__(self) -> None:
                import io

                self.stdout = io.StringIO("")
                self.stderr = io.StringIO("boom\n")

            def wait(self, timeout=None):
                return 1

        popen.return_value = _Proc()
        with pytest.raises(Exception, match="exit 1"):
            run_logged_command(ctx, ["false"], stage="ingest")

    entries = read_log(ctx.run_dir, tail=20)
    assert any("Command failed" in e.get("message", "") for e in entries)
