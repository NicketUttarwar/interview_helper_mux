"""Selection constraint lattice — total order at ranking / selection commit.

Priority (highest first):
1. Unplayable / blank / zero-ms — cannot hard-keep or never-exclude
2. CTA / never-touch packaging
3. Seat / epoch freeze (enforced at commit_selection_mutation)
4. never_exclude_primary_impact — playable non-CTA only
5. Hard-keep restore — remaining playable IDs
6. Framing VO-cover excludes — last (applied by selection_framing_apply)

Specialists stay in hard_keep / framing_coverage_guard / media_ip_cta;
this module is the single post-pass arbiter ranking should call.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

# Lint codes that refuse seal (fail-closed). Soft framing ratio warnings stay open.
_CRITICAL_LINT_PREFIXES = (
    "hard_keep_missing_from_order:",
    "framing:primary impact",
)


def apply_selection_constraints(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    apply_framing: bool = True,
    apply_hard_keep: bool = True,
) -> dict[str, Any]:
    """Apply framing then hard-keep in lattice order (blank/CTA handled inside)."""
    out = artifacts
    if apply_framing:
        from interview_mux.framing_coverage_guard import enforce_framing_ranking

        out = enforce_framing_ranking(ctx, out)
    if apply_hard_keep:
        from interview_mux.hard_keep import enforce_hard_keeps

        out = enforce_hard_keeps(ctx, out)
    return out


def strip_unplayable_from_order(
    ctx: RunContext,
    selection: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Reason-coded unplayable IDs leave ordered; ensure exclude rows exist.

    No live blank heuristics — only playability SSOT classes.
    """
    from interview_mux.playability import unplayable_reason_by_id

    out = dict(selection)
    reasons = unplayable_reason_by_id(ctx, out)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    try:
        from interview_mux.hard_keep import _manifest_segment_ids

        live = _manifest_segment_ids(ctx)
    except Exception:
        live = None
    if live is not None:
        for sid in ordered:
            if sid not in live and sid not in reasons:
                reasons[sid] = "orphan_not_in_manifest"
    if not reasons:
        return out, []
    stripped = [s for s in ordered if s in reasons]
    if not stripped:
        return out, []
    keep_order = [s for s in ordered if s not in reasons]
    out["ordered_segment_ids"] = keep_order

    excl_raw = list(out.get("excluded_segment_ids") or [])
    seen: set[str] = set()
    for row in excl_raw:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "").strip()
        else:
            sid = str(row or "").strip()
        if sid:
            seen.add(sid)
    for sid in stripped:
        if sid in seen:
            continue
        excl_raw.append(
            {"segment_id": sid, "reason": reasons.get(sid) or "blank_or_unusable_answer_audio"}
        )
        seen.add(sid)
    out["excluded_segment_ids"] = excl_raw

    rationales = (
        dict(out["exclude_rationales"])
        if isinstance(out.get("exclude_rationales"), dict)
        else {}
    )
    for sid in stripped:
        rationales[sid] = reasons.get(sid) or rationales.get(sid) or "blank_or_unusable_answer_audio"
    out["exclude_rationales"] = rationales
    return out, stripped


def sanitize_selection_lattice(
    ctx: RunContext,
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Idempotent lattice sanitize: strip unplayable → framing → hard-keep."""
    out, stripped = strip_unplayable_from_order(ctx, artifacts)
    if stripped:
        try:
            ctx.log(
                "selection_lattice: stripped unplayable from order "
                + ", ".join(stripped[:8]),
                level="info",
                stage="full_master_ranking",
            )
        except Exception:
            pass
    return apply_selection_constraints(ctx, out)


def lattice_lint_codes(ctx: RunContext, selection: dict[str, Any]) -> list[str]:
    """Stable lint codes for lattice violations (blank hard-keeps, etc.)."""
    codes: list[str] = []
    ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        keeps = hard_keep_segment_ids(ctx)
    except Exception:
        keeps = set()
    missing = sorted(k for k in keeps if k not in ordered)
    if missing:
        # Should be empty after lattice — blank/CTA already dropped from keeps.
        codes.append(f"hard_keep_missing_from_order:{','.join(missing[:8])}")
    try:
        from interview_mux.framing_coverage_guard import validate_framing_ranking

        for issue in validate_framing_ranking(ctx, selection) or []:
            codes.append(f"framing:{issue}")
    except Exception:
        pass
    return codes


def critical_lattice_lint_codes(codes: list[str]) -> list[str]:
    return [
        c
        for c in codes
        if any(c.startswith(p) or p in c for p in _CRITICAL_LINT_PREFIXES)
    ]


def seal_selection_lattice(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    fail_closed: bool = True,
) -> dict[str, Any]:
    """Sanitize then lint. Fail-closed on hard_keep / primary-impact residuals.

    Safe for ranking persist paths. Do not call under seat freeze when order
    mutation is blocked — callers should only seal when order writes are allowed.
    """
    out = sanitize_selection_lattice(ctx, artifacts)
    codes = lattice_lint_codes(ctx, out)
    critical = critical_lattice_lint_codes(codes)
    if critical and fail_closed:
        raise ValueError(
            "selection_lattice_seal_refused: " + "; ".join(critical[:4])
        )
    if codes and not critical:
        try:
            ctx.log(
                "selection_lattice: advisory lint " + "; ".join(codes[:4]),
                level="warning",
                stage="full_master_ranking",
            )
        except Exception:
            pass
    return out
