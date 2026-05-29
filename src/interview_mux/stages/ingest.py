from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from interview_mux.config import merged_config
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
    subprocess.run(cmd, check=True, capture_output=True)

    checksums: dict[str, object] = {
        "source_path": str(ctx.input_audio()),
        "source_sha256": _sha256(ctx.input_audio()),
        "normalized_sha256": _sha256(normalized),
        "sample_rate": rate,
    }
    if preclean is not None:
        checksums["preclean_path"] = "preclean/isolated.wav"
        checksums["preclean_sha256"] = _sha256(preclean)
    ctx.write_json("ingest/checksums.json", checksums)
    ctx.mark_done("ingest")
    return normalized
