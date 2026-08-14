"""Durable per-unit job manifests for long-running delivery work."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

JOBS_ROOT = "jobs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def job_rel(stage_id: str, job_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in job_id)
    return f"{JOBS_ROOT}/{stage_id}/{safe}.json"


def input_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def load_job(ctx: RunContext, stage_id: str, job_id: str) -> dict[str, Any] | None:
    rel = job_rel(stage_id, job_id)
    path = Path(ctx.run_dir) / rel
    if not path.is_file():
        return None
    try:
        data = ctx.read_json(rel)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_job(ctx: RunContext, doc: dict[str, Any]) -> Path:
    stage_id = str(doc.get("stage_id") or "unknown")
    job_id = str(doc.get("job_id") or "job")
    rel = job_rel(stage_id, job_id)
    dest = Path(ctx.run_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(doc)
    doc["updated_at"] = _utc_now()
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(dest, doc)
    return dest


def begin_job(
    ctx: RunContext,
    *,
    stage_id: str,
    job_id: str,
    units: list[str],
    input_payload: Any = None,
    ladder_step: str | None = None,
) -> dict[str, Any]:
    existing = load_job(ctx, stage_id, job_id)
    if existing and existing.get("status") == "completed":
        return existing
    unit_docs = []
    prev_units = {
        str(u.get("unit_id")): u
        for u in (existing.get("units") or [])
        if isinstance(u, dict)
    } if existing else {}
    for uid in units:
        prev = prev_units.get(uid) or {}
        if prev.get("status") == "completed" and prev.get("output_path"):
            unit_docs.append(dict(prev))
        else:
            unit_docs.append(
                {
                    "unit_id": uid,
                    "status": "pending",
                    "output_path": prev.get("output_path"),
                    "checksum": prev.get("checksum"),
                    "attempts": int(prev.get("attempts") or 0),
                }
            )
    doc = {
        "version": 1,
        "job_id": job_id,
        "stage_id": stage_id,
        "status": "running",
        "input_hash": input_hash(input_payload) if input_payload is not None else (
            str(existing.get("input_hash") or "") if existing else ""
        ),
        "ladder_step": ladder_step or (existing.get("ladder_step") if existing else None),
        "attempts": int((existing or {}).get("attempts") or 0) + 1,
        "heartbeat_at": _utc_now(),
        "terminal_error": None,
        "units": unit_docs,
        "created_at": (existing or {}).get("created_at") or _utc_now(),
        "updated_at": _utc_now(),
    }
    save_job(ctx, doc)
    return doc


def heartbeat_job(ctx: RunContext, stage_id: str, job_id: str) -> None:
    doc = load_job(ctx, stage_id, job_id)
    if not doc:
        return
    doc["heartbeat_at"] = _utc_now()
    save_job(ctx, doc)


def complete_unit(
    ctx: RunContext,
    stage_id: str,
    job_id: str,
    unit_id: str,
    *,
    output_path: str,
    checksum: str | None = None,
) -> dict[str, Any]:
    doc = load_job(ctx, stage_id, job_id) or begin_job(
        ctx, stage_id=stage_id, job_id=job_id, units=[unit_id]
    )
    units = []
    for u in doc.get("units") or []:
        if not isinstance(u, dict):
            continue
        if str(u.get("unit_id")) == unit_id:
            u = dict(u)
            u["status"] = "completed"
            u["output_path"] = output_path
            if checksum:
                u["checksum"] = checksum
            u["attempts"] = int(u.get("attempts") or 0) + 1
        units.append(u)
    doc["units"] = units
    doc["heartbeat_at"] = _utc_now()
    pending = [u for u in units if u.get("status") != "completed"]
    doc["status"] = "completed" if not pending else "partial"
    save_job(ctx, doc)
    return doc


def fail_unit(
    ctx: RunContext,
    stage_id: str,
    job_id: str,
    unit_id: str,
    *,
    error: str,
) -> dict[str, Any]:
    doc = load_job(ctx, stage_id, job_id) or begin_job(
        ctx, stage_id=stage_id, job_id=job_id, units=[unit_id]
    )
    units = []
    for u in doc.get("units") or []:
        if not isinstance(u, dict):
            continue
        if str(u.get("unit_id")) == unit_id:
            u = dict(u)
            u["status"] = "failed"
            u["error"] = error[:800]
            u["attempts"] = int(u.get("attempts") or 0) + 1
        units.append(u)
    doc["units"] = units
    doc["status"] = "partial"
    doc["terminal_error"] = error[:800]
    doc["heartbeat_at"] = _utc_now()
    save_job(ctx, doc)
    return doc


def pending_units(doc: dict[str, Any] | None) -> list[str]:
    if not doc:
        return []
    return [
        str(u.get("unit_id"))
        for u in (doc.get("units") or [])
        if isinstance(u, dict) and u.get("status") != "completed"
    ]


def list_stage_jobs(ctx: RunContext, stage_id: str) -> list[dict[str, Any]]:
    root = Path(ctx.run_dir) / JOBS_ROOT / stage_id
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    from interview_mux.file_store import read_json as fs_read_json

    for path in sorted(root.glob("*.json")):
        try:
            doc = fs_read_json(path)
        except Exception:
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out
