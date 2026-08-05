"""Focused tests for DSP timbre match, VO match routing, S2S CLI, pickup precedence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import resolve_vo_pickup_path
from interview_mux.timbre_match import (
    DEFAULT_MAX_EQ_DB,
    build_firequalizer_filter,
    build_match_command,
    correction_curve_db,
    format_gain_entry,
)
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, minimal_gap_line, patch_executions_root, patch_merged_config

# tools/ is not a package — load s2s_generate by path for argv contract tests.
_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import s2s_generate  # noqa: E402


def _write_tone(
    path: Path,
    *,
    rate: int = 48000,
    seconds: float = 1.5,
    freqs: tuple[float, ...] = (300.0, 3000.0),
    amps: tuple[float, ...] = (0.3, 0.05),
) -> None:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    wave = np.zeros_like(t)
    for f, a in zip(freqs, amps):
        wave += a * np.sin(2 * np.pi * f * t)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), wave.astype(np.float32), rate)


def test_correction_curve_clamped_to_max_eq_db(tmp_path: Path) -> None:
    ref = tmp_path / "ref.wav"
    src = tmp_path / "src.wav"
    # Bright reference vs dull source → positive high-band gains, still clamped.
    _write_tone(ref, freqs=(400.0, 4000.0), amps=(0.15, 0.35))
    _write_tone(src, freqs=(400.0, 4000.0), amps=(0.35, 0.02))
    curve = correction_curve_db(ref, src, max_eq_db=DEFAULT_MAX_EQ_DB)
    assert curve
    gains = [g for _, g in curve]
    assert max(gains) <= DEFAULT_MAX_EQ_DB + 1e-9
    assert min(gains) >= -DEFAULT_MAX_EQ_DB - 1e-9


def test_firequalizer_command_uses_gain_entry_syntax(tmp_path: Path) -> None:
    curve = [(100.0, 0.0), (1000.0, 3.25), (4000.0, -2.5)]
    entry = format_gain_entry(curve)
    assert "entry(100,0.0000)" in entry
    assert "entry(1000,3.2500)" in entry
    assert "; " in entry
    af = build_firequalizer_filter(curve, loudness_gain_db=1.5)
    assert "firequalizer=gain_entry='" in af
    assert "entry(1000,3.2500)" in af
    assert "volume=1.500dB" in af
    assert "sample_rates=48000" in af
    cmd = build_match_command(tmp_path / "in.wav", tmp_path / "out.wav", curve=curve, loudness_gain_db=0.0)
    assert cmd[0] == "ffmpeg"
    assert "-af" in cmd
    assert "pcm_s16le" in cmd


def test_s2s_generate_argv_uses_file_prefix_not_output_or_context() -> None:
    argv = s2s_generate.build_tts_argv(
        model_id="mlx-community/dummy",
        text="Hello",
        ref_audio=Path("/tmp/ref.wav"),
        file_prefix="line_001",
    )
    assert "--file_prefix" in argv
    assert argv[argv.index("--file_prefix") + 1] == "line_001"
    assert "--join_audio" in argv
    assert "--output" not in argv
    assert "--context" not in argv
    assert "-m" in argv and "mlx_audio.tts.generate" in argv


def test_s2s_generate_convert_rejected() -> None:
    with pytest.raises(ValueError, match="timbre_match"):
        s2s_generate.run_payload(
            {
                "mode": "convert",
                "model_id": "x",
                "ref_audio": __file__,
                "out_wav": "/tmp/out.wav",
                "source_audio": __file__,
            }
        )


def test_discover_generated_wav_prefers_joined(tmp_path: Path) -> None:
    prefix = "line_001"
    joined = tmp_path / f"{prefix}.wav"
    numbered = tmp_path / f"{prefix}_000.wav"
    joined.write_bytes(b"RIFF")
    numbered.write_bytes(b"RIFF")
    found = s2s_generate.discover_generated_wav(tmp_path, prefix)
    assert found == joined


def test_resolve_vo_pickup_precedence_clean_before_normalized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {"enabled": False, "speech_qa_enabled": False}
                }
            }
        },
    )
    ctx = RunContext("exec_vo_prec_clean", create=True)
    init_run_meta_for_test(ctx)
    line = minimal_gap_line(line_id="line_001", targets_segment_id="seg_001")
    pickup = ctx.final_path("vo_pickup")
    for sub in ("matched", "synthesized", "clean", "normalized"):
        (pickup / sub).mkdir(parents=True, exist_ok=True)
    (pickup / "normalized" / "line_001.wav").write_bytes(b"RIFF-norm")
    (pickup / "clean" / "line_001.wav").write_bytes(b"RIFF-clean")
    (pickup / "line_001.wav").write_bytes(b"RIFF-raw")
    assert resolve_vo_pickup_path(ctx, line).name == "line_001.wav"
    assert resolve_vo_pickup_path(ctx, line).parent.name == "clean"

    (pickup / "synthesized" / "line_001.wav").write_bytes(b"RIFF-synth")
    assert resolve_vo_pickup_path(ctx, line).parent.name == "synthesized"

    (pickup / "matched" / "line_001.wav").write_bytes(b"RIFF-match")
    assert resolve_vo_pickup_path(ctx, line).parent.name == "matched"


def _match_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RunContext]:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": False},
        },
    )
    rid = "exec_match_001"
    ctx = RunContext(rid, create=True)
    init_run_meta_for_test(ctx)
    line = {
        **minimal_gap_line(line_id="line_001", targets_segment_id="seg_001"),
        "text": "What happened next?",
        "voice_speaker_id": "spk_0",
    }
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": [line]}, skip_handoff=True)
    return TestClient(create_app()), ctx


def test_vo_match_endpoint_uses_dsp_not_s2s_convert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, ctx = _match_client(tmp_path, monkeypatch)
    out = ctx.path("vo_pickup", "matched", "line_001.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"RIFF-matched")

    called = {"dsp": False, "s2s": False}

    def _fake_match(_ctx, _line, source_audio: Path) -> Path:
        called["dsp"] = True
        assert source_audio.name == "line_001_upload.wav"
        assert source_audio.is_file()
        return out

    def _fake_synth(*_a, **_k):
        called["s2s"] = True
        raise AssertionError("s2s convert must not be called")

    monkeypatch.setattr("interview_mux.timbre_match.match_vo_take", _fake_match)
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _fake_synth)

    res = client.post(
        f"/api/runs/{ctx.run_id}/vo/line_001/match",
        files={"file": ("take.wav", b"RIFF----WAVEfmt ", "audio/wav")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["path"].endswith("vo_pickup/matched/line_001.wav")
    assert called["dsp"] is True
    assert called["s2s"] is False
    assert (ctx.path("vo_pickup") / "line_001_upload.wav").is_file()


def test_vo_match_endpoint_fail_open_retains_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, ctx = _match_client(tmp_path, monkeypatch)

    def _boom(_ctx, _line, _src):
        raise RuntimeError("eq failed")

    monkeypatch.setattr("interview_mux.timbre_match.match_vo_take", _boom)
    s2s = MagicMock(side_effect=AssertionError("no s2s"))
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", s2s)

    res = client.post(
        f"/api/runs/{ctx.run_id}/vo/line_001/match",
        files={"file": ("take.wav", b"RIFF----WAVEfmt ", "audio/wav")},
    )
    assert res.status_code == 503
    upload = ctx.path("vo_pickup") / "line_001_upload.wav"
    assert upload.is_file()
    assert not (ctx.path("vo_pickup") / "matched" / "line_001.wav").is_file()
    s2s.assert_not_called()
