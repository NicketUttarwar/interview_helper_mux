from __future__ import annotations

import subprocess
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext


def master_wav(ctx: RunContext, assembly_rel: str, master_rel: str, *, flow: str) -> Path:
    cfg = merged_config()
    target = float(cfg.get("flow1_target_lufs" if flow == "flow1" else "flow2_target_lufs", -16.0))
    assembly = ctx.path(assembly_rel)
    master = ctx.path(master_rel)
    if not assembly.is_file():
        raise FileNotFoundError(assembly)

    # Normalize with ffmpeg loudnorm (approximate LUFS target)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(assembly),
            "-af",
            f"loudnorm=I={target}:TP=-1.5:LRA=11",
            str(master),
        ],
        check=True,
        capture_output=True,
    )
    stage = "master_flow1" if flow == "flow1" else "master_flow2"
    ctx.mark_done(stage)
    return master


def run_master_flow1(ctx: RunContext) -> Path:
    return master_wav(ctx, "flow_1_master/assembly.wav", "flow_1_master/master.wav", flow="flow1")


def run_master_flow2(ctx: RunContext) -> Path:
    return master_wav(ctx, "flow_2_highlights/assembly.wav", "flow_2_highlights/master.wav", flow="flow2")
