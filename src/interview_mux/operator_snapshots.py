"""Persist operator-authored data as independent files under each execution's operator/ dir."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.file_store import read_json, write_json
from interview_mux.run_context import RunContext

OPERATOR_DIR = "operator"
MANIFEST_REL = f"{OPERATOR_DIR}/manifest.json"
ACTION_TRACE_REL = f"{OPERATOR_DIR}/action_trace.jsonl"

def record_action_trace_manifest(run_dir: Path) -> None:
    """Record action_trace.jsonl in operator manifest when first written."""
    from interview_mux.operator_action_trace import ACTION_TRACE_REL

    rel = ACTION_TRACE_REL
    trace_path = run_dir / rel
    if not trace_path.is_file():
        return
    manifest_path = run_dir / MANIFEST_REL
    if manifest_path.is_file():
        data = read_json(manifest_path)
        if isinstance(data, dict) and rel in (data.get("snapshots") or {}):
            return
    ctx = RunContext(run_dir.name, create=False)
    if ctx.run_dir != run_dir:
        # run_id folder name may differ; write manifest directly
        manifest = _load_manifest_direct(run_dir)
    else:
        manifest = _load_manifest(ctx)
    snapshots = manifest.setdefault("snapshots", {})
    snapshots[rel] = {
        "path": rel,
        "updated_at": _now_iso(),
        "source": "action_trace",
    }
    manifest["updated_at"] = _now_iso()
    write_json(run_dir / MANIFEST_REL, manifest)

def _load_manifest_direct(run_dir: Path) -> dict[str, Any]:
    rel = MANIFEST_REL
    path = run_dir / rel
    if path.is_file():
        data = read_json(path)
        if isinstance(data, dict):
            return data
    run_id = run_dir.name
    return {"version": 1, "run_id": run_id, "snapshots": {}}

# Snapshot keys → relative paths under the run directory.
SNAPSHOT_PATHS: dict[str, str] = {
    "transcript_corrected": f"{OPERATOR_DIR}/transcript_corrected.json",
    "transcript_corrected_text": f"{OPERATOR_DIR}/transcript_corrected.txt",
    "transcript_corrections": f"{OPERATOR_DIR}/transcript_corrections.json",
    "analysis_profile": f"{OPERATOR_DIR}/analysis_profile.json",
    "nle_edits": f"{OPERATOR_DIR}/nle_edits.json",
    "acoustic_profile_overrides": f"{OPERATOR_DIR}/acoustic_profile_overrides.json",
    "preclean_decisions": f"{OPERATOR_DIR}/preclean_decisions.json",
    "stage_reuse_decisions": f"{OPERATOR_DIR}/stage_reuse_decisions.json",
    "sfx_prompts": f"{OPERATOR_DIR}/sfx_prompts.json",
    "sfx_listen_results": f"{OPERATOR_DIR}/sfx_listen_results.json",
    "mmaudio_qa": f"{OPERATOR_DIR}/mmaudio_qa.json",
    "sfx_generation_meta": f"{OPERATOR_DIR}/sfx_generation_meta.json",
    "investigation_queue": f"{OPERATOR_DIR}/investigation_queue.json",
}

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _load_manifest(ctx: RunContext) -> dict[str, Any]:
    rel = MANIFEST_REL
    if ctx.artifact_exists(rel):
        data = ctx.read_json(rel)
        if isinstance(data, dict):
            return data
    return {"version": 1, "run_id": ctx.run_id, "snapshots": {}}

def _write_manifest_entry(
    ctx: RunContext,
    key: str,
    *,
    path: str,
    source: str,
    detail: dict[str, Any] | None = None,
) -> None:
    manifest = _load_manifest(ctx)
    snapshots = manifest.setdefault("snapshots", {})
    entry: dict[str, Any] = {
        "path": path,
        "updated_at": _now_iso(),
        "source": source,
    }
    if detail:
        entry["detail"] = detail
    snapshots[key] = entry
    manifest["updated_at"] = _now_iso()
    ctx.write_json(MANIFEST_REL, manifest)

def write_operator_snapshot(
    ctx: RunContext,
    key: str,
    data: Any,
    *,
    source: str,
    detail: dict[str, Any] | None = None,
) -> str:
    """Write JSON snapshot to operator/ and record in manifest. Returns relative path."""
    rel = SNAPSHOT_PATHS.get(key)
    if not rel:
        raise ValueError(f"Unknown operator snapshot key: {key}")
    ctx.write_json(rel, data)
    _write_manifest_entry(ctx, key, path=rel, source=source, detail=detail)
    return rel

def write_operator_text_snapshot(
    ctx: RunContext,
    key: str,
    text: str,
    *,
    source: str,
) -> str:
    """Write plain-text snapshot (e.g. corrected transcript)."""
    rel = SNAPSHOT_PATHS.get(key)
    if not rel:
        raise ValueError(f"Unknown operator snapshot key: {key}")
    from interview_mux.file_store import write_text as fs_write_text

    dest = ctx.path(rel)
    fs_write_text(dest, text)
    _write_manifest_entry(ctx, key, path=rel, source=source)
    return rel

def mirror_artifact_to_operator(
    ctx: RunContext,
    artifact_rel: str,
    data: Any,
    *,
    source: str,
) -> str | None:
    """Copy an editable artifact into operator/artifacts/<sanitized>.json for audit/reuse."""
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", artifact_rel.replace("/", "__"))
    rel = f"{OPERATOR_DIR}/artifacts/{safe}.json"
    ctx.write_json(rel, data)
    _write_manifest_entry(
        ctx,
        f"artifact:{artifact_rel}",
        path=rel,
        source=source,
        detail={"artifact_path": artifact_rel},
    )
    return rel

def persist_operator_transcript(
    ctx: RunContext,
    *,
    source: str,
    include_corrections: bool = False,
) -> None:
    """Save operator-corrected transcript after materialize_transcript (merged full.json)."""
    if not ctx.artifact_exists("transcript/full.json"):
        return
    full = ctx.read_json("transcript/full.json")
    words = full.get("words") or []
    text = full.get("text") or ""
    snapshot = {
        "version": 1,
        "run_id": ctx.run_id,
        "saved_at": _now_iso(),
        "source": source,
        "text": text,
        "words": words,
        "word_count": len(words),
        "review_applied_at": full.get("review_applied_at"),
        "speakers": (
            (ctx.read_json("transcript/speakers.json") or {}).get("speakers")
            if ctx.artifact_exists("transcript/speakers.json")
            else []
        ),
    }
    write_operator_snapshot(ctx, "transcript_corrected", snapshot, source=source)
    write_operator_text_snapshot(ctx, "transcript_corrected_text", text, source=source)
    if include_corrections and ctx.artifact_exists("transcript/corrections.json"):
        corrections = ctx.read_json("transcript/corrections.json")
        write_operator_snapshot(
            ctx,
            "transcript_corrections",
            corrections,
            source=source,
        )

def persist_operator_analysis_profile(ctx: RunContext, *, source: str) -> None:
    if not ctx.artifact_exists("understanding/analysis_state.json"):
        return
    state = ctx.read_json("understanding/analysis_state.json")
    write_operator_snapshot(
        ctx,
        "analysis_profile",
        {
            "version": 1,
            "run_id": ctx.run_id,
            "saved_at": _now_iso(),
            "source": source,
            "analysis_state": state,
            "operator_verified": bool((state.get("meta") or {}).get("operator_verified")),
        },
        source=source,
    )

def persist_operator_nle(ctx: RunContext, *, source: str) -> None:
    from interview_mux.nle_state import NLE_REL, load_nle

    nle = load_nle(ctx)
    write_operator_snapshot(
        ctx,
        "nle_edits",
        {
            "version": 1,
            "run_id": ctx.run_id,
            "saved_at": _now_iso(),
            "source": source,
            "nle": nle,
        },
        source=source,
    )

def persist_operator_acoustic_overrides(ctx: RunContext, overrides: dict[str, Any], *, source: str) -> None:
    write_operator_snapshot(
        ctx,
        "acoustic_profile_overrides",
        {
            "version": 1,
            "run_id": ctx.run_id,
            "saved_at": _now_iso(),
            "source": source,
            "operator_overrides": overrides,
        },
        source=source,
    )

def persist_operator_preclean(ctx: RunContext, *, source: str) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    preclean = meta.get("audio_preclean") if isinstance(meta.get("audio_preclean"), dict) else {}
    write_operator_snapshot(
        ctx,
        "preclean_decisions",
        {
            "version": 1,
            "run_id": ctx.run_id,
            "saved_at": _now_iso(),
            "source": source,
            "audio_preclean": preclean,
        },
        source=source,
    )

def append_operator_stage_reuse(
    ctx: RunContext,
    stage_id: str,
    entry: dict[str, Any],
    *,
    source: str,
) -> None:
    rel = SNAPSHOT_PATHS["stage_reuse_decisions"]
    if ctx.artifact_exists(rel):
        doc = ctx.read_json(rel)
    else:
        doc = {"version": 1, "run_id": ctx.run_id, "decisions": []}
    decisions = doc.setdefault("decisions", [])
    decisions.append(
        {
            "stage_id": stage_id,
            "saved_at": _now_iso(),
            "source": source,
            **entry,
        }
    )
    write_operator_snapshot(ctx, "stage_reuse_decisions", doc, source=source)

def persist_operator_sfx_prompts(ctx: RunContext, payload: dict[str, Any], *, source: str) -> None:
    write_operator_snapshot(
        ctx,
        "sfx_prompts",
        {
            "version": 1,
            "run_id": ctx.run_id,
            "saved_at": _now_iso(),
            "source": source,
            **payload,
        },
        source=source,
    )

def persist_operator_sfx_listen_results(ctx: RunContext, *, source: str) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    results = meta.get("sfx_listen_results") or []
    write_operator_snapshot(
        ctx,
        "sfx_listen_results",
        {
            "version": 1,
            "run_id": ctx.run_id,
            "saved_at": _now_iso(),
            "source": source,
            "results": results,
        },
        source=source,
    )

def persist_operator_mmaudio_snapshots(ctx: RunContext, *, source: str) -> None:
    if ctx.artifact_exists("sound_design/mmaudio_qa.json"):
        write_operator_snapshot(
            ctx,
            "mmaudio_qa",
            {
                "version": 1,
                "run_id": ctx.run_id,
                "saved_at": _now_iso(),
                "source": source,
                "mmaudio_qa": ctx.read_json("sound_design/mmaudio_qa.json"),
            },
            source=source,
        )
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    gen_meta = meta.get("sfx_generation_meta")
    if isinstance(gen_meta, dict) and gen_meta:
        write_operator_snapshot(
            ctx,
            "sfx_generation_meta",
            {
                "version": 1,
                "run_id": ctx.run_id,
                "saved_at": _now_iso(),
                "source": source,
                "sfx_generation_meta": gen_meta,
            },
            source=source,
        )

def persist_operator_investigation_queue(ctx: RunContext, *, source: str) -> None:
    if not ctx.artifact_exists("understanding/investigation_queue.json"):
        return
    queue = ctx.read_json("understanding/investigation_queue.json")
    write_operator_snapshot(
        ctx,
        "investigation_queue",
        {
            "version": 1,
            "run_id": ctx.run_id,
            "saved_at": _now_iso(),
            "source": source,
            "investigation_queue": queue,
        },
        source=source,
    )
