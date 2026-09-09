"""Persist operator/sanitize_*.json audit records."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from interview_mux.artifact_sanitize.types import SanitizeResult


def _slug(rel: str) -> str:
    base = str(rel or "artifact").replace("\\", "/").split("/")[-1]
    stem = base.rsplit(".", 1)[0] if base else "artifact"
    return re.sub(r"[^a-zA-Z0-9_]+", "_", stem).strip("_") or "artifact"


def audit_rel_for(artifact_rel: str) -> str:
    return f"operator/sanitize_{_slug(artifact_rel)}.json"


def write_sanitize_audit(
    ctx: Any,
    result: SanitizeResult,
    *,
    stage_key: str = "",
    mode: str = "",
) -> str:
    """Write audit JSON; returns relative path."""
    rel = audit_rel_for(result.artifact_rel or "artifact")
    payload = {
        "version": 1,
        "artifact": result.artifact_rel,
        "ok": bool(result.ok),
        "status": "ok" if result.ok else "refused",
        "actions": list(result.actions or [])[:80],
        "errors": list(result.errors or [])[:24],
        "metrics": dict(result.metrics or {}),
        "stage_key": stage_key or "",
        "mode": mode or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ctx.write_json(rel, payload, skip_handoff=True)
    except TypeError:
        ctx.write_json(rel, payload)
    except Exception:
        pass
    return rel
