"""Persisted identical-failure supervisor — stop the same heal at 3, survive restarts."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

IDENTICAL_FAILURES_REL = "operator/identical_failures.json"
DEFAULT_HALT_AFTER = 3

_COUNT_SUFFIX_RE = re.compile(r"\sx\d+\b", flags=re.IGNORECASE)
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[\d:.]+Z?")
_HEX_RE = re.compile(r"\b[a-f0-9]{8,}\b", flags=re.IGNORECASE)
_SEG_BRACKET_RE = re.compile(r"\[seg_[a-z0-9_]+\]", flags=re.IGNORECASE)
_SEAM_PAIR_RE = re.compile(
    r"seg_[a-z0-9_]+\s*(?:→|->)\s*seg_[a-z0-9_]+",
    flags=re.IGNORECASE,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def halt_after(*, cfg: dict[str, Any] | None = None) -> int:
    root = cfg if isinstance(cfg, dict) else merged_config()
    raw = (root.get("resilience") or {}) if isinstance(root, dict) else {}
    try:
        n = int(raw.get("identical_failure_halt_after") or DEFAULT_HALT_AFTER)
    except (TypeError, ValueError):
        n = DEFAULT_HALT_AFTER
    return max(1, n)


def normalize_reason(reason: str) -> str:
    text = " ".join(str(reason or "").strip().split())
    text = _TS_RE.sub("<ts>", text)
    text = _COUNT_SUFFIX_RE.sub("", text)
    text = _SEG_BRACKET_RE.sub("[<seg>]", text)
    text = _SEAM_PAIR_RE.sub("<pair>", text)
    text = _HEX_RE.sub("<id>", text)
    return text[:240].strip().lower()


def failure_signature(
    *,
    failed_stage: str,
    producer: str = "",
    reason: str = "",
) -> str:
    key = "|".join(
        [
            str(failed_stage or "").strip(),
            str(producer or "").strip(),
            normalize_reason(reason),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _empty_doc() -> dict[str, Any]:
    return {"version": 1, "updated_at": _utc_now(), "signatures": {}, "order": []}


def read_identical_failures(ctx: RunContext) -> dict[str, Any]:
    path = Path(ctx.run_dir) / IDENTICAL_FAILURES_REL
    if not path.is_file():
        return _empty_doc()
    try:
        data = ctx.read_json(IDENTICAL_FAILURES_REL)
    except Exception:
        return _empty_doc()
    if not isinstance(data, dict):
        return _empty_doc()
    data.setdefault("version", 1)
    data.setdefault("signatures", {})
    data.setdefault("order", [])
    return data


def _write(ctx: RunContext, doc: dict[str, Any]) -> None:
    dest = Path(ctx.run_dir) / IDENTICAL_FAILURES_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(dest, doc)


def record_identical_failure(
    ctx: RunContext,
    *,
    failed_stage: str,
    producer: str = "",
    reason: str = "",
    resume_attempted: str = "",
) -> dict[str, Any]:
    """Increment the persisted counter for this signature. Returns the row + halt flag."""
    sig = failure_signature(
        failed_stage=failed_stage, producer=producer, reason=reason
    )
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    prev = dict(signatures.get(sig) or {})
    count = int(prev.get("count") or 0) + 1
    limit = halt_after()
    row = {
        "signature": sig,
        "failed_stage": str(failed_stage or ""),
        "producer": str(producer or ""),
        "reason": normalize_reason(reason),
        "raw_reason": str(reason or "")[:400],
        "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
        "count": count,
        "halt_after": limit,
        "halt": count >= limit,
        "updated_at": _utc_now(),
        "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
    }
    signatures[sig] = row
    order = [s for s in (doc.get("order") or []) if s != sig]
    order.append(sig)
    doc["signatures"] = signatures
    doc["order"] = order[-200:]
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    try:
        ctx.log(
            f"identical_failure {failed_stage} x{count}/{limit} halt={row['halt']}",
            level="warning" if row["halt"] else "info",
            stage=str(failed_stage or None),
            detail={"signature": sig, "producer": producer, "resume": resume_attempted},
        )
    except Exception:
        pass
    return row


def upsert_fail_key(
    ctx: RunContext,
    fail_key: str,
    count: int,
    *,
    failed_stage: str = "",
    producer: str = "",
    reason: str = "",
    resume_attempted: str = "",
) -> dict[str, Any]:
    """Set the persisted counter for a driver fail_key (absolute count, keepalive-safe)."""
    sig = hashlib.sha256(str(fail_key or "").encode("utf-8")).hexdigest()[:16]
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    prev = dict(signatures.get(sig) or {})
    limit = halt_after()
    n = max(int(prev.get("count") or 0), int(count or 0))
    stage = failed_stage or str(fail_key).split(":")[0]
    row = {
        "signature": sig,
        "fail_key": str(fail_key or ""),
        "failed_stage": stage,
        "producer": str(producer or prev.get("producer") or ""),
        "reason": normalize_reason(reason or fail_key),
        "raw_reason": str(reason or fail_key or "")[:400],
        "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
        "count": n,
        "halt_after": limit,
        "halt": n >= limit,
        "updated_at": _utc_now(),
        "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
    }
    signatures[sig] = row
    order = [s for s in (doc.get("order") or []) if s != sig]
    order.append(sig)
    doc["signatures"] = signatures
    doc["order"] = order[-200:]
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return row


def is_halted(ctx: RunContext, signature: str) -> bool:
    doc = read_identical_failures(ctx)
    row = (doc.get("signatures") or {}).get(signature) or {}
    return bool(row.get("halt")) or int(row.get("count") or 0) >= halt_after()


def halted_rows(ctx: RunContext) -> list[dict[str, Any]]:
    doc = read_identical_failures(ctx)
    out: list[dict[str, Any]] = []
    for sig in doc.get("order") or []:
        row = (doc.get("signatures") or {}).get(sig)
        if isinstance(row, dict) and row.get("halt"):
            out.append(row)
    return out


def clear_halts_matching(
    ctx: RunContext,
    *,
    failed_stage: str = "",
    reason_substr: str = "",
) -> int:
    """Reset halt counters after the root cause of those failures was repaired.

    Without this, a G1/topology heal cannot resume EDL: the supervisor keeps
    `halt=True` for the old G1-missing signature and needs_operator loops.
    """
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    stage_key = str(failed_stage or "").strip().lower()
    needle = str(reason_substr or "").strip().lower()
    cleared = 0
    for sig, row in list(signatures.items()):
        if not isinstance(row, dict):
            continue
        stage = str(row.get("failed_stage") or "").strip().lower()
        reason = str(row.get("reason") or row.get("raw_reason") or "").lower()
        if stage_key and stage != stage_key:
            continue
        if needle and needle not in reason:
            continue
        row = dict(row)
        row["count"] = 0
        row["halt"] = False
        row["cleared_at"] = _utc_now()
        signatures[sig] = row
        cleared += 1
    if not cleared:
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared
