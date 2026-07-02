"""Suggest trim boundaries for vo_pickup recordings from silence/energy."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np

from interview_mux.config import merged_config
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.vo_pickup_trim import get_line_metadata, load_vo_metadata, save_vo_metadata


def _rms_frames(audio: np.ndarray, frame_len: int, hop: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(audio)
    rms = []
    times_ms = []
    for start in range(0, max(1, n - frame_len), hop):
        chunk = audio[start : start + frame_len]
        rms.append(float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2))))
        times_ms.append(start * 1000.0 / 48000)
    return np.array(rms), np.array(times_ms)


def suggest_boundary(wav_path: Path, *, sample_rate: int | None = None) -> dict[str, Any]:
    sr = sample_rate or int(merged_config().get("sample_rate", 48000))
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        framerate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
    audio = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)
    if len(audio) == 0:
        return {"trim_in_ms": 0.0, "trim_out_ms": 0.0, "confidence": 0.0}
    peak = float(np.max(np.abs(audio))) or 1.0
    norm = audio / peak
    frame_len = max(256, int(framerate * 0.02))
    hop = max(128, frame_len // 2)
    rms, times = _rms_frames(norm, frame_len, hop)
    threshold = float((merged_config().get("mix") or {}).get("tbiy_narrative", {}).get("vo_silence_threshold", 0.02))
    speech = rms > threshold
    if not speech.any():
        duration_ms = len(audio) * 1000.0 / framerate
        return {"trim_in_ms": 0.0, "trim_out_ms": round(duration_ms, 1), "confidence": 0.3}
    first = int(np.argmax(speech))
    last = int(len(speech) - 1 - np.argmax(speech[::-1]))
    trim_in = max(0.0, float(times[first]) - 50.0)
    trim_out = float(times[last]) + (frame_len * 1000.0 / framerate) + 80.0
    duration_ms = len(audio) * 1000.0 / framerate
    trim_out = min(trim_out, duration_ms)
    return {
        "trim_in_ms": round(trim_in, 1),
        "trim_out_ms": round(trim_out, 1),
        "confidence": round(float(np.mean(rms[speech])), 3),
        "duration_ms": round(duration_ms, 1),
    }


def suggest_line_boundary(ctx: RunContext, line_id: str) -> dict[str, Any]:
    wav = ctx.path("vo_pickup") / f"{line_id}.wav"
    if not wav.is_file():
        raise FileNotFoundError(f"Missing vo_pickup/{line_id}.wav")
    return suggest_boundary(wav)


def run_vo_boundary_detect(ctx: RunContext) -> None:
    report_path = ctx.path("understanding/gap_report.json")
    if not report_path.is_file():
        ctx.mark_done("vo_boundary_detect")
        return
    report = ctx.read_json("understanding/gap_report.json")
    lines = report.get("interviewer_lines") or []
    meta = load_vo_metadata(ctx)
    updated = False
    with logged_step("vo_boundary/detect", ctx=ctx, stage="vo_boundary_detect"):
        for line in lines:
            if not isinstance(line, dict) or line.get("delivery") != "record":
                continue
            line_id = str(line.get("line_id") or "")
            if not line_id:
                continue
            wav = ctx.path("vo_pickup") / f"{line_id}.wav"
            if not wav.is_file():
                continue
            suggestion = suggest_boundary(wav)
            row = dict(meta.setdefault("lines", {}).get(line_id) or {})
            row.update(
                {
                    "line_id": line_id,
                    "filename": f"{line_id}.wav",
                    "boundary_suggest": suggestion,
                    "boundary_detected_at": suggestion,
                }
            )
            meta["lines"][line_id] = row
            updated = True
        if updated:
            save_vo_metadata(ctx, meta)
        ctx.mark_done("vo_boundary_detect")
        ctx.log(
            "VO boundary suggestions updated",
            level="info",
            stage="vo_boundary_detect",
            detail={"kind": "gate", "lines_processed": len(meta.get("lines") or {})},
        )
