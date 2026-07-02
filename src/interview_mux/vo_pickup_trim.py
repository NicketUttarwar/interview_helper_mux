"""Apply trim bounds to vo_pickup WAV files and persist metadata."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

import numpy as np

from interview_mux.config import merged_config
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext

METADATA_REL = "vo_pickup/metadata.json"


def _metadata_path(ctx: RunContext) -> Path:
    return ctx.path("vo_pickup") / "metadata.json"


def load_vo_metadata(ctx: RunContext) -> dict[str, Any]:
    p = _metadata_path(ctx)
    if not p.is_file():
        return {"lines": {}}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"lines": {}}
    data.setdefault("lines", {})
    return data


def save_vo_metadata(ctx: RunContext, meta: dict[str, Any]) -> None:
    p = _metadata_path(ctx)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def get_line_metadata(ctx: RunContext, line_id: str) -> dict[str, Any]:
    meta = load_vo_metadata(ctx)
    row = meta.get("lines", {}).get(line_id)
    return dict(row) if isinstance(row, dict) else {}


def apply_trim_to_wav(
    src: Path,
    dest: Path,
    *,
    trim_in_ms: float,
    trim_out_ms: float | None,
    sample_rate: int | None = None,
) -> dict[str, Any]:
    sr = sample_rate or int(merged_config().get("sample_rate", 48000))
    with wave.open(str(src), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
    audio = np.frombuffer(raw, dtype=dtype)
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels)
    start_frame = int(max(0, trim_in_ms) * framerate / 1000)
    end_frame = n_frames if trim_out_ms is None else int(min(n_frames, trim_out_ms * framerate / 1000))
    end_frame = max(start_frame + 1, end_frame)
    trimmed = audio[start_frame:end_frame]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(n_channels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        out.writeframes(trimmed.tobytes())
    duration_ms = round((end_frame - start_frame) * 1000 / framerate, 1)
    return {
        "trim_in_ms": trim_in_ms,
        "trim_out_ms": trim_out_ms,
        "duration_ms": duration_ms,
        "sample_rate": framerate,
    }


def apply_vo_trim(
    ctx: RunContext,
    line_id: str,
    *,
    trim_in_ms: float,
    trim_out_ms: float | None,
) -> dict[str, Any]:
    pickup = ctx.path("vo_pickup")
    src = pickup / f"{line_id}.wav"
    if not src.is_file():
        raise FileNotFoundError(f"Missing vo_pickup/{line_id}.wav")
    backup = pickup / f"{line_id}.raw.wav"
    if not backup.is_file():
        backup.write_bytes(src.read_bytes())
    with logged_step("vo_pickup_trim/apply", ctx=ctx, stage="g1_vo_pickup"):
        stats = apply_trim_to_wav(src, src, trim_in_ms=trim_in_ms, trim_out_ms=trim_out_ms)
        meta = load_vo_metadata(ctx)
        lines = meta.setdefault("lines", {})
        row = dict(lines.get(line_id) or {})
        row.update(
            {
                "line_id": line_id,
                "filename": f"{line_id}.wav",
                **stats,
            }
        )
        lines[line_id] = row
        save_vo_metadata(ctx, meta)
        ctx.log(
            f"VO trim applied: {line_id} ({trim_in_ms}–{trim_out_ms} ms)",
            level="success",
            stage="g1_vo_pickup",
            detail={"kind": "gate", "line_id": line_id, **stats},
        )
        return row
