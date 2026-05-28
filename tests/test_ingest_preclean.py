from __future__ import annotations

import wave
from pathlib import Path

from interview_mux.run_context import RunContext
from interview_mux.stages import ingest


def _write_wav(path: Path, *, seconds: float = 0.1, sample_rate: int = 16000) -> None:
    frames = int(seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)


def test_ingest_source_prefers_preclean_isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_702", create=True)
    raw = tmp_path / "input.wav"
    _write_wav(raw)
    ctx.init_run_meta(str(raw))

    isolated = ctx.path("preclean", "isolated.wav")
    _write_wav(isolated, sample_rate=48000)

    src, preclean = ingest._ingest_source(ctx)
    assert src == isolated
    assert preclean == isolated
