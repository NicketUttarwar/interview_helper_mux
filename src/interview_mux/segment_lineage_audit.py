"""Full-pipeline segment ID lineage audit across v2 stage artifacts."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_repairs import is_manifest_segment_id
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

# Artifacts scanned after segmentation exists (ordered for downstream reference universe).
POST_SEGMENTATION_ARTIFACTS: tuple[str, ...] = (
    "segments/boundaries.json",
    "segments/manifest.json",
    "understanding/content_brief.json",
    "understanding/gap_evaluations.json",
    "understanding/gap_report.json",
    "understanding/episode_structure.json",
    "master/coverage_audit.json",
    "master/narrative_plan.json",
    "master/selection.json",
    "master/transitions.json",
    "master/edl.json",
)

SEGMENT_REF_KEYS = frozenset(
    {
        "segment_id",
        "segment_ids",
        "evidence_segment_ids",
        "ordered_segment_ids",
        "orphan_segment_ids",
        "suggested_open_segment_id",
        "anchor_segment_id",
        "opens_with_segment_id",
        "before_segment_id",
        "after_segment_id",
        "targets_segment_id",
        "first_segment_id",
        "bound_segment_ids",
        "segment_order",
    }
)


def _walk_segment_refs(obj: Any, out: set[str], *, list_keys: set[str] | None = None) -> None:
    list_keys = list_keys or SEGMENT_REF_KEYS
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in list_keys:
                if key in ("segment_ids", "evidence_segment_ids", "ordered_segment_ids", "orphan_segment_ids", "bound_segment_ids", "segment_order"):
                    if isinstance(val, list):
                        for item in val:
                            if item is not None and str(item).strip():
                                out.add(str(item).strip())
                elif val is not None and str(val).strip():
                    out.add(str(val).strip())
            else:
                _walk_segment_refs(val, out, list_keys=list_keys)
    elif isinstance(obj, list):
        for item in obj:
            _walk_segment_refs(item, out, list_keys=list_keys)


def collect_segment_refs_from_doc(rel_path: str, doc: dict[str, Any]) -> set[str]:
    """Collect segment ID references from a committed artifact document."""
    refs: set[str] = set()
    if rel_path == "segments/boundaries.json":
        for row in doc.get("boundaries") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                refs.add(str(row["segment_id"]))
        return refs
    if rel_path == "segments/manifest.json":
        for row in doc.get("segments") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                refs.add(str(row["segment_id"]))
        return refs
    if rel_path == "understanding/gap_evaluations.json":
        for row in doc.get("evaluations") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                refs.add(str(row["segment_id"]))
        return refs
    if rel_path == "understanding/gap_report.json":
        for row in doc.get("interviewer_lines") or []:
            if isinstance(row, dict):
                tgt = row.get("targets_segment_id") or row.get("segment_id")
                if tgt:
                    refs.add(str(tgt))
        return refs
    if rel_path == "master/selection.json":
        for sid in doc.get("ordered_segment_ids") or []:
            refs.add(str(sid))
        for item in doc.get("excluded_segment_ids") or []:
            if isinstance(item, str):
                refs.add(str(item))
            elif isinstance(item, dict) and item.get("segment_id"):
                refs.add(str(item["segment_id"]))
        for ch in doc.get("chapters") or []:
            if isinstance(ch, dict):
                for sid in ch.get("segment_ids") or []:
                    refs.add(str(sid))
        return refs
    _walk_segment_refs(doc, refs)
    return refs


def manifest_segment_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return set()
    doc = ctx.read_json("segments/manifest.json")
    if not isinstance(doc, dict):
        return set()
    return {
        str(s.get("segment_id"))
        for s in (doc.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }


def selection_segment_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return set()
    doc = ctx.read_json("master/selection.json")
    if not isinstance(doc, dict):
        return set()
    return {str(x) for x in (doc.get("ordered_segment_ids") or [])}


def reference_universe(ctx: RunContext, *, use_selection: bool = False) -> set[str]:
    if use_selection:
        sel = selection_segment_ids(ctx)
        if sel:
            return sel
    return manifest_segment_ids(ctx)


def _format_violations(refs: set[str]) -> list[str]:
    return sorted(s for s in refs if s and not is_manifest_segment_id(s) and not _is_nle_split_id(s))


def _is_nle_split_id(sid: str) -> bool:
    """NLE split children use seg_XXXa / seg_XXXb suffix pattern."""
    s = str(sid).strip()
    if not s.endswith(("a", "b")):
        return False
    base = s[:-1]
    return is_manifest_segment_id(base) or (base.startswith("seg_") and base[4:].isdigit())


def audit_artifact(
    ctx: RunContext,
    rel_path: str,
    *,
    universe: set[str] | None = None,
) -> dict[str, Any]:
    """Audit one artifact for orphan refs and format violations."""
    result: dict[str, Any] = {
        "path": rel_path,
        "present": False,
        "refs": [],
        "orphans": [],
        "format_violations": [],
        "errors": [],
    }
    if not ctx.artifact_exists(rel_path):
        return result
    doc = ctx.read_json(rel_path)
    if not isinstance(doc, dict):
        result["errors"].append("root is not an object")
        return result
    result["present"] = True
    refs = collect_segment_refs_from_doc(rel_path, doc)
    result["refs"] = sorted(refs)
    fmt_bad = _format_violations(refs)
    result["format_violations"] = fmt_bad
    if universe is not None and universe:
        orphans = sorted(s for s in refs if s not in universe and not _is_nle_split_id(s))
        # NLE split ids may not be in manifest until NLE applied — allow if parent in universe.
        filtered: list[str] = []
        for sid in orphans:
            if sid.endswith(("a", "b")):
                parent = sid[:-1]
                if parent in universe:
                    continue
            filtered.append(sid)
        result["orphans"] = filtered
    return result


def audit_run(ctx: RunContext) -> dict[str, Any]:
    """
    Audit segment ID lineage for a run workspace.

    Returns structured report with hard failures (orphans, format) and soft warnings
    (manifest IDs never referenced downstream).
    """
    manifest_ids = manifest_segment_ids(ctx)
    selection_ids = selection_segment_ids(ctx)
    use_selection = bool(selection_ids)

    artifacts: dict[str, Any] = {}
    hard_failures: list[str] = []
    warnings: list[str] = []

    for rel in POST_SEGMENTATION_ARTIFACTS:
        # selection.json lists excluded IDs on purpose — validate against the
        # manifest, not ordered/kept only (excluded≠orphan).
        if rel == "master/selection.json":
            universe = manifest_ids
        elif rel in (
            "master/transitions.json",
            "master/edl.json",
        ) and use_selection:
            universe = selection_ids or manifest_ids
        elif rel == "master/narrative_plan.json" and use_selection:
            universe = manifest_ids | selection_ids
        else:
            universe = manifest_ids
        info = audit_artifact(ctx, rel, universe=universe if universe else None)
        artifacts[rel] = info
        for sid in info.get("format_violations") or []:
            hard_failures.append(f"{rel}: invalid segment_id format {sid}")
        for sid in info.get("orphans") or []:
            hard_failures.append(f"{rel}: orphan segment ref {sid}")

    # Boundary ↔ manifest symmetry
    if ctx.artifact_exists("segments/boundaries.json") and manifest_ids:
        boundaries = ctx.read_json("segments/boundaries.json")
        boundary_ids = {
            str(b.get("segment_id"))
            for b in (boundaries.get("boundaries") or [])
            if isinstance(b, dict) and b.get("segment_id")
        }
        for sid in sorted(boundary_ids - manifest_ids):
            hard_failures.append(f"boundary segment_id {sid} not in manifest")
        for sid in sorted(manifest_ids - boundary_ids):
            warnings.append(f"manifest segment_id {sid} not in boundaries")

    # Soft warning: manifest segments never referenced in downstream artifacts
    all_refs: set[str] = set()
    for info in artifacts.values():
        all_refs.update(info.get("refs") or [])

    if manifest_ids:
        unreferenced = sorted(manifest_ids - all_refs)
        if unreferenced and len(unreferenced) < len(manifest_ids):
            warnings.append(
                f"{len(unreferenced)} manifest segment(s) never referenced downstream: "
                + ", ".join(unreferenced[:8])
                + ("…" if len(unreferenced) > 8 else "")
            )

    ok = not hard_failures
    return {
        "ok": ok,
        "manifest_segment_count": len(manifest_ids),
        "selection_segment_count": len(selection_ids),
        "artifacts": artifacts,
        "hard_failures": hard_failures,
        "warnings": warnings,
    }


def lineage_warnings_for_gui(ctx: RunContext, *, max_items: int = 6) -> list[str]:
    """GUI-facing lineage notes — only true hard failures (never excluded-as-orphan noise).

    Soft warnings (unreferenced manifest IDs, etc.) stay out of the operator banner.
    """
    report = audit_run(ctx)
    hard = [str(x) for x in (report.get("hard_failures") or []) if str(x).strip()]
    if not hard:
        return []
    items = hard[:max_items]
    if len(hard) > max_items:
        items.append("… additional segment lineage issues")
    return items
