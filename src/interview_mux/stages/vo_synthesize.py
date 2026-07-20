"""Optional G1 S2S gap VO synthesis (fail-open)."""

from __future__ import annotations

from interview_mux.config import merged_config
from interview_mux.local_runtime import LocalRuntimeUnavailable
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux import s2s_runner


def run_vo_synthesize(ctx: RunContext) -> None:
    block = merged_config().get("local_speech") or {}
    if not block.get("enabled", True):
        ctx.log("vo_synthesize skipped — local_speech disabled", level="info", stage="vo_synthesize")
        ctx.mark_done("vo_synthesize")
        return

    if not ctx.artifact_exists("understanding/gap_report.json"):
        ctx.log("vo_synthesize skipped — no gap_report", level="info", stage="vo_synthesize")
        ctx.mark_done("vo_synthesize")
        return

    report = ctx.read_json("understanding/gap_report.json")
    lines = report.get("interviewer_lines") or []
    fail_open = bool(block.get("fail_open", True))
    synthesized = 0
    skipped = 0

    with logged_step("vo_synthesize/lines", ctx=ctx, stage="vo_synthesize"):
        for line in lines:
            if not isinstance(line, dict):
                continue
            if str(line.get("delivery") or "").lower() != "synthesize":
                continue
            if line.get("skipped_optional"):
                skipped += 1
                continue
            try:
                out = s2s_runner.synthesize_line(ctx, line, mode="synthesize")
                synthesized += 1
                ctx.log(
                    f"Synthesized gap VO: {line.get('line_id')} → {out.name}",
                    level="success",
                    stage="vo_synthesize",
                    detail={"line_id": line.get("line_id"), "path": str(out)},
                )
            except LocalRuntimeUnavailable as exc:
                if fail_open:
                    ctx.log(
                        f"S2S fail-open skip {line.get('line_id')}: {exc}",
                        level="warning",
                        stage="vo_synthesize",
                    )
                    skipped += 1
                    continue
                raise RuntimeError(str(exc)) from exc

    ctx.log(
        f"vo_synthesize complete — {synthesized} synthesized, {skipped} skipped",
        level="success" if synthesized else "info",
        stage="vo_synthesize",
    )
    ctx.mark_done("vo_synthesize")
