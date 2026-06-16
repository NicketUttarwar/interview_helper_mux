from __future__ import annotations

import json
import math
import wave
from pathlib import Path

from interview_mux.run_context import RunContext
from interview_mux.stages import understanding


def _write_test_wav(path: Path, *, sample_rate: int = 16000, duration_seconds: float = 1.0) -> None:
    n = int(sample_rate * duration_seconds)
    amp = 8000
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n):
            sample = int(amp * math.sin(2.0 * math.pi * 220.0 * (i / sample_rate)))
            frames += int(sample).to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(bytes(frames))


def test_prosody_summary_uses_spine_f0_bands(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("prosody_spine", create=True)
    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    _write_test_wav(wav)

    ctx.write_json(
        "transcript/full.json",
        {
            "text": "sample",
            "words": [{"text": "sample", "start_ms": 0, "end_ms": 800, "speaker_id": "spk_0"}],
        },
    )
    spine_path = ctx.path("understanding", "interview_spine.json")
    spine_path.parent.mkdir(parents=True, exist_ok=True)
    spine_path.write_text(
        json.dumps(
            {
                "windows": [
                    {"features": {"f0_median_hz": 90}},
                    {"features": {"f0_median_hz": 110}},
                    {"features": {"f0_median_hz": 95}},
                ]
            }
        ),
        encoding="utf-8",
    )

    understanding.run_source_acoustic_profile(ctx)
    profile = ctx.read_json("understanding/source_acoustic_profile.json")
    prosody = profile["prosody_summary"]
    assert prosody["f0_band"] == "low"
    assert prosody["f0_variability"] in ("low", "moderate", "high")
