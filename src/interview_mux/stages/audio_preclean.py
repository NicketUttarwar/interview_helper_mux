from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import require_secret
from interview_mux.elevenlabs_rest import ElevenLabsApiError, isolate_audio
from interview_mux.run_context import RunContext


def run_audio_preclean(ctx: RunContext) -> Path | None:
    """Optionally run ElevenLabs isolation (operator must enable in run_meta)."""
    scope = _selected_scope(ctx)
    if not scope:
        ctx.log(
            "Audio pre-clean skipped (quality offer not accepted).",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean")
        return None

    if scope == "vo_pickup":
        return _run_vo_pickup_preclean(ctx)

    if scope not in {"full_source", "normalized_rebuild"}:
        ctx.log(
            f"Audio pre-clean skipped (unsupported scope: {scope}).",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean")
        return None

    source = ctx.path("ingest", "normalized.wav") if scope == "normalized_rebuild" else ctx.input_audio()
    if not source.is_file():
        raise FileNotFoundError(f"Audio pre-clean source not found: {source}")

    src_hash = _sha256(source)
    lineage_path = ctx.path("preclean", "lineage.json")
    out_path = ctx.path("preclean", "isolated.wav")
    if _can_skip_full_source(
        lineage_path=lineage_path, out_path=out_path, source_sha=src_hash, scope=scope
    ):
        ctx.log(
            "Audio pre-clean unchanged; using existing isolated.wav.",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean")
        return out_path

    api_key = require_secret("ELEVENLABS_API_KEY")
    if source.stat().st_size > _max_upload_from_config():
        ctx.log(
            f"elevenlabs_chunked_isolation: source exceeds upload limit — chunking",
            level="info",
            stage="audio_preclean",
        )
    isolated_bytes = _read_isolation_bytes(api_key=api_key, source=source)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_audio_as_wav(out_path, isolated_bytes)
    _write_provider(ctx, scope)
    _write_full_source_lineage(ctx=ctx, source=source, source_sha=src_hash, scope=scope, output=out_path)
    ctx.log(
        f"Audio pre-clean complete ({scope}) → preclean/isolated.wav",
        level="success",
        stage="audio_preclean",
    )
    ctx.mark_done("audio_preclean")
    return out_path


def invalidate_after_preclean_accept(ctx: RunContext, scope: str) -> None:
    """Clear stage markers so re-run picks up new cleaned audio."""
    from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER

    if scope == "vo_pickup":
        for stage in ("audio_preclean", "vo_ingest"):
            ctx.path(".stage_done", stage).unlink(missing_ok=True)
        flow = (ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}).get(
            "selected_flow"
        )
        if flow == "flow1":
            ctx.clear_from("edl_flow1", FLOW1_ORDER)
        elif flow == "flow2":
            ctx.clear_from("mix_flow2", FLOW2_ORDER)
        ctx.log(
            "Invalidated vo_ingest and downstream flow stages after pickup pre-clean accept.",
            level="warning",
            stage="audio_preclean",
        )
        return

    ctx.clear_from("audio_preclean", ANALYSIS_ORDER)
    flow = (ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}).get(
        "selected_flow"
    )
    if flow == "flow1":
        ctx.clear_from("topic_coverage_audit", FLOW1_ORDER)
    elif flow == "flow2":
        ctx.clear_from("highlight_selection", FLOW2_ORDER)


def _run_vo_pickup_preclean(ctx: RunContext) -> None:
    pickup = ctx.path("vo_pickup")
    sources = sorted(p for p in pickup.glob("*.wav") if p.is_file())
    if not sources:
        ctx.log(
            "Audio pre-clean skipped: no vo_pickup WAV files found.",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean")
        return None

    lineage_path = ctx.path("preclean", "lineage.json")
    if _can_skip_vo_pickup(lineage_path=lineage_path, sources=sources):
        ctx.log(
            "VO pickup pre-clean unchanged; using existing vo_pickup/clean/*.wav.",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean")
        return None

    api_key = require_secret("ELEVENLABS_API_KEY")
    clean_dir = pickup / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for source in sources:
        isolated_bytes = _read_isolation_bytes(api_key=api_key, source=source)
        dest = clean_dir / source.name
        _write_audio_as_wav(dest, isolated_bytes)
        entries.append(
            {
                "source_path": str(source),
                "source_sha256": _sha256(source),
                "output_path": f"vo_pickup/clean/{source.name}",
                "output_sha256": _sha256(dest),
            }
        )

    _write_provider(ctx, "vo_pickup")
    _write_vo_pickup_lineage(ctx, entries)
    ctx.log(
        f"VO pickup pre-clean complete → {len(entries)} file(s) in vo_pickup/clean/",
        level="success",
        stage="audio_preclean",
    )
    ctx.mark_done("audio_preclean")
    return None


def _selected_scope(ctx: RunContext) -> str:
    if not ctx.artifact_exists("run_meta.json"):
        return ""
    meta = ctx.read_json("run_meta.json")
    preclean = meta.get("audio_preclean")
    if not isinstance(preclean, dict):
        return ""
    if not preclean.get("enabled"):
        return ""
    return str(preclean.get("scope") or "").strip()


def _can_skip_full_source(
    *, lineage_path: Path, out_path: Path, source_sha: str, scope: str
) -> bool:
    if not lineage_path.is_file() or not out_path.is_file():
        return False
    try:
        lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        lineage.get("scope") == scope
        and lineage.get("source_sha256") == source_sha
        and lineage.get("provider") == "elevenlabs"
    )


def _can_skip_vo_pickup(*, lineage_path: Path, sources: list[Path]) -> bool:
    if not lineage_path.is_file():
        return False
    try:
        lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if lineage.get("scope") != "vo_pickup" or lineage.get("provider") != "elevenlabs":
        return False
    files = lineage.get("files")
    if not isinstance(files, list):
        return False
    by_name = {
        Path(str(entry.get("source_path", ""))).name: entry.get("source_sha256")
        for entry in files
        if isinstance(entry, dict)
    }
    clean_dir = sources[0].parent / "clean"
    for source in sources:
        expected = by_name.get(source.name)
        if expected != _sha256(source):
            return False
        dest = clean_dir / source.name
        if not dest.is_file():
            return False
    return True


def _max_upload_from_config() -> int:
    from interview_mux.elevenlabs_rest import _max_upload_bytes

    return _max_upload_bytes()


def _read_isolation_bytes(*, api_key: str, source: Path) -> bytes:
    from interview_mux.audio_timeline import chunk_wav_by_max_bytes, concat_clips_with_crossfade
    from interview_mux.config import merged_config
    from interview_mux.elevenlabs_rest import _max_upload_bytes
    from interview_mux.sound_design import load_audio

    max_bytes = _max_upload_bytes()
    raw = source.read_bytes()
    if len(raw) <= max_bytes:
        try:
            return isolate_audio(api_key=api_key, audio_bytes=raw, filename=source.name)
        except ElevenLabsApiError as exc:
            raise RuntimeError(f"Audio pre-clean failed via ElevenLabs REST: {exc}") from exc

    work = source.parent / "_preclean_chunks"
    chunks = chunk_wav_by_max_bytes(source, max_bytes, work_dir=work)
    isolated_segments: list = []
    for i, chunk_path in enumerate(chunks):
        chunk_bytes = chunk_path.read_bytes()
        try:
            iso = isolate_audio(api_key=api_key, audio_bytes=chunk_bytes, filename=chunk_path.name)
        except ElevenLabsApiError as exc:
            raise RuntimeError(f"Audio pre-clean chunk {i} failed: {exc}") from exc
        tmp = work / f"isolated_{i:03d}.wav"
        _write_audio_as_wav(tmp, iso)
        isolated_segments.append(load_audio(tmp))
    crossfade = int((merged_config().get("mix") or {}).get("crossfade_ms_assembly_preview", 80))
    merged = concat_clips_with_crossfade(isolated_segments, crossfade)
    out_tmp = work / "merged_isolated.wav"
    merged.export(str(out_tmp), format="wav")
    return out_tmp.read_bytes()


def _write_audio_as_wav(path: Path, data: bytes) -> None:
    if data[:4] == b"RIFF":
        path.write_bytes(data)
        return
    tmp = path.with_suffix(".isolation.tmp")
    tmp.write_bytes(data)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(path)],
            check=True,
            capture_output=True,
        )
    finally:
        tmp.unlink(missing_ok=True)


def _write_provider(ctx: RunContext, scope: str) -> None:
    provider: dict[str, Any] = {
        "provider": "elevenlabs",
        "scope": scope,
        "api_path": "/v1/audio-isolation",
    }
    ctx.write_json("preclean/provider.json", provider)


def _write_full_source_lineage(
    *, ctx: RunContext, source: Path, source_sha: str, scope: str, output: Path
) -> None:
    lineage: dict[str, Any] = {
        "provider": "elevenlabs",
        "scope": scope,
        "source_path": str(source),
        "source_sha256": source_sha,
        "output_path": "preclean/isolated.wav",
        "isolated_sha256": _sha256(output),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.write_json("preclean/lineage.json", lineage)


def _write_vo_pickup_lineage(ctx: RunContext, entries: list[dict[str, Any]]) -> None:
    lineage: dict[str, Any] = {
        "provider": "elevenlabs",
        "scope": "vo_pickup",
        "files": entries,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.write_json("preclean/lineage.json", lineage)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
