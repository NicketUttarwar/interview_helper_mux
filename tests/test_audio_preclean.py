from __future__ import annotations

import wave
from pathlib import Path

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

    monkeypatch.setattr(audio_preclean, "require_secret", lambda _: "test-key")
    monkeypatch.setattr(audio_preclean, "isolate_audio", lambda **_: src.read_bytes())

    out = audio_preclean.run_audio_preclean(ctx)
    assert out == ctx.path("preclean", "isolated.wav")
    assert out.is_file()
    assert ctx.artifact_exists("preclean/lineage.json")
    assert ctx.artifact_exists("preclean/provider.json")
