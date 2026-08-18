"""Ingest stage — normalize source audio (format + loudness) and record checksums."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.operator_subprocess import format_command, run_logged_command, touch_job_message
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.source_loudness import (
    build_ingest_loudness_filter,
    loudness_lineage_payload,
    loudness_stabilize_cfg,
)

_HASH_PROGRESS_BYTES = 32 << 20  # 32 MiB
_HASH_PROGRESS_SECONDS = 30.0


def _sha256(
    path: Path,
    *,
    ctx: RunContext | None = None,
    label: str | None = None,
) -> str:
    total = path.stat().st_size
    h = hashlib.sha256()
    read_bytes = 0
    last_log_at = time.monotonic()
    last_log_bytes = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            read_bytes += len(chunk)
            now = time.monotonic()
            if ctx and label and (
                read_bytes - last_log_bytes >= _HASH_PROGRESS_BYTES
                or now - last_log_at >= _HASH_PROGRESS_SECONDS
            ):
                pct = int(read_bytes * 100 / total) if total else 0
                touch_job_message(ctx, f"Ingest: hashing {label}… ({pct}%)")
                ctx.log(
                    f"Ingest: hashing {label}… {pct}%",
                    level="info",
                    stage="ingest",
                    detail={
                        "journey_kind": "execute",
                        "event": "hash_progress",
                        "label": label,
                        "bytes_read": read_bytes,
                        "total_bytes": total,
                        "pct": pct,
                        "action_id": "ingest.hash",
                    },
                    action_id="ingest.hash",
                    origin="pipeline",
                )
                last_log_at = now
                last_log_bytes = read_bytes
    return h.hexdigest()


def _ingest_source(ctx: RunContext) -> tuple[Path, Path | None]:
    """Return (ffmpeg input path, optional preclean/isolated.wav path)."""
    isolated = ctx.read_path("preclean", "isolated.wav")
    if isolated.is_file():
        return isolated, isolated
    raw = ctx.input_audio()
    return raw, None


def run_ingest(ctx: RunContext) -> Path:
    cfg = merged_config()
    src, preclean = _ingest_source(ctx)
    if not src.is_file():
        raise FileNotFoundError(f"Input audio not found: {src}")

    out_dir = ctx.path("ingest")
    out_dir.mkdir(parents=True, exist_ok=True)
    normalized = out_dir / "normalized.wav"
    rate = int(cfg.get("sample_rate", 48000))

    source_label = "preclean/isolated.wav" if preclean is not None else str(ctx.input_audio())
    loud_cfg = loudness_stabilize_cfg(cfg)
    af_filter = build_ingest_loudness_filter(loud_cfg)
    touch_job_message(ctx, "Ingest: normalizing audio…")
    stabilize_note = (
        f" + loudness stabilize ({loud_cfg['target_lufs']:g} LUFS)"
        if af_filter
        else " (format only)"
    )
    ctx.log(
        f"Ingest: normalizing {source_label} → ingest/normalized.wav "
        f"({rate} Hz mono{stabilize_note}).",
        level="action",
        stage="ingest",
        detail={
            "journey_kind": "execute",
            "source": str(src),
            "output": "ingest/normalized.wav",
            "loudness_stabilize": af_filter is not None,
            "af_filter": af_filter,
        },
    )
    touch_job_message(
        ctx,
        "Ingest: running ffmpeg loudness stabilize…"
        if af_filter
        else "Ingest: running ffmpeg normalize…",
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
    ]
    if af_filter:
        cmd.extend(["-af", af_filter])
    cmd.extend(
        [
            "-ar",
            str(rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(normalized),
        ]
    )
    with logged_step("ingest/ffmpeg_normalize", ctx=ctx, stage="ingest"):
        run_logged_command(
            ctx,
            cmd,
            stage="ingest",
            label=format_command(cmd),
            action_id="subprocess.ffmpeg",
        )

    lineage = loudness_lineage_payload(loud_cfg, af_filter=af_filter)
    with logged_step("ingest/loudness_lineage", ctx=ctx, stage="ingest"):
        ctx.write_json("ingest/loudness.json", lineage)

    touch_job_message(ctx, "Ingest: computing checksums…")
    with logged_step("ingest/checksums", ctx=ctx, stage="ingest"):
        ctx.log("Ingest: hashing source audio…", level="info", stage="ingest", detail={"journey_kind": "execute", "action_id": "ingest.hash"}, action_id="ingest.hash", origin="pipeline")
        source_sha = _sha256(ctx.input_audio(), ctx=ctx, label="source")
        ctx.log("Ingest: hashing normalized audio…", level="info", stage="ingest", detail={"journey_kind": "execute", "action_id": "ingest.hash"}, action_id="ingest.hash", origin="pipeline")
        normalized_sha = _sha256(normalized, ctx=ctx, label="normalized")

        checksums: dict[str, object] = {
            "source_path": str(ctx.input_audio()),
            "source_sha256": source_sha,
            "normalized_sha256": normalized_sha,
            "sample_rate": rate,
            "loudness_stabilize": bool(lineage.get("enabled")),
        }
        if preclean is not None:
            ctx.log("Ingest: hashing preclean audio…", level="info", stage="ingest", detail={"journey_kind": "execute", "action_id": "ingest.hash"}, action_id="ingest.hash", origin="pipeline")
            checksums["preclean_path"] = "preclean/isolated.wav"
            checksums["preclean_sha256"] = _sha256(preclean, ctx=ctx, label="preclean")
        ctx.log("Ingest: writing ingest/checksums.json", level="info", stage="ingest", detail={"journey_kind": "execute"}, origin="pipeline")
        ctx.write_json("ingest/checksums.json", checksums)
    touch_job_message(ctx, "Ingest: finishing…")
    ctx.log(
        f"Ingest complete — normalized audio at ingest/normalized.wav ({rate} Hz mono"
        f"{stabilize_note}).",
        level="success",
        stage="ingest",
        detail={"journey_kind": "milestone", "source_sha256": source_sha[:12]},
    )
    ctx.mark_done("ingest")
    try:
        from interview_mux.homunculus.source_card import refresh_source_profile, wav_duration_s

        is_video = str(ctx.input_audio()).lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
        duration_s = wav_duration_s(normalized) if normalized.is_file() else None
        refresh_source_profile(ctx, stage="ingest", is_video=is_video, duration_s=duration_s)
    except Exception as exc:  # noqa: BLE001 — profile selection is fail-open
        ctx.log(f"source_profile selection failed: {exc}", level="warning", stage="ingest")
    try:
        from interview_mux.source_readiness import maybe_auto_dismiss_preclean, write_source_readiness

        write_source_readiness(ctx, stage="ingest")
        maybe_auto_dismiss_preclean(ctx, checkpoint="before_ingest")
    except Exception as exc:  # noqa: BLE001 — readiness is fail-open
        ctx.log(f"source_readiness after ingest failed: {exc}", level="warning", stage="ingest")
    return normalized
