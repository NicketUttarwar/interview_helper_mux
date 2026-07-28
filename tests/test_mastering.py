from __future__ import annotations

import io
from pathlib import Path

from interview_mux.mastering_bus import AssemblyBusMetrics
from interview_mux.stages import mastering


class _Proc:
    returncode = 0

    def __init__(self, *, stderr: str = "") -> None:
        self.stderr = stderr


class _Ctx:
    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self.run_dir = run_dir
        self.done: list[str] = []
        self.logs: list[tuple[str, str | None]] = []

    def path(self, rel: str) -> Path:
        return self._run_dir / rel

    def mark_done(self, stage: str) -> None:
        self.done.append(stage)

    def log(
        self,
        message: str,
        *,
        level: str = "info",
        stage: str | None = None,
        detail: str | dict | None = None,
        **_: object,
    ) -> None:
        self.logs.append((message, stage))

    def artifact_exists(self, rel: str) -> bool:
        return (self._run_dir / rel).is_file()

    def read_path(self, rel: str) -> Path:
        return self._run_dir / rel


def test_master_wav_measures_bus_then_applies_loudnorm(monkeypatch, tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assembly_rel = "master/assembly.wav"
    assembly_path = run_dir / assembly_rel
    assembly_path.parent.mkdir(parents=True)
    assembly_path.write_bytes(b"fake wav" + b"\0" * 2048)
    ctx = _Ctx(run_dir)
    calls: list[list[str]] = []

    bus = AssemblyBusMetrics(
        integrated_lufs=-18.5,
        sample_rate_hz=48000,
        channels=2,
        duration_seconds=120.0,
    )

    def _fake_measure(_path: Path) -> AssemblyBusMetrics:
        return bus

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        calls.append(cmd)
        if "-f" in cmd and "null" in cmd:
            return _Proc(
                stderr="""
{
  "input_i" : "-15.1",
  "input_lra" : "4.2",
  "input_tp" : "-2.3",
  "input_thresh" : "-25.0",
  "target_offset" : "-0.4"
}
"""
            )
        return _Proc(stderr="")

    monkeypatch.setattr(mastering, "measure_assembly_bus", _fake_measure)
    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", _fake_run)

    class _FakePopen:
        returncode = 0

        def __init__(self, cmd, **kwargs):  # noqa: ANN001
            calls.append(cmd)
            self.stdout = io.StringIO("")
            self.stderr = io.StringIO("")
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"fake wav")

        def wait(self, timeout=None):  # noqa: ANN001
            return 0

        def kill(self) -> None:
            pass

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.Popen", _FakePopen)
    monkeypatch.setattr(mastering, "merged_config", lambda: {"flow1_target_lufs": -16.0})
    monkeypatch.setattr(mastering, "validate_pre_master", lambda *_a, **_k: [])

    output = mastering.master_wav(ctx, assembly_rel, "master/master.wav", flow="podcast")

    assert output == run_dir / "master/master.wav"
    assert ctx.done == ["master_finalize"]
    assert len(calls) == 1
    assert calls[0][0] == "ffmpeg"
    master_filter = calls[0][calls[0].index("-af") + 1]
    assert master_filter.startswith("alimiter=limit=0.891251:attack=5:release=50,loudnorm=")
    assert "I=-16.0" in master_filter
    assert "TP=-1.0" in master_filter
    assert any("Assembly bus measured -18.50 LUFS" in msg for msg, _ in ctx.logs)


def test_master_wav_blocks_on_pre_master_errors(monkeypatch, tmp_path) -> None:
    run_dir = tmp_path / "run_pre_fail"
    run_dir.mkdir()
    assembly_rel = "master/assembly.wav"
    assembly_path = run_dir / assembly_rel
    assembly_path.parent.mkdir(parents=True, exist_ok=True)
    assembly_path.write_bytes(b"fake wav" + b"\0" * 2048)
    ctx = _Ctx(run_dir)

    monkeypatch.setattr(
        mastering,
        "validate_pre_master",
        lambda *_a, **_k: ["mix_intelligibility QC failed"],
    )
    monkeypatch.setattr(mastering, "record_qc_summary", lambda *_a, **_k: None)

    try:
        mastering.master_wav(ctx, assembly_rel, "master/master.wav", flow="podcast")
    except RuntimeError as exc:
        assert "pre_master validation failed" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for pre_master validation failure.")


def test_extract_loudnorm_json_requires_expected_keys() -> None:
    stderr = '{"input_i":"-16.0","input_tp":"-1.2"}'
    try:
        mastering._extract_loudnorm_json(stderr)
    except RuntimeError as exc:
        assert "missing input_lra, input_thresh, target_offset" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for incomplete loudnorm fields.")


def test_master_filter_chain_can_disable_limiter() -> None:
    chain = mastering._master_filter_chain(
        {"master": {"safety_limiter_enabled": False}},
        target_lufs=-16.0,
        true_peak_dbtp=-0.85,
    )
    assert chain.startswith("loudnorm=")
    assert "alimiter" not in chain
