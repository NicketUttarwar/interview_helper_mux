"""Source-audio fingerprinting for execution folder names and reuse matching."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from interview_mux.assets_audio import ensure_wav_asset

_HASH_SHORT_LEN = 12
_RUN_ID_HASH_RE = re.compile(r"^exec_\d{3}_([a-f0-9]{12})_\d{8}T\d{6}Z$")


def pipeline_wav_path(input_path: Path) -> Path:
    """Return the canonical pipeline WAV (converts m4a/mp4 siblings to .wav first)."""
    return ensure_wav_asset(input_path.resolve())


def source_audio_hash_pair(path: Path) -> tuple[str, str]:
    """Full SHA-256 hex and 12-char short from a single pipeline WAV read."""
    wav = pipeline_wav_path(path)
    h = hashlib.sha256()
    with wav.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    full = h.hexdigest()
    return full, hash_short_from_full(full)


def compute_source_audio_hash(path: Path) -> str:
    """SHA-256 hex of pipeline WAV bytes (never hashes non-WAV containers directly)."""
    return source_audio_hash_pair(path)[0]


def normalized_source_audio_hash(path: Path, *, truncate: int = _HASH_SHORT_LEN) -> str:
    """Lowercase alphanumeric prefix of the pipeline WAV hash (for folder names)."""
    return hash_short_from_full(source_audio_hash_pair(path)[0], short_len=truncate)


def parse_hash_from_run_id(run_id: str) -> str | None:
    """Extract the 12-char hash segment from a new-format execution id."""
    m = _RUN_ID_HASH_RE.match(run_id)
    return m.group(1) if m else None


def hashes_match(a: str, b: str, *, short_len: int = _HASH_SHORT_LEN) -> bool:
    """Compare full or truncated source-audio hashes."""
    if not a or not b:
        return False
    ca = re.sub(r"[^a-z0-9]", "", a.lower())
    cb = re.sub(r"[^a-z0-9]", "", b.lower())
    if ca == cb:
        return True
    return ca[:short_len] == cb[:short_len]


def hash_short_from_full(full_hash: str, *, short_len: int = _HASH_SHORT_LEN) -> str:
    clean = re.sub(r"[^a-z0-9]", "", full_hash.lower())
    return clean[:short_len]
