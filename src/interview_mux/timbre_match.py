"""Deterministic DSP timbre match for operator VO against a speaker reference.

Preserves the upload waveform/performance. Derives a smoothed long-term
spectral correction curve (numpy + soundfile), clamps gains, applies via
FFmpeg firequalizer, then loudness-matches to the reference. No scipy and
no ML voice conversion.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.operator_subprocess import run_command
from interview_mux.run_context import RunContext

PROVIDER = "dsp_firequalizer"
QA_REL = "vo_pickup/timbre_match_qa.json"
TARGET_SR = 48_000
DEFAULT_MAX_EQ_DB = 6.0
# Log-spaced EQ control points covering speech band.
DEFAULT_FREQS_HZ = (
    80.0,
    125.0,
    200.0,
    315.0,
    500.0,
    800.0,
    1250.0,
    2000.0,
    3150.0,
    5000.0,
    8000.0,
    12000.0,
)


def timbre_match_settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = gap_vo_cfg(cfg).get("timbre_match") or {}
    if not isinstance(block, dict):
        block = {}
    return {
        "enabled": bool(block.get("enabled", True)),
        "max_eq_db": float(block.get("max_eq_db", DEFAULT_MAX_EQ_DB)),
    }


def _to_mono(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        return arr
    return np.mean(arr, axis=1)


def _load_mono(path: Path) -> tuple[np.ndarray, int]:
    data, rate = sf.read(str(path), always_2d=False, dtype="float64")
    return _to_mono(data), int(rate)


def long_term_average_spectrum(
    samples: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 4096,
    hop: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (freqs_hz, power_db) long-term average spectrum."""
    if samples.size == 0 or sample_rate <= 0:
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / max(sample_rate, 1))
        return freqs, np.full(freqs.shape, -120.0, dtype=np.float64)
    hop = hop or n_fft // 2
    window = np.hanning(n_fft).astype(np.float64)
    if samples.size < n_fft:
        pad = np.zeros(n_fft, dtype=np.float64)
        pad[: samples.size] = samples
        frames = pad[None, :]
    else:
        n_frames = 1 + (samples.size - n_fft) // hop
        frames = np.lib.stride_tricks.as_strided(
            samples,
            shape=(n_frames, n_fft),
            strides=(samples.strides[0] * hop, samples.strides[0]),
            writeable=False,
        )
    windowed = frames * window
    spec = np.fft.rfft(windowed, axis=1)
    power = np.mean(np.abs(spec) ** 2, axis=0)
    power = np.maximum(power, 1e-20)
    power_db = 10.0 * np.log10(power)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    return freqs, power_db


def _interp_db(freqs: np.ndarray, power_db: np.ndarray, targets: np.ndarray) -> np.ndarray:
    return np.interp(targets, freqs, power_db, left=power_db[0], right=power_db[-1])


def _smooth(values: np.ndarray, radius: int = 1) -> np.ndarray:
    if values.size == 0 or radius <= 0:
        return values
    kernel = np.ones(2 * radius + 1, dtype=np.float64)
    kernel /= kernel.sum()
    padded = np.pad(values, (radius, radius), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def correction_curve_db(
    reference: Path,
    source: Path,
    *,
    max_eq_db: float = DEFAULT_MAX_EQ_DB,
    freqs_hz: tuple[float, ...] = DEFAULT_FREQS_HZ,
) -> list[tuple[float, float]]:
    """Smoothed LTAS correction (ref − source), clamped to ±max_eq_db."""
    ref_samples, ref_sr = _load_mono(reference)
    src_samples, src_sr = _load_mono(source)
    ref_f, ref_db = long_term_average_spectrum(ref_samples, ref_sr)
    src_f, src_db = long_term_average_spectrum(src_samples, src_sr)
    targets = np.asarray(freqs_hz, dtype=np.float64)
    # Only use bands below Nyquist of both signals.
    nyquist = 0.45 * float(min(ref_sr, src_sr))
    usable = targets[targets < nyquist]
    if usable.size == 0:
        usable = np.asarray([min(targets[0], nyquist * 0.5)], dtype=np.float64)
    delta = _interp_db(ref_f, ref_db, usable) - _interp_db(src_f, src_db, usable)
    delta = _smooth(delta, radius=1)
    limit = abs(float(max_eq_db))
    delta = np.clip(delta, -limit, limit)
    return [(float(f), float(g)) for f, g in zip(usable, delta)]


def format_gain_entry(curve: list[tuple[float, float]]) -> str:
    """FFmpeg firequalizer gain_entry body: entry(freq,gain); ..."""
    parts: list[str] = []
    for freq, gain in curve:
        parts.append(f"entry({freq:.6g},{gain:.4f})")
    return "; ".join(parts)


def build_firequalizer_filter(
    curve: list[tuple[float, float]],
    *,
    loudness_gain_db: float = 0.0,
) -> str:
    entry = format_gain_entry(curve)
    # Quotes keep commas inside gain_entry from splitting the filtergraph.
    parts = [f"firequalizer=gain_entry='{entry}':scale=linlog"]
    if abs(loudness_gain_db) >= 0.01:
        parts.append(f"volume={loudness_gain_db:.3f}dB")
    parts.append("aformat=sample_fmts=s16:channel_layouts=mono:sample_rates=48000")
    return ",".join(parts)


def _integrated_lufs(path: Path) -> float | None:
    try:
        from interview_mux.mastering_bus import measure_assembly_bus

        return float(measure_assembly_bus(path).integrated_lufs)
    except Exception:
        return None


def _rms_db(path: Path) -> float:
    samples, _ = _load_mono(path)
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    return 20.0 * math.log10(max(rms, 1e-8))


def loudness_match_gain_db(source: Path, reference: Path) -> float:
    """Gain (dB) to apply to source so its loudness matches reference."""
    src_lufs = _integrated_lufs(source)
    ref_lufs = _integrated_lufs(reference)
    if src_lufs is not None and ref_lufs is not None and math.isfinite(src_lufs) and math.isfinite(ref_lufs):
        return float(ref_lufs - src_lufs)
    return float(_rms_db(reference) - _rms_db(source))


def build_match_command(
    source: Path,
    destination: Path,
    *,
    curve: list[tuple[float, float]],
    loudness_gain_db: float = 0.0,
) -> list[str]:
    af = build_firequalizer_filter(curve, loudness_gain_db=loudness_gain_db)
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-af",
        af,
        "-ac",
        "1",
        "-ar",
        str(TARGET_SR),
        "-c:a",
        "pcm_s16le",
        str(destination),
    ]


def _rel(ctx: RunContext, path: Path) -> str:
    try:
        return path.relative_to(ctx.run_dir).as_posix()
    except ValueError:
        return path.as_posix()


def append_timbre_match_qa(
    ctx: RunContext,
    *,
    line_id: str,
    input_path: Path,
    reference_path: Path,
    output_path: Path | None,
    settings: dict[str, Any],
    ok: bool,
    error: str | None = None,
) -> None:
    rows: list[dict[str, Any]] = []
    if ctx.artifact_exists(QA_REL):
        existing = ctx.read_json(QA_REL)
        if isinstance(existing, list):
            rows = list(existing)
        elif isinstance(existing, dict):
            rows = list(existing.get("entries") or [])
    rows.append(
        {
            "line_id": line_id,
            "provider": PROVIDER,
            "settings": settings,
            "input": _rel(ctx, input_path),
            "reference": _rel(ctx, reference_path),
            "output": _rel(ctx, output_path) if output_path else None,
            "ok": ok,
            "error": error,
        }
    )
    ctx.write_json(QA_REL, {"entries": rows})


def apply_timbre_match(
    source: Path,
    reference: Path,
    destination: Path,
    *,
    max_eq_db: float = DEFAULT_MAX_EQ_DB,
) -> dict[str, Any]:
    """Match source timbre/loudness to reference; write 48 kHz mono PCM16."""
    if not source.is_file():
        raise FileNotFoundError(f"Missing source audio: {source}")
    if not reference.is_file():
        raise FileNotFoundError(f"Missing reference audio: {reference}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    curve = correction_curve_db(reference, source, max_eq_db=max_eq_db)
    # First pass EQ only, then measure loudness on EQ'd audio for accurate gain.
    tmp = destination.with_suffix(".eq_tmp.wav")
    try:
        eq_cmd = build_match_command(source, tmp, curve=curve, loudness_gain_db=0.0)
        run_command(eq_cmd, label=f"timbre_match firequalizer {destination.name}")
        gain_db = loudness_match_gain_db(tmp, reference)
        # Clamp loudness correction modestly so we never invent extreme boosts.
        gain_db = float(np.clip(gain_db, -12.0, 12.0))
        final_cmd = build_match_command(source, destination, curve=curve, loudness_gain_db=gain_db)
        run_command(final_cmd, label=f"timbre_match render {destination.name}")
    finally:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
    if not destination.is_file():
        raise RuntimeError(f"timbre match produced no output: {destination}")
    return {
        "curve": [{"freq_hz": f, "gain_db": g} for f, g in curve],
        "loudness_gain_db": gain_db,
        "max_eq_db": float(max_eq_db),
        "sample_rate": TARGET_SR,
        "provider": PROVIDER,
        "command_af": build_firequalizer_filter(curve, loudness_gain_db=gain_db),
    }


def match_vo_take(
    ctx: RunContext,
    line: dict[str, Any],
    source_audio: Path,
) -> Path:
    """Write DSP-matched take to vo_pickup/matched/{line_id}.wav + QA sidecar."""
    from interview_mux.s2s_runner import resolve_reference_audio

    settings = timbre_match_settings()
    line_id = str(line.get("line_id") or line.get("targets_segment_id") or "line")
    ref = resolve_reference_audio(ctx, line)
    out_dir = ctx.path("vo_pickup", "matched")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"{line_id}.wav"

    if not settings["enabled"]:
        # Passthrough: still preserve performance into matched/ without inventing audio.
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_audio),
            "-ac",
            "1",
            "-ar",
            str(TARGET_SR),
            "-c:a",
            "pcm_s16le",
            str(out_wav),
        ]
        run_command(cmd, label=f"timbre_match passthrough {line_id}")
        append_timbre_match_qa(
            ctx,
            line_id=line_id,
            input_path=source_audio,
            reference_path=ref,
            output_path=out_wav,
            settings={**settings, "passthrough": True},
            ok=True,
        )
        return out_wav

    try:
        meta = apply_timbre_match(
            source_audio,
            ref,
            out_wav,
            max_eq_db=float(settings["max_eq_db"]),
        )
    except Exception as exc:
        append_timbre_match_qa(
            ctx,
            line_id=line_id,
            input_path=source_audio,
            reference_path=ref,
            output_path=None,
            settings=settings,
            ok=False,
            error=str(exc)[:500],
        )
        raise

    append_timbre_match_qa(
        ctx,
        line_id=line_id,
        input_path=source_audio,
        reference_path=ref,
        output_path=out_wav,
        settings={**settings, **{k: meta[k] for k in ("loudness_gain_db", "max_eq_db", "sample_rate", "curve")}},
        ok=True,
    )
    return out_wav
