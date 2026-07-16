"""Rolling analysis memory, investigation queue, and context padding for LLM stages."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.tone_taxonomy import (
    OPERATOR_LOCKABLE_IDENTITY_FIELDS,
    OPERATOR_LOCKABLE_STYLE_FIELDS,
)
from interview_mux.config import merged_config
from interview_mux.prompt_validation import validate_sound_design_plan
from interview_mux.run_context import RunContext

CONTEXT_INDEX_SCHEMA_VERSION = 2
SCHEMA_VERSION = 1

ANALYSIS_STATE_PATH = "understanding/analysis_state.json"
INVESTIGATION_QUEUE_PATH = "understanding/investigation_queue.json"
CONTEXT_INDEX_PATH = "understanding/context_index.json"
ORCHESTRATION_PATH = "understanding/analysis_orchestration.json"
SOUND_DESIGN_PLAN_PATH = "understanding/sound_design_plan.json"

EDITABLE_PROFILE_PATHS = (
    ANALYSIS_STATE_PATH,
    INVESTIGATION_QUEUE_PATH,
    SOUND_DESIGN_PLAN_PATH,
    "understanding/content_brief.json",
    "understanding/speakers.json",
    "segments/manifest.json",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _analysis_cfg() -> dict[str, Any]:
    return merged_config().get("analysis") or {}


def default_analysis_state(run_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "meta": {
            "created_at": _now(),
            "last_updated_at": _now(),
            "last_updated_stage": "",
            "analysis_pass": 1,
            "operator_verified": False,
        },
        "interview_identity": {
            "title": "",
            "one_line_summary": "",
            "source_audio_note": "",
        },
        "themes": [],
        "major_questions": [],
        "style": {
            "tone": "",
            "pacing": "",
            "format_notes": "",
            "interviewer_style": "",
            "interviewee_style": "",
        },
        "narrative": {
            "thesis": "",
            "audience": "",
            "emotional_beats": [],
            "key_claims": [],
        },
        "entities": [],
        "speakers": [],
        "segment_summary": {},
        "gaps_summary": {},
        "hypotheses": [],
        "open_questions": [],
        "confidence": {
            "overall": 0.0,
            "roles": 0.0,
            "segmentation": 0.0,
            "content": 0.0,
            "gaps": 0.0,
        },
        "completion": {
            "analysis_ready": False,
            "blockers": [],
        },
        "operator_notes": "",
    }


def default_investigation_queue() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "items": []}


def default_context_index(run_id: str) -> dict[str, Any]:
    from interview_mux.context_resolver import ARTIFACTS_REGISTRY, default_padding_rules

    return {
        "schema_version": CONTEXT_INDEX_SCHEMA_VERSION,
        "run_id": run_id,
        "artifacts": {},
        "stage_plans": {},
        "artifacts_registry": {k: list(v) for k, v in ARTIFACTS_REGISTRY.items()},
        "padding_rules": default_padding_rules(),
        "volley_entries": [],
        "meta": {
            "plans_synced_at": None,
            "entries_count": 0,
            "last_updated_at": _now(),
        },
    }


def default_orchestration() -> dict[str, Any]:
    cfg = _analysis_cfg()
    return {
        "schema_version": SCHEMA_VERSION,
        "max_iterations_per_stage": int(cfg.get("max_iterations_per_stage", 3)),
        "max_queue_drains_per_stage": int(cfg.get("max_queue_drains_per_stage", 5)),
        "max_volley_retries": int(cfg.get("max_volley_retries", 2)),
        "stage_attempts": {},
        "last_completion_check": None,
    }


def default_sound_design_plan() -> dict[str, Any]:
    return {
        "version": 1,
        "coherence": {
            "sonic_identity": "",
            "primary_mood": "",
            "density": "",
        },
        "palettes": [],
        "assets": [],
        "flow_plans": {
            "podcast": {"profile": "podcast", "cues": []},
            "flow2": {"profile": "montage", "cues": []},
        },
        "generated": {},
    }


def _build_context_index_from_plans(run_id: str) -> dict[str, Any]:
    from interview_mux.context_volley import STAGE_PLANS
    from interview_mux.context_resolver import ARTIFACTS_REGISTRY, default_padding_rules

    idx = default_context_index(run_id)
    stage_plans: dict[str, Any] = {}
    for key, plan in STAGE_PLANS.items():
        stage_plans[key] = {
            "task_line": plan.task_line,
            "prior_stages": list(plan.prior_stages),
            "profile_keys": list(plan.profile_keys),
            "investigation_kinds": sorted(plan.investigation_kinds),
            "max_investigations": plan.max_investigations,
        }
    idx["stage_plans"] = stage_plans
    idx["artifacts_registry"] = {k: list(v) for k, v in ARTIFACTS_REGISTRY.items()}
    idx["meta"]["plans_synced_at"] = _now()
    return idx


def ensure_analysis_workspace(ctx: RunContext) -> None:
    """Create memory files if missing (call before first LLM analysis stage)."""
    scaffold = {"skip_handoff": True}
    if not ctx.artifact_exists(ANALYSIS_STATE_PATH):
        ctx.write_json(
            ANALYSIS_STATE_PATH,
            default_analysis_state(ctx.run_id),
            **scaffold,
        )
    if not ctx.artifact_exists(INVESTIGATION_QUEUE_PATH):
        ctx.write_json(INVESTIGATION_QUEUE_PATH, default_investigation_queue(), **scaffold)
    if not ctx.artifact_exists(CONTEXT_INDEX_PATH):
        ctx.write_json(
            CONTEXT_INDEX_PATH,
            _build_context_index_from_plans(ctx.run_id),
            **scaffold,
        )
    else:
        from interview_mux.context_resolver import context_index_cfg, migrate_context_index_v1_to_v2, sync_stage_plans

        if context_index_cfg().get("sync_plans_on_ensure", True):
            raw = ctx.read_json(CONTEXT_INDEX_PATH)
            migrated = migrate_context_index_v1_to_v2(raw, ctx.run_id)
            synced = sync_stage_plans(ctx, migrated)
            ctx.write_json(CONTEXT_INDEX_PATH, synced, **scaffold)
    if not ctx.artifact_exists(ORCHESTRATION_PATH):
        ctx.write_json(ORCHESTRATION_PATH, default_orchestration(), **scaffold)
    if not ctx.artifact_exists(SOUND_DESIGN_PLAN_PATH):
        plan = default_sound_design_plan()
        sdp_errors = validate_sound_design_plan(plan)
        if sdp_errors:
            raise RuntimeError(
                "default_sound_design_plan() failed schema validation: " + "; ".join(sdp_errors)
            )
        ctx.write_json(SOUND_DESIGN_PLAN_PATH, plan, **scaffold)
    (ctx.path("understanding", "stage_runs")).mkdir(parents=True, exist_ok=True)


def load_analysis_state(ctx: RunContext) -> dict[str, Any]:
    ensure_analysis_workspace(ctx)
    return ctx.read_json(ANALYSIS_STATE_PATH)


def save_analysis_state(ctx: RunContext, state: dict[str, Any], *, stage: str | None = None) -> None:
    if stage == "operator_gui" and ctx.artifact_exists(ANALYSIS_STATE_PATH):
        prior = ctx.read_json(ANALYSIS_STATE_PATH)
        if isinstance(prior, dict):
            locks = set((prior.get("meta") or {}).get("operator_locked_fields") or [])
            locks |= _detect_operator_field_edits(prior, state)
            state.setdefault("meta", {})
            state["meta"]["operator_locked_fields"] = sorted(locks)
    state.setdefault("meta", {})
    state["meta"]["last_updated_at"] = _now()
    if stage:
        state["meta"]["last_updated_stage"] = stage
    ctx.write_json(ANALYSIS_STATE_PATH, state, stage_key=stage or "analysis_profile")
    if stage == "operator_gui":
        try:
            from interview_mux.context_volley import _format_profile_slice, plan_for_stage
            from interview_mux.context_resolver import append_profile_digest, context_index_enabled, write_on_accept

            if context_index_enabled() and write_on_accept():
                plan = plan_for_stage("content_context")
                digest = _format_profile_slice(state, plan.profile_keys)
                if digest:
                    append_profile_digest(
                        ctx,
                        stage_key="operator_gui",
                        content=digest,
                        profile_keys=plan.profile_keys,
                    )
        except Exception:
            pass


def load_queue(ctx: RunContext) -> dict[str, Any]:
    ensure_analysis_workspace(ctx)
    return ctx.read_json(INVESTIGATION_QUEUE_PATH)


def save_queue(ctx: RunContext, queue: dict[str, Any]) -> None:
    from interview_mux.prompt_validation import validate_investigation_queue

    errors = validate_investigation_queue(queue)
    if errors:
        ctx.log(f"investigation_queue schema warnings: {errors[:2]}", level="warning", stage="memory")
    ctx.write_json(INVESTIGATION_QUEUE_PATH, queue, stage_key="analysis_profile")


def _next_inv_id(queue: dict[str, Any]) -> str:
    items = queue.get("items") or []
    nums = []
    for it in items:
        iid = str(it.get("id", ""))
        if iid.startswith("inv_"):
            try:
                nums.append(int(iid.split("_", 1)[1]))
            except ValueError:
                pass
    n = (max(nums) + 1) if nums else 1
    return f"inv_{n:03d}"


def _nested_get(state: dict[str, Any], dotted: str) -> Any:
    cur: Any = state
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _nested_set(state: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = state
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _all_lockable_profile_fields() -> list[str]:
    return list(OPERATOR_LOCKABLE_STYLE_FIELDS) + list(OPERATOR_LOCKABLE_IDENTITY_FIELDS)


def _operator_locked_fields(state: dict[str, Any]) -> set[str]:
    meta = state.get("meta") or {}
    locked = set(meta.get("operator_locked_fields") or [])
    if meta.get("operator_verified"):
        locked.update(_all_lockable_profile_fields())
    return locked


def _detect_operator_field_edits(prior: dict[str, Any], new: dict[str, Any]) -> set[str]:
    edited: set[str] = set()
    for path in _all_lockable_profile_fields():
        old_val = _nested_get(prior, path)
        new_val = _nested_get(new, path)
        if isinstance(old_val, str):
            old_val = old_val.strip()
        if isinstance(new_val, str):
            new_val = new_val.strip()
        if new_val and new_val != old_val:
            edited.add(path)
    return edited


def _derive_one_line_summary(brief: dict[str, Any]) -> str:
    thesis = str(brief.get("thesis") or "").strip()
    if not thesis:
        return ""
    first = thesis.split(".")[0].strip()
    if not first:
        return thesis[:120]
    return first if len(first) <= 120 else first[:117] + "..."


def merge_memory_updates(
    state: dict[str, Any],
    updates: dict[str, Any] | None,
    *,
    skip_operator_conflicts: bool = False,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    conflicts: list[dict[str, str]] = []
    if not updates:
        return state, conflicts
    out = copy.deepcopy(state)
    locked = _operator_locked_fields(out)
    if skip_operator_conflicts:
        _protected = frozenset(
            {
                "narrative_patch",
                "style_patch",
                "themes_append",
                "major_questions_append",
                "interview_identity_patch",
                "themes",
                "major_questions",
                "narrative",
                "style",
                "themes_replace",
                "major_questions_replace",
                "entities_replace",
                "hypotheses_replace",
                "speakers_replace",
                "open_questions_replace",
            }
        )
        updates = {k: v for k, v in updates.items() if k not in _protected}
        if not updates:
            return out, conflicts

    def _append_unique(lst: list, item: Any, id_key: str = "id") -> None:
        if not item:
            return
        if isinstance(item, dict) and id_key in item:
            if any(isinstance(x, dict) and x.get(id_key) == item.get(id_key) for x in lst):
                for i, x in enumerate(lst):
                    if isinstance(x, dict) and x.get(id_key) == item.get(id_key):
                        lst[i] = {**x, **item}
                        return
        elif item in lst:
            return
        lst.append(item)

    for key in ("themes_append", "major_questions_append", "entities_append", "hypotheses_append"):
        if key in updates:
            target = key.replace("_append", "")
            out.setdefault(target, [])
            id_key = "id" if target != "major_questions" else "question"
            for item in updates[key] or []:
                _append_unique(out[target], item, id_key=id_key)

    for key in ("themes", "major_questions", "entities", "hypotheses", "speakers", "open_questions"):
        if key in updates and isinstance(updates[key], list):
            if updates.get(f"{key}_replace"):
                out[key] = updates[key]
            else:
                out.setdefault(key, [])
                for item in updates[key]:
                    if item not in out[key]:
                        out[key].append(item)

    if "narrative_patch" in updates and isinstance(updates["narrative_patch"], dict):
        out.setdefault("narrative", {})
        for k, v in updates["narrative_patch"].items():
            if v is not None and v != "":
                out["narrative"][k] = v

    if "style_patch" in updates and isinstance(updates["style_patch"], dict):
        out.setdefault("style", {})
        for k, v in updates["style_patch"].items():
            if v is None or v == "":
                continue
            path = f"style.{k}"
            current = out["style"].get(k)
            if path in locked:
                if current and str(current).strip() and str(v).strip() != str(current).strip():
                    conflicts.append(
                        {"field": path, "locked": str(current).strip(), "suggested": str(v).strip()}
                    )
                continue
            out["style"][k] = v

    if "interview_identity_patch" in updates and isinstance(updates["interview_identity_patch"], dict):
        out.setdefault("interview_identity", {})
        for k, v in updates["interview_identity_patch"].items():
            if v is None or v == "":
                continue
            path = f"interview_identity.{k}"
            current = out["interview_identity"].get(k)
            if path in locked:
                if current and str(current).strip() and str(v).strip() != str(current).strip():
                    conflicts.append(
                        {"field": path, "locked": str(current).strip(), "suggested": str(v).strip()}
                    )
                continue
            out["interview_identity"][k] = v

    if "confidence_patch" in updates:
        out.setdefault("confidence", {})
        out["confidence"].update(updates["confidence_patch"])

    if "completion_patch" in updates:
        out.setdefault("completion", {})
        out["completion"].update(updates["completion_patch"])

    if "segment_summary_patch" in updates:
        out.setdefault("segment_summary", {})
        out["segment_summary"].update(updates["segment_summary_patch"])

    if "gaps_summary_patch" in updates:
        out.setdefault("gaps_summary", {})
        out["gaps_summary"].update(updates["gaps_summary_patch"])

    return out, conflicts


def enqueue_style_conflicts(
    ctx: RunContext,
    stage_key: str,
    conflicts: list[dict[str, str]],
) -> None:
    if not conflicts:
        return
    items = []
    for row in conflicts:
        field = row.get("field", "style")
        items.append(
            {
                "kind": "style_conflict",
                "question": (
                    f"Transcript suggests {row.get('suggested', '?')} for {field}; "
                    f"operator locked {row.get('locked', '?')}. Review in Story Board."
                ),
                "priority": "medium",
                "blocking": False,
                "suggested_action": {"type": "operator"},
                "target": {"field": field, "stage": stage_key},
            }
        )
    enqueue_investigations(ctx, items, created_by_stage=stage_key)


def _investigation_dedupe_key(item: dict[str, Any]) -> tuple[str, str, str]:
    action = item.get("suggested_action") or {}
    target = item.get("target") or {}
    loc = ""
    if isinstance(target, dict):
        loc = str(
            target.get("window_id")
            or target.get("risk_id")
            or target.get("segment_id")
            or ""
        )
    return (
        str(item.get("kind") or ""),
        str(action.get("stage") or action.get("type") or ""),
        loc,
    )


def enqueue_investigations(
    ctx: RunContext,
    items: list[dict[str, Any]],
    *,
    created_by_stage: str,
    dedupe: bool | None = None,
) -> int:
    """Append investigations to the queue; returns count actually enqueued (after dedupe)."""
    if not items:
        return 0
    from interview_mux.llm_flow_hardening import flow_hardening_cfg, flow_hardening_enabled

    use_dedupe = dedupe
    if use_dedupe is None:
        use_dedupe = flow_hardening_enabled() and flow_hardening_cfg().get(
            "investigation_dedupe", True
        )

    queue = load_queue(ctx)
    existing_ids = {it.get("id") for it in queue.get("items") or []}
    existing_keys: set[tuple[str, str, str]] = set()
    if use_dedupe:
        for it in queue.get("items") or []:
            if it.get("status") == "open":
                existing_keys.add(_investigation_dedupe_key(it))

    added_kinds: list[str] = []
    for raw in items:
        if not raw:
            continue
        if use_dedupe:
            key = _investigation_dedupe_key(raw)
            if key in existing_keys:
                continue
        iid = raw.get("id") or _next_inv_id(queue)
        while iid in existing_ids:
            iid = _next_inv_id(queue)
        entry = {
            "id": iid,
            "priority": raw.get("priority", "medium"),
            "kind": raw.get("kind", "unknown"),
            "target": raw.get("target") or {},
            "question": raw.get("question", ""),
            "suggested_action": raw.get("suggested_action")
            or {"type": "rerun_stage", "stage": created_by_stage},
            "status": "open",
            "blocking": bool(raw.get("blocking", False)),
            "created_by_stage": created_by_stage,
            "created_at": _now(),
        }
        queue.setdefault("items", []).append(entry)
        existing_ids.add(iid)
        added_kinds.append(str(entry.get("kind") or "unknown"))
        if use_dedupe:
            existing_keys.add(_investigation_dedupe_key(entry))
        try:
            from interview_mux.context_resolver import append_investigation_entry, context_index_enabled, write_on_accept

            if context_index_enabled() and write_on_accept():
                append_investigation_entry(ctx, investigation=entry, created_by_stage=created_by_stage)
        except Exception:
            pass
    if added_kinds:
        save_queue(ctx, queue)
        kind_summary = ", ".join(sorted(set(added_kinds)))
        ctx.log(
            f"investigation_enqueue count={len(added_kinds)} kinds={kind_summary}",
            level="info",
            stage=created_by_stage or "memory",
            detail=json.dumps(
                {"created_by_stage": created_by_stage, "kinds": added_kinds},
                ensure_ascii=False,
            ),
        )
    return len(added_kinds)


def drain_open_investigations(ctx: RunContext, limit: int | None = None) -> list[dict[str, Any]]:
    queue = load_queue(ctx)
    open_items = [it for it in queue.get("items") or [] if it.get("status") == "open"]
    open_items.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "medium"), 1))
    if limit:
        open_items = open_items[:limit]
    return open_items


def mark_investigation_done(ctx: RunContext, inv_id: str) -> None:
    queue = load_queue(ctx)
    for it in queue.get("items") or []:
        if it.get("id") == inv_id:
            it["status"] = "done"
            it["resolved_at"] = _now()
    save_queue(ctx, queue)
    try:
        from interview_mux.context_resolver import invalidate_investigation_entry

        invalidate_investigation_entry(ctx, inv_id)
    except Exception:
        pass


def state_summary_for_padding(state: dict[str, Any]) -> dict[str, Any]:
    """Compact view for LLM context — avoids sending full segment lists."""
    return {
        "interview_identity": state.get("interview_identity"),
        "themes": state.get("themes", [])[:20],
        "major_questions": state.get("major_questions", [])[:15],
        "style": state.get("style"),
        "narrative": {
            "thesis": (state.get("narrative") or {}).get("thesis"),
            "audience": (state.get("narrative") or {}).get("audience"),
            "key_claims": ((state.get("narrative") or {}).get("key_claims") or [])[:12],
        },
        "entities": state.get("entities", [])[:25],
        "speakers": state.get("speakers", []),
        "hypotheses": [h for h in state.get("hypotheses", []) if h.get("status") != "rejected"][:10],
        "open_questions": state.get("open_questions", [])[:10],
        "confidence": state.get("confidence"),
        "operator_notes": state.get("operator_notes"),
        "operator_verified": (state.get("meta") or {}).get("operator_verified"),
    }


def build_analysis_context_payload(
    ctx: RunContext,
    stage_key: str,
    stage_data: dict[str, Any],
) -> dict[str, Any]:
    """Deprecated: use context_volley.build_message_volley for API calls."""
    from interview_mux.context_volley import build_message_volley

    volley = build_message_volley(ctx, stage_key, stage_data)
    return {"stage": stage_key, "message_volley": volley}


def should_merge_envelope(
    arbiter_result: dict[str, Any] | None,
    envelope: dict[str, Any],
    *,
    routed_via_collate: bool = False,
) -> bool:
    """Merge memory only after arbiter accept or successful collate."""
    status = envelope.get("status", "complete")
    if status == "blocked":
        return False
    if routed_via_collate and status == "complete":
        blocking = [
            n
            for n in envelope.get("needs") or []
            if n.get("blocking") and n.get("type") != "operator"
        ]
        return not blocking
    if not arbiter_result:
        return status == "complete"
    verdict = str(arbiter_result.get("verdict", "")).strip()
    if verdict == "accept":
        return status == "complete"
    if verdict == "decompose":
        return False
    if verdict in ("enqueue_investigation", "retry_uptier"):
        return False
    return status == "complete"


def should_persist_artifacts(
    arbiter_result: dict[str, Any] | None,
    envelope: dict[str, Any],
    schema_errors: list[str],
    *,
    routed_via_collate: bool = False,
) -> bool:
    """Persist stage artifacts only when merge is allowed and schema is clean."""
    if schema_errors:
        return False
    routing = envelope.get("_routing_meta") or {}
    lint_errors = routing.get("deterministic_lint_errors") or []
    if lint_errors:
        return False
    artifacts = envelope.get("artifacts") or {}
    if not artifacts:
        return False
    return should_merge_envelope(
        arbiter_result,
        envelope,
        routed_via_collate=routed_via_collate,
    )


def _p0_artifact_committed_or_staged(ctx: RunContext, stage_key: str) -> bool:
    """True when P0 producer artifact is complete on disk or staged for write approval."""
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.llm_flow_hardening import producer_artifact_path
    from interview_mux.write_staging import staging_root

    rel = producer_artifact_path(stage_key)
    if not rel:
        return True
    if artifact_status(rel, ctx) == "complete":
        return True
    staged = staging_root(ctx, stage_key) / rel
    return staged.is_file()


def apply_envelope_to_memory(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    *,
    arbiter_result: dict[str, Any] | None = None,
    merge_memory: bool = True,
    routed_via_collate: bool = False,
) -> dict[str, Any]:
    state = load_analysis_state(ctx)
    do_merge = merge_memory and should_merge_envelope(
        arbiter_result,
        envelope,
        routed_via_collate=routed_via_collate,
    )
    operator_needs = [n for n in envelope.get("needs") or [] if n.get("type") == "operator"]
    if do_merge:
        state, style_conflicts = merge_memory_updates(
            state,
            envelope.get("memory_updates"),
            skip_operator_conflicts=bool(operator_needs)
            or bool((state.get("meta") or {}).get("operator_verified")),
        )
        enqueue_style_conflicts(ctx, stage_key, style_conflicts)
        if envelope.get("reasoning_summary"):
            state.setdefault("meta", {})
            passes = state["meta"].get("stage_summaries") or {}
            passes[stage_key] = envelope["reasoning_summary"]
            state["meta"]["stage_summaries"] = passes
            accepted = state["meta"].setdefault("last_accepted_attempt", {})
            if isinstance(accepted, dict):
                orch_path = ctx.path("understanding", "analysis_orchestration.json")
                attempt_n = 1
                if orch_path.is_file():
                    attempt_n = int(
                        (ctx.read_json("understanding/analysis_orchestration.json").get("stage_attempts") or {}).get(
                            stage_key, 1
                        )
                    )
                accepted[stage_key] = attempt_n

        conf = envelope.get("confidence")
        if isinstance(conf, (int, float)):
            state.setdefault("confidence", {})
            state["confidence"]["overall"] = float(conf)

        follow = envelope.get("follow_up_investigations") or []
        enqueue_investigations(ctx, follow, created_by_stage=stage_key)

        try:
            from interview_mux.context_resolver import (
                append_profile_digest,
                append_stage_conclusion,
                context_index_enabled,
                link_entries_to_latest_call,
                profile_digest_from_memory_updates,
                write_on_accept,
            )

            if context_index_enabled() and write_on_accept():
                from interview_mux.progression_spine import is_p0_spine_stage

                if is_p0_spine_stage(stage_key) and not _p0_artifact_committed_or_staged(ctx, stage_key):
                    ctx.log(
                        f"Skipping volley stage_conclusion for {stage_key} — producer artifact not complete or staged.",
                        level="warning",
                        stage=stage_key,
                        detail={"layer": "completeness", "invariant": "T11"},
                    )
                else:
                    orch_path = ctx.path("understanding", "analysis_orchestration.json")
                    attempt_n = 1
                    if orch_path.is_file():
                        attempt_n = int(
                            (
                                ctx.read_json("understanding/analysis_orchestration.json").get("stage_attempts") or {}
                            ).get(stage_key, 1)
                        )
                    if envelope.get("reasoning_summary"):
                        append_stage_conclusion(
                            ctx,
                            stage_key=stage_key,
                            attempt=attempt_n,
                            reasoning_summary=str(envelope["reasoning_summary"]),
                        )
                    digest = profile_digest_from_memory_updates(envelope.get("memory_updates"))
                    if digest:
                        from interview_mux.context_volley import plan_for_stage

                        plan = plan_for_stage(stage_key)
                        append_profile_digest(
                            ctx,
                            stage_key=stage_key,
                            content=digest,
                            profile_keys=plan.profile_keys,
                        )
                    link_entries_to_latest_call(ctx, stage_key=stage_key, attempt=attempt_n)
        except Exception:
            pass

    save_analysis_state(ctx, state, stage=stage_key)
    return state


def _theme_id_from_topic(topic: dict[str, Any], fallback_idx: int) -> str:
    return topic.get("name", "").lower().replace(" ", "_")[:32] or f"theme_{fallback_idx}"


def _upsert_theme(state: dict[str, Any], topic: dict[str, Any], *, source: str) -> None:
    if not isinstance(topic, dict):
        return
    state.setdefault("themes", [])
    theme_id = _theme_id_from_topic(topic, len(state["themes"]))
    segment_ids = list(topic.get("segment_ids") or [])
    confidence = topic.get("confidence", 0.8)
    for existing in state["themes"]:
        if isinstance(existing, dict) and existing.get("id") == theme_id:
            if topic.get("summary"):
                existing["summary"] = topic["summary"]
            if segment_ids:
                existing["segment_ids"] = segment_ids
            if confidence is not None:
                existing["confidence"] = confidence
            sources = list(existing.get("sources") or [])
            if source not in sources:
                sources.append(source)
            existing["sources"] = sources
            return
    state["themes"].append(
        {
            "id": theme_id,
            "label": topic.get("name", ""),
            "summary": topic.get("summary", ""),
            "segment_ids": segment_ids,
            "confidence": confidence,
            "sources": [source],
        }
    )


def sync_content_brief_to_state(ctx: RunContext, brief: dict[str, Any]) -> None:
    state = load_analysis_state(ctx)
    state.setdefault("narrative", {})
    if brief.get("thesis"):
        state["narrative"]["thesis"] = brief["thesis"]
    if brief.get("audience"):
        state["narrative"]["audience"] = brief["audience"]
    if brief.get("key_claims"):
        state["narrative"]["key_claims"] = brief["key_claims"]
    if brief.get("emotional_beats"):
        state["narrative"]["emotional_beats"] = brief["emotional_beats"]
    if brief.get("topic_relationships"):
        state["narrative"]["topic_relationships"] = brief["topic_relationships"]
    for topic in brief.get("topics") or []:
        _upsert_theme(state, topic, source="content_context")
    from interview_mux.interview_spine.theme_evidence import attach_theme_evidence_windows

    attach_theme_evidence_windows(ctx, state)
    for term in brief.get("jargon_glossary") or []:
        if isinstance(term, dict):
            state.setdefault("entities", [])
            state["entities"].append(
                {
                    "name": term.get("term", ""),
                    "plain_definition": term.get("plain_definition", ""),
                    "segment_ids": [term.get("first_segment_id")] if term.get("first_segment_id") else [],
                }
            )
    state.setdefault("interview_identity", {})
    if not _nested_get(state, "interview_identity.one_line_summary"):
        derived = _derive_one_line_summary(brief)
        if derived:
            state["interview_identity"]["one_line_summary"] = derived
    save_analysis_state(ctx, state, stage="content_context")


def sync_content_brief_reanchor_to_state(ctx: RunContext, brief: dict[str, Any]) -> None:
    state = load_analysis_state(ctx)
    state.setdefault("narrative", {})
    if brief.get("key_claims"):
        state["narrative"]["key_claims"] = brief["key_claims"]
    if brief.get("topic_relationships"):
        state["narrative"]["topic_relationships"] = brief["topic_relationships"]
    for topic in brief.get("topics") or []:
        _upsert_theme(state, topic, source="content_brief_reanchor")
    save_analysis_state(ctx, state, stage="content_brief_reanchor")


def sync_speakers_to_state(ctx: RunContext, speakers_doc: dict[str, Any]) -> None:
    from interview_mux.conversation_context import sync_conversation_to_analysis_state

    sync_conversation_to_analysis_state(ctx, speakers_doc)


def sync_gaps_to_state(ctx: RunContext, evaluations: dict[str, Any]) -> None:
    state = load_analysis_state(ctx)
    evals = evaluations.get("evaluations") or []
    by_type: dict[str, int] = {}
    for ev in evals:
        gt = ev.get("gap_type") or "none"
        by_type[gt] = by_type.get(gt, 0) + 1
    state["gaps_summary"] = {
        "total_evaluated": len(evals),
        "not_self_explanatory": sum(1 for e in evals if not e.get("self_explanatory")),
        "by_gap_type": by_type,
        "updated_at": _now(),
    }
    save_analysis_state(ctx, state, stage="missing_framing")


def update_completion_from_analysis(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.llm_flow_hardening import ANALYSIS_READY_ARTIFACT_PATHS, flow_hardening_enabled

    state = load_analysis_state(ctx)
    queue = load_queue(ctx)
    blockers: list[str] = []
    open_blocking = [it for it in queue.get("items") or [] if it.get("status") == "open" and it.get("blocking")]
    if open_blocking:
        kinds = {str(it.get("kind") or "") for it in open_blocking}
        blockers.append(f"{len(open_blocking)} open blocking investigation(s)")
        if "claim_contradiction" in kinds:
            blockers.append("Open blocking claim_contradiction — resolve or re-anchor brief")
    if not state.get("themes"):
        blockers.append("No themes in analysis_state — run content_context or add manually")
    if flow_hardening_enabled():
        for rel in ANALYSIS_READY_ARTIFACT_PATHS:
            st = artifact_status(rel, ctx)
            if st != "complete":
                blockers.append(f"{rel} is {st}")
    ready = len(blockers) == 0 and ctx.is_done("optimal_questions")
    state.setdefault("completion", {})
    state["completion"]["analysis_ready"] = ready
    state["completion"]["blockers"] = blockers
    save_analysis_state(ctx, state)
    return state["completion"]


MAX_UPTIER_RETRIES_PER_STAGE = 2


def uptier_budget_remaining(ctx: RunContext, stage_key: str) -> int:
    """How many retry_uptier primary re-runs remain for this stage in the run."""
    if not ctx.artifact_exists(ORCHESTRATION_PATH):
        return MAX_UPTIER_RETRIES_PER_STAGE
    orch = ctx.read_json(ORCHESTRATION_PATH)
    used = int((orch.get("uptier_counts") or {}).get(stage_key, 0))
    return max(0, MAX_UPTIER_RETRIES_PER_STAGE - used)


def record_uptier_retry(ctx: RunContext, stage_key: str) -> None:
    orch = ctx.read_json(ORCHESTRATION_PATH) if ctx.artifact_exists(ORCHESTRATION_PATH) else default_orchestration()
    counts = orch.setdefault("uptier_counts", {})
    counts[stage_key] = int(counts.get(stage_key, 0)) + 1
    ctx.write_json(ORCHESTRATION_PATH, orch)


def record_stage_attempt(
    ctx: RunContext,
    stage_key: str,
    attempt: int,
    envelope: dict[str, Any],
    *,
    context_volley: list[dict[str, str]] | None = None,
    task_kind: str = "primary",
    arbiter_result: dict[str, Any] | None = None,
    shard_count: int = 0,
    truncation_flags: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    base = ctx.path("understanding", "stage_runs", stage_key)
    base.mkdir(parents=True, exist_ok=True)
    suffix = "" if task_kind in ("primary", "collate") or task_kind.startswith("shard_") else f"_{task_kind}"
    if task_kind.startswith("shard_"):
        path = base / f"attempt_{attempt:03d}_{task_kind}.json"
    elif task_kind == "collate":
        path = base / f"attempt_{attempt:03d}_collate.json"
    else:
        path = base / f"attempt_{attempt:03d}{suffix}.json"
    from interview_mux.file_store import write_json
    from interview_mux.context_volley import volley_char_estimate

    meta = envelope.get("_llm_meta") or {}
    write_json(
        path,
        {
            "stage": stage_key,
            "attempt": attempt,
            "recorded_at": _now(),
            "context_volley": context_volley,
            "context_chars": volley_char_estimate(context_volley) if context_volley else 0,
            "model_tier": meta.get("model_tier"),
            "model_id": meta.get("model_id"),
            "task_kind": task_kind or meta.get("task_kind") or "primary",
            "arbiter_result": arbiter_result,
            "shard_count": shard_count,
            "truncation_flags": truncation_flags or [],
            "envelope": envelope,
            **(extra or {}),
        },
    )
    orch = ctx.read_json(ORCHESTRATION_PATH) if ctx.artifact_exists(ORCHESTRATION_PATH) else default_orchestration()
    orch.setdefault("stage_attempts", {})
    orch["stage_attempts"][stage_key] = attempt
    ctx.write_json(ORCHESTRATION_PATH, orch)


def mark_operator_verified(ctx: RunContext, verified: bool = True) -> None:
    state = load_analysis_state(ctx)
    state.setdefault("meta", {})
    state["meta"]["operator_verified"] = verified
    state["meta"]["operator_verified_at"] = _now() if verified else None
    if verified:
        state["meta"]["operator_locked_fields"] = _all_lockable_profile_fields()
    save_analysis_state(ctx, state, stage="operator")


def maybe_auto_verify_profile(ctx: RunContext) -> bool:
    """Under first_try, auto-verify when profile ready and no critical investigations."""
    from interview_mux.first_try import first_try_mode_enabled
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review

    if not first_try_mode_enabled():
        return False
    if bool((load_analysis_state(ctx).get("meta") or {}).get("operator_verified")):
        return False
    if not analysis_profile_ready_for_review(ctx):
        return False
    # Critical open investigations block auto-verify
    try:
        orch = ctx.read_json("understanding/orchestration.json") if ctx.artifact_exists("understanding/orchestration.json") else {}
        inv = orch.get("investigations") if isinstance(orch, dict) else None
        if isinstance(inv, list):
            for row in inv:
                if not isinstance(row, dict):
                    continue
                if str(row.get("status") or "").lower() in {"open", "blocking", "critical"}:
                    sev = str(row.get("severity") or row.get("priority") or "").lower()
                    if sev in {"critical", "high", "blocking"} or row.get("blocking"):
                        return False
    except Exception:
        pass
    mark_operator_verified(ctx, True)
    state = load_analysis_state(ctx)
    state.setdefault("meta", {})
    state["meta"]["verified_by"] = "first_try_auto"
    save_analysis_state(ctx, state, stage="operator")
    ctx.log(
        "Profile auto-verified (first_try).",
        level="success",
        stage="analysis_profile",
        action_id="gui.analysis_profile.verify",
        detail={"event": "profile_auto_verify", "verified_by": "first_try_auto"},
    )
    return True


def invalidate_sonic_context(ctx: RunContext, *, reason: str, stage: str = "invalidation") -> bool:
    """Remove stale sonic_context artifact when upstream analysis/sound inputs change."""
    rel = "understanding/sonic_context.json"
    if not ctx.artifact_exists(rel):
        return False
    path = ctx.final_path(*rel.split("/"))
    if not path.is_file():
        return False
    path.unlink()

    def patch(meta: dict[str, Any]) -> None:
        meta.pop("sonic_context_hash", None)
        meta.pop("sfx_generation_plan_hashes", None)

    if ctx.artifact_exists("run_meta.json"):
        ctx.mutate_run_meta(patch)

    ctx.log(
        "invalidated understanding/sonic_context.json",
        level="warning",
        stage=stage,
        detail={"reason": reason},
    )
    return True
