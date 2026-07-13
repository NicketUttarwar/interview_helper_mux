"""Runtime volley Q&A store backed by understanding/context_index.json."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from interview_mux.analysis_memory import CONTEXT_INDEX_PATH
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

CONTEXT_INDEX_SCHEMA_VERSION = 2
PLANS_SCHEMA_VERSION = 1

ENTRY_KINDS = frozenset(
    {
        "stage_conclusion",
        "investigation",
        "profile_digest",
        "shard_summary",
        "specialist_finding",
        "artifact_digest",
        "local_framing",
    }
)

ARTIFACTS_REGISTRY: dict[str, tuple[str, ...]] = {
    "speaker_roles": ("understanding/speakers.json",),
    "content_context": ("understanding/content_brief.json",),
    "boundary_detection": ("segments/boundaries.json",),
    "segment_classification": ("segments/manifest.json",),
    "content_brief_reanchor": ("understanding/content_brief.json",),
    "sonic_context_build": ("understanding/sonic_context.json",),
    "sound_design_palettes": ("understanding/sound_design_plan.json",),
    "missing_framing": ("understanding/gap_evaluations.json",),
    "optimal_questions": ("understanding/gap_report.json",),
    "delivery_brief_build": ("understanding/delivery_brief.json",),
    "topic_coverage_audit": ("master/coverage_audit.json",),
    "narrative_arc_plan": ("master/narrative_plan.json",),
    "full_master_ranking": ("master/selection.json",),
    "transitions": ("master/transitions.json",),
    "podcast_sfx_brief": ("master/podcast_sfx_brief.json",),
    "sound_design_plan": ("understanding/sound_design_plan.json",),
    "edl_narrative_audit": ("master/edl_narrative_audit.json",),
    "sfx_prompt_craft": ("sound_design/sfx_prompts.json",),
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def context_index_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    return analysis.get("context_index") or {}

def context_index_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(context_index_cfg(cfg).get("enabled", True))

def prefer_index_over_legacy(cfg: dict[str, Any] | None = None) -> bool:
    return bool(context_index_cfg(cfg).get("prefer_index_over_legacy_summaries", False))

def write_on_accept(cfg: dict[str, Any] | None = None) -> bool:
    return bool(context_index_cfg(cfg).get("write_on_accept", True))

def new_entry_id() -> str:
    return str(uuid.uuid4())

def deterministic_entry_id(
    *,
    kind: str,
    stage_key: str,
    attempt: int,
    suffix: str = "",
) -> str:
    raw = f"{kind}:{stage_key}:{attempt}:{suffix}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"backfill_{digest}"

def default_padding_rules() -> dict[str, Any]:
    ctx_cfg = (merged_config().get("analysis") or {}).get("context") or {}
    return {
        "max_user_json_chars": 96000,
        "max_volley_middle_chars_full": int(ctx_cfg.get("max_stage_data_chars", 64000) // 2),
        "max_volley_middle_chars_shard": 4000,
        "max_entries_per_kind": {
            "stage_conclusion": 24,
            "investigation": 6,
            "specialist_finding": 8,
            "profile_digest": 12,
            "shard_summary": 16,
            "local_framing": 8,
            "artifact_digest": 12,
        },
    }

def migrate_context_index_v1_to_v2(doc: dict[str, Any], run_id: str) -> dict[str, Any]:
    if int(doc.get("schema_version", 1)) >= CONTEXT_INDEX_SCHEMA_VERSION:
        return doc
    out = dict(doc)
    out["schema_version"] = CONTEXT_INDEX_SCHEMA_VERSION
    out.setdefault("run_id", run_id)
    out.setdefault("volley_entries", [])
    if "padding_rules" not in out or not isinstance(out["padding_rules"], dict):
        out["padding_rules"] = default_padding_rules()
    else:
        merged = default_padding_rules()
        merged.update(out["padding_rules"])
        out["padding_rules"] = merged
    out.setdefault("artifacts_registry", {})
    for stage, paths in ARTIFACTS_REGISTRY.items():
        out["artifacts_registry"].setdefault(stage, list(paths))
    out.setdefault("meta", {})
    out["meta"]["migrated_at"] = _now()
    return out

def _plan_to_dict(plan: Any) -> dict[str, Any]:
    return {
        "task_line": plan.task_line,
        "prior_stages": list(plan.prior_stages),
        "profile_keys": list(plan.profile_keys),
        "investigation_kinds": sorted(plan.investigation_kinds),
        "max_investigations": plan.max_investigations,
    }

def sync_stage_plans(ctx: RunContext, index: dict[str, Any] | None = None) -> dict[str, Any]:
    from interview_mux.context_volley import STAGE_PLANS

    idx = index if index is not None else load_context_index(ctx, write=False)
    stage_plans: dict[str, Any] = {}
    for key, plan in STAGE_PLANS.items():
        stage_plans[key] = _plan_to_dict(plan)
    idx["stage_plans"] = stage_plans
    idx.setdefault("artifacts_registry", {})
    for stage, paths in ARTIFACTS_REGISTRY.items():
        idx["artifacts_registry"][stage] = list(paths)
    idx.setdefault("meta", {})
    idx["meta"]["plans_synced_at"] = _now()
    idx["meta"]["plans_schema_version"] = PLANS_SCHEMA_VERSION
    return idx

def load_context_index(ctx: RunContext, *, write: bool = True) -> dict[str, Any]:
    from interview_mux.analysis_memory import ensure_analysis_workspace

    ensure_analysis_workspace(ctx)
    doc = ctx.read_json(CONTEXT_INDEX_PATH)
    doc = migrate_context_index_v1_to_v2(doc, ctx.run_id)
    cfg = context_index_cfg()
    if cfg.get("sync_plans_on_ensure", True):
        doc = sync_stage_plans(ctx, doc)
    doc["meta"] = doc.get("meta") or {}
    doc["meta"]["entries_count"] = len(doc.get("volley_entries") or [])
    if write:
        save_context_index(ctx, doc)
    return doc

def save_context_index(ctx: RunContext, index: dict[str, Any]) -> None:
    index.setdefault("meta", {})
    index["meta"]["last_updated_at"] = _now()
    index["meta"]["entries_count"] = len(index.get("volley_entries") or [])
    ctx.write_json(CONTEXT_INDEX_PATH, index, stage_key="context_index")

def _supersede_prior(
    entries: list[dict[str, Any]],
    *,
    kind: str,
    stage_key: str | None = None,
    investigation_id: str | None = None,
) -> None:
    for entry in entries:
        if entry.get("status") != "active":
            continue
        if entry.get("kind") != kind:
            continue
        src = entry.get("source") or {}
        if stage_key and src.get("stage_key") == stage_key and kind in (
            "stage_conclusion",
            "shard_summary",
            "local_framing",
            "specialist_finding",
            "profile_digest",
        ):
            entry["status"] = "superseded"
        if investigation_id and src.get("investigation_id") == investigation_id and kind == "investigation":
            entry["status"] = "superseded"

def append_volley_entry(
    ctx: RunContext,
    entry: dict[str, Any],
    *,
    supersede_same_source: bool = True,
) -> str:
    if not context_index_enabled() or not write_on_accept():
        return str(entry.get("entry_id") or "")
    idx = load_context_index(ctx, write=False)
    entries: list[dict[str, Any]] = list(idx.get("volley_entries") or [])
    entry_id = str(entry.get("entry_id") or new_entry_id())
    content = str(entry.get("content") or "").strip()
    if not content:
        return entry_id
    kind = str(entry.get("kind") or "stage_conclusion")
    src = entry.get("source") or {}
    stage_key = src.get("stage_key")
    if supersede_same_source:
        _supersede_prior(
            entries,
            kind=kind,
            stage_key=str(stage_key) if stage_key else None,
            investigation_id=str(src.get("investigation_id") or "") or None,
        )
    row = {
        "entry_id": entry_id,
        "kind": kind,
        "role": entry.get("role", "assistant"),
        "content": content,
        "source": src,
        "tags": list(entry.get("tags") or []),
        "scope": entry.get("scope") or {},
        "status": entry.get("status", "active"),
        "supersedes": entry.get("supersedes"),
        "char_count": len(content),
        "recorded_at": entry.get("recorded_at") or _now(),
        "operator_edited": bool(entry.get("operator_edited", False)),
    }
    entries.append(row)
    max_per_kind = (idx.get("padding_rules") or {}).get("max_entries_per_kind") or {}
    cap = int(max_per_kind.get(kind, 48))
    active_kind = [e for e in entries if e.get("kind") == kind and e.get("status") == "active"]
    if len(active_kind) > cap:
        for old in active_kind[: len(active_kind) - cap]:
            old["status"] = "superseded"
    idx["volley_entries"] = entries
    save_context_index(ctx, idx)
    return entry_id

def invalidate_entries_for_stages(ctx: RunContext, stage_keys: tuple[str, ...]) -> int:
    if not context_index_enabled():
        return 0
    idx = load_context_index(ctx, write=False)
    count = 0
    stages = set(stage_keys)
    for entry in idx.get("volley_entries") or []:
        if entry.get("status") != "active":
            continue
        src = entry.get("source") or {}
        if src.get("stage_key") in stages:
            entry["status"] = "invalidated"
            count += 1
        scope = entry.get("scope") or {}
        consumers = scope.get("consumer_stages") or []
        if consumers and stages.intersection(consumers):
            entry["status"] = "invalidated"
            count += 1
    if count:
        save_context_index(ctx, idx)
    return count

def invalidate_entry(ctx: RunContext, entry_id: str) -> bool:
    idx = load_context_index(ctx, write=False)
    for entry in idx.get("volley_entries") or []:
        if entry.get("entry_id") == entry_id:
            entry["status"] = "invalidated"
            save_context_index(ctx, idx)
            return True
    return False

def update_volley_entry(ctx: RunContext, entry_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    idx = load_context_index(ctx, write=False)
    for entry in idx.get("volley_entries") or []:
        if entry.get("entry_id") != entry_id:
            continue
        if "content" in patch:
            entry["content"] = str(patch["content"])
            entry["char_count"] = len(entry["content"])
        if "tags" in patch:
            entry["tags"] = list(patch["tags"])
        if "scope" in patch:
            entry["scope"] = dict(patch["scope"])
        entry["operator_edited"] = True
        entry["recorded_at"] = _now()
        save_context_index(ctx, idx)
        return entry
    return None

def link_entries_to_latest_call(
    ctx: RunContext,
    *,
    stage_key: str,
    attempt: int,
    task_kind: str = "primary",
) -> int:
    call_dir = ctx.path("understanding", "llm_calls", stage_key, f"attempt_{attempt:03d}")
    if not call_dir.is_dir():
        return 0
    matches = sorted(call_dir.glob(f"*_{task_kind}.json"))
    if not matches:
        matches = sorted(call_dir.glob("*.json"))
    if not matches:
        return 0
    latest = matches[-1]
    try:
        import json

        rec = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return 0
    call_id = rec.get("call_id")
    rel_path = str(latest.relative_to(ctx.path()))
    idx = load_context_index(ctx, write=False)
    linked = 0
    for entry in idx.get("volley_entries") or []:
        if entry.get("status") not in ("active", "superseded"):
            continue
        src = entry.setdefault("source", {})
        if src.get("stage_key") == stage_key and int(src.get("attempt") or 0) == attempt:
            if not src.get("call_id"):
                src["call_id"] = call_id
                src["llm_call_path"] = rel_path.replace("\\", "/")
                linked += 1
    if linked:
        save_context_index(ctx, idx)
    return linked

def select_entries_for_stage(
    index: dict[str, Any],
    *,
    stage_key: str,
    prior_stages: tuple[str, ...],
    profile: str,
    task_kind: str,
    investigation_kinds: frozenset[str],
    max_investigations: int,
) -> list[dict[str, Any]]:
    entries = [e for e in (index.get("volley_entries") or []) if e.get("status") == "active"]
    selected: list[dict[str, Any]] = []

    if profile == "collate":
        for e in entries:
            if e.get("kind") == "shard_summary":
                selected.append(e)
        return selected

    if profile == "shard":
        for e in entries:
            if e.get("kind") == "stage_conclusion":
                src = e.get("source") or {}
                if src.get("stage_key") in prior_stages[:1]:
                    selected.append(e)
                    break
        return selected

    if task_kind == "arbiter":
        return []

    for ps in prior_stages:
        for e in entries:
            if e.get("kind") != "stage_conclusion":
                continue
            src = e.get("source") or {}
            if src.get("stage_key") == ps:
                selected.append(e)
                break

    if profile == "full" and max_investigations > 0:
        inv_count = 0
        for e in entries:
            if e.get("kind") != "investigation":
                continue
            src = e.get("source") or {}
            kind = (src.get("investigation_kind") or "")
            scope = e.get("scope") or {}
            kinds = scope.get("investigation_kinds") or []
            if investigation_kinds and kind and kind not in investigation_kinds and not kinds:
                if kind not in investigation_kinds:
                    continue
            selected.append(e)
            inv_count += 1
            if inv_count >= max_investigations:
                break

    if profile == "full":
        for e in entries:
            if e.get("kind") == "profile_digest":
                scope = e.get("scope") or {}
                consumers = scope.get("consumer_stages") or []
                if not consumers or stage_key in consumers:
                    selected.append(e)

    return selected

def apply_padding_budget(
    turns: list[dict[str, str]],
    padding_rules: dict[str, Any],
    *,
    profile: str,
) -> tuple[list[dict[str, str]], list[str]]:
    flags: list[str] = []
    if not turns:
        return turns, flags
    key = "max_volley_middle_chars_shard" if profile == "shard" else "max_volley_middle_chars_full"
    limit = int(padding_rules.get(key, 24000))
    total = sum(len(t.get("content", "")) for t in turns)
    if total <= limit:
        return turns, flags
    trimmed: list[dict[str, str]] = []
    used = 0
    for turn in turns:
        content = turn.get("content", "")
        if used + len(content) > limit:
            room = max(0, limit - used)
            if room > 80:
                trimmed.append(
                    {
                        "role": turn.get("role", "assistant"),
                        "content": content[: room - 20] + "\n…[volley_middle_truncated]",
                    }
                )
                flags.append("volley_middle_truncated")
            break
        trimmed.append(turn)
        used += len(content)
    return trimmed, flags

def _entries_to_turns(
    entries: list[dict[str, Any]],
    *,
    stage_key: str,
    prior_stages: tuple[str, ...],
) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    conclusions: list[str] = []
    for ps in prior_stages:
        for e in entries:
            if e.get("kind") != "stage_conclusion":
                continue
            src = e.get("source") or {}
            if src.get("stage_key") == ps:
                label = ps.replace("_", " ").title()
                conclusions.append(f"**{label}:** {e.get('content', '')}")
                break
    if conclusions:
        turns.append(
            {
                "role": "assistant",
                "content": "## Established conclusions from volley memory\n\n" + "\n".join(conclusions),
            }
        )
    profile_bits: list[str] = []
    for e in entries:
        if e.get("kind") == "profile_digest" and e.get("role") == "user":
            profile_bits.append(str(e.get("content", "")))
    if profile_bits:
        turns.append({"role": "user", "content": "## Interview profile (from memory index)\n\n" + "\n".join(profile_bits)})

    inv_lines: list[str] = []
    for e in entries:
        if e.get("kind") != "investigation":
            continue
        inv_lines.append(f"- {e.get('content', '')}")
    if inv_lines:
        turns.append(
            {
                "role": "user",
                "content": "## Open investigations (from memory index)\n\n" + "\n".join(inv_lines),
            }
        )

    for e in entries:
        if e.get("kind") == "shard_summary":
            src = e.get("source") or {}
            label = src.get("shard_label") or "shard"
            turns.append(
                {
                    "role": "assistant",
                    "content": f"**Shard {label}:** {e.get('content', '')}",
                }
            )
    return turns

def resolve_volley_context(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    profile: str = "full",
    task_kind: str = "primary",
) -> dict[str, Any]:
    from interview_mux.context_volley import plan_for_stage

    empty: dict[str, Any] = {
        "use_index": False,
        "middle_turns": [],
        "truncation_flags": [],
        "plan": plan_for_stage(stage_key),
    }
    if not context_index_enabled() or not prefer_index_over_legacy():
        return empty
    idx = load_context_index(ctx, write=False)
    entries_list = idx.get("volley_entries") or []
    if not entries_list:
        return empty
    plan = plan_for_stage(stage_key, ctx=ctx)
    selected = select_entries_for_stage(
        idx,
        stage_key=stage_key,
        prior_stages=plan.prior_stages,
        profile=profile,
        task_kind=task_kind,
        investigation_kinds=plan.investigation_kinds,
        max_investigations=plan.max_investigations if profile == "full" else 0,
    )
    if not selected:
        return empty
    middle = _entries_to_turns(selected, stage_key=stage_key, prior_stages=plan.prior_stages)
    padding = idx.get("padding_rules") or default_padding_rules()
    middle, flags = apply_padding_budget(middle, padding, profile=profile)
    return {
        "use_index": True,
        "middle_turns": middle,
        "truncation_flags": flags,
        "plan": plan,
    }

def append_stage_conclusion(
    ctx: RunContext,
    *,
    stage_key: str,
    attempt: int,
    reasoning_summary: str,
    consumer_stages: tuple[str, ...] | None = None,
) -> str | None:
    text = (reasoning_summary or "").strip()
    if not text:
        return None
    from interview_mux.context_volley import STAGE_PLANS

    consumers: list[str] = []
    if consumer_stages:
        consumers = list(consumer_stages)
    else:
        for sk, plan in STAGE_PLANS.items():
            if stage_key in plan.prior_stages:
                consumers.append(sk)
    return append_volley_entry(
        ctx,
        {
            "kind": "stage_conclusion",
            "role": "assistant",
            "content": text[:2000],
            "source": {"stage_key": stage_key, "attempt": attempt, "task_kind": "primary"},
            "scope": {"consumer_stages": consumers},
            "tags": [stage_key],
        },
    )

def append_profile_digest(
    ctx: RunContext,
    *,
    stage_key: str,
    content: str,
    profile_keys: tuple[str, ...],
) -> str | None:
    text = (content or "").strip()
    if not text:
        return None
    from interview_mux.context_volley import STAGE_PLANS

    consumers = [sk for sk, plan in STAGE_PLANS.items() if set(profile_keys) & set(plan.profile_keys)]
    profile_content = text if len(text) <= 4000 else text[:4000] + "\n…[truncated]"
    return append_volley_entry(
        ctx,
        {
            "kind": "profile_digest",
            "role": "user",
            "content": profile_content,
            "source": {"stage_key": stage_key, "task_kind": "memory_merge"},
            "scope": {"consumer_stages": consumers},
            "tags": list(profile_keys),
        },
    )

def append_investigation_entry(
    ctx: RunContext,
    *,
    investigation: dict[str, Any],
    created_by_stage: str,
) -> str | None:
    q = (investigation.get("question") or "").strip()
    if not q:
        return None
    iid = str(investigation.get("id") or "")
    kind = str(investigation.get("kind") or "unknown")
    blocking = " [blocking]" if investigation.get("blocking") else ""
    content = f"[{iid}] ({kind}) {q}{blocking}"
    return append_volley_entry(
        ctx,
        {
            "kind": "investigation",
            "role": "user",
            "content": content,
            "source": {
                "stage_key": created_by_stage,
                "investigation_id": iid,
                "investigation_kind": kind,
                "task_kind": "investigation",
            },
            "scope": {"investigation_kinds": [kind]},
            "tags": [kind],
        },
    )

def append_shard_summary(
    ctx: RunContext,
    *,
    stage_key: str,
    attempt: int,
    shard_label: str,
    reasoning_summary: str,
    segment_ids: list[str],
) -> str | None:
    summary = (reasoning_summary or "").strip()
    if not summary:
        return None
    seg = ", ".join(segment_ids[:12]) or "n/a"
    content = f"segments: {seg}\nSummary: {summary[:500]}"
    return append_volley_entry(
        ctx,
        {
            "kind": "shard_summary",
            "role": "assistant",
            "content": content,
            "source": {
                "stage_key": stage_key,
                "attempt": attempt,
                "task_kind": "shard",
                "shard_label": shard_label,
            },
            "tags": ["shard", stage_key],
        },
    )

def append_specialist_finding(
    ctx: RunContext,
    *,
    parent_stage: str,
    specialist_key: str,
    summary: str,
    consumer_stages: list[str],
) -> str | None:
    text = (summary or "").strip()
    if not text:
        return None
    return append_volley_entry(
        ctx,
        {
            "kind": "specialist_finding",
            "role": "assistant",
            "content": f"[{specialist_key}] {text[:800]}",
            "source": {"stage_key": parent_stage, "task_kind": "specialist", "specialist_key": specialist_key},
            "scope": {"consumer_stages": consumer_stages},
            "tags": [specialist_key, parent_stage],
        },
    )

def append_local_framing_entry(
    ctx: RunContext,
    *,
    stage_key: str,
    attempt: int,
    turns: list[dict[str, str]],
    model_id: str | None,
) -> str | None:
    if not turns:
        return None
    lines = [f"{t.get('role', 'user').upper()}: {t.get('content', '')[:400]}" for t in turns[:2]]
    content = "\n".join(lines)
    return append_volley_entry(
        ctx,
        {
            "kind": "local_framing",
            "role": "assistant",
            "content": content[:1200],
            "source": {
                "stage_key": stage_key,
                "attempt": attempt,
                "task_kind": "local_framing",
                "model_id": model_id or "",
            },
            "tags": ["local_llm", stage_key],
        },
    )

def profile_digest_from_memory_updates(
    updates: dict[str, Any] | None,
) -> str:
    if not updates:
        return ""
    lines: list[str] = []
    if updates.get("themes_append"):
        labels = [
            t.get("label", t.get("id", ""))
            for t in updates["themes_append"]
            if isinstance(t, dict)
        ]
        if labels:
            lines.append("New themes: " + "; ".join(labels[:8]))
    if updates.get("major_questions_append"):
        qs = updates["major_questions_append"]
        if qs:
            lines.append(
                "New questions: "
                + "; ".join(
                    (q.get("question", str(q)) if isinstance(q, dict) else str(q)) for q in qs[:5]
                )
            )
    if updates.get("narrative_patch") and isinstance(updates["narrative_patch"], dict):
        thesis = updates["narrative_patch"].get("thesis")
        if thesis:
            lines.append(f"Thesis patch: {thesis[:200]}")
    return "\n".join(lines)

def sync_investigation_entries_from_queue(ctx: RunContext) -> int:
    from interview_mux.analysis_memory import load_queue

    if not context_index_enabled() or not write_on_accept():
        return 0
    queue = load_queue(ctx)
    count = 0
    for item in queue.get("items") or []:
        if item.get("status") != "open":
            continue
        append_investigation_entry(ctx, investigation=item, created_by_stage=str(item.get("created_by_stage") or ""))
        count += 1
    return count

def invalidate_investigation_entry(ctx: RunContext, investigation_id: str) -> None:
    idx = load_context_index(ctx, write=False)
    for entry in idx.get("volley_entries") or []:
        if entry.get("kind") != "investigation":
            continue
        src = entry.get("source") or {}
        if src.get("investigation_id") == investigation_id:
            entry["status"] = "superseded"
    save_context_index(ctx, idx)
