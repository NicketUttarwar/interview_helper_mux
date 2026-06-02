"""
Structured storage for every OpenAI Chat Completions call (and future local LLM calls).

Records are written under understanding/llm_calls/ for copy-paste review and volley reconstruction.
Spec: docs/cross-cutting/llm-call-record-framework.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.file_store import write_json
from interview_mux.run_context import RunContext

SCHEMA_VERSION = 1
INDEX_NAME = "index.jsonl"


class CallImportance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def _importance_for_task_kind(task_kind: str) -> str:
    if task_kind in ("primary", "collate", "arbiter"):
        return CallImportance.HIGH.value
    if task_kind in ("shard", "specialist") or task_kind.startswith("shard"):
        return CallImportance.MEDIUM.value
    return CallImportance.LOW.value


def _phase_for_stage(stage_key: str) -> str:
    flow1 = {
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "edl_narrative_audit",
        "transitions",
        "podcast_sfx_brief",
        "sound_design_palettes",
        "sound_design_plan_flow1",
        "elevenlabs_prompt_craft",
    }
    flow2 = {"highlight_selection", "sfx_brief", "sound_design_plan_flow2"}
    flow3 = {"podcast_show_description"}
    if stage_key in flow1:
        return "flow1"
    if stage_key in flow2:
        return "flow2"
    if stage_key in flow3:
        return "flow3"
    if stage_key.startswith("_"):
        return "system"
    return "analysis"


def build_call_label(
    *,
    stage_key: str,
    attempt: int,
    sequence: int,
    task_kind: str,
) -> str:
    """Stable human label: phase:stage:aNNN:seq:task_kind"""
    phase = _phase_for_stage(stage_key)
    tk = task_kind.replace(" ", "_")
    return f"{phase}:{stage_key}:a{attempt:03d}:{sequence:02d}:{tk}"


def build_call_id(
    *,
    run_id: str,
    stage_key: str,
    attempt: int,
    sequence: int,
    task_kind: str,
) -> str:
    """Unique id across runs (includes run_id)."""
    return f"{run_id}/{stage_key}/a{attempt:03d}/{sequence:02d}_{task_kind}"


def llm_call_records_enabled(cfg: dict[str, Any] | None = None) -> bool:
    analysis = (cfg or merged_config()).get("analysis") or {}
    rec = analysis.get("llm_call_records") or {}
    return bool(rec.get("enabled", True))


def _write_markdown_sidecar(cfg: dict[str, Any]) -> bool:
    rec = (cfg.get("analysis") or {}).get("llm_call_records") or {}
    return bool(rec.get("write_markdown_sidecar", True))


def _attempt_from_ctx(ctx: RunContext, stage_key: str, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    path = ctx.path("understanding", "analysis_orchestration.json")
    if not path.is_file():
        return 1
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return int((doc.get("stage_attempts") or {}).get(stage_key, 1))
    except (json.JSONDecodeError, TypeError, ValueError):
        return 1


def _next_sequence(call_dir: Path) -> int:
    if not call_dir.is_dir():
        return 1
    return len(list(call_dir.glob("*.json"))) + 1


def split_messages_for_volley(
    messages: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    """Separate system prompt from user/assistant volley turns."""
    system_parts: list[str] = []
    volley: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant"):
            volley.append({"role": role, "content": content})
    return "\n\n".join(system_parts), volley


def messages_to_openai_format(record: dict[str, Any]) -> list[dict[str, str]]:
    """Full Chat Completions message list (system + volley)."""
    req = record.get("request") or {}
    if req.get("messages"):
        return list(req["messages"])
    volley = (record.get("volley") or {}).get("turns") or []
    system = (record.get("volley") or {}).get("system_prompt") or ""
    out: list[dict[str, str]] = []
    if system:
        out.append({"role": "system", "content": system})
    out.extend(volley)
    return out


def messages_to_volley_only(record: dict[str, Any]) -> list[dict[str, str]]:
    """User/assistant turns only — for re-injection into build_message_volley."""
    return list((record.get("volley") or {}).get("turns") or [])


def record_to_markdown(record: dict[str, Any]) -> str:
    """Copy-paste friendly transcript of one call."""
    lines = [
        f"# LLM call: {record.get('label', '')}",
        "",
        f"- **call_id:** `{record.get('call_id', '')}`",
        f"- **provider:** {record.get('provider', '')}",
        f"- **task_kind:** {record.get('task_kind', '')} ({record.get('importance', '')})",
        f"- **model:** {record.get('model_id', '')} ({record.get('model_tier', '')})",
        f"- **recorded_at:** {record.get('recorded_at', '')}",
        "",
    ]
    system = (record.get("volley") or {}).get("system_prompt") or ""
    if system:
        lines.extend(["## System", "", "```", system.strip(), "```", ""])
    for i, turn in enumerate((record.get("volley") or {}).get("turns") or [], start=1):
        role = turn.get("role", "user").upper()
        lines.extend([f"## Turn {i} — {role}", "", turn.get("content", "").strip(), ""])
    raw = (record.get("response") or {}).get("raw_content") or ""
    if raw:
        lines.extend(["## Assistant response (raw)", "", raw.strip(), ""])
    env = (record.get("response") or {}).get("parsed_envelope")
    if env:
        lines.extend(
            [
                "## Parsed envelope (summary)",
                "",
                f"- status: {env.get('status')}",
                f"- confidence: {env.get('confidence')}",
                f"- reasoning_summary: {(env.get('reasoning_summary') or '')[:500]}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def record_llm_call(
    ctx: RunContext,
    *,
    stage_key: str,
    prompt_ref: str,
    request_messages: list[dict[str, str]],
    raw_response: str,
    parsed_envelope: dict[str, Any] | None,
    task_kind: str,
    model_id: str,
    model_tier: str,
    provider: str = "openai",
    call_attempt: int | None = None,
    record_stage_key: str | None = None,
    temperature: float | None = None,
    response_format: dict[str, str] | None = None,
    truncation_flags: list[str] | None = None,
    extra_links: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Persist one API call. Returns the written record document.
    """
    cfg = merged_config()
    if not llm_call_records_enabled(cfg):
        return {}

    stage = record_stage_key or stage_key
    attempt = _attempt_from_ctx(ctx, stage, call_attempt)
    call_dir = ctx.path("understanding", "llm_calls", stage, f"attempt_{attempt:03d}")
    call_dir.mkdir(parents=True, exist_ok=True)
    sequence = _next_sequence(call_dir)
    tk = task_kind if not task_kind.startswith("shard_") else task_kind
    filename = f"{sequence:02d}_{tk}.json"
    rel_path = Path("understanding") / "llm_calls" / stage / f"attempt_{attempt:03d}" / filename

    system_prompt, volley_turns = split_messages_for_volley(request_messages)
    context_chars = sum(len(m.get("content", "")) for m in request_messages)
    context_chars += len(raw_response or "")

    label = build_call_label(
        stage_key=stage,
        attempt=attempt,
        sequence=sequence,
        task_kind=tk,
    )
    call_id = build_call_id(
        run_id=ctx.run_id,
        stage_key=stage,
        attempt=attempt,
        sequence=sequence,
        task_kind=tk,
    )

    attempt_artifact = (
        f"understanding/stage_runs/{stage}/attempt_{attempt:03d}.json"
        if tk in ("primary", "collate") or tk.startswith("shard")
        else f"understanding/stage_runs/{stage}/attempt_{attempt:03d}_{tk}.json"
    )

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "call_id": call_id,
        "label": label,
        "provider": provider,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": ctx.run_id,
        "stage_key": stage,
        "prompt_key": stage_key if stage_key != stage else stage_key,
        "prompt_ref": prompt_ref,
        "attempt": attempt,
        "sequence": sequence,
        "task_kind": tk,
        "importance": _importance_for_task_kind(tk),
        "model_id": model_id,
        "model_tier": model_tier,
        "request": {
            "messages": request_messages,
            "temperature": temperature,
            "response_format": response_format,
        },
        "response": {
            "raw_content": raw_response,
            "parsed_envelope": parsed_envelope,
        },
        "volley": {
            "system_prompt": system_prompt,
            "turns": volley_turns,
        },
        "context_chars": context_chars,
        "truncation_flags": truncation_flags or [],
        "links": {
            "attempt_artifact": attempt_artifact,
            "relative_path": str(rel_path).replace("\\", "/"),
            **(extra_links or {}),
        },
    }

    out_path = ctx.path(*rel_path.parts)
    write_json(out_path, record)

    if _write_markdown_sidecar(cfg):
        md_path = out_path.with_suffix(".md")
        md_path.write_text(record_to_markdown(record), encoding="utf-8")

    _append_index(ctx, record, rel_path)
    return record


def _append_index(ctx: RunContext, record: dict[str, Any], rel_path: Path) -> None:
    index_path = ctx.path("understanding", "llm_calls", INDEX_NAME)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "call_id": record.get("call_id"),
        "label": record.get("label"),
        "run_id": record.get("run_id"),
        "stage_key": record.get("stage_key"),
        "attempt": record.get("attempt"),
        "sequence": record.get("sequence"),
        "task_kind": record.get("task_kind"),
        "importance": record.get("importance"),
        "provider": record.get("provider"),
        "model_id": record.get("model_id"),
        "recorded_at": record.get("recorded_at"),
        "path": str(rel_path).replace("\\", "/"),
    }
    with index_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_call_record(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def list_calls_for_run(run_dir: Path) -> list[dict[str, Any]]:
    index_path = run_dir / "understanding" / "llm_calls" / INDEX_NAME
    if not index_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def reconstruct_volley_from_calls(
    records: list[dict[str, Any]],
    *,
    include_system_as_user: bool = False,
) -> list[dict[str, str]]:
    """
    Merge multiple call records into one user/assistant volley (ordered by sequence).
    Useful when rebuilding context from saved files.
    """
    ordered = sorted(records, key=lambda r: (r.get("attempt", 0), r.get("sequence", 0)))
    merged: list[dict[str, str]] = []
    for rec in ordered:
        if include_system_as_user:
            sys_p = (rec.get("volley") or {}).get("system_prompt") or ""
            if sys_p:
                merged.append(
                    {
                        "role": "user",
                        "content": f"## System (from {rec.get('label')})\n{sys_p}",
                    }
                )
        for turn in (rec.get("volley") or {}).get("turns") or []:
            merged.append({"role": turn["role"], "content": turn["content"]})
        raw = (rec.get("response") or {}).get("raw_content") or ""
        if raw.strip():
            merged.append(
                {
                    "role": "assistant",
                    "content": raw.strip(),
                }
            )
    return merged
