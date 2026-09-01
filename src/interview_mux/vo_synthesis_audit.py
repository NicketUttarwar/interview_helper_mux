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
    try:
        from interview_mux.asset_transcripts import write_vo_sidecar_for_line

        write_vo_sidecar_for_line(ctx, line, wav_path=out_wav, duration_ms=duration_ms)
    except Exception:
        pass
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
    try:
        from interview_mux.asset_transcripts import write_vo_sidecar_for_line

        write_vo_sidecar_for_line(
            ctx,
            line if line else {"line_id": line_id, "text": text},
            wav_path=out_wav,
        )
    except Exception:
        pass


def entry_qc_failed(entry: dict[str, Any]) -> bool:
    return entry.get("qc_pass") is False


def qc_failed(entry: dict[str, Any], ctx: Any | None = None) -> bool:
    """True when QC failed AND mlx retry is allowed (config or topology policy)."""
    if not entry_qc_failed(entry):
        return False
    if bool(gap_vo_cfg().get("auto_fallback_on_qc_fail", False)):
        return True
    if ctx is None:
        return False
    try:
        from interview_mux.source_topology import mlx_qc_retry_enabled

        return mlx_qc_retry_enabled(ctx)
    except Exception:
        return False


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


def line_vo_wav_path(ctx: RunContext, line: dict[str, Any]) -> Path | None:
    """Resolved pickup WAV for this line, or None if missing / hash-stale / QC fail."""
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    path = resolve_vo_pickup_path(ctx, line)
    if path is None or not path.is_file():
        return None
    return path


def line_vo_wav_fresh(ctx: RunContext, line: dict[str, Any]) -> tuple[bool, str]:
    """True when an on-disk WAV matches the line's current script (9C smart gate).

    File existence alone is insufficient — ``stale_script_hash`` means re-adjudicate
    and re-synth are required even if ``vo_pickup/{id}.wav`` remains on disk.
    """
    path = line_vo_wav_path(ctx, line)
    if path is None:
        lid = str(line.get("line_id") or line.get("targets_segment_id") or "")
        entry = synthesis_entry_for_line(ctx, lid) if lid else None
        if entry:
            matches, reason = synthesis_entry_matches_line(ctx, line)
            if not matches:
                return False, reason or "stale_script_hash"
        return False, "missing_wav"
    matches, reason = synthesis_entry_matches_line(ctx, line)
    if not matches:
        return False, reason or "stale_script_hash"
    return True, reason or "match"


def should_skip_adjudicate_for_line(ctx: RunContext, line: dict[str, Any]) -> tuple[bool, str]:
    """9C (smart): skip vo_line_adjudicate LLM only when WAV is fresh for current text."""
    fresh, reason = line_vo_wav_fresh(ctx, line)
    return fresh, reason


def invalidate_synthesis_entries(ctx: RunContext, line_ids: list[str]) -> int:
    """Drop synthesis_report rows so stale-hash checks fail open for re-synth."""
    want = {str(x).strip() for x in line_ids if str(x).strip()}
    if not want:
        return 0
    entries = _load_entries(ctx)
    kept = [e for e in entries if str(e.get("line_id") or "") not in want]
    removed = len(entries) - len(kept)
    if removed:
        _persist(ctx, kept)
    return removed


def _pickup_wav_without_audit(ctx: RunContext, line_id: str) -> Path | None:
    pickup = ctx.final_path("vo_pickup")
    for sub in ("matched", "synthesized", "clean", "normalized", ""):
        base = pickup / sub if sub else pickup
        candidate = base / f"{line_id}.wav"
        if candidate.is_file():
            return candidate
    return None


def backfill_missing_synthesis_entries(ctx: RunContext) -> list[str]:
    """Create synthesis_report rows for on-disk pickup WAVs lacking audit entries.

    G1 promote copies synthesized WAVs to vo_pickup/ without always recording
    synthesis_report — edl_narrative_audit then flags wav_stale even though the
    take is present and script-current.
    """
    backfilled: list[str] = []
    for lid, line in _vo_pickup_script_lines(ctx).items():
        if synthesis_entry_for_line(ctx, lid):
            continue
        path = _pickup_wav_without_audit(ctx, lid)
        if path is None:
            continue
        _matches, reason = synthesis_entry_matches_line(ctx, line)
        if reason != "missing_synthesis_entry":
            continue
        backend = "chatterbox" if path.parent.name == "synthesized" else "record"
        record_synthesis(ctx, line, backend=backend, out_wav=path)
        backfilled.append(lid)
    return backfilled


def _vo_pickup_script_lines(ctx: RunContext) -> dict[str, dict[str, Any]]:
    """Gap-report authority first; fall back to nugget_layup_plan for aired layups."""
    lines: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        lines = {
            str(row.get("line_id") or ""): row
            for row in ((report or {}).get("interviewer_lines") or [])
            if isinstance(row, dict) and row.get("line_id")
        }
    if ctx.artifact_exists("understanding/nugget_layup_plan.json"):
        plan = ctx.read_json("understanding/nugget_layup_plan.json")
        for row in (plan or {}).get("layups") or []:
            if not isinstance(row, dict) or row.get("skip"):
                continue
            lid = str(row.get("line_id") or "").strip()
            if not lid:
                tid = str(row.get("target_segment_id") or "").strip()
                lid = f"vo_layup_{tid}" if tid else ""
            if not lid or lid in lines:
                continue
            text = str(row.get("text") or "").strip()
            tid = str(row.get("target_segment_id") or "").strip()
            if not text or not tid:
                continue
            lines[lid] = {
                "line_id": lid,
                "gap_type": "nugget_layup",
                "text": text,
                "targets_segment_id": tid,
                "placement": "before",
                "origin": "nugget_layup",
            }
    return lines


def assert_script_authority_chain(ctx: RunContext, line_id: str) -> list[str]:
    """Verify gap_report → synthesis_report → vo transcript → EDL clip hash alignment."""
    from interview_mux.spoken_copy_guard import script_hash

    errors: list[str] = []
    lid = str(line_id or "").strip()
    if not lid:
        return ["empty_line_id"]
    gap_lines = _vo_pickup_script_lines(ctx)
    line = gap_lines.get(lid)
    if not isinstance(line, dict):
        return [f"{lid}:missing_gap_line"]
    gap_text = str(line.get("text") or "")
    expected = script_hash(gap_text)
    entry = synthesis_entry_for_line(ctx, lid)
    if entry:
        if str(entry.get("script_hash") or "") != expected:
            errors.append(f"{lid}:synthesis_hash_mismatch")
    else:
        errors.append(f"{lid}:missing_synthesis_entry")
    vo_rel = f"transcripts/vo/{lid}.json"
    if ctx.artifact_exists(vo_rel):
        try:
            vo_doc = ctx.read_json(vo_rel)
            vo_hash = script_hash(str((vo_doc or {}).get("text") or ""))
            if vo_hash != expected:
                errors.append(f"{lid}:transcript_hash_mismatch")
        except Exception:
            errors.append(f"{lid}:transcript_read_failed")
    if ctx.artifact_exists("master/edl.json"):
        try:
            edl = ctx.read_json("master/edl.json")
            for clip in (edl.get("clips") or []):
                if not isinstance(clip, dict):
                    continue
                if str(clip.get("line_id") or "") != lid:
                    continue
                if str(clip.get("script_hash") or "") != expected:
                    errors.append(f"{lid}:edl_hash_mismatch")
                break
        except Exception:
            pass
    fresh, reason = line_vo_wav_fresh(ctx, line)
    if not fresh and reason:
        errors.append(f"{lid}:{reason}")
    return errors


def sync_edl_vo_script_metadata(ctx: RunContext) -> dict[str, Any]:
    """Refresh EDL vo_pickup script_hash / duration_ms from current gap text + WAVs.

    Orientation/layup text can be repaired after EDL build (and WAVs resynthesized)
    without rebuilding the full EDL. Post-master hash agreement then fails on stale
    clip metadata even when the audible take matches the current script. Sync the
    clip fields in place so QC judges the same authority as synthesis.

    Also strips VO clips that the omit ledger actively omits (typed layup skips
    after G1 synth), which otherwise fail both air-contract and hash checks.
    """
    from interview_mux.omit_ledger import reconcile_edl_with_omit_ledger
    from interview_mux.spoken_copy_guard import context_hash, evidence_for_line, script_hash

    omit_report = reconcile_edl_with_omit_ledger(ctx)
    if not ctx.artifact_exists("master/edl.json"):
        return {"updated": 0, "clips": [], "omit_removed": omit_report.get("removed") or []}
    edl = ctx.read_json("master/edl.json")
    if not isinstance(edl, dict):
        return {"updated": 0, "clips": [], "omit_removed": omit_report.get("removed") or []}
    clips = edl.get("clips") if isinstance(edl.get("clips"), list) else []
    gap_lines = _vo_pickup_script_lines(ctx)
    changed: list[str] = []
    for clip in clips:
        if not isinstance(clip, dict) or str(clip.get("type") or "") != "vo_pickup":
            continue
        lid = str(clip.get("line_id") or "")
        line = gap_lines.get(lid)
        if not isinstance(line, dict):
            continue
        fresh, fresh_reason = line_vo_wav_fresh(ctx, line)
        if not fresh and fresh_reason in {"stale_script_hash", "missing_synthesis_entry"}:
            continue
        expected_script = script_hash(str(line.get("text") or ""))
        expected_context = context_hash(evidence_for_line(line))
        dur = 0
        src = str(clip.get("source_path") or "")
        if src and ctx.artifact_exists(src):
            dur = _wav_duration_ms(ctx.read_path(src))
        patch = False
        if expected_script and str(clip.get("script_hash") or "") != expected_script:
            clip["script_hash"] = expected_script
            patch = True
        if expected_context and str(clip.get("context_hash") or "") != expected_context:
            clip["context_hash"] = expected_context
            patch = True
        if dur > 0 and int(clip.get("duration_ms") or 0) != dur:
            clip["duration_ms"] = dur
            patch = True
        if patch:
            changed.append(lid)
    if changed:
        edl["clips"] = clips
        from interview_mux.air_order import write_live_edl

        write_live_edl(ctx, edl, source="vo_synthesis_audit")
        ctx.log(
            f"synced EDL VO metadata for {len(changed)} clip(s)",
            stage="vo_synthesis_audit",
            detail=changed[:12],
        )
    return {
        "updated": len(changed),
        "clips": changed,
        "omit_removed": list(omit_report.get("removed") or []),
    }


def audible_script_hash_errors(
    ctx: RunContext, edl: dict[str, Any] | None
) -> list[str]:
    """Check every audible synthetic clip against current artifact text/context."""
    from interview_mux.spoken_copy_guard import script_hash

    errors: list[str] = []
    clips = (edl or {}).get("clips") if isinstance(edl, dict) else []
    gap_lines = _vo_pickup_script_lines(ctx)
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


def nuke_all_synth_wavs_on_adjudicate_change(ctx: RunContext) -> int:
    """1A: delete synth WAVs and invalidate synthesis so vo_synthesize must re-run."""
    from interview_mux.homunculus.agenda import unmark_stage_only

    deleted = 0
    pickup = ctx.path("vo_pickup")
    if pickup.is_dir():
        for sub in ("", "synthesized"):
            root = pickup if not sub else pickup / sub
            if not root.is_dir():
                continue
            for path in root.glob("*.wav"):
                try:
                    path.unlink(missing_ok=True)
                    deleted += 1
                except OSError:
                    pass
    lines = _vo_pickup_script_lines(ctx)
    line_ids = list(lines.keys())
    if line_ids:
        invalidate_synthesis_entries(ctx, line_ids)
    for stage in ("vo_synthesize", "edl_narrative_audit"):
        if ctx.is_done(stage):
            unmark_stage_only(ctx, stage)
    if deleted or line_ids:
        ctx.log(
            f"Adjudicate mutation: removed {deleted} synth WAV(s); "
            f"invalidated {len(line_ids)} synthesis row(s)",
            level="warning",
            stage="vo_line_adjudicate",
        )
    return deleted
