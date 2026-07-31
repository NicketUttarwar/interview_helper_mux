"""Unified audit trail for gap VO synthesis (Chatterbox, mlx-audio, record)."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.run_context import RunContext
from interview_mux.vo_speech_qa import (
    FORBIDDEN_VO_BACKENDS,
    analyze_vo_wav,
    backend_allowed_for_vo,
    vo_speech_qa_cfg,
)

SYNTHESIS_REPORT_REL = "vo_pickup/synthesis_report.json"


def post_synthesis_qc_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return vo_speech_qa_cfg(cfg)


def _wav_duration_ms(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate() or 48000
            return int(1000 * wf.getnframes() / rate)
    except Exception:
        pass
    try:
        import subprocess

        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return max(0, int(float(proc.stdout.strip()) * 1000))
    except Exception:
        pass
    return 0


def _load_entries(ctx: RunContext) -> list[dict[str, Any]]:
    # Always read the committed report — never a stage pending overlay (EDL staging
    # must not shadow or ENOENT on vo_pickup/synthesis_report.json).
    path = ctx.final_path(*SYNTHESIS_REPORT_REL.split("/"))
    if not path.is_file():
        return []
    try:
        from interview_mux.file_store import read_json as fs_read_json

        doc = fs_read_json(path)
    except Exception:
        return []
    if isinstance(doc, dict):
        return list(doc.get("entries") or [])
    if isinstance(doc, list):
        return list(doc)
    return []


def _persist(ctx: RunContext, entries: list[dict[str, Any]]) -> None:
    from interview_mux.file_store import write_json as fs_write_json

    path = ctx.final_path(*SYNTHESIS_REPORT_REL.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(path, {"entries": entries})


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
    voice_ref_id: str | None = None,
    attempt: int | None = None,
) -> dict[str, Any]:
    if not backend_allowed_for_vo(backend):
        raise ValueError(
            f"Forbidden VO backend {backend!r}; allowed synthesis must be speech "
            f"(not {sorted(FORBIDDEN_VO_BACKENDS)})"
        )
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
    if voice_ref_id:
        entry["voice_ref_id"] = voice_ref_id
    if attempt is not None:
        entry["attempt"] = int(attempt)
    if fallback_from:
        entry["fallback_from"] = fallback_from
    if fallback_reason:
        entry["fallback_reason"] = fallback_reason

    qc = post_synthesis_qc_cfg()
    reasons: list[str] = []
    speech_ok = True
    if qc.get("enabled") and qc.get("speech_qa_enabled", True) and out_wav and out_wav.is_file():
        speech = analyze_vo_wav(out_wav, cfg=qc)
        entry["speech_qa"] = {
            "tonal_peak_ratio": speech.get("tonal_peak_ratio"),
            "speech_band_ratio": speech.get("speech_band_ratio"),
            "envelope_cv": speech.get("envelope_cv"),
        }
        if not speech.get("pass"):
            speech_ok = False
            reasons.extend(str(r) for r in (speech.get("reasons") or []))
    # Duration is advisory when speech QA passes — Chatterbox often lands shorter/longer
    # than word-count estimates without being a tone stub.
    duration_notes = ""
    if qc.get("enabled") and out_wav and est is not None:
        tol = float(qc.get("duration_tolerance_ratio", 0.5))
        expected_ms = float(est) * 1000
        low = expected_ms * (1 - tol)
        high = expected_ms * (1 + tol)
        if duration_ms < low or duration_ms > high:
            duration_notes = f"duration {duration_ms}ms outside {low:.0f}-{high:.0f}ms"
            if not speech_ok or not qc.get("speech_qa_enabled", True):
                reasons.append(duration_notes)
            else:
                entry["qc_notes_advisory"] = duration_notes
    if qc.get("enabled") and out_wav:
        if reasons:
            entry["qc_pass"] = False
            entry["qc_notes"] = "; ".join(reasons)
        else:
            entry["qc_pass"] = True
            if duration_notes and "qc_notes_advisory" not in entry:
                entry["qc_notes_advisory"] = duration_notes

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
    if not backend_allowed_for_vo(backend):
        raise ValueError(f"Forbidden VO backend {backend!r}")
    entries = [e for e in _load_entries(ctx) if str(e.get("line_id")) != line_id]
    entry: dict[str, Any] = {
        "line_id": line_id,
        "backend": backend,
        "out_wav": out_wav.relative_to(ctx.run_dir).as_posix()
        if out_wav.is_relative_to(ctx.run_dir)
        else str(out_wav),
        "duration_ms": _wav_duration_ms(out_wav),
    }
    qc = post_synthesis_qc_cfg()
    if qc.get("enabled") and qc.get("speech_qa_enabled", True) and out_wav.is_file():
        speech = analyze_vo_wav(out_wav, cfg=qc)
        entry["speech_qa"] = {
            "tonal_peak_ratio": speech.get("tonal_peak_ratio"),
            "speech_band_ratio": speech.get("speech_band_ratio"),
            "envelope_cv": speech.get("envelope_cv"),
        }
        entry["qc_pass"] = bool(speech.get("pass"))
        if not speech.get("pass"):
            entry["qc_notes"] = "; ".join(str(r) for r in (speech.get("reasons") or []))
    entries.append(entry)
    _persist(ctx, entries)


def entry_qc_failed(entry: dict[str, Any]) -> bool:
    return entry.get("qc_pass") is False


def qc_failed(entry: dict[str, Any]) -> bool:
    """True when QC failed AND config allows mlx fallback after QC fail."""
    return entry_qc_failed(entry) and bool(gap_vo_cfg().get("auto_fallback_on_qc_fail", False))


def synthesis_entry_for_line(ctx: RunContext, line_id: str) -> dict[str, Any] | None:
    for e in _load_entries(ctx):
        if str(e.get("line_id")) == str(line_id):
            return e if isinstance(e, dict) else None
    return None


def line_has_approved_vo_backend(ctx: RunContext, line_id: str) -> bool:
    entry = synthesis_entry_for_line(ctx, line_id)
    if not entry:
        return False
    backend = str(entry.get("backend") or "")
    if backend in {"skipped"} or not backend_allowed_for_vo(backend):
        return False
    if entry.get("qc_pass") is False:
        return False
    return True
