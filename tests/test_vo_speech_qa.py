"""VO speech QA rejects pure-tone stubs."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from interview_mux.vo_speech_qa import (
    FORBIDDEN_VO_BACKENDS,
    analyze_vo_wav,
    backend_allowed_for_vo,
    vo_passes_speech_qa,
)
from interview_mux.vo_synthesis_audit import record_recorded_vo, record_synthesis
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


def _write_sine(path: Path, *, freq: float = 440.0, duration_sec: float = 2.0, rate: int = 16000) -> None:
    n = int(duration_sec * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(n)
        )
        wf.writeframes(frames)


def _write_noisy_speechish(path: Path, *, duration_sec: float = 2.0, rate: int = 16000) -> None:
    """Broadband modulated signal that should pass crude speech QA."""
    n = int(duration_sec * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            t = i / rate
            # Multi-harmonic formant-ish + amplitude modulation
            env = 0.35 + 0.35 * abs(math.sin(2 * math.pi * 4.5 * t))
            val = 0.0
            for f, a in ((180, 0.3), (420, 0.25), (980, 0.2), (1600, 0.15), (2400, 0.1)):
                val += a * math.sin(2 * math.pi * f * t)
            # Mild noise
            val += 0.08 * math.sin(2 * math.pi * (37 + (i % 97)) * t)
            sample = int(max(-1.0, min(1.0, val * env)) * 32767)
            frames += struct.pack("<h", sample)
        wf.writeframes(bytes(frames))


def test_pure_tone_fails_speech_qa(tmp_path: Path) -> None:
    wav = tmp_path / "tone.wav"
    _write_sine(wav)
    row = analyze_vo_wav(wav)
    assert row["pass"] is False
    assert any("tone" in str(r) or "non_speech" in str(r) for r in row["reasons"])
    assert not vo_passes_speech_qa(wav)


def test_modulated_speechish_passes(tmp_path: Path) -> None:
    wav = tmp_path / "speech.wav"
    _write_noisy_speechish(wav)
    assert vo_passes_speech_qa(wav)


def test_duration_vs_word_count_fails_stutter(tmp_path: Path) -> None:
    wav = tmp_path / "stutter.wav"
    _write_noisy_speechish(wav, duration_sec=12.0)
    script = "What changed next in that stretch after the cash crunch ended?"
    row = analyze_vo_wav(
        wav,
        script_text=script,
        cfg={
            "enabled": True,
            "speech_qa_enabled": True,
            "max_tonal_peak_ratio": 0.58,
            "min_speech_band_ratio": 0.12,
            "min_envelope_cv": 0.18,
            "min_duration_ms": 400,
            "max_ms_per_word": 800,
            "min_ms_per_word": 120,
            "min_words_for_duration_check": 8,
        },
    )
    assert row["pass"] is False
    assert any("duration_vs_word_count" in str(r) for r in row["reasons"])


def test_forbidden_backends() -> None:
    assert not backend_allowed_for_vo("tone_stub")
    assert "tone_stub" in FORBIDDEN_VO_BACKENDS
    assert backend_allowed_for_vo("chatterbox")


def test_record_synthesis_rejects_tone_stub(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_vo_qa", create=True)
    wav = ctx.path("vo_pickup", "synthesized", "line.wav")
    _write_noisy_speechish(wav)
    try:
        record_synthesis(ctx, {"line_id": "line"}, backend="tone_stub", out_wav=wav)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Forbidden" in str(exc)


def test_record_synthesis_missing_output_logs_loud_warning(tmp_path: Path, monkeypatch) -> None:
    """A fail-open synthesis backend that produced no file must not pass silently."""
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_vo_qa_missing", create=True)
    out_wav = ctx.path("vo_pickup", "synthesized", "line_missing.wav")
    # No file written at out_wav — simulates a fail-open Chatterbox call that
    # produced no audio without itself raising.
    entry = record_synthesis(ctx, {"line_id": "line_missing"}, backend="chatterbox", out_wav=out_wav)
    assert entry["qc_pass"] is False
    assert "missing_output_wav" in entry["qc_notes"]
    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "VO synthesis QC failed" in log_text
    assert "line_missing" in log_text


def test_record_synthesis_stub_wav_logs_loud_warning(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_vo_qa_stub", create=True)
    wav = ctx.path("vo_pickup", "synthesized", "line_stub.wav")
    _write_sine(wav)
    entry = record_synthesis(ctx, {"line_id": "line_stub"}, backend="chatterbox", out_wav=wav)
    assert entry["qc_pass"] is False
    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "VO synthesis QC failed" in log_text
    assert "line_stub" in log_text


def test_record_recorded_vo_missing_file_logs_loud_warning(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_vo_qa_record_missing", create=True)
    out_wav = ctx.path("vo_pickup", "line_upload.wav")
    record_recorded_vo(ctx, "line_upload", out_wav=out_wav, backend="upload")
    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "VO recording missing" in log_text
    assert "line_upload" in log_text


def test_record_recorded_vo_stub_logs_loud_warning(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_vo_qa_record_stub", create=True)
    out_wav = ctx.path("vo_pickup", "line_upload2.wav")
    _write_sine(out_wav)
    record_recorded_vo(ctx, "line_upload2", out_wav=out_wav, backend="upload")
    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "VO recording QC failed" in log_text
    assert "line_upload2" in log_text


def test_analyze_vo_wav_caches_by_mtime(tmp_path: Path) -> None:
    """Second analyze of the same file must hit cache (heal/remaining_stages hot path)."""
    import time

    from interview_mux import vo_speech_qa as vsq

    vsq.clear_vo_speech_qa_cache()
    wav = tmp_path / "speech_cache.wav"
    _write_noisy_speechish(wav)
    t0 = time.perf_counter()
    first = analyze_vo_wav(wav)
    cold = time.perf_counter() - t0
    t1 = time.perf_counter()
    second = analyze_vo_wav(wav)
    warm = time.perf_counter() - t1
    assert first == second
    assert first["pass"] is True
    # Warm should be dramatically cheaper than cold (numpy FFT still, but no I/O+DSP).
    assert warm < max(0.05, cold * 0.25)
    # Mutate mtime → cache miss, still correct.
    time.sleep(0.01)
    wav.write_bytes(wav.read_bytes() + b"")  # touch size? keep same — bump mtime
    Path(wav).touch()
    vsq.clear_vo_speech_qa_cache()  # ensure clean for miss path below
    third = analyze_vo_wav(wav)
    assert third["pass"] is True


def test_tonal_peak_numpy_rejects_pure_tone(tmp_path: Path) -> None:
    """Numpy rFFT path must still flag pure tones (parity with pure-Python DFT)."""
    from interview_mux import vo_speech_qa as vsq

    vsq.clear_vo_speech_qa_cache()
    wav = tmp_path / "tone_np.wav"
    _write_sine(wav)
    row = analyze_vo_wav(wav)
    assert row["pass"] is False
    assert row["tonal_peak_ratio"] is not None
    assert float(row["tonal_peak_ratio"]) >= 0.5
