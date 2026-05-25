from __future__ import annotations

import hashlib
import json
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


def run_ingest(ctx: RunContext) -> Path:
    cfg = merged_config()
    src = ctx.input_audio()
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

    checksums = {
        "source_path": str(src),
        "source_sha256": _sha256(src),
        "normalized_sha256": _sha256(normalized),
        "sample_rate": rate,
    }
    (out_dir / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    ctx.mark_done("ingest")
    return normalized
