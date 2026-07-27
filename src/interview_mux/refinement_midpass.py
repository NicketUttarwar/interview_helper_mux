"""On-flight mid-pass helpers — shard / early-exit inside one CFI count."""

from __future__ import annotations

from typing import Any, Callable


def shard_lines_by_act(
    lines: list[dict[str, Any]],
    *,
    chapters: list[dict[str, Any]] | None = None,
    max_per_shard: int = 12,
) -> list[list[dict[str, Any]]]:
    """Split interviewer lines into act/chapter shards for long recomposes.

    Still counts as **one** ledger refinement when the outer pass records once.
    """
    if not lines:
        return []
    if chapters:
        buckets: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            cid = str(ch.get("chapter_id") or ch.get("id") or f"ch_{len(order)}")
            order.append(cid)
            buckets[cid] = []
        unassigned: list[dict[str, Any]] = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            act = str(line.get("act_id") or line.get("chapter_id") or "")
            if act and act in buckets:
                buckets[act].append(line)
            else:
                unassigned.append(line)
        shards = [buckets[cid] for cid in order if buckets.get(cid)]
        if unassigned:
            shards.append(unassigned)
        if shards:
            return shards
    # Fallback: fixed-size shards
    return [lines[i : i + max_per_shard] for i in range(0, len(lines), max_per_shard)]


def early_exit_if_shard_fails(
    shard_results: list[dict[str, Any]],
    *,
    ok_key: str = "ok",
) -> dict[str, Any] | None:
    """If the first shard fails rubric/feasibility, quarantine and keep champion.

    Returns a quarantine payload when early-exit should fire; else None.
    """
    if not shard_results:
        return None
    first = shard_results[0]
    if not isinstance(first, dict):
        return {"quarantine": True, "reason_code": "shard_invalid", "kept_champion": True}
    if first.get(ok_key) is False or first.get("accepted") is False:
        return {
            "quarantine": True,
            "reason_code": str(first.get("reason_code") or "shard_fail"),
            "kept_champion": True,
            "failed_shard_index": 0,
        }
    return None


def run_sharded(
    lines: list[dict[str, Any]],
    process_shard: Callable[[list[dict[str, Any]], int], dict[str, Any]],
    *,
    chapters: list[dict[str, Any]] | None = None,
    max_per_shard: int = 12,
) -> dict[str, Any]:
    """Process shards sequentially; early-exit on first failure; one outer CFI."""
    shards = shard_lines_by_act(lines, chapters=chapters, max_per_shard=max_per_shard)
    results: list[dict[str, Any]] = []
    merged: list[dict[str, Any]] = []
    for idx, shard in enumerate(shards):
        result = process_shard(shard, idx)
        results.append(result)
        quit_payload = early_exit_if_shard_fails(results)
        if quit_payload:
            return {**quit_payload, "shard_results": results, "lines": merged}
        if isinstance(result.get("lines"), list):
            merged.extend(result["lines"])
        else:
            merged.extend(shard)
    return {
        "quarantine": False,
        "shard_count": len(shards),
        "shard_results": results,
        "lines": merged,
    }
