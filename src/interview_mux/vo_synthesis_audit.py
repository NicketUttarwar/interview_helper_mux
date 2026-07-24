"""Unified audit trail for gap VO synthesis (Chatterbox, mlx-audio, record)."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.run_context import RunContext

SYNTHESIS_REPORT_REL = "vo_pickup/synthesis_report.json"


def post_synthesis_qc_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = ((cfg or merged_config()).get("analysis") or {}).get("gap_vo") or {}
    raw = block.get("post_synthesis_qc") or {}
    defaults = {
        "enabled": False,
        "duration_tolerance_ratio": 0.5,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def _wav_duration_ms(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate() or 48000
            return int(1000 * wf.getnframes() / rate)
    except Exception:
        return 0


def _load_entries(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists(SYNTHESIS_REPORT_REL):
        return []
    doc = ctx.read_json(SYNTHESIS_REPORT_REL)
    if isinstance(doc, dict):
        return list(doc.get("entries") or [])
    if isinstance(doc, list):
        return list(doc)
    return []


def _persist(ctx: RunContext, entries: list[dict[str, Any]]) -> None:
    ctx.write_json(SYNTHESIS_REPORT_REL, {"entries": entries}, skip_handoff=True)


def record_synthesis(
    ctx: RunContext,
    line: dict[str, Any],
    *,
    backend: str,
    out_wav: Path | None = None,
    ref_audio: str | None = None,
    fallback_from: str | None = None,
    fallback_reason: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    line_id = str(line.get("line_id") or line.get("targets_segment_id") or "line")
    duration_ms = _wav_duration_ms(out_wav) if out_wav else 0
    est = line.get("estimated_duration_sec")
    entry: dict[str, Any] = {
        "line_id": line_id,
        "backend": backend,
        "out_wav": out_wav.relative_to(ctx.run_dir).as_posix()
        if out_wav and out_wav.is_relative_to(ctx.run_dir)
        else (str(out_wav) if out_wav else None),
        "ref_audio": ref_audio,
        "duration_ms": duration_ms,
        "estimated_duration_sec": est,
        "model_id": model_id,
    }
    if fallback_from:
        entry["fallback_from"] = fallback_from
    if fallback_reason:
        entry["fallback_reason"] = fallback_reason

    qc = post_synthesis_qc_cfg()
    if qc.get("enabled") and out_wav and est:
        tol = float(qc.get("duration_tolerance_ratio", 0.5))
        expected_ms = float(est) * 1000
        low = expected_ms * (1 - tol)
        high = expected_ms * (1 + tol)
        if duration_ms < low or duration_ms > high:
            entry["qc_pass"] = False
            entry["qc_notes"] = f"duration {duration_ms}ms outside {low:.0f}-{high:.0f}ms"
        else:
            entry["qc_pass"] = True

    entries = [e for e in _load_entries(ctx) if str(e.get("line_id")) != line_id]
    entries.append(entry)
    _persist(ctx, entries)
    return entry


def record_skipped_vo(ctx: RunContext, line_id: str, *, reason: str | None = None) -> None:
    entries = [e for e in _load_entries(ctx) if str(e.get("line_id")) != line_id]
    row: dict[str, Any] = {"line_id": line_id, "backend": "skipped"}
    if reason:
        row["fallback_reason"] = reason
    entries.append(row)
    _persist(ctx, entries)


def record_recorded_vo(
    ctx: RunContext,
    line_id: str,
    *,
    out_wav: Path,
    backend: str = "record",
) -> None:
    entries = [e for e in _load_entries(ctx) if str(e.get("line_id")) != line_id]
    entries.append(
        {
            "line_id": line_id,
            "backend": backend,
            "out_wav": out_wav.relative_to(ctx.run_dir).as_posix()
            if out_wav.is_relative_to(ctx.run_dir)
            else str(out_wav),
            "duration_ms": _wav_duration_ms(out_wav),
        }
    )
    _persist(ctx, entries)


def qc_failed(entry: dict[str, Any]) -> bool:
    return entry.get("qc_pass") is False and gap_vo_cfg().get("auto_fallback_on_qc_fail", False)
