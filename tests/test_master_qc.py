from __future__ import annotations

from pathlib import Path

from interview_mux import master_qc


class _Proc:
    returncode = 0

    def __init__(self, *, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def test_verify_master_pass(monkeypatch) -> None:
    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[0] == "ffprobe":
            return _Proc(
                stdout='{"streams":[{"sample_rate":"48000","channels":2}],"format":{"duration":"132.0"}}'
            )
        if cmd[0] == "ffmpeg":
            return _Proc(
                stderr="""
[Parsed_loudnorm_0 @ 0x0]
{
  "input_i" : "-16.2",
  "input_tp" : "-1.4"
}
"""
            )
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", _fake_run)
    result = master_qc.verify_master(Path("/tmp/flow_1_master/master.wav"), flow="flow1")
    assert result.ok is True
    assert result.failures == []


def test_verify_master_failures(monkeypatch) -> None:
    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[0] == "ffprobe":
            return _Proc(
                stdout='{"streams":[{"sample_rate":"32000","channels":2}],"format":{"duration":"80.0"}}'
            )
        if cmd[0] == "ffmpeg":
            return _Proc(
                stderr="""
{
  "input_i" : "-11.0",
  "input_tp" : "-0.2"
}
"""
            )
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", _fake_run)
    result = master_qc.verify_master(Path("/tmp/flow_2_highlights/master.wav"), flow="flow2")
    assert result.ok is False
    assert any("Integrated LUFS" in line for line in result.failures)
    assert any("True peak" in line for line in result.failures)
    assert any("Sample rate" in line for line in result.failures)
