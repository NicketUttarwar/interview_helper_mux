"""Reject pure-tone / non-speech WAV stubs masquerading as host VO pickups."""

from __future__ import annotations

import math
import re
import struct
import wave
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config

FORBIDDEN_VO_BACKENDS = frozenset({"tone_stub", "sine_stub", "music_stub", "musical_stub"})

# Path+mtime+size+cfg fingerprint → analyze_vo_wav row. Hot path: G1 /
# resolve_vo_pickup_path / remaining_stages re-enter this dozens of times per
# heal (forensics exec_13198: unpaid_land(mix) burned ~12s in pure-Python DFT).
_ANALYZE_CACHE: dict[tuple[str, int, int, str], dict[str, Any]] = {}
_ANALYZE_CACHE_MAX = 256


def _analyze_cache_key(path: Path, cfg: dict[str, Any], script_text: str | None) -> tuple[str, int, int, str] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    # Stable cfg subset that affects metrics / pass-fail.
    cfg_fp = (
        f"{cfg.get('enabled')}|{cfg.get('speech_qa_enabled')}|"
        f"{cfg.get('max_tonal_peak_ratio')}|{cfg.get('min_speech_band_ratio')}|"
        f"{cfg.get('min_envelope_cv')}|{cfg.get('min_duration_ms')}|"
        f"{cfg.get('max_ms_per_word')}|{cfg.get('min_ms_per_word')}|"
        f"{cfg.get('min_words_for_duration_check')}|{(script_text or '')[:200]}"
    )
    return (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size), cfg_fp)


def clear_vo_speech_qa_cache() -> None:
    """Test / heal helper — drop analyze cache."""
    _ANALYZE_CACHE.clear()


def vo_speech_qa_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = ((cfg or merged_config()).get("analysis") or {}).get("gap_vo") or {}
    raw = block.get("post_synthesis_qc") or {}
    defaults = {
        "enabled": True,
        "speech_qa_enabled": True,
        "max_tonal_peak_ratio": 0.58,
        "min_speech_band_ratio": 0.12,
        "min_envelope_cv": 0.18,
        "min_duration_ms": 400,
        "max_ms_per_word": 800,
        "min_ms_per_word": 120,
        "min_words_for_duration_check": 8,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def _read_mono_floats(path: Path) -> tuple[list[float], int]:
    try:
        with wave.open(str(path), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        if sample_width != 2:
            raise ValueError(f"unsupported sample width {sample_width}")
        count = len(raw) // 2
        samples = struct.unpack(f"<{count}h", raw)
        if n_channels > 1:
            samples = [samples[i] for i in range(0, count, n_channels)]
        return [s / 32768.0 for s in samples], rate
    except Exception:
        # Float32 / odd encodings from Chatterbox — decode via ffmpeg.
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(path),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(tmp_path),
                ],
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0 or not tmp_path.is_file():
                raise ValueError(f"ffmpeg decode failed for {path.name}")
            return _read_mono_floats(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _envelope_cv(samples: list[float], rate: int, *, window_ms: int = 40) -> float:
    """Coefficient of variation of short-window RMS — speech modulates; tones don't."""
    if not samples or rate <= 0:
        return 0.0
    window = max(1, int(rate * window_ms / 1000))
    if len(samples) < window * 4:
        return 0.0
    vals: list[float] = []
    for i in range(0, len(samples) - window, window):
        vals.append(_rms(samples[i : i + window]))
    if not vals:
        return 0.0
    mean = sum(vals) / len(vals)
    if mean < 1e-6:
        return 0.0
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return math.sqrt(var) / mean


def _speech_band_ratio(samples: list[float], rate: int) -> float:
    """Proxy speech-band energy via zero-crossing frequency windows (300–3400 Hz)."""
    if not samples or rate <= 0:
        return 0.0
    total = _rms(samples)
    if total < 1e-6:
        return 0.0
    band: list[float] = []
    window = max(1, int(rate / 200))
    for i in range(0, len(samples) - window, window):
        chunk = samples[i : i + window]
        zc = sum(1 for a, b in zip(chunk, chunk[1:]) if a * b < 0)
        freq_est = zc * rate / (2 * len(chunk))
        if 300.0 <= freq_est <= 3400.0:
            band.extend(chunk)
    if not band:
        return 0.0
    return _rms(band) / total


def _tonal_peak_ratio(samples: list[float], rate: int) -> float:
    """Fraction of spectral energy in the single strongest FFT bin (pure-tone proxy)."""
    if not samples or rate <= 0:
        return 0.0
    # Use a mid slice for stability; downsample to ~4 kHz analysis rate.
    mid = samples[len(samples) // 4 : 3 * len(samples) // 4] or samples
    step = max(1, rate // 4000)
    down = mid[::step]
    n = len(down)
    # Power-of-two window ≤ 2048
    nfft = 1
    while nfft * 2 <= min(n, 2048):
        nfft *= 2
    if nfft < 64:
        return 0.0
    chunk = down[:nfft]
    # Vectorized rFFT (numpy is a runtime dep) — pure-Python DFT was ~0.5–1s/clip
    # and dominated remaining_stages / unpaid_land(mix) heals (exec_13198).
    try:
        import numpy as np

        arr = np.asarray(chunk, dtype=np.float64)
        window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(nfft) / max(1, nfft - 1))
        windowed = arr * window
        spec = np.fft.rfft(windowed)
        mags = (spec.real * spec.real + spec.imag * spec.imag)[1:]  # skip DC
        total = float(mags.sum()) if mags.size else 0.0
        if total < 1e-12:
            return 0.0
        return float(mags.max() / total)
    except Exception:
        pass
    # Hann window
    windowed = [
        chunk[i] * (0.5 - 0.5 * math.cos(2 * math.pi * i / max(1, nfft - 1))) for i in range(nfft)
    ]
    # Real DFT magnitudes (skip DC)
    mags: list[float] = []
    half = nfft // 2
    for k in range(1, half):
        re = 0.0
        im = 0.0
        for i, x in enumerate(windowed):
            ang = 2 * math.pi * k * i / nfft
            re += x * math.cos(ang)
            im -= x * math.sin(ang)
        mags.append(re * re + im * im)
    total = sum(mags)
    if total < 1e-12:
        return 0.0
    return max(mags) / total


def analyze_vo_wav(
    path: Path,
    *,
    cfg: dict[str, Any] | None = None,
    script_text: str | None = None,
) -> dict[str, Any]:
    """Return speech-QA metrics and pass/fail for a VO pickup WAV."""
    qc = cfg or vo_speech_qa_cfg()
    cache_key = _analyze_cache_key(Path(path), qc, script_text)
    if cache_key is not None:
        hit = _ANALYZE_CACHE.get(cache_key)
        if hit is not None:
            return dict(hit)
    row: dict[str, Any] = {
        "path": str(path),
        "pass": False,
        "reasons": [],
        "tonal_peak_ratio": None,
        "speech_band_ratio": None,
        "envelope_cv": None,
        "duration_ms": 0,
    }
    if not path.is_file():
        row["reasons"].append("missing_file")
        return row
    try:
        samples, rate = _read_mono_floats(path)
    except Exception as exc:
        row["reasons"].append(f"unreadable_wav:{exc}")
        return row
    if not samples or rate <= 0:
        row["reasons"].append("empty_wav")
        return row
    duration_ms = int(1000 * len(samples) / rate)
    row["duration_ms"] = duration_ms
    min_ms = int(qc.get("min_duration_ms", 400))
    if duration_ms < min_ms:
        row["reasons"].append(f"too_short:{duration_ms}ms")
        return row
    if _rms(samples) < 1e-5:
        row["reasons"].append("near_silence")
        return row

    tonal = _tonal_peak_ratio(samples, rate)
    speech = _speech_band_ratio(samples, rate)
    env_cv = _envelope_cv(samples, rate)
    row["tonal_peak_ratio"] = round(tonal, 4)
    row["speech_band_ratio"] = round(speech, 4)
    row["envelope_cv"] = round(env_cv, 4)

    max_tonal = float(qc.get("max_tonal_peak_ratio", 0.58))
    min_speech = float(qc.get("min_speech_band_ratio", 0.12))
    min_cv = float(qc.get("min_envelope_cv", 0.18))

    if tonal >= max_tonal and env_cv < min_cv:
        row["reasons"].append("pure_tone_detected")
    if speech < min_speech and tonal >= max_tonal * 0.85:
        row["reasons"].append("non_speech_spectrum")
    if env_cv < min_cv * 0.5 and tonal >= 0.4:
        row["reasons"].append("flat_envelope_tone")

    words = len(re.findall(r"\S+", str(script_text or "")))
    min_words = int(qc.get("min_words_for_duration_check", 8))
    if words >= min_words and duration_ms > 0:
        max_ppw = float(qc.get("max_ms_per_word", 800))
        min_ppw = float(qc.get("min_ms_per_word", 120))
        ms_per_word = duration_ms / words
        if ms_per_word > max_ppw or ms_per_word < min_ppw:
            row["reasons"].append(
                f"duration_vs_word_count:{duration_ms}ms for {words} words"
            )

    row["pass"] = not row["reasons"]
    if cache_key is not None:
        if len(_ANALYZE_CACHE) >= _ANALYZE_CACHE_MAX:
            # Drop an arbitrary oldest-ish entry (FIFO-ish via next(iter)).
            try:
                del _ANALYZE_CACHE[next(iter(_ANALYZE_CACHE))]
            except Exception:
                _ANALYZE_CACHE.clear()
        _ANALYZE_CACHE[cache_key] = dict(row)
    return row


def vo_passes_speech_qa(path: Path, *, cfg: dict[str, Any] | None = None) -> bool:
    qc = cfg or vo_speech_qa_cfg()
    if not qc.get("enabled", True) or not qc.get("speech_qa_enabled", True):
        return True
    return bool(analyze_vo_wav(path, cfg=qc).get("pass"))


def backend_allowed_for_vo(backend: str | None) -> bool:
    return str(backend or "").strip().lower() not in FORBIDDEN_VO_BACKENDS
