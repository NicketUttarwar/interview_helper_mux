"""Artifact lifecycle: fingerprints, post-commit validation, reuse, stale reads."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from interview_mux.artifact_dependency_graph import transitive_invalidate
from interview_mux.config import merged_config
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS


class LifecyclePhase(str, Enum):
    PRESTAGE = "prestage"
    PRE_CALL = "pre_call"
    LLM_EXECUTE = "llm_execute"
    STAGED_WRITE = "staged_write"
    STAGED_VALIDATE = "staged_validate"
    AWAITING_APPROVAL = "awaiting_approval"
    COMMITTED = "committed"
    POST_COMMIT_VALIDATE = "post_commit_validate"
    CONSUMED = "consumed"
    INVALIDATED = "invalidated"


def lifecycle_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "fingerprint_enabled": True,
        "post_commit_validate": True,
        "read_stale_guard": True,
        "reuse_validate": True,
    }
    return {**defaults, **(analysis.get("artifact_lifecycle") or {})}


def fingerprint_artifact(artifact: dict[str, Any], stage_key: str) -> dict[str, Any]:
    out = copy.deepcopy(artifact)
    body = {k: v for k, v in out.items() if k != "_meta"}
    raw = json.dumps(body, sort_keys=True, default=str)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    meta = dict(out.get("_meta") or {})
    meta.update(
        {
            "producer_stage": stage_key,
            "content_hash": h,
            "committed_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
        }
    )
    out["_meta"] = meta
    return out


def _record_fingerprint(ctx: Any, rel: str, content_hash: str, stage_key: str) -> None:
    def _mut(meta: dict[str, Any]) -> None:
        fps = dict(meta.get("artifact_fingerprints") or {})
        fps[rel] = {"hash": content_hash, "producer_stage": stage_key}
        meta["artifact_fingerprints"] = fps

    if hasattr(ctx, "mutate_run_meta"):
        ctx.mutate_run_meta(_mut)


def restamp_committed_artifact(
    ctx: Any,
    rel: str,
    *,
    producer_stage: str,
    doc: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fingerprint + write + record so consumer stale guards match the on-disk body.

    Used after nested stage commits and after heals that rewrite an artifact
    outside its producer stage's flush list (e.g. content_brief id remap).
    """
    if doc is None:
        if not ctx.artifact_exists(rel):
            return None
        raw = ctx.read_json(rel)
        if not isinstance(raw, dict):
            return None
        doc = raw
    fp = fingerprint_artifact(doc, producer_stage)
    ctx.write_json(rel, fp, stage_key=producer_stage, skip_handoff=True)
    h = str((fp.get("_meta") or {}).get("content_hash") or "")
    if h:
        _record_fingerprint(ctx, rel, h, producer_stage)
    return fp


def post_commit_validate(ctx: Any, stage_key: str) -> list[str]:
    if not lifecycle_cfg().get("post_commit_validate", True):
        return []
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel or not ctx.artifact_exists(rel):
        return []
    from interview_mux.stage_acceptance import stage_acceptance_ok

    result = stage_acceptance_ok(ctx, stage_key, staged=False, include_downstream=False)
    return result.all_errors


def read_stale_guard(ctx: Any, rel: str, *, consumer_stage: str) -> str | None:
    if not lifecycle_cfg().get("read_stale_guard", True):
        return None
    if not ctx.artifact_exists(rel):
        return None
    try:
        from interview_mux.file_store import read_json as fs_read_json
        from interview_mux.write_staging import resolve_read_path

        committed = ctx.final_path(*rel.split("/"))
        if committed.is_file():
            doc = fs_read_json(committed)
        else:
            doc = fs_read_json(resolve_read_path(ctx, rel))
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    meta = doc.get("_meta") or {}
    if meta.get("stale"):
        return f"{rel} is marked stale ({meta.get('stale_reason') or 'upstream fix'})"
    stored = {}
    if ctx.artifact_exists("run_meta.json"):
        try:
            meta_path = resolve_read_path(ctx, "run_meta.json")
            stored = (fs_read_json(meta_path) or {}).get("artifact_fingerprints") or {}
        except Exception:
            stored = {}
    entry = stored.get(rel) or {}
    if entry.get("hash") and meta.get("content_hash") and entry["hash"] != meta["content_hash"]:
        return f"{rel} fingerprint mismatch — re-run producer {entry.get('producer_stage')}"
    return None


def validate_reuse_copy(ctx: Any, stage_key: str, source_run_id: str) -> list[str]:
    if not lifecycle_cfg().get("reuse_validate", True):
        return []
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel or not ctx.artifact_exists(rel):
        return [f"reuse missing artifact {rel}"]
    from interview_mux.prompt_validation import validate_artifact_write
    from interview_mux.sufficiency_engine import evaluate

    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return [f"reuse invalid json {rel}"]
    errors = list(validate_artifact_write(rel, doc) or [])
    evaluated = evaluate(stage_key, doc, ctx)
    findings = evaluated.get("findings") if isinstance(evaluated, dict) else evaluated
    for f in findings or []:
        blocking = getattr(f, "blocking", None)
        if blocking is None and isinstance(f, dict):
            blocking = f.get("blocking")
        if blocking:
            message = getattr(f, "message", None) or (f.get("message") if isinstance(f, dict) else str(f))
            if message:
                errors.append(str(message))
    return errors


def invalidate_downstream_memory(ctx: Any, from_stage: str) -> list[str]:
    """Bundle stale stamps, volley index invalidation, and stage summary clears on redo."""
    stamped = stamp_stale_and_archive(ctx, from_stage)
    downstream = tuple(transitive_invalidate(from_stage))
    if downstream:
        from interview_mux.artifact_cross_validate import invalidate_stage_summaries
        from interview_mux.context_resolver import invalidate_entries_for_stages

        invalidate_stage_summaries(ctx, downstream)
        invalidate_entries_for_stages(ctx, downstream)
    return stamped


def stamp_stale_and_archive(ctx: Any, from_stage: str) -> list[str]:
    stamped: list[str] = []
    for sid in transitive_invalidate(from_stage):
        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
        if not rel or not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
            if isinstance(doc, dict):
                meta = dict(doc.get("_meta") or {})
                meta["stale"] = True
                meta["stale_reason"] = f"invalidated_by:{from_stage}"
                doc["_meta"] = meta
                ctx.write_json(rel, doc, stage_key=sid, skip_handoff=True)
                stamped.append(rel)
        except Exception:
            continue
    return stamped


def apply_fingerprints_on_flush(ctx: Any, stage_key: str, flushed_paths: list[str]) -> None:
    if not lifecycle_cfg().get("fingerprint_enabled", True):
        return
    for rel in flushed_paths:
        if rel not in STAGE_ARTIFACT_DISK_PATHS.values():
            continue
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
            if isinstance(doc, dict):
                fp = fingerprint_artifact(doc, stage_key)
                ctx.write_json(rel, fp, stage_key=stage_key, skip_handoff=True)
                h = (fp.get("_meta") or {}).get("content_hash")
                if h:
                    _record_fingerprint(ctx, rel, str(h), stage_key)
        except Exception:
            continue


def run_phase_checks(ctx: Any, stage_key: str, phase: LifecyclePhase) -> list[str]:
    """Pre-stage / pre-call lifecycle gates."""
    errors: list[str] = []
    from interview_mux.stage_contract import evaluate_when, load_contract

    contract = load_contract(stage_key)
    if contract:
        for inp in contract.inputs:
            if not inp.hard:
                continue
            if not evaluate_when(inp.when, ctx):
                continue
            if inp.path and not ctx.artifact_exists(inp.path):
                errors.append(f"missing input {inp.path} for {stage_key}")
            elif inp.path:
                stale = read_stale_guard(ctx, inp.path, consumer_stage=stage_key)
                if stale:
                    errors.append(stale)
    if phase == LifecyclePhase.PRESTAGE and errors:
        return errors
    # pre_call adds schema preflight for LLM stages
    if phase == LifecyclePhase.PRE_CALL:
        from interview_mux.llm_preflight import run_schema_preflight
        from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

        if stage_key in STAGE_ARTIFACT_SCHEMAS:
            errors.extend(run_schema_preflight(stage_key, "primary"))
    return errors


def _artifact_lifecycle_phase(ctx: Any, rel: str, *, stage_id: str) -> str:
    from interview_mux.write_staging import has_pending_writes, staged_path

    if not rel:
        return "n_a"
    if not ctx.artifact_exists(rel):
        staged = staged_path(ctx, rel, stage_id=stage_id)
        if staged.is_file():
            return "staged"
        return "pending"
    try:
        doc = ctx.read_json(rel)
        meta = (doc.get("_meta") or {}) if isinstance(doc, dict) else {}
        if meta.get("stale"):
            return "invalidated"
    except Exception:
        pass
    if has_pending_writes(ctx, stage_id):
        staged = staged_path(ctx, rel, stage_id=stage_id)
        if staged.is_file():
            return "staged"
    return "committed"


def split_artifact_lists(
    ctx: Any, stage_id: str, artifacts: list[str]
) -> tuple[list[str], list[str], dict[str, str]]:
    committed: list[str] = []
    staged: list[str] = []
    lifecycle: dict[str, str] = {}
    for rel in artifacts:
        if not rel or rel.endswith("/"):
            continue
        phase = _artifact_lifecycle_phase(ctx, rel, stage_id=stage_id)
        lifecycle[rel] = phase
        if phase == "staged":
            staged.append(rel)
        elif phase in ("committed", "invalidated"):
            committed.append(rel)
    return committed, staged, lifecycle


def build_outputs_view(ctx: Any, stage_id: str) -> list[dict[str, Any]]:
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return []
    rows: list[dict[str, Any]] = []
    for rel in info.artifacts or []:
        if not rel or rel.endswith("/"):
            continue
        phase = _artifact_lifecycle_phase(ctx, rel, stage_id=stage_id)
        from interview_mux.artifact_completeness import artifact_status_for_stage
        from interview_mux.sufficiency_engine import evaluate, sufficiency_enabled

        suff = "ok"
        if sufficiency_enabled() and ctx.artifact_exists(rel):
            try:
                doc = ctx.read_json(rel)
                if isinstance(doc, dict):
                    blocking = [f for f in evaluate(stage_id, doc, ctx) if f.blocking]
                    suff = "blocking" if blocking else "ok"
            except Exception:
                suff = "unknown"
        rows.append(
            {
                "path": rel,
                "label": rel.split("/")[-1],
                "status": artifact_status_for_stage(rel, ctx, stage_id),
                "phase": phase,
                "kind": "artifact",
                "sufficiency_status": suff,
            }
        )
    return rows


def stage_output_mode(ctx: Any, stage_id: str) -> str:
    from interview_mux.web.stages import STAGE_BY_ID

    if stage_id == "audio_preclean":
        from interview_mux.stages.audio_preclean import preclean_was_skipped

        if ctx.is_done("audio_preclean") and preclean_was_skipped(ctx):
            return "optional_skipped"

    # N/A gates force-marked done must not T1-downgrade to incomplete via pending deps.
    if stage_id == "g1_5_preview_pickup":
        from interview_mux.gates_tbiy import g1_5_preview_pickup_enabled
        from interview_mux.production_profile import is_tbiy

        if not g1_5_preview_pickup_enabled() or not is_tbiy(ctx):
            return "optional_skipped"

    if stage_id in ("missing_framing", "optimal_questions", "g1_vo_pickup"):
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        if gap_fill_was_skipped(ctx):
            return "optional_skipped"

    info = STAGE_BY_ID.get(stage_id)
    if not info or not info.artifacts:
        return "none"
    statuses = []
    for rel in info.artifacts:
        if rel and not rel.endswith("/"):
            statuses.append(_artifact_lifecycle_phase(ctx, rel, stage_id=stage_id))
    if not statuses:
        return "none"
    if all(s == "pending" for s in statuses):
        return "not_started"
    if any(s == "staged" for s in statuses):
        return "awaiting_approval"
    if all(s in ("committed", "n_a") for s in statuses):
        return "committed"
    return "partial"


__all__ = [
    "LifecyclePhase",
    "apply_fingerprints_on_flush",
    "build_outputs_view",
    "fingerprint_artifact",
    "invalidate_downstream_memory",
    "lifecycle_cfg",
    "post_commit_validate",
    "read_stale_guard",
    "restamp_committed_artifact",
    "run_phase_checks",
    "split_artifact_lists",
    "stage_output_mode",
    "stamp_stale_and_archive",
    "validate_reuse_copy",
]
