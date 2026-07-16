"""GUI/API helpers for browsing and editing LLM call records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.file_store import write_json
from interview_mux.llm_call_record import (
    INDEX_NAME,
    load_call_record,
    list_calls_for_run,
    messages_to_openai_format,
)
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER, FLOW2_ORDER, FLOW3_ORDER
from interview_mux.run_context import RunContext

LLM_CALLS_PREFIX = "understanding/llm_calls/"


def _iter_llm_call_index_paths(ctx: RunContext) -> list[Path]:
    """Committed index plus any staged indexes under .pending_writes/."""
    paths: list[Path] = []
    committed = ctx.run_dir / "understanding" / "llm_calls" / INDEX_NAME
    if committed.is_file():
        paths.append(committed)
    pending_root = ctx.run_dir / ".pending_writes"
    if pending_root.is_dir():
        for stage_dir in sorted(pending_root.iterdir()):
            if not stage_dir.is_dir():
                continue
            staged = stage_dir / "understanding" / "llm_calls" / INDEX_NAME
            if staged.is_file() and staged not in paths:
                paths.append(staged)
    return paths


def _list_call_rows(ctx: RunContext) -> list[dict[str, Any]]:
    """Merge LLM call index rows; staged entries override committed paths."""
    index_paths = _iter_llm_call_index_paths(ctx)
    if not index_paths:
        return list_calls_for_run(ctx.run_dir)
    by_path: dict[str, dict[str, Any]] = {}
    for index_path in index_paths:
        for line in index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rel = str(row.get("path", "")).replace("\\", "/")
            if rel:
                by_path[rel] = row
    return list(by_path.values())


def _resolve_llm_call_path(ctx: RunContext, rel: str) -> Path:
    return ctx.read_path(*rel.split("/"))


def _stage_sort_key(stage_key: str) -> tuple[int, str]:
    order: list[str] = []
    for seq in (ANALYSIS_ORDER, DELIVERY_ORDER, FLOW2_ORDER, FLOW3_ORDER):
        for s in seq:
            if s not in order:
                order.append(s)
    if stage_key in order:
        return (order.index(stage_key), stage_key)
    return (9999, stage_key)


def _assert_llm_call_path(path: str) -> None:
    norm = path.replace("\\", "/").lstrip("/")
    if ".." in norm.split("/"):
        raise ValueError("Invalid path")
    if not norm.startswith(LLM_CALLS_PREFIX) or not norm.endswith(".json"):
        raise ValueError("Path must be an llm_calls JSON record")


def _summarize_record(doc: dict[str, Any], rel_path: str) -> dict[str, Any]:
    volley = doc.get("volley") or {}
    turns = volley.get("turns") or []
    return {
        "path": rel_path,
        "call_id": doc.get("call_id"),
        "label": doc.get("label"),
        "stage_key": doc.get("stage_key"),
        "attempt": doc.get("attempt"),
        "sequence": doc.get("sequence"),
        "task_kind": doc.get("task_kind"),
        "importance": doc.get("importance"),
        "provider": doc.get("provider"),
        "model_id": doc.get("model_id"),
        "model_tier": doc.get("model_tier"),
        "recorded_at": doc.get("recorded_at"),
        "context_chars": doc.get("context_chars"),
        "truncation_flags": doc.get("truncation_flags") or [],
        "turn_count": len(turns),
        "has_system": bool((volley.get("system_prompt") or "").strip()),
        "verification_ok": (doc.get("verification") or {}).get("ok", True),
        "interaction_id": doc.get("interaction_id"),
    }


def list_verification_alerts(ctx: RunContext) -> list[dict[str, Any]]:
    """Recent LLM calls with failed schema verification (for GUI attention)."""
    rows = _list_call_rows(ctx)
    alerts: list[dict[str, Any]] = []
    for row in reversed(rows[-40:]):
        rel = str(row.get("path", "")).replace("\\", "/")
        if not rel:
            continue
        full = _resolve_llm_call_path(ctx, rel)
        if not full.is_file():
            continue
        try:
            doc = load_call_record(full)
        except (json.JSONDecodeError, OSError):
            continue
        ver = doc.get("verification") or {}
        if ver.get("ok") is False:
            alerts.append(
                {
                    "stage_key": doc.get("stage_key"),
                    "interaction_id": doc.get("interaction_id") or ver.get("interaction_id"),
                    "errors": ver.get("errors") or [],
                    "path": rel,
                    "task_kind": doc.get("task_kind"),
                }
            )
    return alerts[:10]


def list_llm_calls_summary(ctx: RunContext) -> dict[str, Any]:
    """Index rows + nested tree for GUI (summaries only)."""
    rows = _list_call_rows(ctx)
    calls: list[dict[str, Any]] = []
    for row in rows:
        rel = row.get("path", "").replace("\\", "/")
        full = _resolve_llm_call_path(ctx, rel) if rel else None
        if full and full.is_file():
            try:
                doc = load_call_record(full)
                calls.append(_summarize_record(doc, rel))
            except (json.JSONDecodeError, OSError):
                calls.append({**row, "path": rel, "load_error": True})
        else:
            calls.append({**row, "path": rel})

    calls.sort(
        key=lambda c: (
            _stage_sort_key(str(c.get("stage_key", ""))),
            int(c.get("attempt") or 0),
            int(c.get("sequence") or 0),
        )
    )

    tree: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for c in calls:
        stage = str(c.get("stage_key", "unknown"))
        attempt = int(c.get("attempt") or 1)
        key = f"attempt_{attempt:03d}"
        tree.setdefault(stage, {}).setdefault(key, []).append(c)

    stages = sorted(tree.keys(), key=lambda s: _stage_sort_key(s))
    return {
        "run_id": ctx.run_id,
        "call_count": len(calls),
        "calls": calls,
        "tree": tree,
        "stages": stages,
        "verification_alerts": list_verification_alerts(ctx),
    }


def get_llm_call_record(ctx: RunContext, path: str) -> dict[str, Any]:
    _assert_llm_call_path(path)
    full = _resolve_llm_call_path(ctx, path)
    if not full.is_file():
        raise FileNotFoundError(path)
    doc = load_call_record(full)
    doc["_gui"] = {
        "path": path.replace("\\", "/"),
        "openai_messages": messages_to_openai_format(doc),
    }
    return doc


def update_llm_call_record(
    ctx: RunContext,
    path: str,
    *,
    volley: dict[str, Any] | None = None,
    raw_response: str | None = None,
) -> dict[str, Any]:
    _assert_llm_call_path(path)
    full = _resolve_llm_call_path(ctx, path)
    if not full.is_file():
        raise FileNotFoundError(path)
    doc = load_call_record(full)

    if volley is not None:
        system = str(volley.get("system_prompt") or "")
        turns = volley.get("turns") or []
        if not isinstance(turns, list):
            raise ValueError("volley.turns must be a list")
        clean_turns: list[dict[str, str]] = []
        for t in turns:
            role = str(t.get("role", "")).strip()
            if role not in ("user", "assistant"):
                raise ValueError(f"Invalid volley role: {role}")
            clean_turns.append({"role": role, "content": str(t.get("content", ""))})
        doc["volley"] = {"system_prompt": system, "turns": clean_turns}
        rebuilt: list[dict[str, str]] = []
        if system.strip():
            rebuilt.append({"role": "system", "content": system})
        rebuilt.extend(clean_turns)
        doc.setdefault("request", {})["messages"] = rebuilt
        doc["context_chars"] = sum(len(m.get("content", "")) for m in rebuilt)
        if raw_response is not None:
            doc["context_chars"] += len(raw_response)
        elif (doc.get("response") or {}).get("raw_content"):
            doc["context_chars"] += len(doc["response"]["raw_content"])

    if raw_response is not None:
        doc.setdefault("response", {})["raw_content"] = raw_response

    write_json(full, doc)
    if _write_markdown_sidecar_enabled():
        md_path = full.with_suffix(".md")
        from interview_mux.llm_call_record import record_to_markdown

        md_path.write_text(record_to_markdown(doc), encoding="utf-8")
    return get_llm_call_record(ctx, path)


def _write_markdown_sidecar_enabled() -> bool:
    rec = (merged_config().get("analysis") or {}).get("llm_call_records") or {}
    return bool(rec.get("write_markdown_sidecar", True))
