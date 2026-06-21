from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.deepfilter_runner import enhance_wav
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext


def write_skip_artifact(
    ctx: RunContext,
    *,
    checkpoint: str,
    scope: str,
    reason: str = "operator_dismissed",
) -> None:
    """Record that optional pre-clean was skipped — no preclean outputs required."""
    from interview_mux.file_store import write_json as fs_write_json

    row: dict[str, Any] = {
        "status": "skipped",
        "checkpoint": checkpoint,
        "scope": scope,
        "reason": reason,
        "skipped_at": datetime.now(timezone.utc).isoformat(),
    }
    dest = ctx.final_path("preclean/skip.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, row)


def ensure_preclean_skipped(
    ctx: RunContext,
    *,
    checkpoint: str,
    scope: str,
    reason: str = "operator_dismissed",
) -> None:
    """Finalize optional pre-clean without outputs so downstream stages can run."""
    write_skip_artifact(ctx, checkpoint=checkpoint, scope=scope, reason=reason)
    if not ctx.is_done("audio_preclean"):
        ctx.log(
            f"Audio pre-clean skipped ({checkpoint}, scope={scope}).",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean", force=True)


def preclean_was_skipped(ctx: RunContext) -> bool:
    if ctx.artifact_exists("preclean/skip.json"):
        return True
    if not ctx.is_done("audio_preclean"):
        return False
    return not ctx.artifact_exists("preclean/isolated.wav") and not ctx.path(
        "vo_pickup", "clean"
    ).is_dir()


def run_audio_preclean(ctx: RunContext) -> Path | None:
    """Optionally run DeepFilterNet noise reduction (operator must enable in run_meta)."""
    scope = _selected_scope(ctx)
    if not scope:
        checkpoint, skip_scope = _skip_context_from_meta(ctx)
        ensure_preclean_skipped(
            ctx,
            checkpoint=checkpoint,
            scope=skip_scope,
            reason="quality_offer_not_accepted",
        )
        return None

    if scope == "vo_pickup":
        return _run_vo_pickup_preclean(ctx)

    if scope not in {"full_source", "normalized_rebuild"}:
        ensure_preclean_skipped(
            ctx,
            checkpoint="before_ingest",
            scope=scope,
            reason="unsupported_scope",
        )
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

    provider_name = "deepfilternet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if source.stat().st_size > _chunk_max_bytes():
        ctx.log(
            "deepfilter_chunked_enhance: source exceeds chunk_max_bytes — chunking",
            level="info",
            stage="audio_preclean",
        )
    with logged_step("audio_preclean/deepfilter_enhance", ctx=ctx, stage="audio_preclean"):
        _enhance_source_to_output(ctx=ctx, source=source, output=out_path)
    with logged_step("audio_preclean/write_lineage", ctx=ctx, stage="audio_preclean"):
        _write_provider(ctx, scope, provider=provider_name)
        _write_full_source_lineage(
            ctx=ctx,
            source=source,
            source_sha=src_hash,
            scope=scope,
            output=out_path,
            provider=provider_name,
        )
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
        ensure_preclean_skipped(
            ctx,
            checkpoint="g1_vo_pickup",
            scope="vo_pickup",
            reason="no_vo_pickup_files",
        )
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

    clean_dir = pickup / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    with logged_step("audio_preclean/vo_pickup_enhance", ctx=ctx, stage="audio_preclean"):
        for source in sources:
            dest = clean_dir / source.name
            _enhance_source_to_output(ctx=ctx, source=source, output=dest)
            entries.append(
                {
                    "source_path": str(source),
                    "source_sha256": _sha256(source),
                    "output_path": f"vo_pickup/clean/{source.name}",
                    "output_sha256": _sha256(dest),
                    "provider": "deepfilternet",
                }
            )

    vo_provider = "deepfilternet"
    with logged_step("audio_preclean/vo_pickup_lineage", ctx=ctx, stage="audio_preclean"):
        _write_provider(ctx, "vo_pickup", provider=vo_provider)
        _write_vo_pickup_lineage(ctx, entries, provider=vo_provider)
    ctx.log(
        f"VO pickup pre-clean complete → {len(entries)} file(s) in vo_pickup/clean/",
        level="success",
        stage="audio_preclean",
    )
    ctx.mark_done("audio_preclean")
    return None


def _skip_context_from_meta(ctx: RunContext) -> tuple[str, str]:
    checkpoint = "before_ingest"
    scope = "full_source"
    if not ctx.artifact_exists("run_meta.json"):
        return checkpoint, scope
    meta = ctx.read_json("run_meta.json")
    preclean = meta.get("audio_preclean")
    if isinstance(preclean, dict):
        from interview_mux.operator_quality import preclean_checkpoint_decision

        if preclean_checkpoint_decision(meta, "g1_vo_pickup") == "dismiss":
            checkpoint = "g1_vo_pickup"
            scope = "vo_pickup"
        elif preclean_checkpoint_decision(meta, "before_ingest") == "dismiss":
            checkpoint = "before_ingest"
            scope = str(preclean.get("scope") or "full_source")
        elif str(preclean.get("scope") or "").strip():
            scope = str(preclean.get("scope") or scope)
    return checkpoint, scope


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
        and lineage.get("provider") == "deepfilternet"
    )


def _can_skip_vo_pickup(*, lineage_path: Path, sources: list[Path]) -> bool:
    if not lineage_path.is_file():
        return False
    try:
        lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if lineage.get("scope") != "vo_pickup":
        return False
    if lineage.get("provider") != "deepfilternet":
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


def _chunk_max_bytes() -> int:
    from interview_mux.config import merged_config

    row = merged_config().get("audio_preclean") or {}
    return int(row.get("chunk_max_bytes", 52_428_800))


def _enhance_source_to_output(*, ctx: RunContext, source: Path, output: Path) -> None:
    from interview_mux.audio_timeline import chunk_wav_by_max_bytes, concat_clips_with_crossfade
    from interview_mux.config import merged_config
    from interview_mux.sound_design import load_audio

    max_bytes = _chunk_max_bytes()
    if source.stat().st_size <= max_bytes:
        enhance_wav(source, output, ctx=ctx)
        return

    work = source.parent / "_preclean_chunks"
    chunks = chunk_wav_by_max_bytes(source, max_bytes, work_dir=work)
    enhanced_segments: list = []
    for i, chunk_path in enumerate(chunks):
        tmp = work / f"enhanced_{i:03d}.wav"
        enhance_wav(chunk_path, tmp, ctx=ctx)
        enhanced_segments.append(load_audio(tmp))
    crossfade = int((merged_config().get("mix") or {}).get("crossfade_ms_assembly_preview", 80))
    merged = concat_clips_with_crossfade(enhanced_segments, crossfade)
    out_tmp = work / "merged_enhanced.wav"
    merged.export(str(out_tmp), format="wav")
    output.write_bytes(out_tmp.read_bytes())


def _write_provider(ctx: RunContext, scope: str, *, provider: str = "deepfilternet") -> None:
    row: dict[str, Any] = {
        "provider": provider,
        "scope": scope,
    }
    if provider == "deepfilternet":
        from interview_mux.config import merged_config

        cfg = merged_config().get("deepfilter") or {}
        row["model"] = cfg.get("model", "DeepFilterNet3")
    ctx.write_json("preclean/provider.json", row)


def _write_full_source_lineage(
    *,
    ctx: RunContext,
    source: Path,
    source_sha: str,
    scope: str,
    output: Path,
    provider: str,
) -> None:
    lineage: dict[str, Any] = {
        "provider": provider,
        "scope": scope,
        "source_path": str(source),
        "source_sha256": source_sha,
        "output_path": "preclean/isolated.wav",
        "isolated_sha256": _sha256(output),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.write_json("preclean/lineage.json", lineage)


def _write_vo_pickup_lineage(
    ctx: RunContext,
    entries: list[dict[str, Any]],
    *,
    provider: str,
) -> None:
    lineage: dict[str, Any] = {
        "provider": provider,
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
