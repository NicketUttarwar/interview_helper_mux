from __future__ import annotations

import json
import subprocess
from pathlib import Path

from interview_mux.run_context import RunContext


def _segment_by_id(ctx: RunContext) -> dict[str, dict]:
    manifest = ctx.read_json("segments/manifest.json")
    segs = manifest.get("segments") or []
    return {s["segment_id"]: s for s in segs}


def run_edl(ctx: RunContext) -> None:
    selection = ctx.read_json("flow_1_master/selection.json")
    by_id = _segment_by_id(ctx)
    clips = []
    timeline_ms = 0
    for sid in selection.get("ordered_segment_ids") or []:
        seg = by_id.get(sid)
        if not seg:
            continue
        dur = int(seg["end_ms"]) - int(seg["start_ms"])
        clips.append(
            {
                "segment_id": sid,
                "source_start_ms": seg["start_ms"],
                "source_end_ms": seg["end_ms"],
                "timeline_start_ms": timeline_ms,
                "type": "speech",
            }
        )
        timeline_ms += dur
    ctx.write_json("flow_1_master/edl.json", {"clips": clips, "timeline_duration_ms": timeline_ms})
    ctx.mark_done("edl_flow1")


def run_mux(ctx: RunContext) -> Path:
    edl = ctx.read_json("flow_1_master/edl.json")
    source = ctx.path("ingest", "normalized.wav")
    work = ctx.path("flow_1_master", "_clips")
    work.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    for i, clip in enumerate(edl.get("clips") or []):
        out = work / f"clip_{i:04d}.wav"
        start = clip["source_start_ms"] / 1000.0
        end = clip["source_end_ms"] / 1000.0
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-ss",
                str(start),
                "-to",
                str(end),
                "-c",
                "copy",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        clip_paths.append(out)

    concat_list = work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in clip_paths),
        encoding="utf-8",
    )
    assembly = ctx.path("flow_1_master", "assembly.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(assembly),
        ],
        check=True,
        capture_output=True,
    )
    ctx.mark_done("mux_flow1")
    return assembly
