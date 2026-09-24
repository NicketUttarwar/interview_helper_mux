"""Sanitize master/edl.json + co-rebuild assembly_ledger (W6)."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
from interview_mux.artifact_sanitize.types import SanitizeResult

REL = "master/edl.json"
LEDGER_REL = "master/assembly_ledger.json"


def sanitize_edl(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})

    try:
        from interview_mux.edl_source_contract import sanitize_edl_source_paths

        cleaned, notes = sanitize_edl_source_paths(ctx, out)
        if isinstance(cleaned, dict):
            out = cleaned
        if notes:
            actions.append({"action": "sanitize_edl_source_paths", "notes": list(notes)[:20]})
    except TypeError:
        try:
            from interview_mux.edl_source_contract import sanitize_edl_source_paths

            cleaned = sanitize_edl_source_paths(ctx, out)
            if isinstance(cleaned, dict):
                out = cleaned
                actions.append({"action": "sanitize_edl_source_paths"})
        except Exception:
            pass
    except Exception:
        pass

    clips = out.get("clips") or out.get("items") or out.get("timeline")
    if clips is not None and not isinstance(clips, (list, dict)):
        errors.append("edl clips/timeline invalid")

    # Order vs selection
    try:
        from interview_mux.order_hash import order_hashes_match

        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict) and not order_hashes_match(sel, out):
                errors.append("selection_edl_order_drift")
    except Exception:
        pass

    # Rebuild ledger (derive-only)
    ledger = None
    try:
        from interview_mux.assembly_ledger import build_assembly_ledger

        ledger = build_assembly_ledger(ctx, edl=out)
        actions.append({"action": "rebuild_assembly_ledger"})
        if isinstance(ledger, dict):
            naked = int(ledger.get("naked_seam_count") or 0)
            if naked > 0 and not ledger.get("complete", True):
                errors.append(f"naked_seams:{naked}")
            elif naked > 0:
                actions.append({"action": "note_naked_seams", "count": naked})
            out["_pending_ledger"] = ledger
    except Exception as exc:
        actions.append({"action": "ledger_rebuild_failed", "error": str(exc)[:120]})

    ok = not errors
    out = stamp_sanitize_meta(
        out,
        ok=ok,
        source="artifact_sanitize.edl",
        actions_n=len(actions),
    )
    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=ok,
        errors=errors,
        artifact_rel=REL,
        metrics={"actions": len(actions)},
    )


def persist_edl_and_ledger(
    ctx: Any,
    edl: dict[str, Any],
    *,
    source: str = "artifact_sanitize.edl",
) -> SanitizeResult:
    """Atomic EDL + ledger commit."""
    result = sanitize_edl(ctx, edl)
    from interview_mux.artifact_sanitize.audit import write_sanitize_audit

    write_sanitize_audit(ctx, result, stage_key=source, mode="persist")
    plan = dict(result.doc)
    ledger = plan.pop("_pending_ledger", None)
    try:
        from interview_mux.air_order import write_live_edl

        write_live_edl(ctx, plan, source="artifact_sanitize.edl:" + str(source or "edl"))
    except Exception:
        ctx.write_json(REL, plan)
    if isinstance(ledger, dict):
        try:
            ctx.write_json(LEDGER_REL, ledger)
        except Exception:
            try:
                from interview_mux.assembly_ledger import write_assembly_ledger

                write_assembly_ledger(ctx, edl=plan)
            except Exception:
                pass
    elif result.ok:
        try:
            from interview_mux.assembly_ledger import write_assembly_ledger

            write_assembly_ledger(ctx, edl=plan)
        except Exception:
            pass
    return result


def edl_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary

    if not block_consumers_on_unsanitary():
        return []
    if not ctx.artifact_exists(REL):
        return [f"{REL} missing"]
    errs: list[str] = []
    try:
        doc = ctx.read_json(REL)
    except Exception as exc:
        return [f"{REL} unreadable: {exc}"]
    if not isinstance(doc, dict):
        return [f"{REL} invalid"]
    # Ledger is co-emitted by edl — missing ledger must not block re-running edl
    # (exec_13183: edl_unsanitary ledger missing → heal cannot reseat phantom VO).
    if not ctx.artifact_exists(LEDGER_REL):
        try:
            from interview_mux.assembly_ledger import write_assembly_ledger

            write_assembly_ledger(ctx, edl=doc)
        except Exception:
            pass
        if not ctx.artifact_exists(LEDGER_REL):
            errs.append(f"{LEDGER_REL} missing")
    result = sanitize_edl(ctx, doc)
    if not result.ok:
        errs.extend(result.errors or ["edl sanitize refused"])
    # Cluster C: gap omit XOR EDL/WAV orientation seat.
    try:
        from interview_mux.hosted_vo_authority import assert_books_agree

        errs.extend(assert_books_agree(ctx))
    except Exception:
        pass
    return errs
