from __future__ import annotations

from pathlib import Path

from interview_mux.mastering_bus import AssemblyBusMetrics
from interview_mux.stages import mastering


class _Proc:
    def __init__(self, *, stderr: str = "") -> None:
        self.stderr = stderr


class _Ctx:
    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self.done: list[str] = []
        self.logs: list[tuple[str, str | None]] = []

    def path(self, rel: str) -> Path:
        return self._run_dir / rel

    def mark_done(self, stage: str) -> None:
        self.done.append(stage)

    def log(self, message: str, *, level: str = "info", stage: str | None = None, detail: str | None = None) -> None:
        self.logs.append((message, stage))


def test_master_wav_measures_bus_then_applies_loudnorm(monkeypatch, tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assembly_rel = "flow_1_master/assembly.wav"
    assembly_path = run_dir / assembly_rel
    assembly_path.parent.mkdir(parents=True)
    assembly_path.write_bytes(b"fake wav")
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

    def _fake_run(cmd, check, capture_output, text):  # noqa: ANN001
        assert check is True
        assert capture_output is True
        assert text is True
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
    monkeypatch.setattr(mastering.subprocess, "run", _fake_run)
    monkeypatch.setattr(mastering, "merged_config", lambda: {"flow1_target_lufs": -16.0})
    monkeypatch.setattr(mastering, "validate_pre_master", lambda *_a, **_k: [])
    monkeypatch.setattr(mastering, "_maybe_warn_low_sfx_energy", lambda *_a, **_k: None)

    output = mastering.master_wav(ctx, assembly_rel, "flow_1_master/master.wav", flow="flow1")

    assert output == run_dir / "flow_1_master/master.wav"
    assert ctx.done == ["master_flow1"]
    assert len(calls) == 2
    assert calls[0][0] == "ffmpeg"
    assert "print_format=json" in calls[0][calls[0].index("-af") + 1]
    second_filter = calls[1][calls[1].index("-af") + 1]
    assert "linear=true" in second_filter
    assert "measured_I=-18.50" in second_filter
    assert "offset=2.50" in second_filter
    assert "TP=-1.0" in second_filter
    assert any("Assembly bus measured -18.50 LUFS" in msg for msg, _ in ctx.logs)


def test_master_wav_warns_low_sfx_energy(monkeypatch, tmp_path) -> None:
    from run_fixtures import isolated_run_ctx, sound_design_plan_with
    import struct
    import wave

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "master_sfx_warn")
    assembly = ctx.path("flow_1_master", "assembly.wav")
    assembly.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    n = rate
    with wave.open(str(assembly), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{n}h", *([50] * n)))
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "bed_01",
                    "role": "ambient_bed",
                    "description": "warm bed",
                    "duration_seconds": 4.0,
                }
            ],
            flow_plans={
                "flow1": {
                    "cues": [
                        {
                            "cue_id": "c1",
                            "asset_id": "bed_01",
                            "placement": "under_segment",
                            "segment_id": "seg_001",
                        }
                    ]
                }
            },
        ),
        skip_handoff=True,
    )

    bus = AssemblyBusMetrics(
        integrated_lufs=-30.0,
        sample_rate_hz=48000,
        channels=1,
        duration_seconds=1.0,
    )

    def _fake_measure(_path: Path) -> AssemblyBusMetrics:
        return bus

    def _fake_run(cmd, check, capture_output, text):  # noqa: ANN001
        return _Proc(
            stderr='{"input_i":"-30.0","input_lra":"2.0","input_tp":"-5.0","input_thresh":"-40.0","target_offset":"14.0"}'
        )

    monkeypatch.setattr(mastering, "measure_assembly_bus", _fake_measure)
    monkeypatch.setattr(mastering.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        mastering,
        "merged_config",
        lambda: {"flow1_target_lufs": -16.0, "mix": {"master_sfx_energy_threshold": 0.03}},
    )
    monkeypatch.setattr(mastering, "validate_pre_master", lambda *_a, **_k: [])

    logs: list[str] = []

    def _capture_log(message: str, *, level: str = "info", stage: str | None = None, detail: str | None = None) -> None:
        logs.append(message)

    monkeypatch.setattr(ctx, "log", _capture_log)
    mastering.master_wav(ctx, "flow_1_master/assembly.wav", "flow_1_master/master.wav", flow="flow1")
    assert any("master_sfx_energy_low" in msg for msg in logs)


def test_extract_loudnorm_json_requires_expected_keys() -> None:
    stderr = '{"input_i":"-16.0","input_tp":"-1.2"}'
    try:
        mastering._extract_loudnorm_json(stderr)
    except RuntimeError as exc:
        assert "missing input_lra, input_thresh, target_offset" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for incomplete loudnorm fields.")
