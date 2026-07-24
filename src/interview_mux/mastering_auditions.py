"""Micro-render auditions: judge candidates on rendered audio, not plan text.

Spec: docs/cross-cutting/mastering-audition-loop.md
Schema: mastering_audition_manifest.schema.json
Artifact: mastering/auditions/{candidate_id}/manifest.json

Manifest planning is pure and testable; rendering is a separate step so the
plan can be inspected (and smoke-tested) without touching ffmpeg.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext

AUDITION_DIR = "mastering/auditions"
WINDOW_KINDS: tuple[str, ...] = ("opening", "hinge", "dense")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def audition_rel(candidate_id: str, name: str = "manifest.json") -> str:
    return f"{AUDITION_DIR}/{candidate_id}/{name}"


def plan_hash(candidate: dict[str, Any]) -> str:
    payload = {
        "cold_open": candidate.get("cold_open"),
        "ordered_segment_ids": candidate.get("ordered_segment_ids"),
        "vo_line_ids": candidate.get("vo_line_ids"),
        "sfx_cue_refs": candidate.get("sfx_cue_refs"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def select_audition_candidates(
    candidates: list[dict[str, Any]],
    *,
    eligible_ids: set[str] | frozenset[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Top N feasible, integrity-clean candidates, in the order they were ranked."""
    conf = gate_cfg("auditions", cfg)
    limit = max(1, int(conf.get("max_auditions") or 3))
    pool = [
        c
        for c in candidates
        if eligible_ids is None or str(c.get("candidate_id")) in eligible_ids
    ]
    return pool[:limit]


def plan_windows(
    candidate: dict[str, Any],
    segments: dict[str, dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Pick the opening, one hinge, and the densest speech region.

    A candidate with no cold open still gets an `opening` window — how the episode
    begins is exactly what the panel needs to hear.
    """
    conf = gate_cfg("auditions", cfg)
    lengths = dict(conf.get("window_ms") or {})
    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or [])]
    cold = candidate.get("cold_open") if isinstance(candidate.get("cold_open"), dict) else {}

    windows: list[dict[str, Any]] = []
    windows.append(
        _opening_window(cold, ordered, segments, int(lengths.get("opening") or 20000))
    )
    hinge = _hinge_window(candidate, ordered, segments, int(lengths.get("hinge") or 20000))
    if hinge:
        windows.append(hinge)
    dense = _dense_window(ordered, segments, int(lengths.get("dense") or 30000))
    if dense:
        windows.append(dense)

    total_cap = int(conf.get("total_max_ms") or 90000)
    return _fit_total(windows, total_cap)


def _segment_span(segments: dict[str, dict[str, Any]], sid: str) -> tuple[int, int] | None:
    seg = segments.get(sid)
    if not seg:
        return None
    start, end = seg.get("start_ms"), seg.get("end_ms")
    if start is None or end is None:
        return None
    return int(start), int(end)


def _opening_window(
    cold: dict[str, Any],
    ordered: list[str],
    segments: dict[str, dict[str, Any]],
    length_ms: int,
) -> dict[str, Any]:
    kind = str(cold.get("kind") or "none")
    refs: list[str] = []
    span: tuple[int, int] | None = None
    note: str | None = None

    if kind in {"vo_clone_open", "vo_plus_segment"} and cold.get("vo_line_id"):
        refs.append(str(cold["vo_line_id"]))
    if kind in {"segment_hook", "vo_plus_segment"} and cold.get("segment_id"):
        sid = str(cold["segment_id"])
        refs.append(sid)
        span = _segment_span(segments, sid)
    if not refs:
        note = "no cold open — rendering the body start instead"
        if ordered:
            refs.append(ordered[0])
            span = _segment_span(segments, ordered[0])

    window: dict[str, Any] = {
        "kind": "opening",
        "duration_ms": length_ms,
        "source_refs": refs,
        "note": note,
    }
    if span:
        window["source_start_ms"] = span[0]
        window["source_end_ms"] = min(span[1], span[0] + length_ms)
        window["duration_ms"] = window["source_end_ms"] - window["source_start_ms"]
    return window


def _hinge_window(
    candidate: dict[str, Any],
    ordered: list[str],
    segments: dict[str, dict[str, Any]],
    length_ms: int,
) -> dict[str, Any] | None:
    """Render across a planned boundary so the panel hears the actual seam."""
    boundaries = [str(b) for b in (candidate.get("chapter_boundary_segment_ids") or [])]
    hinge_at = next((b for b in boundaries if b in ordered), None)
    if hinge_at is None and len(ordered) >= 2:
        hinge_at = ordered[len(ordered) // 2]
    if hinge_at is None:
        return None
    idx = ordered.index(hinge_at)
    before = ordered[idx - 1] if idx > 0 else None
    span = _segment_span(segments, hinge_at)
    window: dict[str, Any] = {
        "kind": "hinge",
        "duration_ms": length_ms,
        "source_refs": [r for r in (before, hinge_at) if r],
        "note": "spans one planned transition",
    }
    if span:
        window["source_start_ms"] = span[0]
        window["source_end_ms"] = min(span[1], span[0] + length_ms)
        window["duration_ms"] = max(0, window["source_end_ms"] - window["source_start_ms"])
    return window


def _dense_window(
    ordered: list[str], segments: dict[str, dict[str, Any]], length_ms: int
) -> dict[str, Any] | None:
    """Densest speech region by words per second, falling back to the longest segment."""
    best: tuple[float, str] | None = None
    for sid in ordered:
        seg = segments.get(sid) or {}
        span = _segment_span(segments, sid)
        if not span:
            continue
        duration_s = max(0.001, (span[1] - span[0]) / 1000.0)
        words = seg.get("word_count")
        density = float(words) / duration_s if words else duration_s / 1000.0
        if best is None or density > best[0]:
            best = (density, sid)
    if best is None:
        return None
    sid = best[1]
    span = _segment_span(segments, sid)
    window: dict[str, Any] = {
        "kind": "dense",
        "duration_ms": length_ms,
        "source_refs": [sid],
        "note": "densest speech region",
    }
    if span:
        window["source_start_ms"] = span[0]
        window["source_end_ms"] = min(span[1], span[0] + length_ms)
        window["duration_ms"] = max(0, window["source_end_ms"] - window["source_start_ms"])
    return window


def _fit_total(windows: list[dict[str, Any]], total_cap: int) -> list[dict[str, Any]]:
    """Trim proportionally so auditions stay cheap; opening is trimmed last."""
    total = sum(int(w.get("duration_ms") or 0) for w in windows)
    if total <= total_cap or total == 0:
        return _assign_preview_offsets(windows)
    overflow = total - total_cap
    for window in sorted(windows, key=lambda w: 0 if w["kind"] == "opening" else 1, reverse=True):
        if overflow <= 0:
            break
        duration = int(window.get("duration_ms") or 0)
        trim = min(overflow, max(0, duration - 5000))
        window["duration_ms"] = duration - trim
        if window.get("source_end_ms") is not None and window.get("source_start_ms") is not None:
            window["source_end_ms"] = window["source_start_ms"] + window["duration_ms"]
        overflow -= trim
    return _assign_preview_offsets(windows)


def _assign_preview_offsets(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cursor = 0
    for window in windows:
        window["preview_start_ms"] = cursor
        cursor += int(window.get("duration_ms") or 0)
    return windows


def build_manifest(
    candidate: dict[str, Any],
    segments: dict[str, dict[str, Any]],
    *,
    transcripts: dict[str, str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan an audition without rendering. `rendered` flips once audio exists."""
    candidate_id = str(candidate.get("candidate_id") or "candidate")
    windows = plan_windows(candidate, segments, cfg=cfg)
    if transcripts:
        for window in windows:
            texts = [transcripts.get(ref) for ref in window.get("source_refs") or []]
            joined = " ".join(t for t in texts if t)
            window["transcript"] = joined or None

    warnings: list[str] = []
    for window in windows:
        if window.get("source_start_ms") is None and window["kind"] != "opening":
            warnings.append(f"{window['kind']} window has no resolvable source span")

    return {
        "version": 1,
        "candidate_id": candidate_id,
        "plan_hash": plan_hash(candidate),
        "preview_path": None,
        "rendered": False,
        "windows": windows,
        "total_duration_ms": sum(int(w.get("duration_ms") or 0) for w in windows),
        "features": {},
        "render_warnings": warnings,
        "generated_at": _now(),
    }


def render_audition(ctx: RunContext, manifest: dict[str, Any]) -> dict[str, Any]:
    """Cut the planned windows out of the normalized source and concatenate them.

    Reuses the same ffmpeg slicing the assembly preview does; a full master is
    never rendered per candidate.
    """
    from interview_mux.operator_subprocess import run_command

    candidate_id = str(manifest["candidate_id"])
    source = ctx.read_path("ingest", "normalized.wav")
    if not source.is_file():
        manifest["render_warnings"] = [
            *manifest.get("render_warnings", []),
            "ingest/normalized.wav missing — audition not rendered",
        ]
        return manifest

    work = ctx.path(AUDITION_DIR, candidate_id, "_clips")
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i, window in enumerate(manifest.get("windows") or []):
        start_ms, end_ms = window.get("source_start_ms"), window.get("source_end_ms")
        if start_ms is None or end_ms is None or end_ms <= start_ms:
            continue
        out = work / f"{i:02d}_{window['kind']}.wav"
        run_command(
            [
                "ffmpeg", "-y", "-i", str(source),
                "-ss", f"{start_ms / 1000.0}",
                "-to", f"{end_ms / 1000.0}",
                "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
                str(out),
            ],
            stage="mastering_audition",
            label=f"audition {candidate_id} {window['kind']}",
            capture_output=True,
        )
        clips.append(out)

    if not clips:
        manifest["render_warnings"] = [
            *manifest.get("render_warnings", []),
            "no renderable windows",
        ]
        return manifest

    preview = ctx.path(AUDITION_DIR, candidate_id, "preview.wav")
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    run_command(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(preview)],
        stage="mastering_audition",
        label=f"audition {candidate_id} concat",
        capture_output=True,
    )

    manifest["preview_path"] = audition_rel(candidate_id, "preview.wav")
    manifest["rendered"] = preview.is_file()
    if manifest["rendered"]:
        manifest["features"] = measure_features(preview)
    return manifest


def measure_features(preview: Path) -> dict[str, Any]:
    """Acoustic summary critics reason over in place of raw audio."""
    from interview_mux.mmaudio_asset_qa import _read_wav_frames, _rms

    try:
        samples, rate = _read_wav_frames(preview)
    except (OSError, ValueError, EOFError):
        return {}
    if not samples:
        return {}

    peak = max(abs(s) for s in samples)
    rms = _rms(samples)
    window = max(1, rate // 10)
    silent = 0
    frames = 0
    for i in range(0, len(samples) - window, window):
        frames += 1
        if _rms(samples[i : i + window]) < 0.005:
            silent += 1
    # RMS dBFS proxy, not true BS.1770 loudness — auditions only need relative comparison.
    return {
        "integrated_lufs": round(20 * math.log10(rms), 2) if rms > 1e-6 else None,
        "peak_dbfs": round(20 * math.log10(peak), 2) if peak > 1e-6 else None,
        "silence_ratio": round(silent / frames, 4) if frames else None,
        "speech_band_ratio": None,
        "bed_under_speech_margin_db": None,
        "transition_jolt_db": None,
    }


def write_manifest(ctx: RunContext, manifest: dict[str, Any]) -> None:
    ctx.write_json(audition_rel(str(manifest["candidate_id"])), manifest)


def auditions_required(cfg: dict[str, Any] | None = None) -> bool:
    return gate_mode("auditions", cfg) == "authoritative"
