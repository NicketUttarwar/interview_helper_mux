from __future__ import annotations

import hashlib
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.operator_subprocess import format_command, run_logged_command, touch_job_message
from interview_mux.run_context import RunContext


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ingest_source(ctx: RunContext) -> tuple[Path, Path | None]:
    """Return (ffmpeg input path, optional preclean/isolated.wav path)."""
    isolated = ctx.path("preclean", "isolated.wav")
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
    ctx.log(
        f"Ingest: normalizing {source_label} → ingest/normalized.wav ({rate} Hz mono).",
        level="action",
        stage="ingest",
        detail={"journey_kind": "execute", "source": str(src), "output": "ingest/normalized.wav"},
    )
    touch_job_message(ctx, "Ingest: running ffmpeg normalize…")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ar",
        str(rate),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(normalized),
    ]
    run_logged_command(
        ctx,
        cmd,
        stage="ingest",
        label=format_command(cmd),
    )

    touch_job_message(ctx, "Ingest: computing checksums…")
    ctx.log("Ingest: hashing source audio…", level="info", stage="ingest", detail={"journey_kind": "execute"})
    source_sha = _sha256(ctx.input_audio())
    ctx.log("Ingest: hashing normalized audio…", level="info", stage="ingest", detail={"journey_kind": "execute"})
    normalized_sha = _sha256(normalized)

    checksums: dict[str, object] = {
        "source_path": str(ctx.input_audio()),
        "source_sha256": source_sha,
        "normalized_sha256": normalized_sha,
        "sample_rate": rate,
    }
    if preclean is not None:
        ctx.log("Ingest: hashing preclean audio…", level="info", stage="ingest", detail={"journey_kind": "execute"})
        checksums["preclean_path"] = "preclean/isolated.wav"
        checksums["preclean_sha256"] = _sha256(preclean)
    ctx.write_json("ingest/checksums.json", checksums)
    ctx.log(
        f"Ingest complete — normalized audio at ingest/normalized.wav ({rate} Hz mono).",
        level="success",
        stage="ingest",
        detail={"journey_kind": "milestone", "source_sha256": source_sha[:12]},
    )
    ctx.mark_done("ingest")
    return normalized
