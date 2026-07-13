from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from interview_mux import master_qc

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "verify_master.py"

class _Proc:
    returncode = 0

    def __init__(self, *, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr

def test_verify_master_cli_pass(monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    wav = tmp_path / "master" / "master.wav"
    wav.parent.mkdir(parents=True)
    wav.write_bytes(b"RIFF")

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[0] == "ffprobe":
            return _Proc(
                stdout='{"streams":[{"sample_rate":"48000","channels":2}],"format":{"duration":"120.0"}}'
            )
        if cmd[0] == "ffmpeg":
            return _Proc(stderr='{"input_i" : "-16.0", "input_tp" : "-1.5"}')
        raise AssertionError(cmd)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", _fake_run)
    monkeypatch.setattr(sys, "argv", ["verify_master.py", str(wav)])

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(CLI), run_name="__main__")
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "OK:" in out
    assert "integrated_lufs=" in out

def test_verify_master_cli_fail(monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    wav = tmp_path / "flow_2_highlights" / "master.wav"
    wav.parent.mkdir(parents=True)
    wav.write_bytes(b"RIFF")

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[0] == "ffprobe":
            return _Proc(
                stdout='{"streams":[{"sample_rate":"48000","channels":2}],"format":{"duration":"90.0"}}'
            )
        if cmd[0] == "ffmpeg":
            return _Proc(stderr='{"input_i" : "-20.0", "input_tp" : "-0.5"}')
        raise AssertionError(cmd)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", _fake_run)
    monkeypatch.setattr(sys, "argv", ["verify_master.py", str(wav)])

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(CLI), run_name="__main__")
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "FAIL:" in out

def test_detect_flow_from_path() -> None:
    assert master_qc.detect_flow_from_path(Path("data/run/master/master.wav")) == "podcast"
    assert master_qc.detect_flow_from_path(Path("/tmp/master.wav")) is None
