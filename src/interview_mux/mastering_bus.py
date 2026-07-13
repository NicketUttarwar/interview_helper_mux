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


def measure_assembly_bus(path: Path) -> AssemblyBusMetrics:
    """ITU-R BS.1770 integrated loudness on the assembly bus (pre-limiter)."""
    if not path.is_file():
        raise FileNotFoundError(path)

    data, rate = sf.read(path, always_2d=True, dtype="float64")
    channels = int(data.shape[1]) if data.ndim == 2 else 1
    duration_seconds = float(data.shape[0]) / float(rate) if rate else 0.0

    meter = pyln.Meter(rate)
    integrated_lufs = float(meter.integrated_loudness(data))
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
