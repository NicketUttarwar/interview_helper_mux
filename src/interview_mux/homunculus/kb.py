"""Per-run knowledge base — lessons, style tags, conductor thinking notes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.homunculus.ledger import append_ledger
from interview_mux.run_context import RunContext

KB_REL = "mastering/homunculus/kb.json"
THINKING_REL = "mastering/homunculus/thinking.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_kb(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(KB_REL):
        return {"schema_version": 1, "lessons": [], "styles": [], "musicgen": {}}
    raw = ctx.read_json(KB_REL)
    if not isinstance(raw, dict):
        return {"schema_version": 1, "lessons": [], "styles": [], "musicgen": {}}
    raw.setdefault("lessons", [])
    raw.setdefault("styles", [])
    raw.setdefault("musicgen", {})
    return raw


def write_kb(ctx: RunContext, doc: dict[str, Any]) -> dict[str, Any]:
    doc["schema_version"] = 1
    ctx.write_json(KB_REL, doc)
    return doc


def append_thinking(ctx: RunContext, note: str, *, identity: str = "conductor") -> dict[str, Any]:
    from interview_mux.volley_packet_lint import strip_forbidden_metadata

    cleaned = strip_forbidden_metadata({"note": note})
    text = str(cleaned.get("note") if isinstance(cleaned, dict) else note)[:4000]
    row = {"at": _now(), "identity": identity, "note": text}
    path = ctx.path(THINKING_REL)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    append_ledger(ctx, {"kind": "thinking", "identity": f"thinking:{identity}"})
    return row


def record_style(ctx: RunContext, *, speaker_id: str, style: str, source: str) -> dict[str, Any]:
    doc = read_kb(ctx)
    styles = list(doc.get("styles") or [])
    entry = {"speaker_id": speaker_id, "style": style, "source": source, "at": _now()}
    styles.append(entry)
    doc["styles"] = styles[-80:]
    write_kb(ctx, doc)
    return entry


def record_musicgen_outcome(ctx: RunContext, meta: dict[str, Any]) -> None:
    doc = read_kb(ctx)
    mg = dict(doc.get("musicgen") or {})
    step = str(meta.get("fidelity_step") or meta.get("model_id") or "")
    backend = str(meta.get("backend") or "")
    mg["last_step"] = step
    mg["last_backend"] = backend
    if "large" not in step.lower() or backend in {"mmaudio", "mmaudio_backup", "musical_stub"}:
        mg["large_aborted"] = True
        mg["do_not_insist_large"] = True
    mg["at"] = _now()
    doc["musicgen"] = mg
    write_kb(ctx, doc)


def musicgen_large_aborted(ctx: RunContext) -> bool:
    return bool((read_kb(ctx).get("musicgen") or {}).get("large_aborted"))


def record_reject_lessons(
    ctx: RunContext,
    *,
    failed_dimensions: list[str],
    implicated_groups: list[str],
    reason: str,
) -> list[dict[str, Any]]:
    from interview_mux.homunculus.source_card import read_source_card

    card = read_source_card(ctx) or {}
    doc = read_kb(ctx)
    lessons_rows = list(doc.get("lessons") or [])
    added: list[dict[str, Any]] = []
    dims = failed_dimensions or ["reject"]
    for dim in dims:
        lesson_id = f"lesson:{dim}:{len(lessons_rows) + len(added) + 1}"
        row = {
            "lesson_id": lesson_id,
            "do_not_repeat": True,
            "failed_dimension": dim,
            "implicated_groups": list(implicated_groups or []),
            "topology": card.get("topology") or card.get("format_class"),
            "speaker_id": card.get("pickup_speaker_id"),
            "reason": reason[:400],
            "at": _now(),
        }
        lessons_rows.append(row)
        added.append(row)
    doc["lessons"] = lessons_rows[-40:]
    write_kb(ctx, doc)
    append_ledger(
        ctx,
        {
            "kind": "kb_lesson",
            "identity": "kb",
            "lesson_ids": [r["lesson_id"] for r in added],
        },
    )
    return added


def lessons(ctx: RunContext) -> list[dict[str, Any]]:
    raw = read_kb(ctx).get("lessons") or []
    return [r for r in raw if isinstance(r, dict)]


def lesson_ids(ctx: RunContext) -> list[str]:
    return [str(r.get("lesson_id")) for r in lessons(ctx) if r.get("lesson_id")]
