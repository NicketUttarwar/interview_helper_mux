from __future__ import annotations

import json
import subprocess
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.master_qc import TARGETS, FlowName
from interview_mux.run_context import RunContext


def master_wav(ctx: RunContext, assembly_rel: str, master_rel: str, *, flow: str) -> Path:
    flow_name: FlowName = flow if flow in TARGETS else "flow1"
    thresholds = TARGETS[flow_name]
    cfg = merged_config()
    target = float(
        cfg.get(
            "flow1_target_lufs" if flow_name == "flow1" else "flow2_target_lufs",
            thresholds.target_lufs,
        )
    )
    true_peak = float(thresholds.max_true_peak_dbtp)
    assembly = ctx.path(assembly_rel)
    master = ctx.path(master_rel)
    if not assembly.is_file():
        raise FileNotFoundError(assembly)

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
    measured = _extract_loudnorm_json(measure.stderr or "")

    # Two-pass loudness normalization ensures measured values from pass 1 drive final gain.
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
    stage = "master_flow1" if flow == "flow1" else "master_flow2"
    ctx.mark_done(stage)
    return master


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
