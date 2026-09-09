"""Sanitize VO synthesize status + synthesis_report bind (W5)."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
from interview_mux.artifact_sanitize.types import SanitizeResult

STATUS_REL = "mastering/vo_synthesize.json"
REPORT_REL = "vo_pickup/synthesis_report.json"


def sanitize_synthesis_report(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})

    try:
        from interview_mux.vo_synthesis_audit import canonicalize_synthesis_out_wav_paths

        canonicalize_synthesis_out_wav_paths(ctx)
        actions.append({"action": "canonicalize_out_wav_paths"})
    except Exception:
        pass

    entries = out.get("entries") or out.get("lines") or out.get("renders") or out.get("items")
    key = None
    for k in ("entries", "lines", "renders", "items"):
        if k in out:
            key = k
            break
    if entries is not None and not isinstance(entries, list):
        return SanitizeResult(
            doc=out,
            ok=False,
            errors=["synthesis_report entries invalid"],
            artifact_rel=REPORT_REL,
        )
    if isinstance(entries, list) and key:
        kept = []
        for row in entries:
            if not isinstance(row, dict):
                continue
            wav = str(row.get("out_wav") or row.get("wav_path") or "")
            sha = str(row.get("wav_sha256") or "")
            if wav and not sha:
                actions.append(
                    {
                        "action": "drop_missing_wav_sha",
                        "line_id": row.get("line_id"),
                    }
                )
                continue
            # Drop if path claimed but file missing
            if wav:
                try:
                    exists = ctx.artifact_exists(wav) if hasattr(ctx, "artifact_exists") else False
                    if not exists:
                        from pathlib import Path

                        p = Path(wav)
                        if not p.is_file():
                            # try under run root
                            try:
                                rp = ctx.path(wav) if hasattr(ctx, "path") else None
                                if rp is not None and not Path(rp).is_file():
                                    actions.append(
                                        {
                                            "action": "drop_missing_wav",
                                            "line_id": row.get("line_id"),
                                        }
                                    )
                                    continue
                            except Exception:
                                actions.append(
                                    {
                                        "action": "drop_missing_wav",
                                        "line_id": row.get("line_id"),
                                    }
                                )
                                continue
                except Exception:
                    pass
            kept.append(row)
        if len(kept) != len(entries):
            out[key] = kept

    # Seated bind refuse via compact coverage
    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        stale = compact_vo_coverage_stale_or_missing(ctx) or []
        if stale:
            errors.extend([f"seated_bind_stale:{s}" for s in list(stale)[:8]])
    except Exception:
        pass

    ok = not errors
    out = stamp_sanitize_meta(
        out,
        ok=ok,
        source="artifact_sanitize.synthesis_report",
        actions_n=len(actions),
    )
    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=ok,
        errors=errors,
        artifact_rel=REPORT_REL,
        metrics={"actions": len(actions)},
    )


def sanitize_vo_synthesize_report(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    """Status JSON sanitizer — attach bind_summary; do not forge binds."""
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})

    bind_summary: dict[str, Any] = {"stale": [], "ok": True}
    if ctx.artifact_exists(REPORT_REL):
        try:
            report = ctx.read_json(REPORT_REL)
            if isinstance(report, dict):
                rr = sanitize_synthesis_report(ctx, report)
                actions.extend(rr.actions)
                if not rr.ok:
                    errors.extend(rr.errors)
                    bind_summary["ok"] = False
                    bind_summary["errors"] = list(rr.errors)[:8]
                # Persist report if changed and ok
                if rr.changed and rr.ok:
                    try:
                        ctx.write_json(REPORT_REL, rr.doc, skip_handoff=True)
                    except TypeError:
                        ctx.write_json(REPORT_REL, rr.doc)
                    except Exception:
                        pass
        except Exception as exc:
            errors.append(f"synthesis_report_unreadable:{exc}")
            bind_summary["ok"] = False

    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        stale = list(compact_vo_coverage_stale_or_missing(ctx) or [])
        bind_summary["stale"] = stale[:24]
        if stale:
            bind_summary["ok"] = False
            errors.extend([f"seated_bind_stale:{s}" for s in stale[:8]])
    except Exception:
        pass

    out["bind_summary"] = bind_summary
    lines = out.get("lines") or out.get("renders") or out.get("items")
    if lines is not None and not isinstance(lines, list):
        errors.append("vo_synthesize lines/renders invalid")

    ok = not errors
    out = stamp_sanitize_meta(
        out,
        ok=ok,
        source="artifact_sanitize.vo_synthesize",
        actions_n=len(actions),
    )
    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=ok,
        errors=errors,
        artifact_rel=STATUS_REL,
        metrics={"actions": len(actions), "bind_ok": bind_summary.get("ok")},
    )


def vo_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary

    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        stale = list(compact_vo_coverage_stale_or_missing(ctx) or [])
        if stale:
            return [f"seated_bind_stale:{s}" for s in stale[:8]]
    except Exception as exc:
        return [f"vo_sanitary_check_failed:{exc}"]
    return []
