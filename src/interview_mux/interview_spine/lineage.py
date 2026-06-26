from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.interview_spine.paths import SPINE_PATH


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_json(doc: dict[str, Any]) -> str:
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_derived_from(ctx) -> dict[str, Any]:
    normalized = ctx.read_path("ingest", "normalized.wav")
    transcript = ctx.read_json("transcript/full.json") if ctx.artifact_exists("transcript/full.json") else {}
    preclean = ctx.read_path("preclean", "isolated.wav")
    sap = ctx.read_json("understanding/source_acoustic_profile.json") if ctx.artifact_exists(
        "understanding/source_acoustic_profile.json"
    ) else {}

    row: dict[str, Any] = {
        "normalized_wav": "ingest/normalized.wav",
        "normalized_wav_sha256": _sha256(normalized) if normalized.is_file() else "",
        "transcript": "transcript/full.json",
        "transcript_sha256": _sha256_json(transcript) if transcript else "",
        "source_acoustic_profile": "understanding/source_acoustic_profile.json",
        "source_acoustic_profile_sha256": _sha256_json(sap) if sap else "",
        "preclean_isolated": "preclean/isolated.wav" if preclean.is_file() else None,
        "preclean_isolated_sha256": _sha256(preclean) if preclean.is_file() else None,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "stage": "interview_spine_build",
    }
    return row


def derived_from_matches(ctx, prior: dict[str, Any]) -> bool:
    if not isinstance(prior, dict):
        return False
    current = build_derived_from(ctx)
    keys = (
        "normalized_wav_sha256",
        "transcript_sha256",
        "source_acoustic_profile_sha256",
        "preclean_isolated_sha256",
    )
    for key in keys:
        if prior.get(key) != current.get(key):
            return False
    return True


def can_skip_rebuild(ctx) -> bool:
    spine_path = ctx.read_path(*SPINE_PATH.split("/"))
    if not spine_path.is_file():
        return False
    prior = ctx.read_json(SPINE_PATH)
    if not isinstance(prior, dict):
        return False
    return derived_from_matches(ctx, prior.get("derived_from") or {})
