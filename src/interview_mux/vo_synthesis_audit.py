"""Unified audit trail for gap VO synthesis (Chatterbox, mlx-audio, record)."""

from __future__ import annotations

import hashlib
import os
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


class VoScriptWavRebindError(ValueError):
    """Raised when a new script hash is stamped onto unchanged WAV bytes.

    Text rewrites must re-synthesize (or re-record) audio before the audit
    trail, EDL, or mix may treat the take as current.
    """


# (path, size, mtime_ns) -> digest. The completeness checks hash the same few
# WAVs hundreds of times per conductor pass; a changed file changes its size or
# mtime, so the key can never serve stale bytes (ISSUES entry 60).
_SHA_CACHE: dict[tuple[str, int, int], str] = {}
_SHA_CACHE_MAX = 4096


def wav_content_sha256(path: Path) -> str:
    """SHA-256 of WAV file bytes — binds audit script_hash to audible content."""
    try:
        st = os.stat(path)
        key = (os.path.normcase(os.path.abspath(path)), int(st.st_size), int(st.st_mtime_ns))
    except OSError:
        key = None
    if key is not None:
        hit = _SHA_CACHE.get(key)
        if hit is not None:
            return hit
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    out = digest.hexdigest()
    if key is not None:
        if len(_SHA_CACHE) >= _SHA_CACHE_MAX:
            _SHA_CACHE.clear()
        _SHA_CACHE[key] = out
    return out


def committed_rel_for_wav(ctx: RunContext, out_wav: Path) -> str:
    """Store audit paths as committed run-relative paths (never ``.pending_writes/…``)."""
    try:
        rel = out_wav.relative_to(ctx.run_dir).as_posix()
    except ValueError:
        return out_wav.as_posix()
    prefix = ".pending_writes/"
    if rel.startswith(prefix):
        rest = rel[len(prefix) :]
        if "/" in rest:
            # .pending_writes/<stage>/master/... → master/...
            rel = rest.split("/", 1)[1]
    return rel


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
    wav_just_rendered: bool = False,
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

    new_script = script_hash(str(line.get("text") or ""))
    wav_sha: str | None = None
    if out_wav is not None and out_wav.is_file():
        wav_sha = wav_content_sha256(out_wav)
    existing = synthesis_entry_for_line(ctx, line_id)
    if existing and isinstance(existing, dict):
        old_script = str(existing.get("script_hash") or "")
        old_sha = str(existing.get("wav_sha256") or "")
        if old_script and old_script != new_script:
            # Script rewrite: only accept when a renderer just wrote new audio.
            if not wav_just_rendered:
                raise VoScriptWavRebindError(
                    f"Cannot rebind new script to existing VO audit for {line_id} "
                    f"without re-synthesis (stale_wav_script_rebind). "
                    f"Re-run vo_synthesize so the WAV matches the current text."
                )
            if old_sha and wav_sha and old_sha == wav_sha:
                # Renderer claimed a new take but bytes are identical — still refuse.
                raise VoScriptWavRebindError(
                    f"Script changed for {line_id} but WAV bytes are unchanged "
                    f"(stale_wav_script_rebind). Re-synthesize before mixing."
                )

    duration_ms = _wav_duration_ms(out_wav) if out_wav else 0
    est = line.get("estimated_duration_sec")
    entry: dict[str, Any] = {
        "line_id": line_id,
        "backend": backend,
        "out_wav": committed_rel_for_wav(ctx, out_wav) if out_wav else None,
        "ref_audio": ref_audio,
        "duration_ms": duration_ms,
        "estimated_duration_sec": est,
        "model_id": model_id,
        "normalized_script": normalize_script(str(line.get("text") or "")),
        "script_hash": new_script,
        "context_hash": context_hash(evidence_for_line(line)),
    }
    if wav_sha:
        entry["wav_sha256"] = wav_sha
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
        "out_wav": committed_rel_for_wav(ctx, out_wav),
        "duration_ms": _wav_duration_ms(out_wav),
        "normalized_script": normalize_script(text),
        "script_hash": script_hash(text),
        "context_hash": context_hash(evidence_for_line(line)),
    }
    if out_wav.is_file():
        entry["wav_sha256"] = wav_content_sha256(out_wav)
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
    """Return whether the approved WAV audit matches current script and context.

    Also requires ``wav_sha256`` binding so a later text rewrite cannot silently
    re-stamp the audit onto old audio and pass mix/EDL gates.
    """
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
    bound_sha = str(entry.get("wav_sha256") or "").strip()
    if not bound_sha:
        return False, "missing_wav_content_hash"
    wav_path = _audited_wav_path(ctx, entry, line)
    if wav_path is None or not wav_path.is_file():
        return False, "missing_wav"
    if wav_content_sha256(wav_path) != bound_sha:
        return False, "wav_content_mismatch"
    expected_context = context_hash(evidence_for_line(line))
    if not entry.get("context_hash"):
        return False, "missing_context_hash"
    if str(entry.get("context_hash")) != expected_context:
        # Script-matched audio is still the correct spoken take; context_hash can
        # drift when evidence enrichment changes without a text rewrite.
        return True, "script_match_stale_context"
    return True, "match"


def _candidate_rels_for_out_wav(rel: str) -> list[str]:
    """Expand a stored ``out_wav`` into committed + pending fallbacks."""
    raw = str(rel or "").strip().replace("\\", "/").lstrip("./")
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def _add(item: str) -> None:
        norm = item.replace("\\", "/").lstrip("./")
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)

    _add(raw)
    prefix = ".pending_writes/"
    if raw.startswith(prefix):
        rest = raw[len(prefix) :]
        if "/" in rest:
            _add(rest.split("/", 1)[1])
    return out


def _audited_wav_path(
    ctx: RunContext, entry: dict[str, Any], line: dict[str, Any]
) -> Path | None:
    """Resolve on-disk WAV for an audit row without calling resolve_vo_pickup_path.

    ``resolve_vo_pickup_path`` itself consults ``synthesis_entry_matches_line``, so
    path lookup here must stay acyclic. Prefer committed paths when audit still
    names a flushed ``.pending_writes/<stage>/…`` shadow.

    When ``wav_sha256`` is bound, prefer any candidate whose bytes match that
    digest. A mid-flight re-synth can overwrite ``synthesized/`` while the seated
    ``vo_pickup/{id}.wav`` still holds the audited take — returning the overwritten
    path first falsely yields ``wav_content_mismatch`` and reopens G1.
    """
    candidates: list[Path] = []
    seen: set[str] = set()

    def _add(cand: Path) -> None:
        # Existence first, then a lexical identity. Path.resolve() walks every
        # component through the filesystem on Windows (OneDrive paths make it
        # worse) and was 76 % of the conductor's time between stages on the
        # one-hour run (ISSUES entry 60). Run paths carry no symlinks, so
        # abspath + normcase names the same file.
        if not cand.is_file():
            return
        key = os.path.normcase(os.path.abspath(str(cand)))
        if key in seen:
            return
        seen.add(key)
        candidates.append(cand)

    # Stage shadow dirs that exist, listed once per call. Probing every stage
    # dir x every sub-path cost hundreds of stat() calls per VO line on a run
    # with ~70 staging dirs (ISSUES entry 60).
    try:
        pending_root = ctx.path(".pending_writes")
        pending_dirs = (
            [e.path for e in os.scandir(pending_root) if e.is_dir()]
            if pending_root.is_dir()
            else []
        )
    except OSError:
        pending_dirs = []

    def _pending_with(first: str) -> list[Path]:
        return [Path(d) for d in pending_dirs if os.path.isdir(os.path.join(d, first))]

    rel = str(entry.get("out_wav") or "").strip()
    for candidate_rel in _candidate_rels_for_out_wav(rel):
        for resolver in (
            lambda r=candidate_rel: ctx.final_path(*r.split("/")),
            lambda r=candidate_rel: ctx.read_path(*r.split("/")),
            lambda r=candidate_rel: ctx.path(*r.split("/")),
        ):
            try:
                _add(resolver())
            except Exception:
                continue
        # Probe pending stage shadows for the same rel. EDL bridge heal can
        # promote stale bytes into committed vo_pickup/ while the sha-bound take
        # remains under .pending_writes/vo_synthesize/… (exec_11165 seated_bind_stale).
        try:
            if candidate_rel:
                first = candidate_rel.split("/", 1)[0]
                for stage_dir in _pending_with(first):
                    _add(stage_dir.joinpath(*candidate_rel.split("/")))
        except Exception:
            pass
    lid = str(line.get("line_id") or entry.get("line_id") or "").strip()
    seg = str(line.get("targets_segment_id") or "").strip()
    # Spoken transition WAVs live under master/transitions/, not vo_pickup/.
    if lid.startswith("tr_"):
        for sub in ("", "synthesized"):
            base = ctx.final_path("master", "transitions", sub) if sub else ctx.final_path(
                "master", "transitions"
            )
            _add(base / f"{lid}.wav")
    pickup = ctx.final_path("vo_pickup")
    for sub in ("matched", "synthesized", "clean", "normalized", ""):
        base = pickup / sub if sub else pickup
        for key in (lid, seg):
            if not key:
                continue
            _add(base / f"{key}.wav")
    # Pending vo_pickup shadows by line id (covers audits with blank/odd out_wav).
    try:
        if lid:
            for stage_dir in _pending_with("vo_pickup"):
                for sub in ("matched", "synthesized", "clean", "normalized", ""):
                    base = (
                        stage_dir / "vo_pickup" / sub
                        if sub
                        else stage_dir / "vo_pickup"
                    )
                    _add(base / f"{lid}.wav")
    except Exception:
        pass
    if not candidates:
        return None
    bound = str(entry.get("wav_sha256") or "").strip()
    if bound:
        for cand in candidates:
            try:
                if wav_content_sha256(cand) == bound:
                    return cand
            except Exception:
                continue
        # Bound sha unmatched — honest miss (never return wrong bytes).
        return None
    return candidates[0]

def canonicalize_synthesis_out_wav_paths(ctx: RunContext) -> list[str]:
    """Rewrite synthesis_report ``out_wav`` to committed files that exist on disk.

    After EDL/staging flush, audits must not keep dead ``.pending_writes/…`` paths.
    """
    entries = _load_entries(ctx)
    if not entries:
        return []
    updated: list[str] = []
    rewritten: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            rewritten.append(raw)
            continue
        row = dict(raw)
        lid = str(row.get("line_id") or "").strip()
        line = {"line_id": lid, "targets_segment_id": lid}
        resolved = _audited_wav_path(ctx, row, line)
        if resolved is not None and resolved.is_file():
            new_rel = committed_rel_for_wav(ctx, resolved)
            old_rel = str(row.get("out_wav") or "").strip()
            if new_rel and new_rel != old_rel:
                row["out_wav"] = new_rel
                updated.append(lid or new_rel)
        rewritten.append(row)
    if updated:
        _persist(ctx, rewritten)
        ctx.log(
            f"canonicalized synthesis out_wav for {len(updated)} line(s)",
            level="info",
            stage="vo_synthesis_audit",
            detail={"line_ids": updated[:12]},
        )
    return updated


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
    """Do not stamp current gap text onto orphan WAVs.

    Earlier builds forged ``synthesis_report`` rows for on-disk pickups so EDL
    hash checks would pass after G1 promote. That allowed rewritten scripts to
    ship with stale audio. Orphan WAVs without an audit must be re-synthesized
    (``wav_just_rendered=True``) before they can match.
    """
    orphans: list[str] = []
    for lid, line in _vo_pickup_script_lines(ctx).items():
        if synthesis_entry_for_line(ctx, lid):
            continue
        path = _pickup_wav_without_audit(ctx, lid)
        if path is None:
            continue
        orphans.append(lid)
    if orphans:
        ctx.log(
            "VO pickup WAV(s) lack synthesis audit — refusing silent backfill; "
            f"re-synthesize required: {orphans[:8]}",
            level="warning",
            stage="g1_vo_pickup",
            detail={"orphan_line_ids": orphans[:24]},
        )
    return []


def purge_stale_vo_wavs_for_script_drift(ctx: RunContext) -> list[str]:
    """Delete pickup WAVs whose audit no longer matches current gap script.

    Call before mix / when gap text is rewritten so vo_synthesize must regenerate.
    """
    purged: list[str] = []
    for lid, line in _vo_pickup_script_lines(ctx).items():
        matches, reason = synthesis_entry_matches_line(ctx, line)
        if matches:
            continue
        if reason == "missing_wav" and not _pickup_wav_without_audit(ctx, lid):
            # No file and no usable audit path — nothing to purge.
            if not synthesis_entry_for_line(ctx, lid):
                continue
        removed_files = _delete_pickup_wavs_for_line(ctx, lid)
        invalidate_synthesis_entries(ctx, [lid])
        purged.append(lid)
        ctx.log(
            f"Purged stale VO for {lid} ({reason}); re-synthesis required",
            level="warning",
            stage="vo_synthesize",
            detail={"line_id": lid, "reason": reason, "removed_files": removed_files},
        )
    return purged


# Stages unmarked so the pipeline re-runs: re-adjudicate → re-synth → re-seat.
_SPOKEN_TEXT_CASCADE_STAGES: tuple[str, ...] = (
    "vo_line_adjudicate",
    "vo_synthesize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
    "mix",
    "junction_snip_qa",
    "master_finalize",
)

# Transition-bridge text drift reseats audio/EDL/mix — not VO line adjudication.
# Unmarking vo_line_adjudicate here trips 5A stage-order migration which then
# wipes music stages (mmaudio_sfx+) whose artifacts are still valid.
_TRANSITION_SPOKEN_TEXT_CASCADE_STAGES: tuple[str, ...] = (
    "vo_synthesize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
    "mix",
    "junction_snip_qa",
    "master_finalize",
)

GAP_REPORT_REL = "understanding/gap_report.json"


def gap_spoken_texts(report: dict[str, Any] | None) -> dict[str, str]:
    """Map line_id → spoken text from a gap_report document."""
    out: dict[str, str] = {}
    if not isinstance(report, dict):
        return out
    for row in report.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if not lid:
            continue
        out[lid] = str(row.get("text") or "")
    return out


def detect_spoken_text_line_ids(
    prior_report: dict[str, Any] | None,
    new_report: dict[str, Any] | None,
) -> list[str]:
    """Line ids whose spoken ``text`` changed, appeared, or disappeared."""
    prior = gap_spoken_texts(prior_report)
    new = gap_spoken_texts(new_report)
    changed: list[str] = []
    for lid, text in new.items():
        if prior.get(lid) != text:
            changed.append(lid)
    for lid in prior:
        if lid not in new:
            changed.append(lid)
    return sorted(set(changed))


def _delete_pickup_wavs_for_line(ctx: RunContext, line_id: str) -> int:
    removed = 0
    pickup = ctx.final_path("vo_pickup")
    for sub in ("matched", "synthesized", "clean", "normalized", ""):
        base = pickup / sub if sub else pickup
        candidate = base / f"{line_id}.wav"
        if candidate.is_file():
            try:
                candidate.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _unmark_spoken_text_cascade_stages(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_guardrails import (
        invalidation_allowed_downstream,
        music_clear_blocked,
    )
    from interview_mux.homunculus.agenda import unmark_stage_only

    unmarked: list[str] = []
    source = "gap_report_write"
    for stage in _SPOKEN_TEXT_CASCADE_STAGES:
        if not ctx.is_done(stage):
            continue
        if not invalidation_allowed_downstream(source, stage):
            continue
        if music_clear_blocked(ctx, stage, source=source):
            continue
        unmark_stage_only(ctx, stage)
        unmarked.append(stage)
    return unmarked


def unmark_transition_spoken_text_cascade_stages(ctx: RunContext) -> list[str]:
    """Unmark synth→EDL→mix after transition-bridge text drift (not adjudicate)."""
    from interview_mux.delivery_guardrails import (
        invalidation_allowed_downstream,
        music_clear_blocked,
    )
    from interview_mux.homunculus.agenda import unmark_stage_only

    unmarked: list[str] = []
    source = "transitions_write"
    for stage in _TRANSITION_SPOKEN_TEXT_CASCADE_STAGES:
        if not ctx.is_done(stage):
            continue
        if not invalidation_allowed_downstream(source, stage):
            continue
        if music_clear_blocked(ctx, stage, source=source):
            continue
        unmark_stage_only(ctx, stage)
        unmarked.append(stage)
    return unmarked


def unmark_vo_script_cascade_stages(ctx: RunContext) -> list[str]:
    """Public: unmark adjudicate → synth → EDL/mix after spoken-script drift."""
    return _unmark_spoken_text_cascade_stages(ctx)


def _clear_g1_complete_milestone(ctx: RunContext) -> None:
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if not isinstance(meta, dict):
            return
        milestones = meta.get("journey_milestones")
        if not isinstance(milestones, dict) or not milestones.get("g1_complete"):
            return
        milestones["g1_complete"] = False
        meta["journey_milestones"] = milestones
        ctx.write_json("run_meta.json", meta, skip_handoff=True)
    except Exception:
        pass


def propagate_spoken_text_change(
    ctx: RunContext,
    *,
    prior_report: dict[str, Any] | None = None,
    new_report: dict[str, Any] | None = None,
    line_ids: list[str] | None = None,
    stage: str = "spoken_text",
) -> dict[str, Any]:
    """Canonical cascade: spoken text change → stale → purge → re-adjudicate/synth/reseat.

    Does not invoke LLM/Chatterbox itself — unmarks producer/consumer stages so the
    normal pipeline re-runs adjudicate (if needed) → synthesize → EDL/mix reseat.

    Lines whose *new* text still matches an on-disk WAV audit are left alone
    (e.g. synth guard writeback that aligns gap_report to the take just rendered).
    """
    if getattr(ctx, "_spoken_text_cascade_depth", 0):
        return {"changed": [], "purged": [], "unmarked": [], "skipped": "reentrant"}

    if line_ids is None:
        if prior_report is not None or new_report is not None:
            line_ids = detect_spoken_text_line_ids(prior_report, new_report)
        else:
            line_ids = []
            for lid, line in _vo_pickup_script_lines(ctx).items():
                fresh, _reason = line_vo_wav_fresh(ctx, line)
                if not fresh and (
                    _pickup_wav_without_audit(ctx, lid) is not None
                    or synthesis_entry_for_line(ctx, lid) is not None
                ):
                    line_ids.append(lid)

    want = sorted({str(x).strip() for x in (line_ids or []) if str(x).strip()})
    if not want:
        return {"changed": [], "purged": [], "unmarked": []}

    report = new_report
    if not isinstance(report, dict):
        report = (
            ctx.read_json(GAP_REPORT_REL)
            if ctx.artifact_exists(GAP_REPORT_REL)
            else {}
        )
    by_id = {
        str(row.get("line_id") or ""): row
        for row in ((report or {}).get("interviewer_lines") or [])
        if isinstance(row, dict) and row.get("line_id")
    }
    prior_texts = gap_spoken_texts(prior_report)

    stale: list[str] = []
    schedule_unmark = False
    for lid in want:
        line = by_id.get(lid)
        has_entry = synthesis_entry_for_line(ctx, lid) is not None
        has_wav = _pickup_wav_without_audit(ctx, lid) is not None
        if isinstance(line, dict):
            fresh, _reason = line_vo_wav_fresh(ctx, line)
            if fresh:
                continue
            prior_text = prior_texts.get(lid)
            new_text = str(line.get("text") or "")
            if has_entry:
                # Audit-bound take no longer matches current spoken text.
                stale.append(lid)
            elif has_wav and prior_text is not None and prior_text != new_text:
                # Replaced spoken copy while an unbound WAV remains on disk.
                stale.append(lid)
            else:
                # New line / first publish — no purge; still reseat if consumers done.
                schedule_unmark = True
        else:
            # Removed from gap_report — drop orphan audio/audit.
            if has_wav or has_entry:
                stale.append(lid)

    if not stale and not schedule_unmark:
        return {"changed": want, "purged": [], "unmarked": [], "skipped": "audio_fresh"}

    if schedule_unmark and not stale:
        # Only unmark when a downstream consumer already completed — otherwise a
        # first gap_report write would thrash empty stage_done markers for no gain.
        if not any(ctx.is_done(sid) for sid in _SPOKEN_TEXT_CASCADE_STAGES):
            return {"changed": want, "purged": [], "unmarked": [], "skipped": "no_audio_yet"}

    setattr(ctx, "_spoken_text_cascade_depth", 1)
    try:
        purged: list[str] = []
        for lid in stale:
            removed_files = _delete_pickup_wavs_for_line(ctx, lid)
            invalidate_synthesis_entries(ctx, [lid])
            purged.append(lid)
            ctx.log(
                f"Purged stale VO for {lid} (spoken_text_change); re-synthesis required",
                level="warning",
                stage=stage or "spoken_text",
                detail={"line_id": lid, "reason": "spoken_text_change", "removed_files": removed_files},
            )
        unmarked = _unmark_spoken_text_cascade_stages(ctx) if (purged or schedule_unmark) else []
        if purged:
            _clear_g1_complete_milestone(ctx)
        if purged or unmarked:
            ctx.log(
                "Spoken text change cascade: "
                f"purged={len(purged)} unmarked={unmarked[:6]}",
                level="warning",
                stage=stage or "spoken_text",
                detail={"purged": purged[:24], "unmarked": unmarked},
            )
        return {"changed": want, "purged": purged, "unmarked": unmarked}
    finally:
        setattr(ctx, "_spoken_text_cascade_depth", 0)


def maybe_propagate_gap_spoken_text_change(
    ctx: RunContext,
    *,
    prior_report: dict[str, Any] | None,
    new_report: dict[str, Any],
    stage: str | None = None,
) -> dict[str, Any]:
    """Post-write hook for ``understanding/gap_report.json`` mutations."""
    if not isinstance(new_report, dict):
        return {"changed": [], "purged": [], "unmarked": []}
    changed = detect_spoken_text_line_ids(prior_report, new_report)
    if not changed:
        return {"changed": [], "purged": [], "unmarked": []}
    return propagate_spoken_text_change(
        ctx,
        prior_report=prior_report,
        new_report=new_report,
        line_ids=changed,
        stage=stage or "gap_report_write",
    )


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
    """Refresh EDL vo_pickup + transition script_hash / duration_ms from authority.

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
    changed: list[str] = []
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        ctype = str(clip.get("type") or "")
        if ctype == "vo_pickup":
            lid = str(clip.get("line_id") or "")
            line = gap_lines.get(lid)
            if not isinstance(line, dict):
                continue
            fresh, fresh_reason = line_vo_wav_fresh(ctx, line)
            if not fresh and fresh_reason in {"stale_script_hash", "missing_synthesis_entry"}:
                continue
            expected_script = script_hash(str(line.get("text") or ""))
            expected_context = context_hash(evidence_for_line(line))
            label = lid
        elif ctype == "transition":
            a = str(clip.get("after_segment_id") or "")
            b = str(clip.get("before_segment_id") or "")
            row = transitions.get((a, b))
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            # Only restamp when a seated WAV exists (or empty seat with duration 0).
            src = str(clip.get("source_path") or "")
            if src and not ctx.artifact_exists(src):
                continue
            expected_script = script_hash(text)
            expected_context = None
            label = f"tr_{a}_{b}"
            line = None
        else:
            continue
        dur = 0
        src = str(clip.get("source_path") or "")
        if src and ctx.artifact_exists(src):
            dur = _wav_duration_ms(ctx.read_path(src))
        patch = False
        if expected_script and str(clip.get("script_hash") or "") != expected_script:
            clip["script_hash"] = expected_script
            patch = True
        if ctype == "vo_pickup" and expected_context and str(clip.get("context_hash") or "") != expected_context:
            clip["context_hash"] = expected_context
            patch = True
        if dur > 0 and int(clip.get("duration_ms") or 0) != dur:
            clip["duration_ms"] = dur
            patch = True
        if patch:
            changed.append(label)
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



def edl_seat_preflight(ctx: RunContext) -> dict[str, Any]:
    """Pre-mix/preview/finalize seat authority: sync stamps, heal paths, fail-closed.

    Sync EDL script_hash/duration/source_path when WAVs are fresh. Never skip a
    required seated line to unblock mix (empty-seat skip only for omitted seats).
    """
    report: dict[str, Any] = {"ok": True, "errors": [], "synced": {}}
    try:
        from interview_mux.transition_vo import (
            ensure_pre_mix_transition_integrity,
            restamp_edl_transition_source_paths,
        )

        try:
            ensure_pre_mix_transition_integrity(ctx, synthesize=False)
        except Exception as exc:
            report.setdefault("warnings", []).append(f"transition_integrity:{exc}")
        try:
            restamp_edl_transition_source_paths(ctx)
        except Exception as exc:
            report.setdefault("warnings", []).append(f"restamp:{exc}")
    except Exception:
        pass
    try:
        report["synced"] = sync_edl_vo_script_metadata(ctx)
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"sync_failed:{exc}")
        return report
    try:
        errors = audible_script_hash_errors(
            ctx,
            ctx.read_json("master/edl.json")
            if ctx.artifact_exists("master/edl.json")
            else None,
        )
        hard = [
            e
            for e in errors
            if any(
                tok in str(e)
                for tok in (
                    "missing",
                    "stale",
                    "wav_missing",
                    "script_hash",
                    "not_fresh",
                )
            )
        ]
        if hard:
            report["ok"] = False
            report["errors"].extend(hard[:20])
    except Exception as exc:
        report.setdefault("warnings", []).append(f"hash_check:{exc}")
    return report


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
                try:
                    from interview_mux.hosted_vo_authority import (
                        ORIENTATION_LINE_ID,
                        decide_orientation,
                        identify_hosted_vo_floor,
                    )

                    if lid == ORIENTATION_LINE_ID:
                        gap_doc = (
                            ctx.read_json("understanding/gap_report.json")
                            if ctx.artifact_exists("understanding/gap_report.json")
                            else {}
                        )
                        ordered: list[str] = []
                        if ctx.artifact_exists("master/selection.json"):
                            sel = ctx.read_json("master/selection.json")
                            if isinstance(sel, dict):
                                ordered = [
                                    str(x)
                                    for x in (sel.get("ordered_segment_ids") or [])
                                    if x
                                ]
                        if isinstance(gap_doc, dict):
                            decision = decide_orientation(ctx, gap_doc, ordered)
                            if decision.disposition in {"HEARD_KEEP", "HOLLOW_MINT"}:
                                ident = identify_hosted_vo_floor(ctx, persist=True)
                                errors.append(
                                    f"{lid}:missing_current_script:remint_needed:"
                                    f"{decision.disposition}:{ident.resume_producer}"
                                )
                                continue
                except Exception:
                    pass
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


def nuke_all_synth_wavs_on_adjudicate_change(
    ctx: RunContext,
    *,
    line_ids: list[str] | None = None,
) -> int:
    """Delete gap-VO pickup WAVs so vo_synthesize re-runs for changed lines.

    Never glob-deletes ``vo_pickup/*.wav`` (that wiped transition ``tr_*`` bridges
    and every untouched layup WAV — exec_11130 thrash). Only script line ids from
    gap_report (or an explicit ``line_ids`` subset) are removed.
    """
    script_lines = _vo_pickup_script_lines(ctx)
    if line_ids is None:
        targets = list(script_lines.keys())
    else:
        targets = [str(x) for x in line_ids if str(x).strip()]
    deleted = 0
    for lid in targets:
        deleted += int(_delete_pickup_wavs_for_line(ctx, lid) or 0)
    if targets:
        invalidate_synthesis_entries(ctx, targets)
    unmarked = _unmark_spoken_text_cascade_stages(ctx)
    _clear_g1_complete_milestone(ctx)
    if deleted or targets:
        ctx.log(
            f"Adjudicate mutation: removed {deleted} synth WAV(s); "
            f"invalidated {len(targets)} synthesis row(s); "
            f"unmarked={unmarked[:6]}",
            level="warning",
            stage="vo_line_adjudicate",
            detail={"line_ids": targets[:24]},
        )
    return deleted
