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
    """Count open invokes: started rows not closed by a matching failed status.

    Successful runs keep their ``started`` row (``done`` is not an extra invoke).
    Failed attempts do not burn the cap. Nested ``llm`` rows for a stage that
    already has ``kind=stage`` (or host) dispatches are part of that invoke —
    they must not consume extra identity counts.
    """
    rows = [r for r in read_ledger(ctx) if r.get("identity") == identity]
    kinds = {r.get("kind") for r in rows}
    if "stage" in kinds or "host" in kinds:
        rows = [r for r in rows if r.get("kind") in {"stage", "host"}]
    started = 0
    failed = 0
    done = 0
    for row in rows:
        status = row.get("status")
        if status in (None, "started"):
            started += 1
        elif status == "failed":
            failed += 1
        elif status == "done":
            done += 1
    if "stage" in kinds or "host" in kinds:
        # Only finished pipeline work burns the cap. Unclosed started rows
        # (SystemExit / recycle) and ledger-done without .stage_done do not.
        if not ctx.is_done(identity):
            return 0
    return max(0, started - failed)


def count_problem(ctx: RunContext, problem_id: str) -> int:
    return sum(
        1
        for row in read_ledger(ctx)
        if row.get("kind") == "analyze_issue" and row.get("problem_id") == problem_id
    )


def has_packet_hash(ctx: RunContext, identity: str, packet_hash: str) -> bool:
    """True only while an identical packed call is in flight for this identity.

    Completed hashes may retry when the stage did not persist — schema retries
    and re-executes after a starved pack must not hard-stop the run.

    ``done``/``failed`` rows historically omitted ``packet_hash``; close any
    open start for this identity when a later terminal row appears (exec_11165
    specialist identical_packed_call sticky).
    """
    open_started = False
    for row in read_ledger(ctx):
        if row.get("identity") != identity:
            continue
        status = row.get("status")
        row_hash = str(row.get("packet_hash") or "")
        if status == "started" and row_hash == packet_hash:
            open_started = True
        elif status in {"done", "failed"}:
            # Terminal row closes in-flight starts for this identity. Prefer
            # hash match when present; otherwise close sticky starts whose done
            # rows were written without packet_hash (legacy ledger).
            if not row_hash or row_hash == packet_hash:
                open_started = False
    return open_started


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
    """True only until the matching seed walk runs — not sticky across later phases."""
    requested = False
    for row in read_ledger(ctx):
        kind = row.get("kind")
        if kind == "walk_seed_remainder":
            requested = True
        elif kind == "fallback" and row.get("identity") == "walk_seed_agenda":
            requested = False
    return requested
