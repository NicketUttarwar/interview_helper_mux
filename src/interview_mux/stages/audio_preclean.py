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
    """Optionally run ElevenLabs isolation before ingest."""
    mode = _selected_mode(ctx)
    if mode not in {"full_source", "normalized_rebuild"}:
        ctx.log(
            "Audio pre-clean skipped (quality offer not accepted).",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean")
        return None

    source = ctx.path("ingest", "normalized.wav") if mode == "normalized_rebuild" else ctx.input_audio()
    if not source.is_file():
        raise FileNotFoundError(f"Audio pre-clean source not found: {source}")

    src_hash = _sha256(source)
    lineage_path = ctx.path("preclean", "lineage.json")
    out_path = ctx.path("preclean", "isolated.wav")
    if _can_skip(lineage_path=lineage_path, out_path=out_path, source_sha=src_hash, scope=mode):
        ctx.log(
            "Audio pre-clean unchanged; using existing isolated.wav.",
            level="info",
            stage="audio_preclean",
        )
        ctx.mark_done("audio_preclean")
        return out_path

    api_key = require_secret("ELEVENLABS_API_KEY")
    isolated_bytes = _read_isolation_bytes(api_key=api_key, source=source)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_audio_as_wav(out_path, isolated_bytes)
    _write_provider(ctx, mode)
    _write_lineage(ctx=ctx, source=source, source_sha=src_hash, scope=mode, output=out_path)
    ctx.log(
        f"Audio pre-clean complete ({mode}) → preclean/isolated.wav",
        level="success",
        stage="audio_preclean",
    )
    ctx.mark_done("audio_preclean")
    return out_path


def _selected_mode(ctx: RunContext) -> str:
    meta_path = ctx.path("run_meta.json")
    if not meta_path.is_file():
        return ""
    meta = ctx.read_json("run_meta.json")
    preclean = meta.get("audio_preclean")
    if not isinstance(preclean, dict):
        return ""
    if not preclean.get("enabled"):
        return ""
    scope = str(preclean.get("scope") or "").strip()
    return scope


def _can_skip(*, lineage_path: Path, out_path: Path, source_sha: str, scope: str) -> bool:
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


def _read_isolation_bytes(*, api_key: str, source: Path) -> bytes:
    try:
        return isolate_audio(api_key=api_key, audio_bytes=source.read_bytes(), filename=source.name)
    except ElevenLabsApiError as exc:
        raise RuntimeError(f"Audio pre-clean failed via ElevenLabs REST: {exc}") from exc


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


def _write_lineage(*, ctx: RunContext, source: Path, source_sha: str, scope: str, output: Path) -> None:
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
