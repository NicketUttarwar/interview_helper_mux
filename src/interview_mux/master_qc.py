from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FlowName = Literal["flow1", "flow2"]


@dataclass(frozen=True)
class QCTarget:
    flow: FlowName
    target_lufs: float
    tolerance_lufs: float
    max_true_peak_dbtp: float


@dataclass(frozen=True)
class MasterMetrics:
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    integrated_lufs: float
    true_peak_dbtp: float


@dataclass(frozen=True)
class VerificationResult:
    flow: FlowName
    source: Path
    metrics: MasterMetrics
    checks: list[str]
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


TARGETS: dict[FlowName, QCTarget] = {
    "flow1": QCTarget(flow="flow1", target_lufs=-16.0, tolerance_lufs=1.0, max_true_peak_dbtp=-1.0),
    "flow2": QCTarget(flow="flow2", target_lufs=-14.0, tolerance_lufs=1.0, max_true_peak_dbtp=-1.0),
}


def detect_flow_from_path(path: Path) -> FlowName | None:
    path_str = str(path).replace("\\", "/")
    if "/flow_1_master/" in path_str:
        return "flow1"
    if "/flow_2_highlights/" in path_str:
        return "flow2"
    return None


def verify_master(path: Path, *, flow: FlowName | None = None) -> VerificationResult:
    resolved_flow = flow or detect_flow_from_path(path)
    if resolved_flow is None:
        raise ValueError(
            "Could not infer flow target from path. Pass --flow flow1|flow2 or use a standard run path."
        )

    target = TARGETS[resolved_flow]
    metrics = _collect_metrics(path)
    checks: list[str] = []
    failures: list[str] = []

    checks.append(f"sample_rate_hz={metrics.sample_rate_hz} (expected 44100 or 48000)")
    if metrics.sample_rate_hz not in (44100, 48000):
        failures.append(f"Sample rate {metrics.sample_rate_hz}Hz is out of spec (expected 44100 or 48000).")

    checks.append(f"duration_seconds={metrics.duration_seconds:.2f} (> 0)")
    if metrics.duration_seconds <= 0:
        failures.append("Duration must be greater than zero.")

    lower_lufs = target.target_lufs - target.tolerance_lufs
    upper_lufs = target.target_lufs + target.tolerance_lufs
    checks.append(
        f"integrated_lufs={metrics.integrated_lufs:.2f} (target {target.target_lufs:.1f} +/- {target.tolerance_lufs:.1f})"
    )
    if not (lower_lufs <= metrics.integrated_lufs <= upper_lufs):
        failures.append(
            f"Integrated LUFS {metrics.integrated_lufs:.2f} out of range [{lower_lufs:.1f}, {upper_lufs:.1f}]."
        )

    checks.append(f"true_peak_dbtp={metrics.true_peak_dbtp:.2f} (must be <= {target.max_true_peak_dbtp:.1f})")
    if metrics.true_peak_dbtp > target.max_true_peak_dbtp:
        failures.append(
            f"True peak {metrics.true_peak_dbtp:.2f} dBTP exceeds ceiling {target.max_true_peak_dbtp:.1f} dBTP."
        )

    return VerificationResult(
        flow=resolved_flow,
        source=path,
        metrics=metrics,
        checks=checks,
        failures=failures,
    )


def _collect_metrics(path: Path) -> MasterMetrics:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    probe_data = json.loads(probe.stdout or "{}")
    stream = (probe_data.get("streams") or [{}])[0]
    duration = float((probe_data.get("format") or {}).get("duration") or 0.0)
    sample_rate = int(stream.get("sample_rate") or 0)
    channels = int(stream.get("channels") or 0)

    loudness = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    loudness_data = _extract_loudnorm_json(loudness.stderr or "")
    integrated_lufs = float(loudness_data["input_i"])
    true_peak_dbtp = float(loudness_data["input_tp"])
    return MasterMetrics(
        duration_seconds=duration,
        sample_rate_hz=sample_rate,
        channels=channels,
        integrated_lufs=integrated_lufs,
        true_peak_dbtp=true_peak_dbtp,
    )


def _extract_loudnorm_json(stderr: str) -> dict[str, str]:
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Could not parse loudnorm metrics from ffmpeg output.")
    payload = stderr[start : end + 1]
    data = json.loads(payload)
    if "input_i" not in data or "input_tp" not in data:
        raise RuntimeError("Incomplete loudnorm output from ffmpeg (missing input_i or input_tp).")
    return data
