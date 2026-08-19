"""Archive downstream artifacts and clear staging on pipeline invalidation."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.stage_execution_reuse import stage_reuse_output_specs
from interview_mux.web.stages import STAGE_BY_ID

_OPERATIONAL_PREFIXES = (
    ".stage_done/",
    ".pending_writes/",
    ".archived/",
    "logs/",
    "operator/",
)

_OPERATIONAL_EXACT = frozenset(
    {
        "run_meta.json",
        "gui_job.json",
    }
)


def _is_operational_artifact(rel: str) -> bool:
    if rel in _OPERATIONAL_EXACT:
        return True
    return any(rel.startswith(p) for p in _OPERATIONAL_PREFIXES)


def _pipeline_orders() -> tuple[list[str], ...]:
    from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER

    return (ANALYSIS_ORDER, DELIVERY_ORDER)


def _order_containing(stage_id: str) -> list[str] | None:
    for order in _pipeline_orders():
        if stage_id in order:
            return order
    return None


def _artifact_producer_stages(rel: str) -> list[str]:
    """Stages that own ``rel`` as a primary/committed output (not mere readers)."""
    producers: list[str] = [
        sid for sid, path in STAGE_ARTIFACT_DISK_PATHS.items() if path == rel
    ]
    seen = set(producers)
    for sid, info in STAGE_BY_ID.items():
        outs = list(info.artifacts) + list(info.audio_outputs)
        outs.extend(stage_reuse_output_specs(sid))
        if rel in outs and sid not in seen:
            seen.add(sid)
            producers.append(sid)
    return producers


def _preserve_cross_order_upstream_artifact(
    ctx: RunContext,
    rel: str,
    *,
    order: list[str],
    invalidation_slice: set[str],
) -> bool:
    """Keep analysis-owned artifacts when invalidating an unrelated delivery slice."""
    producers = _artifact_producer_stages(rel)
    if not producers:
        return False
    from_order = tuple(order)
    from_idx = min((order.index(s) for s in invalidation_slice if s in order), default=-1)
    for producer in producers:
        if producer in invalidation_slice:
            continue
        if producer not in order:
            continue
        # Upstream owner of a shared path (content_brief, boundaries) must
        # survive even if its done marker was already cleared.
        if from_idx >= 0 and order.index(producer) < from_idx:
            return True
        if ctx.is_done(producer):
            return True
    return False


def _collect_stage_output_paths(stage_id: str) -> list[str]:
    paths: list[str] = []
    info = STAGE_BY_ID.get(stage_id)
    if info:
        paths.extend(info.artifacts)
        paths.extend(info.audio_outputs)
    paths.extend(stage_reuse_output_specs(stage_id))
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if not p or p.endswith("/") or p.startswith("glob:"):
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def archive_artifacts_from(ctx: RunContext, from_stage: str, order: list[str]) -> str | None:
    """Move downstream stage outputs to .archived/{iso_ts}/; return archive dir name."""
    if from_stage not in order:
        return None
    idx = order.index(from_stage)
    invalidation_slice = set(order[idx:])
    rel_paths: list[str] = []
    for sid in order[idx:]:
        rel_paths.extend(_collect_stage_output_paths(sid))
    seen: set[str] = set()
    to_archive: list[str] = []
    for rel in rel_paths:
        if rel in seen or _is_operational_artifact(rel):
            continue
        seen.add(rel)
        if _preserve_cross_order_upstream_artifact(
            ctx,
            rel,
            order=order,
            invalidation_slice=invalidation_slice,
        ):
            continue
        if ctx.final_path(*rel.split("/")).is_file():
            to_archive.append(rel)
    if not to_archive:
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = f".archived/{ts}"
    archive_root = ctx.run_dir / archive_dir
    archive_root.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []
    for rel in sorted(to_archive):
        src = ctx.final_path(*rel.split("/"))
        if not src.is_file():
            continue
        dest = archive_root.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        archived.append(rel)

    if not archived:
        if archive_root.is_dir() and not any(archive_root.rglob("*")):
            shutil.rmtree(archive_root, ignore_errors=True)
        return None

    entry = {
        "from_stage": from_stage,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "archive_dir": archive_dir,
        "paths": archived,
    }

    def _patch(meta: dict[str, Any]) -> None:
        history = list(meta.get("invalidation_archive") or [])
        history.append(entry)
        meta["invalidation_archive"] = history

    ctx.mutate_run_meta(_patch)
    ctx.log(
        f"Archived {len(archived)} artifact(s) from {from_stage} onward to {archive_dir}.",
        level="warning",
        stage=from_stage,
        detail={"invalidation_archive": entry},
    )
    return archive_dir


def clear_pending_writes_from(ctx: RunContext, from_stage: str, order: list[str]) -> None:
    """Discard staged writes and pending_write_approval for invalidated stages."""
    if from_stage not in order:
        return
    from interview_mux.write_staging import discard_stage_writes

    idx = order.index(from_stage)
    for sid in order[idx:]:
        discard_stage_writes(ctx, sid)
