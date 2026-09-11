from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.deepfilter_runner import DeepFilterUnavailable, enhance_wav, enhance_wav_batch
from interview_mux.operator_subprocess import JobProgressReporter
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark


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
        heal_or_refuse_mark(ctx, "audio_preclean", force=True)


def preclean_was_skipped(ctx: RunContext) -> bool:
    if ctx.artifact_exists("preclean/skip.json"):
        return True
    if not ctx.is_done("audio_preclean"):
        return False
    return not ctx.artifact_exists("preclean/isolated.wav") and not ctx.final_path(
        "vo_pickup", "clean"
    ).is_dir()


def run_audio_preclean(ctx: RunContext) -> Path | None:
    """Optionally run DeepFilterNet noise reduction (operator must enable in run_meta)."""
    from interview_mux.operator_subprocess import touch_job_progress

    touch_job_progress(
        ctx,
        "Audio pre-clean: preparing source…",
        phase="prepare",
    )
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

    source = ctx.read_path("ingest", "normalized.wav") if scope == "normalized_rebuild" else ctx.input_audio()
    if not source.is_file():
        raise FileNotFoundError(f"Audio pre-clean source not found: {source}")

    if source.stat().st_size > 10_000_000:
        touch_job_progress(
            ctx,
            "Audio pre-clean: hashing source audio…",
            phase="prepare",
        )
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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if source.stat().st_size > _chunk_max_bytes():
        ctx.log(
            "deepfilter_chunked_enhance: source exceeds chunk_max_bytes — chunking",
            level="info",
            stage="audio_preclean",
        )
    progress = JobProgressReporter(ctx, stage="audio_preclean", phase="deepfilter")
    with logged_step("audio_preclean/deepfilter_enhance", ctx=ctx, stage="audio_preclean"):
        provider_name = _enhance_source_to_output(
            ctx=ctx, source=source, output=out_path, progress=progress
        )
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
    from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER

    if scope == "vo_pickup":
        for stage in ("audio_preclean", "vo_ingest"):
            ctx.path(".stage_done", stage).unlink(missing_ok=True)
        # Pillar C: refuse post-assembly edl clear when gain gate says no.
        try:
            asm = ctx.final_path("master", "assembly.wav")
            if asm.is_file() and asm.stat().st_size > 0:
                from interview_mux.timeline_reopen_meta_gate import (
                    INTENT_MIX_REWALK,
                    decide_timeline_reopen,
                )

                gate = decide_timeline_reopen(
                    ctx,
                    intent=INTENT_MIX_REWALK,
                    detail={"from_stage": "edl", "source": "preclean_vo_pickup"},
                )
                if not gate.get("allow"):
                    ctx.log(
                        "preclean vo_pickup: edl clear refused by timeline reopen gate "
                        f"({gate.get('refuse_reason')})",
                        level="warning",
                        stage="audio_preclean",
                    )
                    return
        except Exception:
            ctx.log(
                "preclean vo_pickup: edl clear fail-closed refuse on gate error",
                level="warning",
                stage="audio_preclean",
            )
            return
        ctx.clear_from("edl", DELIVERY_ORDER)
        ctx.log(
            "Invalidated vo_ingest and downstream flow stages after pickup pre-clean accept.",
            level="warning",
            stage="audio_preclean",
        )
        return

    ctx.clear_from("audio_preclean", ANALYSIS_ORDER)
    ctx.clear_from("topic_coverage_audit", DELIVERY_ORDER)


def _run_vo_pickup_preclean(ctx: RunContext) -> None:
    pickup = ctx.final_path("vo_pickup")
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
    providers: set[str] = set()
    progress = JobProgressReporter(
        ctx,
        stage="audio_preclean",
        phase="deepfilter",
        step_total=len(sources),
    )
    progress.set_phase(
        "deepfilter",
        f"Enhancing {len(sources)} VO pickup file(s) with DeepFilterNet…",
        step_total=len(sources),
        log=True,
    )
    with logged_step("audio_preclean/vo_pickup_enhance", ctx=ctx, stage="audio_preclean"):
        for i, source in enumerate(sources, start=1):
            dest = clean_dir / source.name
            progress.tick(
                i,
                f"Enhancing pickup {i}/{len(sources)}: {source.name}…",
                force=True,
                log=True,
            )
            provider = _enhance_source_to_output(
                ctx=ctx, source=source, output=dest, progress=None
            )
            providers.add(provider)
            entries.append(
                {
                    "source_path": str(source),
                    "source_sha256": _sha256(source),
                    "output_path": f"vo_pickup/clean/{source.name}",
                    "output_sha256": _sha256(dest),
                    "provider": provider,
                }
            )

    vo_provider = next(iter(providers)) if len(providers) == 1 else "mixed"
    with logged_step("audio_preclean/vo_pickup_lineage", ctx=ctx, stage="audio_preclean"):
        _write_provider(ctx, "vo_pickup", provider=vo_provider)
        _write_vo_pickup_lineage(ctx, entries, provider=vo_provider)
    ctx.log(
        f"VO pickup pre-clean complete → {len(entries)} file(s) in vo_pickup/clean/",
        level="success",
        stage="audio_preclean",
    )
    ctx.mark_done("audio_preclean")
    try:
        from interview_mux.source_readiness import write_source_readiness

        write_source_readiness(ctx, stage="audio_preclean")
    except Exception as exc:  # noqa: BLE001
        ctx.log(f"source_readiness after preclean failed: {exc}", level="warning", stage="audio_preclean")
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
    from interview_mux.config import merged_config
    from interview_mux.operator_quality import preclean_checkpoint_decision

    cfg = (merged_config().get("audio_preclean") or {})
    auto_run = bool(cfg.get("auto_run_before_ingest", True)) or str(cfg.get("default_action") or "").lower() == "run"

    if not ctx.artifact_exists("run_meta.json"):
        return "full_source" if auto_run else ""
    meta = ctx.read_json("run_meta.json")
    if not isinstance(meta, dict):
        return "full_source" if auto_run else ""
    if preclean_checkpoint_decision(meta, "before_ingest") == "dismiss":
        return ""
    if preclean_checkpoint_decision(meta, "g1_vo_pickup") == "dismiss" and str(
        (meta.get("audio_preclean") or {}).get("scope") or ""
    ) == "vo_pickup":
        return ""

    preclean = meta.get("audio_preclean")
    if not isinstance(preclean, dict):
        preclean = {}
    if preclean.get("enabled"):
        return str(preclean.get("scope") or "full_source").strip() or "full_source"

    if auto_run:
        # Enable full-source DeepFilterNet by default unless operator dismissed.
        def patch(m: dict[str, Any]) -> None:
            ap = dict(m.get("audio_preclean") or {})
            ap["enabled"] = True
            ap["scope"] = str(ap.get("scope") or "full_source") or "full_source"
            ap["provider"] = str(ap.get("provider") or "deepfilternet")
            ap["default_action"] = "run"
            decisions = list(ap.get("decisions") or [])
            decisions.append(
                {
                    "checkpoint": "before_ingest",
                    "action": "accept",
                    "scope": ap["scope"],
                    "at": datetime.now(timezone.utc).isoformat(),
                    "reason": "default_auto_run",
                    "by": "audio_preclean",
                }
            )
            ap["decisions"] = decisions
            m["audio_preclean"] = ap

        ctx.mutate_run_meta(patch)
        return "full_source"
    return ""


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
        and lineage.get("provider") in {"deepfilternet", "ffmpeg_local", "mixed"}
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
    if lineage.get("provider") not in {"deepfilternet", "ffmpeg_local", "mixed"}:
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


def _preclean_work_dir(ctx: RunContext) -> Path:
    return ctx.run_dir / "_preclean_work"


def _enhance_source_to_output(
    *,
    ctx: RunContext,
    source: Path,
    output: Path,
    progress: JobProgressReporter | None = None,
) -> str:
    """Enhance with DeepFilterNet, falling back to deterministic local FFmpeg."""
    try:
        _enhance_source_with_deepfilter(
            ctx=ctx,
            source=source,
            output=output,
            progress=progress,
        )
        return "deepfilternet"
    except DeepFilterUnavailable as exc:
        from interview_mux.config import merged_config

        cfg = merged_config().get("audio_preclean") or {}
        if not bool(cfg.get("local_fallback_enabled", True)):
            raise
        ctx.log(
            f"DeepFilterNet unavailable; using ffmpeg_local denoise: {exc}",
            level="warning",
            stage="audio_preclean",
            detail={"provider": "ffmpeg_local", "fallback_reason": str(exc)},
        )
        if progress is not None:
            progress.set_phase("ffmpeg_local", "Enhancing audio with local FFmpeg…", log=True)
        from interview_mux.ffmpeg_denoise import denoise_wav

        denoise_wav(
            source,
            output,
            highpass_hz=int(cfg.get("ffmpeg_highpass_hz", 80)),
            lowpass_hz=int(cfg.get("ffmpeg_lowpass_hz", 12_000)),
            noise_reduction_db=float(cfg.get("ffmpeg_afftdn_nr", 12.0)),
            ctx=ctx,
        )
        return "ffmpeg_local"


def _enhance_source_with_deepfilter(
    *,
    ctx: RunContext,
    source: Path,
    output: Path,
    progress: JobProgressReporter | None = None,
) -> None:
    from interview_mux.audio_timeline import chunk_wav_by_max_bytes, concat_clips_with_crossfade
    from interview_mux.config import merged_config
    from interview_mux.file_store import atomic_copy
    from interview_mux.sound_design import load_audio

    max_bytes = _chunk_max_bytes()
    if source.stat().st_size <= max_bytes:
        if progress is not None:
            progress.set_phase(
                "deepfilter",
                "Enhancing audio with DeepFilterNet…",
                step_total=1,
                log=True,
            )
            progress.tick(1, "Enhancing audio with DeepFilterNet…", force=True)
        enhance_wav(source, output, ctx=ctx)
        return

    work = _preclean_work_dir(ctx)
    if progress is not None:
        progress.set_phase(
            "split",
            "Splitting source audio into chunks for DeepFilterNet…",
            log=True,
        )
    chunks = chunk_wav_by_max_bytes(
        source,
        max_bytes,
        work_dir=work,
        heartbeat=(
            (lambda msg: progress.tick(0, msg, force=True, log=True))
            if progress is not None
            else None
        ),
    )
    chunk_total = len(chunks)
    if progress is not None:
        progress.set_phase(
            "deepfilter",
            f"Enhancing {chunk_total} chunk(s) with DeepFilterNet…",
            step_total=chunk_total,
            log=True,
        )
    batch_pairs: list[tuple[Path, Path]] = []
    for i, chunk_path in enumerate(chunks):
        tmp = work / f"enhanced_{i:03d}.wav"
        batch_pairs.append((chunk_path, tmp))
    enhance_wav_batch(batch_pairs, ctx=ctx, progress=progress)
    enhanced_segments: list = []
    for i, (_, tmp) in enumerate(batch_pairs):
        chunk_num = i + 1
        if progress is not None:
            progress.tick(
                chunk_num,
                f"Loaded enhanced chunk {chunk_num}/{chunk_total}…",
                force=True,
                log=True,
            )
        enhanced_segments.append(load_audio(tmp))
    if progress is not None:
        progress.set_phase(
            "merge",
            f"Merging {chunk_total} enhanced chunk(s)…",
            step_total=chunk_total,
            log=True,
        )
        progress.tick(
            chunk_total,
            f"Merging {chunk_total} enhanced chunk(s)…",
            force=True,
            log=True,
        )
    crossfade = int((merged_config().get("mix") or {}).get("crossfade_ms_assembly_preview", 80))
    merged = concat_clips_with_crossfade(enhanced_segments, crossfade)
    out_tmp = work / "merged_enhanced.wav"
    merged.export(str(out_tmp), format="wav")
    atomic_copy(out_tmp, output)


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
