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
    from interview_mux.prompt_validation import validate_synthesis_report

    path = ctx.final_path(*SYNTHESIS_REPORT_REL.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_entries: list[dict[str, Any]] = []
    for raw in entries:
        row = dict(raw)
        backend = str(row.get("backend") or "")
        if backend != "skipped" and (
            not row.get("script_hash") or not row.get("context_hash")
        ):
            row["legacy_backend"] = backend
            row["backend"] = "skipped"
            row["fallback_reason"] = "legacy_entry_missing_copy_hashes"
        safe_entries.append(row)
    report = {"entries": safe_entries}
    errors = validate_synthesis_report(report)
    if errors:
        raise ValueError("invalid synthesis report: " + "; ".join(errors))
    fs_write_json(path, report)


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
    from interview_mux.spoken_copy_guard import (
        context_hash,
        evidence_for_line,
        normalize_script,
        script_hash,
    )

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
        "normalized_script": normalize_script(str(line.get("text") or "")),
        "script_hash": script_hash(str(line.get("text") or "")),
        "context_hash": context_hash(evidence_for_line(line)),
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
    if qc.get("enabled") and out_wav is not None and not out_wav.is_file():
        # Chatterbox/mlx-audio produced no output at all — the loudest possible
        # stub. Flag it exactly like a failed speech QA rather than silently
        # skipping the check (previously fell through with no qc_pass at all).
        speech_ok = False
        reasons.append("missing_output_wav")
    elif qc.get("enabled") and qc.get("speech_qa_enabled", True) and out_wav and out_wav.is_file():
        speech = analyze_vo_wav(out_wav, cfg=qc, script_text=str(line.get("text") or ""))
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
            # Loud at synthesis time — don't wait for vo_ingest/edl to discover
            # a stub VO line hours later in the run.
            ctx.log(
                f"VO synthesis QC failed for {line_id} (backend={backend}): {entry['qc_notes']}",
                level="warning",
                stage="g1_vo_pickup",
                detail={"line_id": line_id, "backend": backend, "reasons": reasons},
            )
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
    line: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        line = next(
            (
                dict(row)
                for row in ((report or {}).get("interviewer_lines") or [])
                if isinstance(row, dict)
                and str(row.get("line_id") or "") == str(line_id)
            ),
            {},
        )
    from interview_mux.spoken_copy_guard import (
        context_hash,
        evidence_for_line,
        normalize_script,
        script_hash,
    )

    text = str(line.get("text") or "")
    entry: dict[str, Any] = {
        "line_id": line_id,
        "backend": backend,
        "out_wav": out_wav.relative_to(ctx.run_dir).as_posix()
        if out_wav.is_relative_to(ctx.run_dir)
        else str(out_wav),
        "duration_ms": _wav_duration_ms(out_wav),
        "normalized_script": normalize_script(text),
        "script_hash": script_hash(text),
        "context_hash": context_hash(evidence_for_line(line)),
    }
    qc = post_synthesis_qc_cfg()
    if qc.get("enabled") and not out_wav.is_file():
        entry["qc_pass"] = False
        entry["qc_notes"] = "missing_output_wav"
        ctx.log(
            f"VO recording missing for {line_id} (backend={backend}): no file at upload path",
            level="warning",
            stage="g1_vo_pickup",
            detail={"line_id": line_id, "backend": backend},
        )
    elif qc.get("enabled") and qc.get("speech_qa_enabled", True) and out_wav.is_file():
        speech = analyze_vo_wav(out_wav, cfg=qc)
        entry["speech_qa"] = {
            "tonal_peak_ratio": speech.get("tonal_peak_ratio"),
            "speech_band_ratio": speech.get("speech_band_ratio"),
            "envelope_cv": speech.get("envelope_cv"),
        }
        entry["qc_pass"] = bool(speech.get("pass"))
        if not speech.get("pass"):
            entry["qc_notes"] = "; ".join(str(r) for r in (speech.get("reasons") or []))
            ctx.log(
                f"VO recording QC failed for {line_id} (backend={backend}): {entry['qc_notes']}",
                level="warning",
                stage="g1_vo_pickup",
                detail={"line_id": line_id, "backend": backend, "reasons": speech.get("reasons")},
            )
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


def synthesis_entry_matches_line(
    ctx: RunContext, line: dict[str, Any]
) -> tuple[bool, str]:
    """Return whether the approved WAV audit matches current script and context."""
    from interview_mux.spoken_copy_guard import context_hash, evidence_for_line, script_hash

    line_id = str(line.get("line_id") or line.get("targets_segment_id") or "")
    entry = synthesis_entry_for_line(ctx, line_id)
    if not entry:
        return False, "missing_synthesis_entry"
    expected_script = script_hash(str(line.get("text") or ""))
    if not entry.get("script_hash"):
        return False, "missing_script_hash"
    if str(entry.get("script_hash")) != expected_script:
        return False, "stale_script_hash"
    expected_context = context_hash(evidence_for_line(line))
    if not entry.get("context_hash"):
        return False, "missing_context_hash"
    if str(entry.get("context_hash")) != expected_context:
        # Script-matched audio is still the correct spoken take; context_hash can
        # drift when evidence enrichment changes without a text rewrite.
        return True, "script_match_stale_context"
    return True, "match"


def audible_script_hash_errors(
    ctx: RunContext, edl: dict[str, Any] | None
) -> list[str]:
    """Check every audible synthetic clip against current artifact text/context."""
    from interview_mux.spoken_copy_guard import script_hash

    errors: list[str] = []
    clips = (edl or {}).get("clips") if isinstance(edl, dict) else []
    gap_lines: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        gap_lines = {
            str(row.get("line_id") or ""): row
            for row in ((report or {}).get("interviewer_lines") or [])
            if isinstance(row, dict) and row.get("line_id")
        }
    transitions: dict[tuple[str, str], dict[str, Any]] = {}
    if ctx.artifact_exists("master/transitions.json"):
        doc = ctx.read_json("master/transitions.json")
        transitions = {
            (
                str(row.get("after_segment_id") or ""),
                str(row.get("before_segment_id") or ""),
            ): row
            for row in ((doc or {}).get("transitions") or [])
            if isinstance(row, dict)
        }
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        by_id = {
            str(row.get("segment_id")): row
            for row in ((manifest or {}).get("segments") or [])
            if isinstance(row, dict) and row.get("segment_id")
        }

    for clip in clips or []:
        if not isinstance(clip, dict) or not clip.get("source_path"):
            continue
        ctype = str(clip.get("type") or "")
        if ctype == "vo_pickup":
            lid = str(clip.get("line_id") or "")
            line = gap_lines.get(lid)
            if not line:
                errors.append(f"{lid}:missing_current_script")
                continue
        elif ctype == "transition":
            a = str(clip.get("after_segment_id") or "")
            b = str(clip.get("before_segment_id") or "")
            row = transitions.get((a, b))
            if not row:
                errors.append(f"{a}->{b}:missing_current_transition")
                continue
            line = {
                "line_id": f"tr_{a}_{b}",
                "text": str(row.get("text") or ""),
                "targets_segment_id": a,
                "placement": "after",
                "after_segment_id": a,
                "before_segment_id": b,
                "before_excerpt": (by_id.get(a) or {}).get("text"),
                "after_excerpt": (by_id.get(b) or {}).get("text"),
                "before_topic": (by_id.get(a) or {}).get("topic"),
                "after_topic": (by_id.get(b) or {}).get("topic"),
                "source_gap_ms": row.get("source_gap_ms"),
                "strict_grounding": True,
            }
        else:
            continue
        expected = script_hash(str(line.get("text") or ""))
        if clip.get("script_hash") and str(clip.get("script_hash")) != expected:
            errors.append(f"{line.get('line_id')}:edl_script_hash_stale")
        matches, reason = synthesis_entry_matches_line(ctx, line)
        if not matches:
            errors.append(f"{line.get('line_id')}:{reason}")
    return errors


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
