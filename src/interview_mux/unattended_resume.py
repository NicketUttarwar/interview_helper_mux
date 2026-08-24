"""Resume the producer of a partial/missing artifact — never the blocked consumer."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

_JSON_PATH_RE = re.compile(r"([a-z0-9_./-]+\.json)", flags=re.IGNORECASE)

# Consumer stage → analysis producer to resume when the consumer is blocked on
# missing/partial upstream artifacts (homunculus rewind / archive).
_CONSUMER_FALLBACK_PRODUCER: dict[str, str] = {
    "topic_coverage_audit": "missing_framing",
    "sonic_context_build": "content_brief_reanchor",
    "sound_design_palettes": "content_brief_reanchor",
    "edl_narrative_audit": "sound_design_vo_finalize",
    "full_master_ranking": "narrative_arc_plan",
}


def json_paths_in_message(message: str) -> list[str]:
    return [m.group(1) for m in _JSON_PATH_RE.finditer(str(message or ""))]


def resume_producer_for_block(
    ctx: RunContext,
    *,
    consumer_stage: str,
    message: str = "",
) -> str | None:
    """Return the pipeline stage that should be re-run to fill the blocking artifact."""
    from interview_mux.artifact_completeness import preferred_fill_stage

    low = str(message or "").lower()
    for rel in json_paths_in_message(message):
        try:
            fill = preferred_fill_stage(rel, ctx)
        except Exception:
            fill = None
        if fill and fill != consumer_stage:
            return fill
        if not ctx.artifact_exists(rel):
            fill = preferred_fill_stage(rel, ctx)
            if fill:
                return fill
    probes: tuple[tuple[str, str], ...] = (
        ("segment_classification", "segments/manifest.json"),
        ("content_brief_reanchor", "understanding/content_brief.json"),
        ("missing_framing", "understanding/gap_evaluations.json"),
        ("gap_framing_compose", "understanding/gap_report.json"),
        ("delivery_brief_build", "understanding/delivery_brief.json"),
        ("sound_design_palettes", "understanding/sound_design_plan.json"),
    )
    if (
        consumer_stage == "topic_coverage_audit"
        or "topic_coverage_audit" in low
        or "gap_evaluations.json" in low
        or "gap_report.json" in low
        or "p0 spine incomplete" in low
    ):
        for cand, rel in probes:
            if not ctx.artifact_exists(rel):
                return cand
            try:
                from interview_mux.artifact_completeness import artifact_status_for_stage

                if artifact_status_for_stage(rel, ctx, cand) != "complete":
                    return preferred_fill_stage(rel, ctx) or cand
            except Exception:
                return cand
    fallback = _CONSUMER_FALLBACK_PRODUCER.get(consumer_stage)
    if fallback and fallback != consumer_stage:
        return fallback
    return None
