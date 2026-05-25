from __future__ import annotations

import subprocess
from pathlib import Path

from interview_mux.run_context import RunContext


def run_micro_assembly(ctx: RunContext) -> Path:
    selection = ctx.read_json("flow_2_highlights/selection.json")
    manifest = ctx.read_json("segments/manifest.json")
    by_id = {s["segment_id"]: s for s in (manifest.get("segments") or [])}
    source = ctx.path("ingest", "normalized.wav")
    work = ctx.path("flow_2_highlights", "_clips")
    work.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    highlights = selection.get("highlights") or []
    for i, hl in enumerate(highlights):
        sid = hl.get("segment_id")
        seg = by_id.get(sid) if sid else None
        start_ms = hl.get("start_ms") or (seg and seg["start_ms"])
        end_ms = hl.get("end_ms") or (seg and seg["end_ms"])
        if start_ms is None or end_ms is None:
            continue
        out = work / f"clip_{i:04d}.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-ss",
                str(start_ms / 1000.0),
                "-to",
                str(end_ms / 1000.0),
                "-c",
                "copy",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        clip_paths.append(out)

        sfx_dir = ctx.path("flow_2_highlights", "sfx")
        sfx_files = sorted(sfx_dir.glob("*.wav")) if sfx_dir.is_dir() else []
        if i < len(sfx_files):
            clip_paths.append(sfx_files[i])

    if not clip_paths:
        raise RuntimeError("No highlight clips extracted")

    concat_list = work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in clip_paths),
        encoding="utf-8",
    )
    assembly = ctx.path("flow_2_highlights", "assembly.wav")
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
    ctx.mark_done("mux_flow2")
    return assembly
