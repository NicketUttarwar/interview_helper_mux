"""Registry: sanitize_artifact / assert helpers / sanitary error collectors."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.artifact_sanitize.audit import write_sanitize_audit
from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary
from interview_mux.artifact_sanitize.types import SanitizeResult

SanitizeFn = Callable[[Any, dict[str, Any]], SanitizeResult]

SANITIZERS: dict[str, SanitizeFn] = {}


def register(rel: str, fn: SanitizeFn) -> None:
    SANITIZERS[str(rel).replace("\\", "/")] = fn


def _ensure_registered() -> None:
    if SANITIZERS:
        return
    from interview_mux.artifact_sanitize import (
        air_script,
        coverage_audit,
        edl,
        gap_report,
        nugget_layup_plan,
        omit_ledger,
        selection,
        sound_design_plan,
        transitions,
        vo_synthesize,
    )

    register("master/selection.json", selection.sanitize_master_selection)
    register("understanding/gap_report.json", gap_report.sanitize_gap_report)
    register("master/transitions.json", transitions.sanitize_transitions)
    register("mastering/vo_synthesize.json", vo_synthesize.sanitize_vo_synthesize_report)
    register("vo_pickup/synthesis_report.json", vo_synthesize.sanitize_synthesis_report)
    register("master/edl.json", edl.sanitize_edl)
    register("understanding/nugget_layup_plan.json", nugget_layup_plan.sanitize_nugget_layup_plan)
    register("mastering/mastering_plan.json", air_script.sanitize_mastering_plan)
    register("understanding/sound_design_plan.json", sound_design_plan.sanitize_sound_design_plan)
    register("understanding/omit_ledger.json", omit_ledger.sanitize_omit_ledger)
    register("master/coverage_audit.json", coverage_audit.sanitize_coverage_audit)
    register("master/narrative_plan.json", coverage_audit.sanitize_narrative_plan)
    register("sound_design/sfx_prompts.json", coverage_audit.sanitize_sfx_prompts)
    register("sound_design/mmaudio_qa.json", coverage_audit.sanitize_mmaudio_qa)


def sanitize_artifact(
    ctx: Any,
    rel: str,
    doc: dict[str, Any] | None = None,
    *,
    mode: str = "commit",
    stage_key: str = "",
    write_audit: bool = True,
) -> SanitizeResult:
    """Run registered sanitizer for ``rel``. Loads from disk when doc is None."""
    _ensure_registered()
    path = str(rel or "").replace("\\", "/")
    fn = SANITIZERS.get(path)
    if fn is None:
        payload = dict(doc or {})
        return SanitizeResult(
            doc=payload,
            ok=True,
            errors=[],
            artifact_rel=path,
            metrics={"skipped": "no_sanitizer"},
        )
    if doc is None:
        if not ctx.artifact_exists(path):
            return SanitizeResult(
                doc={},
                ok=False,
                errors=[f"missing artifact: {path}"],
                artifact_rel=path,
            )
        loaded = ctx.read_json(path)
        if not isinstance(loaded, dict):
            return SanitizeResult(
                doc={},
                ok=False,
                errors=[f"invalid artifact type: {path}"],
                artifact_rel=path,
            )
        doc = loaded
    result = fn(ctx, dict(doc))
    result.artifact_rel = path
    if write_audit:
        write_sanitize_audit(ctx, result, stage_key=stage_key, mode=mode)
    return result


def selection_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    if not ctx.artifact_exists("master/selection.json"):
        return ["master/selection.json missing"]
    try:
        from interview_mux.artifact_sanitize.selection import (
            selection_sanitary_errors as _errs,
        )

        return _errs(ctx)
    except Exception as exc:
        return [f"selection sanitary check failed: {exc}"]


def gap_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.artifact_sanitize.gap_report import gap_sanitary_errors as _errs

        return _errs(ctx)
    except Exception as exc:
        return [f"gap sanitary check failed: {exc}"]


def layup_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.artifact_sanitize.nugget_layup_plan import (
            layup_sanitary_errors as _errs,
        )

        return _errs(ctx)
    except Exception as exc:
        return [f"layup sanitary check failed: {exc}"]


def air_contract_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.artifact_sanitize.air_script import (
            air_contract_sanitary_errors as _errs,
        )

        return _errs(ctx)
    except Exception as exc:
        return [f"air_contract sanitary check failed: {exc}"]


def transitions_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.artifact_sanitize.transitions import (
            transitions_sanitary_errors as _errs,
        )

        return _errs(ctx)
    except Exception as exc:
        return [f"transitions sanitary check failed: {exc}"]


def vo_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.artifact_sanitize.vo_synthesize import vo_sanitary_errors as _errs

        return _errs(ctx)
    except Exception as exc:
        return [f"vo sanitary check failed: {exc}"]


def edl_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.artifact_sanitize.edl import edl_sanitary_errors as _errs

        return _errs(ctx)
    except Exception as exc:
        return [f"edl sanitary check failed: {exc}"]


def sdp_sanitary_errors(ctx: Any) -> list[str]:
    if not block_consumers_on_unsanitary():
        return []
    try:
        from interview_mux.artifact_sanitize.sound_design_plan import (
            sdp_sanitary_errors as _errs,
        )

        return _errs(ctx)
    except Exception as exc:
        return [f"sdp sanitary check failed: {exc}"]


def assert_selection_sanitary(ctx: Any) -> None:
    errs = selection_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError(
        "selection_unsanitary — resume selection_order_sanitize: " + "; ".join(errs[:4])
    )


def assert_gap_sanitary(ctx: Any) -> None:
    errs = gap_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError(
        "gap_unsanitary — resume gap_report_sanitize: " + "; ".join(errs[:4])
    )


def assert_layup_sanitary(ctx: Any) -> None:
    errs = layup_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError(
        "layup_unsanitary — resume nugget_layup_compose: " + "; ".join(errs[:4])
    )


def assert_air_contract_sanitary(ctx: Any) -> None:
    errs = air_contract_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError(
        "air_contract_unsanitary — resume air_contract_sanitize: " + "; ".join(errs[:4])
    )


def assert_transitions_sanitary(ctx: Any) -> None:
    errs = transitions_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError(
        "transitions_unsanitary — resume transitions: " + "; ".join(errs[:4])
    )


def assert_vo_sanitary(ctx: Any) -> None:
    errs = vo_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError(
        "vo_unsanitary — resume vo_synthesize: " + "; ".join(errs[:4])
    )


def assert_edl_sanitary(ctx: Any) -> None:
    errs = edl_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError("edl_unsanitary — resume edl: " + "; ".join(errs[:4]))


def assert_sdp_sanitary(ctx: Any) -> None:
    errs = sdp_sanitary_errors(ctx)
    if not errs:
        return
    raise RuntimeError(
        "sdp_unsanitary — resume sound_design_plan: " + "; ".join(errs[:4])
    )


def assert_sanitized_or_raise(ctx: Any, rel: str) -> SanitizeResult:
    result = sanitize_artifact(ctx, rel, mode="assert")
    if not result.ok:
        raise RuntimeError(
            f"sanitize_refused:{rel}: " + "; ".join((result.errors or ["unknown"])[:4])
        )
    return result
