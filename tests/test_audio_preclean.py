from __future__ import annotations

import uuid
import wave
from pathlib import Path

import pytest

from interview_mux.deepfilter_runner import DeepFilterUnavailable
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
    from run_fixtures import mark_done_raw, patch_executions_root, patch_merged_config

    patch_executions_root(monkeypatch, tmp_path)
    patch_merged_config(
        monkeypatch,
        {
            "audio_preclean": {
                "enabled": False,
                "auto_run_before_ingest": False,
                "default_action": "skip",
            },
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
        },
    )
    ctx = RunContext("run_700_preclean_off", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src)
    ctx.init_run_meta(str(src))

    out = audio_preclean.run_audio_preclean(ctx)
    assert out is None
    assert ctx.artifact_exists("preclean/skip.json")
    mark_done_raw(ctx, "audio_preclean")
    assert ctx.is_done("audio_preclean")
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
    run_id = f"run_chunk_{uuid.uuid4().hex[:12]}"
    ctx = RunContext(run_id, create=True)
    src = tmp_path / "input.wav"
    _write_wav(src, seconds=2.0)
    assert src.stat().st_size > 500
    ctx.init_run_meta(str(src))

    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {"enabled": True, "scope": "full_source"}
    ctx.write_json("run_meta.json", meta)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "audio_preclean",
            "current_stage": "audio_preclean",
            "message": "Running Audio pre-clean… (1/1)",
        },
    )

    monkeypatch.setattr(audio_preclean, "_chunk_max_bytes", lambda: 500)

    def fake_chunk(source, max_bytes, *, work_dir, **kwargs):
        work_dir.mkdir(parents=True, exist_ok=True)
        chunks = []
        for i in range(3):
            chunk = work_dir / f"chunk_{i:03d}.wav"
            chunk.write_bytes(source.read_bytes())
            chunks.append(chunk)
        return chunks

    monkeypatch.setattr(
        "interview_mux.audio_timeline.chunk_wav_by_max_bytes",
        fake_chunk,
    )

    def fake_enhance(input_path, output_path, **kwargs):
        output_path.write_bytes(input_path.read_bytes())

    def fake_enhance_batch(pairs, **kwargs):
        for input_path, output_path in pairs:
            output_path.write_bytes(input_path.read_bytes())

    monkeypatch.setattr(audio_preclean, "enhance_wav_batch", fake_enhance_batch)

    out = audio_preclean.run_audio_preclean(ctx)
    assert out == ctx.path("preclean", "isolated.wav")
    assert out.is_file()
    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "Enhancing 3 chunk(s) with DeepFilterNet" in log_text
    job = ctx.read_json("gui_job.json")
    assert job.get("step_total", 0) >= 2
    assert job.get("step_index", 0) >= 2
    assert "chunk" in str(job.get("message", "")).lower()
    assert (ctx.run_dir / "_preclean_work").is_dir()


def test_audio_preclean_falls_back_when_deepfilter_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_ff_fail", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src)
    ctx.init_run_meta(str(src))

    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {"enabled": True, "scope": "full_source"}
    ctx.write_json("run_meta.json", meta)

    monkeypatch.setattr(
        audio_preclean,
        "enhance_wav",
        lambda *a, **k: (_ for _ in ()).throw(DeepFilterUnavailable("dfn down")),
    )
    monkeypatch.setattr(
        "interview_mux.ffmpeg_denoise.denoise_wav",
        lambda source, output, **kwargs: output.write_bytes(source.read_bytes()),
    )

    out = audio_preclean.run_audio_preclean(ctx)

    assert out is not None and out.is_file()
    assert ctx.read_json("preclean/provider.json")["provider"] == "ffmpeg_local"
    assert ctx.read_json("preclean/lineage.json")["provider"] == "ffmpeg_local"


def test_audio_preclean_raises_when_fallback_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_ff_disabled", create=True)
    src = tmp_path / "input.wav"
    _write_wav(src)
    ctx.init_run_meta(str(src))
    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {"enabled": True, "scope": "full_source"}
    ctx.write_json("run_meta.json", meta)
    monkeypatch.setattr(
        audio_preclean,
        "enhance_wav",
        lambda *a, **k: (_ for _ in ()).throw(DeepFilterUnavailable("dfn down")),
    )
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {
            "audio_preclean": {
                "local_fallback_enabled": False,
                "chunk_max_bytes": 52_428_800,
            }
        },
    )

    with pytest.raises(DeepFilterUnavailable, match="dfn down"):
        audio_preclean.run_audio_preclean(ctx)
