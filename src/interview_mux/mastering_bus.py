from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pyloudnorm as pyln
import soundfile as sf

from interview_mux.master_qc import FlowName, TARGETS


@dataclass(frozen=True)
class AssemblyBusMetrics:
    integrated_lufs: float
    sample_rate_hz: int
    channels: int
    duration_seconds: float


_BLOCK_FRAMES = 1 << 20


def streamed_integrated_loudness(path: Path) -> tuple[float, int, int, int]:
    """BS.1770-4 integrated loudness, streamed; same result as pyloudnorm.

    ``Meter.integrated_loudness`` needs the whole file as float64 plus a
    filtered copy: several GB for a 40-minute stereo master, which the memory
    guard killed on the one-hour run (ISSUES entry 58). K-weighting runs block
    by block with carried filter state; gating uses per-100 ms sums of squares,
    so memory is a few MB whatever the length. Returns (lufs, rate, channels,
    frames).
    """
    import numpy as np
    import scipy.signal

    with sf.SoundFile(str(path)) as handle:
        rate = int(handle.samplerate)
        channels = int(handle.channels)
    meter = pyln.Meter(rate)
    stages = list(meter._filters.values())
    zi = [
        [scipy.signal.lfilter_zi(st.b, st.a) * 0.0 for st in stages]
        for _ in range(channels)
    ]
    step = int(round(meter.block_size * (1.0 - meter.overlap) * rate))
    per_block_steps = int(round(1.0 / (1.0 - meter.overlap)))
    step_sums: list[np.ndarray] = []
    carry = np.zeros((0, channels), dtype=np.float64)
    frames = 0
    for chunk in sf.blocks(str(path), blocksize=_BLOCK_FRAMES, always_2d=True, dtype="float64"):
        frames += len(chunk)
        filtered = np.empty_like(chunk)
        for ch in range(channels):
            x = chunk[:, ch]
            for k, st in enumerate(stages):
                x, zi[ch][k] = scipy.signal.lfilter(st.b, st.a, x, zi=zi[ch][k])
                x = st.passband_gain * x
            filtered[:, ch] = x
        buf = np.concatenate([carry, filtered]) if carry.size else filtered
        usable = (len(buf) // step) * step
        if usable:
            sq = np.square(buf[:usable]).reshape(-1, step, channels).sum(axis=1)
            step_sums.append(sq)
        carry = buf[usable:]
    if carry.size:
        tail = np.zeros((1, channels))
        tail[0] = np.square(carry).sum(axis=0)
        step_sums.append(tail)
    if not step_sums:
        return float("-inf"), rate, channels, frames
    steps = np.concatenate(step_sums)
    T = frames / float(rate)
    num_blocks = int(np.round((T - meter.block_size) / (meter.block_size * (1.0 - meter.overlap)))) + 1
    if num_blocks <= 0:
        return float("-inf"), rate, channels, frames
    window = meter.block_size * rate
    z = np.zeros((channels, num_blocks))
    for j in range(num_blocks):
        seg = steps[j : j + per_block_steps]
        z[:, j] = seg.sum(axis=0) / window
    gains = np.array([1.0, 1.0, 1.0, 1.41, 1.41][:channels])
    with np.errstate(divide="ignore", invalid="ignore"):
        block_l = -0.691 + 10.0 * np.log10((gains[:, None] * z).sum(axis=0))
        abs_gate = block_l >= -70.0
        if not np.any(abs_gate):
            return float("-inf"), rate, channels, frames
        z_abs = z[:, abs_gate].mean(axis=1)
        gamma_r = -0.691 + 10.0 * np.log10((gains * z_abs).sum()) - 10.0
        gate = (block_l > gamma_r) & (block_l > -70.0)
        if not np.any(gate):
            return float("-inf"), rate, channels, frames
        z_gated = z[:, gate].mean(axis=1)
        lufs = -0.691 + 10.0 * np.log10((gains * z_gated).sum())
    return float(lufs), rate, channels, frames


def measure_assembly_bus(path: Path) -> AssemblyBusMetrics:
    """ITU-R BS.1770 integrated loudness on the assembly bus (pre-limiter)."""
    if not path.is_file():
        raise FileNotFoundError(path)

    integrated_lufs, rate, channels, frames = streamed_integrated_loudness(path)
    duration_seconds = float(frames) / float(rate) if rate else 0.0
    if not math.isfinite(integrated_lufs):
        raise RuntimeError(
            f"Could not measure assembly bus loudness for {path.name} "
            "(signal silent or below BS.1770 absolute gate)."
        )

    return AssemblyBusMetrics(
        integrated_lufs=integrated_lufs,
        sample_rate_hz=int(rate),
        channels=channels,
        duration_seconds=duration_seconds,
    )


def target_lufs_for_flow(flow: FlowName, *, config: dict | None = None) -> float:
    thresholds = TARGETS[flow]
    cfg = config or {}
    key = "flow1_target_lufs" if flow == "podcast" else "flow2_target_lufs"
    return float(cfg.get(key, thresholds.target_lufs))


def loudnorm_offset(target_lufs: float, measured_lufs: float) -> str:
    return f"{target_lufs - measured_lufs:.2f}"
