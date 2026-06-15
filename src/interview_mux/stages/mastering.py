from __future__ import annotations

import json
import subprocess
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.master_qc import TARGETS, FlowName
from interview_mux.mastering_bus import loudnorm_offset, measure_assembly_bus, target_lufs_for_flow
from interview_mux.operator_quality import record_qc_summary
from interview_mux.run_context import RunContext
from interview_mux.sdp_cross_validate import validate_pre_master
from interview_mux.sound_design import load_sound_design_plan


def master_wav(ctx: RunContext, assembly_rel: str, master_rel: str, *, flow: str) -> Path:
    flow_name: FlowName = flow if flow in TARGETS else "flow1"
    thresholds = TARGETS[flow_name]
    cfg = merged_config()
    target = target_lufs_for_flow(flow_name, config=cfg)
    true_peak = float(thresholds.max_true_peak_dbtp)
    assembly = ctx.path(assembly_rel)
    master = ctx.path(master_rel)
    if not assembly.is_file():
        raise FileNotFoundError(assembly)

    stage = "master_flow1" if flow == "flow1" else "master_flow2"
    pre_errors = validate_pre_master(ctx, flow_name)
    if pre_errors:
        summary = "; ".join(pre_errors[:4])
        ctx.log(
            f"pre_master validation: {summary}",
            level="warning",
            stage=stage,
            detail="pre_master_validation_warn",
        )
        record_qc_summary(
            ctx,
            "pre_master",
            {"passed": False, "errors": pre_errors[:12], "flow": flow_name, "at_stage": stage},
        )

    bus = measure_assembly_bus(assembly)
    _maybe_warn_low_sfx_energy(ctx, assembly=assembly, flow=flow_name, stage=stage)
    ctx.log(
        (
            f"Assembly bus measured {bus.integrated_lufs:.2f} LUFS "
            f"(target {target:.1f} ± {thresholds.tolerance_lufs:.1f}, "
            f"true-peak ceiling {true_peak:.1f} dBTP)"
        ),
        stage=stage,
        detail=(
            f"sample_rate_hz={bus.sample_rate_hz} channels={bus.channels} "
            f"duration_s={bus.duration_seconds:.2f}"
        ),
    )

    measured = _ffmpeg_loudnorm_probe(assembly, target=target, true_peak=true_peak)
    measured["input_i"] = f"{bus.integrated_lufs:.2f}"
    measured["target_offset"] = loudnorm_offset(target, bus.integrated_lufs)

    loudnorm_filter = (
        f"loudnorm=I={target}:TP={true_peak}:LRA=11:"
        f"measured_I={measured['input_i']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:"
        "linear=true:print_format=summary"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(assembly),
            "-af",
            loudnorm_filter,
            str(master),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    ctx.mark_done(stage)
    ctx.log(
        f"Master complete — {master_rel} at {target:.1f} LUFS target.",
        level="success",
        stage=stage,
        detail=str(master),
    )
    return master


def _maybe_warn_low_sfx_energy(
    ctx: RunContext,
    *,
    assembly: Path,
    flow: FlowName,
    stage: str,
) -> None:
    """Warn when SDP plans SFX but assembly shows negligible high-band energy."""
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return
    sdp = load_sound_design_plan(ctx)
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict) and a.get("asset_id")]
    if not assets:
        return
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    plan = flow_plans.get(flow) if isinstance(flow_plans.get(flow), dict) else {}
    cues = plan.get("cues") if isinstance(plan.get("cues"), list) else []
    if not cues and not assets:
        return
    try:
        from interview_mux.mmaudio_asset_qa import _band_energy_ratio, _read_wav_frames

        samples, rate = _read_wav_frames(assembly)
        high_band = _band_energy_ratio(samples, rate, 4000.0, 12000.0)
        mid_band = _band_energy_ratio(samples, rate, 800.0, 4000.0)
        sfx_proxy = max(high_band, mid_band * 0.6)
    except (OSError, ValueError, RuntimeError):
        return
    threshold = float((merged_config().get("mix") or {}).get("master_sfx_energy_threshold", 0.03))
    if sfx_proxy >= threshold:
        return
    ctx.log(
        (
            f"master_sfx_energy_low: SDP has {len(assets)} asset(s) and {len(cues)} cue(s) "
            f"but assembly SFX-band proxy={sfx_proxy:.4f} < {threshold}"
        ),
        level="warning",
        stage=stage,
        detail="master_sfx_energy_low",
    )
    record_qc_summary(
        ctx,
        "master_sfx_energy",
        {
            "passed": False,
            "sfx_band_proxy": round(sfx_proxy, 4),
            "threshold": threshold,
            "asset_count": len(assets),
            "cue_count": len(cues),
            "flow": flow,
            "at_stage": stage,
        },
    )


def _ffmpeg_loudnorm_probe(assembly: Path, *, target: float, true_peak: float) -> dict[str, str]:
    measure = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(assembly),
            "-af",
            f"loudnorm=I={target}:TP={true_peak}:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return _extract_loudnorm_json(measure.stderr or "")


def _extract_loudnorm_json(stderr: str) -> dict[str, str]:
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Could not parse loudnorm metrics from ffmpeg output.")
    data = json.loads(stderr[start : end + 1])
    required = ("input_i", "input_lra", "input_tp", "input_thresh", "target_offset")
    missing = [key for key in required if key not in data]
    if missing:
        missing_keys = ", ".join(missing)
        raise RuntimeError(f"Incomplete loudnorm output from ffmpeg (missing {missing_keys}).")
    return data


def run_master_flow1(ctx: RunContext) -> Path:
    return master_wav(ctx, "flow_1_master/assembly.wav", "flow_1_master/master.wav", flow="flow1")


def run_master_flow2(ctx: RunContext) -> Path:
    return master_wav(ctx, "flow_2_highlights/assembly.wav", "flow_2_highlights/master.wav", flow="flow2")
