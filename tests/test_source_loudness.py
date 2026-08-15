"""Tests for source loudness stabilize (ingest)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.source_loudness import (
    build_ingest_loudness_filter,
    loudness_lineage_payload,
    loudness_stabilize_cfg,
)
from interview_mux.stages import ingest as ingest_mod


def _write_wav(path: Path, *, seconds: float = 0.25, sample_rate: int = 16000, amp: int = 200) -> None:
    frames = int(seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Quiet PCM so stabilize has something to boost (not silence).
    sample = amp.to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(sample * frames)


def test_loudness_stabilize_defaults_upward_only() -> None:
    cfg = loudness_stabilize_cfg({})
    assert cfg["enabled"] is True
    assert cfg["target_lufs"] == -18.0
    assert cfg["dynaudnorm"] is True
    assert cfg["dynaudnorm_mode"] == "upward_only"
    af = build_ingest_loudness_filter(cfg)
    assert af is not None
    assert af.startswith("acompressor=mode=upward")
    assert "threshold=0.125" in af
    assert "loudnorm=I=-18" in af
    assert "dual_mono=true" in af
    assert "dynaudnorm=" not in af


def test_loudness_stabilize_can_disable() -> None:
    cfg = loudness_stabilize_cfg({"ingest": {"loudness_stabilize": {"enabled": False}}})
    assert build_ingest_loudness_filter(cfg) is None
    payload = loudness_lineage_payload(cfg, af_filter=None)
    assert payload["enabled"] is False


def test_loudness_stabilize_loudnorm_only() -> None:
    cfg = loudness_stabilize_cfg(
        {"ingest": {"loudness_stabilize": {"enabled": True, "dynaudnorm": False}}}
    )
    af = build_ingest_loudness_filter(cfg)
    assert af == "loudnorm=I=-18:TP=-1.5:LRA=11:dual_mono=true"


def test_loudness_stabilize_classic_dynaudnorm() -> None:
    cfg = loudness_stabilize_cfg(
        {
            "ingest": {
                "loudness_stabilize": {
                    "enabled": True,
                    "dynaudnorm": True,
                    "dynaudnorm_mode": "classic",
                    "dynaudnorm_frame_ms": 500,
                    "dynaudnorm_gausssize": 31,
                }
            }
        }
    )
    af = build_ingest_loudness_filter(cfg)
    assert af is not None
    assert af.startswith("dynaudnorm=")
    assert "v='max(p\\,0.95)'" in af
    assert "loudnorm=I=-18" in af
    assert "acompressor=" not in af
    lineage = loudness_lineage_payload(cfg, af_filter=af)
    assert lineage["dynaudnorm_mode"] == "classic"


def test_loudness_stabilize_rejects_bad_gausssize() -> None:
    cfg = loudness_stabilize_cfg(
        {
            "ingest": {
                "loudness_stabilize": {
                    "dynaudnorm_mode": "classic",
                    "dynaudnorm_gausssize": 14,
                }
            }
        }
    )
    with pytest.raises(ValueError, match="gausssize"):
        build_ingest_loudness_filter(cfg)


def test_loudness_stabilize_rejects_bad_upward_threshold() -> None:
    cfg = loudness_stabilize_cfg(
        {"ingest": {"loudness_stabilize": {"upward_threshold": 2.0}}}
    )
    with pytest.raises(ValueError, match="upward_threshold"):
        build_ingest_loudness_filter(cfg)


def test_run_ingest_applies_loudness_af_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_EXECUTIONS_ROOT", str(tmp_path / "executions"))
    ctx = RunContext("exec_test_loudness_ingest", create=True)
    wav = tmp_path / "input.wav"
    _write_wav(wav)
    ctx.init_run_meta(str(wav), source_audio_hash="b" * 64)

    captured: dict[str, list[str]] = {}

    def fake_run(ctx_arg, cmd, **kwargs):
        captured["cmd"] = list(cmd)
        out = Path(cmd[-1])
        _write_wav(out, sample_rate=48000, amp=4000)
        return None

    monkeypatch.setattr(ingest_mod, "run_logged_command", fake_run)
    monkeypatch.setattr(ingest_mod, "touch_job_message", lambda *a, **k: None)
    monkeypatch.setattr(
        ingest_mod,
        "merged_config",
        lambda: {"sample_rate": 48000, "ingest": {"loudness_stabilize": {"enabled": True}}},
    )

    out = ingest_mod.run_ingest(ctx)
    assert out.is_file()
    cmd = captured["cmd"]
    assert "-af" in cmd
    af = cmd[cmd.index("-af") + 1]
    assert "acompressor=mode=upward" in af
    assert "loudnorm=I=-18" in af
    lineage = ctx.read_json("ingest/loudness.json")
    assert lineage["enabled"] is True
    assert lineage["dynaudnorm_mode"] == "upward_only"
    assert "loudnorm=" in str(lineage["af_filter"])
    checksums = ctx.read_json("ingest/checksums.json")
    assert checksums["loudness_stabilize"] is True


def test_run_ingest_skips_af_when_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_EXECUTIONS_ROOT", str(tmp_path / "executions"))
    ctx = RunContext("exec_test_loudness_off", create=True)
    wav = tmp_path / "input.wav"
    _write_wav(wav)
    ctx.init_run_meta(str(wav), source_audio_hash="c" * 64)

    captured: dict[str, list[str]] = {}

    def fake_run(ctx_arg, cmd, **kwargs):
        captured["cmd"] = list(cmd)
        out = Path(cmd[-1])
        _write_wav(out, sample_rate=48000, amp=4000)
        return None

    monkeypatch.setattr(ingest_mod, "run_logged_command", fake_run)
    monkeypatch.setattr(ingest_mod, "touch_job_message", lambda *a, **k: None)
    monkeypatch.setattr(
        ingest_mod,
        "merged_config",
        lambda: {"sample_rate": 48000, "ingest": {"loudness_stabilize": {"enabled": False}}},
    )

    ingest_mod.run_ingest(ctx)
    assert "-af" not in captured["cmd"]
    assert ctx.read_json("ingest/loudness.json")["enabled"] is False
    assert ctx.read_json("ingest/checksums.json")["loudness_stabilize"] is False


def test_run_ingest_uses_preclean_then_stabilizes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_EXECUTIONS_ROOT", str(tmp_path / "executions"))
    ctx = RunContext("exec_test_loudness_preclean", create=True)
    raw = tmp_path / "input.wav"
    _write_wav(raw)
    ctx.init_run_meta(str(raw), source_audio_hash="d" * 64)
    isolated = ctx.path("preclean", "isolated.wav")
    _write_wav(isolated, sample_rate=48000, amp=100)

    captured: dict[str, list[str]] = {}

    def fake_run(ctx_arg, cmd, **kwargs):
        captured["cmd"] = list(cmd)
        _write_wav(Path(cmd[-1]), sample_rate=48000, amp=5000)
        return None

    monkeypatch.setattr(ingest_mod, "run_logged_command", fake_run)
    monkeypatch.setattr(ingest_mod, "touch_job_message", lambda *a, **k: None)
    monkeypatch.setattr(ingest_mod, "merged_config", lambda: {"sample_rate": 48000})

    ingest_mod.run_ingest(ctx)
    assert captured["cmd"][captured["cmd"].index("-i") + 1] == str(isolated)
    assert "-af" in captured["cmd"]
