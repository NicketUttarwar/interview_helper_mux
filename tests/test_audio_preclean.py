from __future__ import annotations

import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages import audio_preclean


def _write_wav(path: Path, *, seconds: float = 0.1, sample_rate: int = 16000) -> None:
    frames = int(seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)


def test_audio_preclean_skips_when_not_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_700", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src)
    ctx.init_run_meta(str(src))

    out = audio_preclean.run_audio_preclean(ctx)
    assert out is None
    assert ctx.is_done("audio_preclean")
    assert ctx.artifact_exists("preclean/skip.json")
    assert not ctx.artifact_exists("preclean/isolated.wav")


def test_audio_preclean_runs_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_701", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src)
    ctx.init_run_meta(str(src))
    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {"enabled": True, "scope": "full_source"}
    ctx.write_json("run_meta.json", meta)

    def fake_enhance(input_path, output_path, **kwargs):
        output_path.write_bytes(input_path.read_bytes())

    monkeypatch.setattr(audio_preclean, "enhance_wav", fake_enhance)

    out = audio_preclean.run_audio_preclean(ctx)
    assert out == ctx.path("preclean", "isolated.wav")
    assert out.is_file()
    assert ctx.artifact_exists("preclean/lineage.json")
    provider = ctx.read_json("preclean/provider.json")
    assert provider["provider"] == "deepfilternet"


def test_audio_preclean_vo_pickup_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_703", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src)
    ctx.init_run_meta(str(src))
    pickup = ctx.path("vo_pickup", "line_001.wav")
    _write_wav(pickup)

    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {"enabled": True, "scope": "vo_pickup"}
    ctx.write_json("run_meta.json", meta)

    def fake_enhance(input_path, output_path, **kwargs):
        output_path.write_bytes(input_path.read_bytes())

    monkeypatch.setattr(audio_preclean, "enhance_wav", fake_enhance)

    out = audio_preclean.run_audio_preclean(ctx)
    assert out is None
    clean = ctx.path("vo_pickup", "clean", "line_001.wav")
    assert clean.is_file()
    lineage = ctx.read_json("preclean/lineage.json")
    assert lineage["scope"] == "vo_pickup"
    assert lineage["files"][0]["output_path"] == "vo_pickup/clean/line_001.wav"


def test_audio_preclean_chunk_path_for_oversized_wav(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_chunk", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src, seconds=2.0)
    assert src.stat().st_size > 500
    ctx.init_run_meta(str(src))

    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {"enabled": True, "scope": "full_source"}
    ctx.write_json("run_meta.json", meta)

    monkeypatch.setattr(audio_preclean, "_chunk_max_bytes", lambda: 500)

    def fake_enhance(input_path, output_path, **kwargs):
        output_path.write_bytes(input_path.read_bytes())

    monkeypatch.setattr(audio_preclean, "enhance_wav", fake_enhance)

    out = audio_preclean.run_audio_preclean(ctx)
    assert out == ctx.path("preclean", "isolated.wav")
    assert out.is_file()
    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "deepfilter_chunked_enhance" in log_text


def test_audio_preclean_raises_when_deepfilter_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_ff_fail", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src)
    ctx.init_run_meta(str(src))

    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {"enabled": True, "scope": "full_source"}
    ctx.write_json("run_meta.json", meta)

    monkeypatch.setattr(audio_preclean, "enhance_wav", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dfn down")))

    with pytest.raises(RuntimeError, match="dfn down"):
        audio_preclean.run_audio_preclean(ctx)
