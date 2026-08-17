"""Admit every tool/LLM output: keep, reformat, or drop. Persist only after keep/reformat."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.homunculus.ledger import append_ledger
from interview_mux.run_context import RunContext

AdmitAction = Literal["keep", "reformat", "drop"]
ADMITTED_REL = "mastering/homunculus/admitted.jsonl"
MEMORY_REL = "mastering/homunculus/memory.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def admit(
    ctx: RunContext,
    *,
    identity: str,
    action: AdmitAction,
    payload: Any,
    fact_id: str | None = None,
    reformat_as: dict[str, Any] | None = None,
    downstream: list[str] | None = None,
    docs_cited: list[str] | None = None,
) -> dict[str, Any]:
    fid = fact_id or f"{identity}:{_now()}"
    record = {
        "at": _now(),
        "identity": identity,
        "action": action,
        "fact_id": fid,
        "downstream": list(downstream or []),
        "docs_cited": list(docs_cited or []),
        "reformat_as": reformat_as,
    }
    _append_jsonl(ctx, ADMITTED_REL, record)
    append_ledger(
        ctx,
        {
            "kind": "admit",
            "identity": f"admit:{identity}",
            "action": action,
            "fact_id": fid,
            "docs_cited": record["docs_cited"],
        },
    )
    if action == "drop":
        return record
    meaning = _tape_meaning(reformat_as if action == "reformat" and reformat_as else payload)
    _remember(ctx, fid, identity, meaning)
    return record


def persist_artifact(ctx: RunContext, rel: str, payload: Any, *, fact_id: str) -> None:
    """Write only after a keep/reformat admit for this fact."""
    if not _fact_admitted_keep(ctx, fact_id):
        raise RuntimeError(f"persist refused: fact {fact_id} was not keep/reformat admitted")
    from interview_mux.homunculus.ledger import read_ledger

    for row in read_ledger(ctx):
        if (
            row.get("kind") == "persist"
            and row.get("fact_id") == fact_id
            and row.get("rel") == rel
            and row.get("status") == "done"
        ):
            return
    append_ledger(
        ctx,
        {"kind": "persist", "identity": "persist_artifact", "fact_id": fact_id, "rel": rel, "status": "started"},
    )
    setattr(ctx, "_homunculus_persisting", True)
    try:
        ctx.write_json(rel, payload)
    finally:
        if hasattr(ctx, "_homunculus_persisting"):
            delattr(ctx, "_homunculus_persisting")
    append_ledger(
        ctx,
        {"kind": "persist", "identity": "persist_artifact", "fact_id": fact_id, "rel": rel, "status": "done"},
    )


def _fact_admitted_keep(ctx: RunContext, fact_id: str) -> bool:
    for row in read_admitted(ctx):
        if row.get("fact_id") == fact_id and row.get("action") in {"keep", "reformat"}:
            return True
    return False


def read_admitted(ctx: RunContext) -> list[dict[str, Any]]:
    path = ctx.path(ADMITTED_REL)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def read_memory(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(MEMORY_REL):
        return {"facts": []}
    raw = ctx.read_json(MEMORY_REL)
    return raw if isinstance(raw, dict) else {"facts": []}


def memory_facts(ctx: RunContext) -> list[dict[str, Any]]:
    facts = read_memory(ctx).get("facts") or []
    return list(facts) if isinstance(facts, list) else []


def _remember(ctx: RunContext, fact_id: str, identity: str, meaning: Any) -> None:
    mem = read_memory(ctx)
    facts = list(mem.get("facts") or [])
    facts.append(
        {
            "fact_id": fact_id,
            "identity": identity,
            "meaning": meaning,
            "at": _now(),
        }
    )
    ctx.write_json(MEMORY_REL, {"schema_version": 1, "facts": facts})


def _tape_meaning(payload: Any) -> Any:
    if isinstance(payload, dict):
        denied = {"exists", "stage_done", "run_meta", "path_ok", "file_exists"}
        return {k: v for k, v in payload.items() if k not in denied}
    return payload


def _append_jsonl(ctx: RunContext, rel: str, row: dict[str, Any]) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
