"""Crash-safe append-only ledger. Append before side effects."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

LEDGER_REL = "mastering/homunculus/ledger.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_ledger(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists(LEDGER_REL):
        return []
    raw = ctx.read_json(LEDGER_REL)
    if isinstance(raw, dict):
        rows = raw.get("entries")
        return list(rows) if isinstance(rows, list) else []
    if isinstance(raw, list):
        return list(raw)
    return []


def append_ledger(ctx: RunContext, entry: dict[str, Any]) -> dict[str, Any]:
    rows = read_ledger(ctx)
    row = dict(entry)
    row.setdefault("at", _now())
    row.setdefault("seq", len(rows) + 1)
    rows.append(row)
    ctx.write_json(LEDGER_REL, {"schema_version": 1, "entries": rows})
    return row


def count_identity(ctx: RunContext, identity: str) -> int:
    """Count invokes. started (or unstatused) rows only — done/failed are not extra invokes."""
    n = 0
    for row in read_ledger(ctx):
        if row.get("identity") != identity:
            continue
        status = row.get("status")
        if status in (None, "started"):
            n += 1
    return n


def count_problem(ctx: RunContext, problem_id: str) -> int:
    return sum(
        1
        for row in read_ledger(ctx)
        if row.get("kind") == "analyze_issue" and row.get("problem_id") == problem_id
    )


def has_packet_hash(ctx: RunContext, identity: str, packet_hash: str) -> bool:
    return any(
        row.get("identity") == identity and row.get("packet_hash") == packet_hash
        for row in read_ledger(ctx)
    )


def packet_hash_for(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def last_fact_ids(ctx: RunContext) -> list[str]:
    for row in reversed(read_ledger(ctx)):
        ids = row.get("fact_ids")
        if isinstance(ids, list) and ids:
            return [str(x) for x in ids]
    return []


def last_fact_ids_for_tool(ctx: RunContext, tool_id: str) -> list[str]:
    for row in reversed(read_ledger(ctx)):
        if row.get("kind") != "pack_volley":
            continue
        if str(row.get("tool_id") or "") != tool_id:
            continue
        ids = row.get("fact_ids")
        if isinstance(ids, list) and ids:
            return [str(x) for x in ids]
    return []


def remainder_requested(ctx: RunContext) -> bool:
    return any(row.get("kind") == "walk_seed_remainder" for row in read_ledger(ctx))
