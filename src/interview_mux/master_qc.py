from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydub import AudioSegment

from interview_mux.config import merged_config
from interview_mux.operator_quality import record_qc_summary
from interview_mux.run_context import RunContext

FlowName = Literal["podcast", "flow2"]

SPEECH_BAND_LOW_HZ = 300
SPEECH_BAND_HIGH_HZ = 4000
_RMS_FLOOR = 1e-12
_SILENT_SPEECH_RMS = 0.002

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
    "podcast": QCTarget(flow="podcast", target_lufs=-16.0, tolerance_lufs=1.0, max_true_peak_dbtp=-1.0),
    "flow2": QCTarget(flow="flow2", target_lufs=-14.0, tolerance_lufs=1.0, max_true_peak_dbtp=-1.0),
}

def detect_flow_from_path(path: Path) -> FlowName | None:
    path_str = str(path).replace("\\", "/")
    if "/master/" in path_str:
        return "podcast"
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
    from interview_mux.operator_subprocess import run_command

    probe = run_command(
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
        label=f"ffprobe master metrics {path.name}",
        capture_output=True,
    )
    probe_data = json.loads(probe.stdout or "{}")
    stream = (probe_data.get("streams") or [{}])[0]
    duration = float((probe_data.get("format") or {}).get("duration") or 0.0)
    sample_rate = int(stream.get("sample_rate") or 0)
    channels = int(stream.get("channels") or 0)

    loudness = run_command(
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
        label=f"ffmpeg loudnorm measure {path.name}",
        capture_output=True,
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

@dataclass(frozen=True)
class BedSpeechWindow:
    segment_id: str
    start_ms: int
    end_ms: int
    duck_under_speech_db: float

@dataclass(frozen=True)
class IntelligibilityResult:
    flow: FlowName
    source: Path
    ok: bool
    bed_windows_checked: int
    failures: list[str]
    flagged_segment_ids: list[str]
    window_metrics: list[dict[str, Any]] = field(default_factory=list)

def intelligibility_qc_config() -> dict[str, Any]:
    mix = merged_config().get("mix") or {}
    qc = mix.get("intelligibility_qc")
    return qc if isinstance(qc, dict) else {}

def intelligibility_qc_enabled() -> bool:
    return bool(intelligibility_qc_config().get("enabled"))

def speech_band_rms(segment: AudioSegment) -> float:
    """RMS of 300 Hz–4 kHz band (speech intelligibility range)."""
    if len(segment) <= 0:
        return 0.0
    filtered = segment.high_pass_filter(SPEECH_BAND_LOW_HZ).low_pass_filter(SPEECH_BAND_HIGH_HZ)
    samples = np.array(filtered.get_array_of_samples(), dtype=np.float64)
    if filtered.channels > 1:
        samples = samples.reshape(-1, filtered.channels).mean(axis=1)
    max_val = float(2 ** (8 * filtered.sample_width - 1))
    normalized = samples / max_val
    return float(np.sqrt(np.mean(np.square(normalized))))

def _max_allowed_excess_db(duck_under_speech_db: float, qc_cfg: dict[str, Any]) -> float:
    override = qc_cfg.get("max_speech_band_excess_db")
    if override is not None:
        return float(override)
    # Tighter duck contract => less bed bleed allowed in the speech band.
    return max(3.0, min(8.0, 14.0 - (duck_under_speech_db - 14.0) * 0.5))

def collect_flow1_bed_speech_windows(
    ctx: RunContext,
    *,
    segment_timing: dict[str, tuple[int, int]],
    contract: dict[str, Any],
) -> list[BedSpeechWindow]:
    """Windows where under_segment beds overlap speech (Flow 1 only)."""
    if contract.get("underscore_policy") == "skip":
        return []
    plan_path = "understanding/sound_design_plan.json"
    if not ctx.artifact_exists(plan_path):
        return []
    plan = ctx.read_json(plan_path)
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    duck_default = float(contract.get("duck_under_speech_db", 16.0))
    windows: list[BedSpeechWindow] = []
    seen: set[str] = set()

    for cue in cues:
        if not isinstance(cue, dict):
            continue
        if str(cue.get("placement") or "") != "under_segment":
            continue
        seg_id = str(cue.get("segment_id") or "")
        timing = segment_timing.get(seg_id)
        if not timing or seg_id in seen:
            continue
        start_ms, end_ms = timing
        if end_ms <= start_ms:
            continue
        duck_db = float(cue.get("duck_under_speech_db", duck_default))
        windows.append(
            BedSpeechWindow(
                segment_id=seg_id,
                start_ms=start_ms,
                end_ms=end_ms,
                duck_under_speech_db=duck_db,
            )
        )
        seen.add(seg_id)
    return windows

def analyze_mix_intelligibility(
    assembly: AudioSegment,
    speech_stem: AudioSegment,
    bed_windows: list[BedSpeechWindow],
    *,
    flow: FlowName,
    source: Path,
    duck_under_speech_db: float,
    qc_cfg: dict[str, Any] | None = None,
) -> IntelligibilityResult:
    """Compare speech-band energy in bed-heavy regions vs speech-only stem."""
    cfg = qc_cfg if qc_cfg is not None else intelligibility_qc_config()
    if not bed_windows:
        return IntelligibilityResult(
            flow=flow,
            source=source,
            ok=True,
            bed_windows_checked=0,
            failures=[],
            flagged_segment_ids=[],
        )

    silent_ceiling_dbfs = float(cfg.get("silent_speech_mix_ceiling_dbfs", -32.0))
    failures: list[str] = []
    flagged: list[str] = []
    metrics: list[dict[str, Any]] = []

    for window in bed_windows:
        mix_chunk = assembly[window.start_ms : window.end_ms]
        speech_chunk = speech_stem[window.start_ms : window.end_ms]
        mix_rms = speech_band_rms(mix_chunk)
        speech_rms = speech_band_rms(speech_chunk)
        window_max_excess = _max_allowed_excess_db(window.duck_under_speech_db, cfg)

        if speech_rms < _SILENT_SPEECH_RMS:
            mix_dbfs = 20.0 * math.log10(max(mix_rms, _RMS_FLOOR))
            passed = mix_dbfs <= silent_ceiling_dbfs
            detail = {
                "segment_id": window.segment_id,
                "start_ms": window.start_ms,
                "end_ms": window.end_ms,
                "mix_speech_band_dbfs": round(mix_dbfs, 2),
                "speech_stem_rms": round(speech_rms, 6),
                "silent_speech": True,
                "threshold_dbfs": silent_ceiling_dbfs,
                "passed": passed,
            }
        else:
            excess_db = 20.0 * math.log10(max(mix_rms, _RMS_FLOOR) / max(speech_rms, _RMS_FLOOR))
            passed = excess_db <= window_max_excess
            detail = {
                "segment_id": window.segment_id,
                "start_ms": window.start_ms,
                "end_ms": window.end_ms,
                "mix_speech_band_rms": round(mix_rms, 6),
                "speech_stem_rms": round(speech_rms, 6),
                "excess_db": round(excess_db, 2),
                "max_excess_db": round(window_max_excess, 2),
                "passed": passed,
            }

        metrics.append(detail)
        if passed:
            continue
        flagged.append(window.segment_id)
        if detail.get("silent_speech"):
            failures.append(
                f"segment {window.segment_id}: speech-band bed energy {detail['mix_speech_band_dbfs']:.1f} dBFS "
                f"exceeds ceiling {silent_ceiling_dbfs:.1f} dBFS on near-silent speech"
            )
        else:
            failures.append(
                f"segment {window.segment_id}: speech-band excess {detail['excess_db']:.1f} dB "
                f"exceeds {detail['max_excess_db']:.1f} dB duck allowance"
            )

    return IntelligibilityResult(
        flow=flow,
        source=source,
        ok=not failures,
        bed_windows_checked=len(bed_windows),
        failures=failures,
        flagged_segment_ids=sorted(set(flagged)),
        window_metrics=metrics,
    )

def maybe_check_mix_intelligibility(
    ctx: RunContext,
    *,
    assembly_path: Path,
    flow: FlowName,
    stage: str,
    speech_stem: AudioSegment,
    segment_timing: dict[str, tuple[int, int]],
    contract: dict[str, Any],
) -> IntelligibilityResult | None:
    """Optional post-mix QC: beds must not mask the speech band after ducking."""
    if not intelligibility_qc_enabled():
        return None

    assembly = AudioSegment.from_file(str(assembly_path))
    bed_windows = (
        collect_flow1_bed_speech_windows(ctx, segment_timing=segment_timing, contract=contract)
        if flow == "podcast"
        else []
    )
    duck_db = float(contract.get("duck_under_speech_db", 16.0))
    result = analyze_mix_intelligibility(
        assembly,
        speech_stem,
        bed_windows,
        flow=flow,
        source=assembly_path,
        duck_under_speech_db=duck_db,
    )

    summary = {
        "passed": result.ok,
        "flow": flow,
        "bed_windows_checked": result.bed_windows_checked,
        "flagged_segment_ids": result.flagged_segment_ids,
        "failures": result.failures[:12],
        "window_metrics": result.window_metrics[:24],
        "duck_under_speech_db": duck_db,
        "at_stage": stage,
    }
    record_qc_summary(ctx, "mix_intelligibility", summary)

    if result.ok:
        ctx.log(
            (
                f"{stage}: mix intelligibility QC passed "
                f"({result.bed_windows_checked} bed-under-speech window(s) checked)"
            ),
            level="success",
            stage=stage,
            detail="intelligibility_pass",
        )
        return result

    seg_ids = ", ".join(result.flagged_segment_ids) or "unknown"
    ctx.log(
        f"{stage}: mix intelligibility QC failed — bed may mask speech band in segment(s): {seg_ids}",
        level="warning",
        stage=stage,
        detail="intelligibility_warn",
    )
    return result
