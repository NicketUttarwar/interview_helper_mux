"""Compile bounded, provenanced evidence packets for mastering LLM consumers.

Spec: docs/cross-cutting/mastering-quality-hardening.md (Workstream 2)
Schema: mastering_evidence_packet.schema.json
Artifact: mastering/evidence_packets/{consumer_id}.json
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_hardening_config import gate_cfg
from interview_mux.run_context import RunContext

PACKET_DIR = "mastering/evidence_packets"

# Rough characters-per-token; deliberately conservative so budgets are not exceeded.
_CHARS_PER_TOKEN = 4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_tokens(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def content_hash(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_item(
    *,
    ref: str,
    kind: str,
    salience: float,
    inline: Any = None,
    sha256: str | None = None,
    segment_ids: list[str] | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    confidence: float | None = None,
    freshness: str = "current",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ref": ref,
        "kind": kind,
        "salience": max(0.0, min(1.0, float(salience))),
        "freshness": freshness,
        "inline": inline,
        "tokens": estimate_tokens(inline),
    }
    if sha256 is not None:
        item["sha256"] = sha256
    elif inline is not None:
        item["sha256"] = content_hash(inline)
    if segment_ids:
        item["segment_ids"] = list(segment_ids)
    if start_ms is not None:
        item["start_ms"] = int(start_ms)
    if end_ms is not None:
        item["end_ms"] = int(end_ms)
        if start_ms is not None:
            item["duration_ms"] = max(0, int(end_ms) - int(start_ms))
    if confidence is not None:
        item["confidence"] = max(0.0, min(1.0, float(confidence)))
    return item


def compile_packet(
    *,
    consumer_id: str,
    items: list[dict[str, Any]],
    consumer_kind: str = "other",
    max_tokens: int | None = None,
    truncation_policy: str | None = None,
    inline_max_chars: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fit `items` inside a token budget, keeping provenance for everything dropped.

    Items are never silently lost: anything that does not fit is recorded in
    `omitted` with its ref so the consumer can still retrieve it on demand.
    """
    conf = gate_cfg("context", cfg)
    budget = int(max_tokens if max_tokens is not None else conf["default_max_tokens"])
    policy = str(truncation_policy or conf["truncation_policy"])
    inline_cap = int(inline_max_chars if inline_max_chars is not None else conf["inline_max_chars"])

    prepared = [_apply_inline_cap(dict(item), inline_cap, policy) for item in items]
    ordered = sorted(prepared, key=_salience_key, reverse=True)

    kept: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    used = 0
    for item in ordered:
        tokens = int(item.get("tokens") or estimate_tokens(item.get("inline")))
        if used + tokens <= budget:
            item["tokens"] = tokens
            kept.append(item)
            used += tokens
            continue
        pointer = _as_pointer(item)
        pointer_tokens = int(pointer.get("tokens") or 0)
        if policy != "drop_lowest_salience" and used + pointer_tokens <= budget:
            kept.append(pointer)
            used += pointer_tokens
            continue
        omitted.append(
            {
                "ref": str(item.get("ref")),
                "reason": f"budget exceeded ({tokens} tokens, {budget - used} remaining)",
                "salience": item.get("salience"),
            }
        )

    return {
        "version": 1,
        "consumer_id": consumer_id,
        "consumer_kind": consumer_kind,
        "budget": {
            "max_tokens": budget,
            "used_tokens": used,
            "truncation_policy": policy,
            "exceeded": bool(omitted),
        },
        "items": kept,
        "omitted": omitted,
        "generated_at": _now(),
    }


def _salience_key(item: dict[str, Any]) -> tuple[float, str]:
    return (float(item.get("salience") or 0.0), str(item.get("ref") or ""))


def _apply_inline_cap(item: dict[str, Any], inline_cap: int, policy: str) -> dict[str, Any]:
    """Replace oversized inline content with a pointer, preserving the hash."""
    inline = item.get("inline")
    if inline is None:
        item["tokens"] = 0
        return item
    text = inline if isinstance(inline, str) else json.dumps(inline, ensure_ascii=False)
    if len(text) <= inline_cap:
        item["tokens"] = estimate_tokens(inline)
        return item
    item.setdefault("sha256", content_hash(inline))
    if policy == "summarize":
        item["inline"] = text[:inline_cap]
        item["truncated"] = True
    else:
        item["inline"] = None
        item["truncated"] = True
    item["tokens"] = estimate_tokens(item["inline"])
    return item


def _as_pointer(item: dict[str, Any]) -> dict[str, Any]:
    pointer = dict(item)
    pointer["inline"] = None
    pointer["truncated"] = True
    pointer["tokens"] = 0
    return pointer


def packet_rel(consumer_id: str) -> str:
    return f"{PACKET_DIR}/{consumer_id}.json"


def write_packet(ctx: RunContext, packet: dict[str, Any]) -> None:
    ctx.write_json(packet_rel(str(packet["consumer_id"])), packet)


def load_packet(ctx: RunContext, consumer_id: str) -> dict[str, Any] | None:
    rel = packet_rel(consumer_id)
    if not ctx.artifact_exists(rel):
        return None
    doc = ctx.read_json(rel)
    return doc if isinstance(doc, dict) else None


def provenance_complete(packet: dict[str, Any]) -> list[str]:
    """Refs whose inline content is present but unhashed — provenance holes."""
    holes: list[str] = []
    for item in packet.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("inline") is not None and not item.get("sha256"):
            holes.append(str(item.get("ref")))
    return holes
