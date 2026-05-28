from __future__ import annotations

import math
import wave
from pathlib import Path

from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.run_context import RunContext
from interview_mux.stages import understanding


def _write_test_wav(path: Path, *, sample_rate: int = 16000, duration_seconds: float = 1.2) -> None:
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


def test_analysis_order_places_source_acoustic_profile_after_transcript_review():
    review_idx = ANALYSIS_ORDER.index("transcript_review_build")
    sap_idx = ANALYSIS_ORDER.index("source_acoustic_profile")
    speaker_idx = ANALYSIS_ORDER.index("speaker_roles")
    palettes_idx = ANALYSIS_ORDER.index("sound_design_palettes")
    assert sap_idx == review_idx + 1
    assert speaker_idx == sap_idx + 1
    assert palettes_idx > sap_idx


def test_run_source_acoustic_profile_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_301", create=True)
    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    _write_test_wav(wav)

    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello world this is a quick interview sample",
            "words": [
                {"text": "hello", "start_ms": 0, "end_ms": 220, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 260, "end_ms": 450, "speaker_id": "spk_0"},
                {"text": "this", "start_ms": 800, "end_ms": 980, "speaker_id": "spk_1"},
                {"text": "is", "start_ms": 1010, "end_ms": 1100, "speaker_id": "spk_1"},
                {"text": "a", "start_ms": 1120, "end_ms": 1180, "speaker_id": "spk_1"},
                {"text": "quick", "start_ms": 1300, "end_ms": 1520, "speaker_id": "spk_0"},
                {"text": "interview", "start_ms": 1680, "end_ms": 1950, "speaker_id": "spk_0"},
                {"text": "sample", "start_ms": 2100, "end_ms": 2350, "speaker_id": "spk_0"},
            ],
            "segments": [
                {"speaker_label": "spk_0", "start_time": "0.0", "end_time": "1.2"},
                {"speaker_label": "spk_1", "start_time": "1.1", "end_time": "1.8"},
            ],
        },
    )

    understanding.run_source_acoustic_profile(ctx)

    out = ctx.read_json("understanding/source_acoustic_profile.json")
    assert out["derived_from"]["stage"] == "source_acoustic_profile"
    assert out["pacing"]["global_wpm"] > 0
    assert len(out["pacing"]["wpm_by_quartile"]) == 4
    assert out["energy"]["dynamic_range_db"] >= 0
    assert "bed_level_db_range" in out["mix_contract"]
    assert ctx.is_done("source_acoustic_profile")
