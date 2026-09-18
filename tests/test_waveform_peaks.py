"""ING-B3: ingest owns waveform_peaks; GUI load path never persists."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from interview_mux.run_context import RunContext
from interview_mux.waveform_peaks import (
    PEAKS_REL,
    load_or_generate_peaks,
    persist_normalized_peaks,
)


def _write_silence_wav(path: Path, *, seconds: float = 0.5, rate: int = 48000) -> None:
    n = int(rate * seconds)
    pcm = np.zeros(n, dtype=np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())


@pytest.fixture
def peaks_ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_EXECUTIONS_ROOT", str(tmp_path / "executions"))
    ctx = RunContext("exec_test_waveform_peaks", create=True)
    wav = tmp_path / "input.wav"
    _write_silence_wav(wav)
    ctx.init_run_meta(str(wav), source_audio_hash="b" * 64)
    norm = ctx.path("ingest", "normalized.wav")
    _write_silence_wav(norm)
    return ctx


def test_persist_normalized_peaks_writes_cache(peaks_ctx):
    ctx = peaks_ctx
    payload = persist_normalized_peaks(ctx)
    assert payload["source_path"] == "ingest/normalized.wav"
    assert ctx.artifact_exists(PEAKS_REL) or ctx.path(PEAKS_REL).is_file() or (
        ctx.read_path(PEAKS_REL).is_file()
    )
    # Prefer final or staged path readability via load
    loaded = load_or_generate_peaks(ctx, "ingest/normalized.wav")
    assert loaded["source_fingerprint"] == payload["source_fingerprint"]
    assert isinstance(loaded.get("peaks"), list)


def test_load_or_generate_peaks_does_not_write(peaks_ctx, monkeypatch):
    ctx = peaks_ctx
    writes: list[str] = []

    def _deny_write(rel, data, **kwargs):
        writes.append(rel)
        raise AssertionError(f"GUI path must not write {rel}")

    monkeypatch.setattr(ctx, "write_json", _deny_write)
    # No cache yet — ephemeral generate still OK
    out = load_or_generate_peaks(ctx, "ingest/normalized.wav")
    assert out["peaks"]
    assert writes == []
    assert not ctx.read_path(PEAKS_REL).is_file()
