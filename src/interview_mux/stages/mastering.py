from __future__ import annotations

import json
import subprocess
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.master_qc import TARGETS, FlowName
from interview_mux.mastering_bus import loudnorm_offset, measure_assembly_bus, target_lufs_for_flow
from interview_mux.operator_quality import record_qc_summary
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.sdp_cross_validate import validate_pre_master

def master_wav(ctx: RunContext, assembly_rel: str, master_rel: str, *, flow: str) -> Path:
    stage = "master_finalize"
    flow_name: FlowName = flow if flow in TARGETS else "podcast"
    thresholds = TARGETS[flow_name]
    cfg = merged_config()
    target = target_lufs_for_flow(flow_name, config=cfg)
    true_peak = float(thresholds.max_true_peak_dbtp)
    assembly = ctx.read_path(assembly_rel)
    master = ctx.path(master_rel)
    if not assembly.is_file():
        raise FileNotFoundError(assembly)
    if assembly.stat().st_size < 1024:
        raise RuntimeError(
            f"{stage}: assembly speech path is empty/corrupt ({assembly_rel}). "
            "Refuse master finalize — fix mix/speech stems before export."
        )

    with logged_step(f"{stage}/pre_master_validation", ctx=ctx, stage=stage):
        pre_errors = validate_pre_master(ctx, flow_name)
        if pre_errors:
            from interview_mux.coverage_limits import is_non_blocking_lint, pre_master_soft_fail_enabled

            blocking = [e for e in pre_errors if not is_non_blocking_lint(e)]
            soft_only = [e for e in pre_errors if is_non_blocking_lint(e)]
            if soft_only and pre_master_soft_fail_enabled():
                ctx.log(
                    f"pre_master soft warnings: {'; '.join(soft_only[:4])}",
                    level="warning",
                    stage=stage,
                    detail={"pre_master_soft_warnings": soft_only[:12]},
                )
            if blocking or not pre_master_soft_fail_enabled():
                summary = "; ".join((blocking or pre_errors)[:4])
                ctx.log(
                    f"pre_master validation failed: {summary}",
                    level="error",
                    stage=stage,
                    detail={"pre_master_validation": (blocking or pre_errors)[:12]},
                )
                record_qc_summary(
                    ctx,
                    "pre_master",
                    {
                        "passed": False,
                        "errors": (blocking or pre_errors)[:12],
                        "flow": flow_name,
                        "at_stage": stage,
                    },
                )
                raise RuntimeError(f"pre_master validation failed: {summary}")

    with logged_step(f"{stage}/measure_bus", ctx=ctx, stage=stage):
        bus = measure_assembly_bus(assembly)
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

    with logged_step(f"{stage}/loudnorm_render", ctx=ctx, stage=stage):
        from interview_mux.operator_subprocess import run_command

        run_command(
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
            ctx=ctx,
            stage=stage,
            label=f"ffmpeg loudnorm master → {master_rel}",
            capture_output=True,
        )
    ctx.mark_done(stage)
    ctx.log(
        f"Master complete — {master_rel} at {target:.1f} LUFS target.",
        level="success",
        stage=stage,
        detail=str(master),
    )
    return master

def _ffmpeg_loudnorm_probe(assembly: Path, *, target: float, true_peak: float) -> dict[str, str]:
    from interview_mux.operator_subprocess import run_command

    measure = run_command(
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
        label=f"ffmpeg loudnorm probe {assembly.name}",
        capture_output=True,
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

def run_master_finalize(ctx: RunContext) -> Path:
    return master_wav(ctx, "master/assembly.wav", "master/master.wav", flow="podcast")

