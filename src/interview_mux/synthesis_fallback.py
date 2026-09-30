"""Fall back from Chatterbox / mlx synthesis to manual G1 record-upload.

Default posture (``fallback_to_manual_on_failure: false``): irreparable synthesis
failures hard-stop via ``loud_fail.raise_loud_failure`` so the operator sees the
break in Activity, terminal, and gui_log — they do not silently continue.
"""

from __future__ import annotations

import functools
import subprocess
from datetime import datetime, timezone
from typing import Any

from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.gap_vo_gates import resolve_gap_vo_delivery, set_gap_vo_delivery
from interview_mux.run_context import RunContext


class SynthesisFallbackToManual(Exception):
    """Synthesis exhausted — run switched to manual record path (legacy opt-in)."""

    def __init__(
        self,
        message: str,
        *,
        notice: str,
        line_ids: list[str],
        reason: str,
    ) -> None:
        super().__init__(message)
        self.notice = notice
        self.line_ids = line_ids
        self.reason = reason


def manual_fallback_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(gap_vo_cfg(cfg).get("fallback_to_manual_on_failure", False))


def clear_chatterbox_runtime_cache() -> None:
    _probe_chatterbox_runtime.cache_clear()


def chatterbox_runtime_available() -> bool:
    """True when local Chatterbox venv imports cleanly (cached per serve process)."""
    return _probe_chatterbox_runtime()


@functools.lru_cache(maxsize=1)
def _probe_chatterbox_runtime() -> bool:
    try:
        from interview_mux.local_runtime import LocalRuntimeUnavailable, runtime_python

        py = runtime_python("chatterbox")
    except LocalRuntimeUnavailable:
        return False

    try:
        subprocess.run(
            [str(py), "-c", "import chatterbox"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def synthesis_fallback_notice(ctx: RunContext) -> str | None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if isinstance(meta, dict):
        raw = meta.get("synthesis_fallback_notice")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def fallback_to_manual_collection(
    ctx: RunContext,
    *,
    reason: str,
    line_ids: list[str] | None = None,
    switch_delivery: bool = True,
    stage: str = "g1_vo_pickup",
) -> dict[str, Any]:
    """Switch synthesize lines to record; persist operator notice.

    When ``fallback_to_manual_on_failure`` is false (default), raises a loud
    hard-stop instead of continuing.
    """
    if not manual_fallback_enabled():
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            f"Voice synthesis failed and manual fallback is disabled: {reason.strip()}",
            stage=stage,
            reason="synthesis_failed_no_manual_fallback",
            detail={
                "line_ids": list(line_ids or []),
                "hint": (
                    "Fix Chatterbox / mlx-audio runtime, approve a usable voice reference, "
                    "or set analysis.gap_vo.fallback_to_manual_on_failure=true to allow "
                    "manual record/upload after synthesis failure."
                ),
            },
            action_id="pipeline.synthesis.hard_stop",
        )

    affected: list[str] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        lines = list(report.get("interviewer_lines") or [])
        wanted = {str(x) for x in line_ids} if line_ids else None
        changed = False
        for line in lines:
            if not isinstance(line, dict):
                continue
            lid = str(line.get("line_id") or "")
            if wanted is not None and lid not in wanted:
                continue
            if str(line.get("delivery") or "").lower() != "synthesize":
                continue
            if line.get("skipped_optional"):
                continue
            line["delivery"] = "record"
            line["synthesis_fallback_reason"] = reason[:500]
            affected.append(lid or str(line.get("targets_segment_id") or ""))
            changed = True
        if changed:
            # Delivery is a stamped field; the report belongs to compose or the
            # layup, so present the owner's key with the End-A reason (ISSUES 101).
            from interview_mux.seat_authority import persist_gap_report_stamp

            persist_gap_report_stamp(ctx, report, reason="stamp_gap_omit_flags")
            try:
                from interview_mux.delivery_brief import rebuild_delivery_brief

                rebuild_delivery_brief(ctx, reason="synthesis_fallback_to_manual")
            except Exception:
                pass

    if switch_delivery and resolve_gap_vo_delivery(ctx) == "chatterbox":
        set_gap_vo_delivery(ctx, "record")

    notice = (
        "Automatic synthesis unavailable — switched to manual record/upload at G1. "
        f"{reason.strip()}"
    ).strip()
    if affected:
        preview = ", ".join(affected[:4])
        suffix = "…" if len(affected) > 4 else ""
        notice = f"{notice} Lines: {preview}{suffix}."

    now = datetime.now(timezone.utc).isoformat()

    def patch(meta: dict[str, Any]) -> None:
        meta["synthesis_fallback_notice"] = notice
        meta["synthesis_fallback_at"] = now
        meta["synthesis_fallback_reason"] = reason[:500]
        prev = meta.get("synthesis_fallback_line_ids") or []
        merged = sorted({str(x) for x in list(prev) + affected if x})
        meta["synthesis_fallback_line_ids"] = merged

    ctx.mutate_run_meta(patch)
    ctx.log(
        notice,
        level="warning",
        stage=stage,
        action_id="pipeline.synthesis.fallback_to_manual",
        detail={
            "reason": reason[:500],
            "line_ids": affected,
            "switch_delivery": switch_delivery,
        },
    )

    if affected:
        from interview_mux.vo_synthesis_audit import record_skipped_vo

        for lid in affected:
            if lid:
                record_skipped_vo(ctx, lid, reason=f"manual_fallback: {reason[:120]}")

    return {
        "notice": notice,
        "line_ids": affected,
        "reason": reason,
        "delivery": "record",
    }


def maybe_fallback_after_synthesis_failure(
    ctx: RunContext,
    line: dict[str, Any],
    exc: Exception,
    *,
    stage: str = "vo_synthesize",
) -> None:
    """On total synthesis failure: hard-stop (default) or switch to manual (opt-in)."""
    line_id = str(line.get("line_id") or line.get("targets_segment_id") or "")
    if not manual_fallback_enabled():
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            f"Voice synthesis failed for {line_id or 'line'}: {exc}",
            stage=stage,
            reason="synthesis_failed",
            detail={
                "line_id": line_id,
                "hint": (
                    "Fix the Chatterbox / mlx-audio stack and voice reference, "
                    "or enable analysis.gap_vo.fallback_to_manual_on_failure to "
                    "continue with manual record/upload."
                ),
            },
            action_id="pipeline.synthesis.hard_stop",
            cause=exc,
        )
    payload = fallback_to_manual_collection(
        ctx,
        reason=str(exc),
        line_ids=[line_id] if line_id else None,
        stage=stage,
    )
    raise SynthesisFallbackToManual(
        str(exc),
        notice=str(payload.get("notice") or ""),
        line_ids=list(payload.get("line_ids") or []),
        reason=str(exc),
    ) from exc


def ensure_chatterbox_or_manual(ctx: RunContext, *, stage: str = "gap_delivery") -> dict[str, Any] | None:
    """When operator chose Chatterbox but runtime is missing: hard-stop or fall back."""
    if resolve_gap_vo_delivery(ctx) != "chatterbox":
        return None
    if chatterbox_runtime_available():
        return None
    return fallback_to_manual_collection(
        ctx,
        reason="Chatterbox runtime unavailable (venv or import check failed)",
        line_ids=None,
        switch_delivery=True,
        stage=stage,
    )
