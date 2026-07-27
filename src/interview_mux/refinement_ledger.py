"""Ordered refinement call ledger — anti-loop counts per CFI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

LEDGER_REL = "understanding/refinement_ledger.json"


def _empty(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "schema_version": 1,
        "calls": [],
        "counts_by_cfi": {},
        "order_of_refinement_pass_ids": [],
    }


def load_ledger(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(LEDGER_REL):
        return _empty(ctx.run_id)
    doc = ctx.read_json(LEDGER_REL)
    if not isinstance(doc, dict):
        return _empty(ctx.run_id)
    doc.setdefault("calls", [])
    doc.setdefault("counts_by_cfi", {})
    doc.setdefault("order_of_refinement_pass_ids", [])
    doc.setdefault("schema_version", 1)
    return doc


def save_ledger(ctx: RunContext, doc: dict[str, Any]) -> None:
    doc["run_id"] = ctx.run_id
    ctx.write_json(LEDGER_REL, doc, skip_handoff=True)


def refinement_count(ctx: RunContext, cfi_id: str) -> int:
    doc = load_ledger(ctx)
    row = (doc.get("counts_by_cfi") or {}).get(cfi_id) or {}
    return int(row.get("refinement") or 0)


def first_pass_count(ctx: RunContext, cfi_id: str) -> int:
    doc = load_ledger(ctx)
    row = (doc.get("counts_by_cfi") or {}).get(cfi_id) or {}
    return int(row.get("first_pass") or 0)


def can_run_refinement(ctx: RunContext, cfi_id: str, *, max_second: int = 1) -> bool:
    return refinement_count(ctx, cfi_id) < max_second


def record_call(
    ctx: RunContext,
    *,
    cfi_id: str,
    human_key: str,
    stage_id: str,
    pass_id: str | None,
    pass_index: int,
    kind: str,
    outcome: str = "ok",
    refines_cfi: str | None = None,
    gate: str | None = None,
    input_hash: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from interview_mux.refinement_catalog import refinement_cfg

    cfg = refinement_cfg()
    max_second = int(cfg.get("max_second_runs_per_cfi") or 1)
    if kind == "refinement" and not can_run_refinement(ctx, cfi_id, max_second=max_second):
        ctx.log(
            f"refinement_ledger: blocked second run for {cfi_id}",
            level="warning",
            stage=stage_id,
            action_id="refinement_blocked_cap",
            detail={"cfi_id": cfi_id},
        )
        raise RuntimeError(f"refinement cap exceeded for CFI {cfi_id}")

    doc = load_ledger(ctx)
    calls: list[dict[str, Any]] = list(doc.get("calls") or [])
    seq = len(calls) + 1
    entry: dict[str, Any] = {
        "seq": seq,
        "at": datetime.now(timezone.utc).isoformat(),
        "cfi_id": cfi_id,
        "human_key": human_key,
        "stage_id": stage_id,
        "pass_id": pass_id,
        "pass_index": pass_index,
        "kind": kind,
        "outcome": outcome,
    }
    if refines_cfi:
        entry["refines_cfi"] = refines_cfi
    if gate:
        entry["gate"] = gate
    if input_hash:
        entry["input_hash"] = input_hash
    if detail:
        entry["detail"] = detail
    calls.append(entry)
    doc["calls"] = calls

    counts = dict(doc.get("counts_by_cfi") or {})
    row = dict(counts.get(cfi_id) or {"first_pass": 0, "refinement": 0, "total": 0})
    if kind == "refinement":
        row["refinement"] = int(row.get("refinement") or 0) + 1
    else:
        row["first_pass"] = int(row.get("first_pass") or 0) + 1
    row["total"] = int(row.get("first_pass") or 0) + int(row.get("refinement") or 0)
    counts[cfi_id] = row
    doc["counts_by_cfi"] = counts

    if kind == "refinement" and pass_id:
        order = list(doc.get("order_of_refinement_pass_ids") or [])
        if pass_id not in order:
            order.append(pass_id)
        doc["order_of_refinement_pass_ids"] = order

    save_ledger(ctx, doc)
    return entry


def reset_ledger_from_stages(ctx: RunContext, stage_ids: set[str]) -> None:
    """Drop calls whose stage_id is in the cleared set; recompute counts."""
    doc = load_ledger(ctx)
    kept = [c for c in (doc.get("calls") or []) if str(c.get("stage_id") or "") not in stage_ids]
    counts: dict[str, dict[str, int]] = {}
    order: list[str] = []
    for i, c in enumerate(kept, start=1):
        c["seq"] = i
        cid = str(c.get("cfi_id") or "")
        row = counts.setdefault(cid, {"first_pass": 0, "refinement": 0, "total": 0})
        kind = str(c.get("kind") or "first_pass")
        if kind == "refinement":
            row["refinement"] += 1
            pid = c.get("pass_id")
            if pid and pid not in order:
                order.append(str(pid))
        else:
            row["first_pass"] += 1
        row["total"] = row["first_pass"] + row["refinement"]
    doc["calls"] = kept
    doc["counts_by_cfi"] = counts
    doc["order_of_refinement_pass_ids"] = order
    save_ledger(ctx, doc)
