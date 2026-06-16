from __future__ import annotations

import hashlib
import json
from typing import Any

from interview_mux.coherence.analyze import _build_derived_from
from interview_mux.coherence.paths import COHERENCE_REPORT_PATH


def derived_from_matches(ctx, prior: dict[str, Any], phase: str) -> bool:
    if not isinstance(prior, dict):
        return False
    duration = prior.get("duration_ms")
    if duration is None:
        from interview_mux.coherence.duration_gate import interview_duration_ms

        duration = interview_duration_ms(ctx)
    current = _build_derived_from(ctx, phase, int(duration or 0))
    keys = ("interview_spine_sha256", "content_brief_sha256", "manifest_sha256")
    for key in keys:
        if prior.get(key) != current.get(key):
            return False
    return True


def can_skip_rebuild(ctx, phase: str) -> bool:
    if not ctx.artifact_exists(COHERENCE_REPORT_PATH):
        return False
    prior = ctx.read_json(COHERENCE_REPORT_PATH)
    if not isinstance(prior, dict):
        return False
    return derived_from_matches(ctx, prior.get("derived_from") or {}, phase)


def sha256_report(doc: dict[str, Any]) -> str:
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
