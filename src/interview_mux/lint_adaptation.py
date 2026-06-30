"""Lint-driven retry adaptation registry."""

from __future__ import annotations

from typing import Any

from interview_mux.classification_obligation import missing_segment_ids
from interview_mux.run_context import RunContext

_LINT_CLASSIFICATION_COVERAGE_APPENDIX = (
    "Return exactly one classification per required_segment_id in classification_obligation. "
    "Do not omit segment ids. Merge shard outputs by segment_id."
)

_LINT_CLASSIFICATION_TYPE_APPENDIX = (
    "Vary segment types: use interviewer_question, setup, interviewer_reaction, aside, coda "
    "where transcript evidence supports — do not tag every segment interviewee_answer."
)

_LINT_BOUNDARY_TIMELINE_APPENDIX = (
    "Boundaries must have unique segment_id values, strictly increasing start_ms/end_ms, "
    "and no zero-length spans. Merge micro-boundaries rather than duplicating ids."
)

_LINT_BOUNDARY_MERGE_APPENDIX = (
    "Prefer 700/1200 ms pause tiers on calm speech; avoid hundreds of 400 ms micro-boundaries."
)


def itr_repair_hints(
    schema_errors: list[str] | None,
    lint_errors: list[str] | None,
) -> str | None:
    """Volley retry hints for known ITR auto-repairable patterns."""
    joined = " ".join((schema_errors or []) + (lint_errors or [])).lower()
    hints: list[str] = []
    if "topic_tags" in joined and "null" in joined:
        hints.append("Use topic_tags: [] instead of null (deterministic repair applies).")
    if "flags" in joined and "null" in joined:
        hints.append("Use flags: [] instead of null.")
    if "warnings" in joined and "null" in joined:
        hints.append("Use warnings: [] instead of null on boundaries.")
    if "duplicate segment_id" in joined:
        hints.append("Each segment_id must appear once — duplicates are auto-dropped if repair runs.")
    if "manifest times not monotonic" in joined or "zero-length boundary" in joined:
        hints.append("Ensure monotonic start_ms/end_ms with no zero-length boundaries.")
    if "segment_coverage_ratio" in joined:
        hints.append("Include every required_segment_id from classification_obligation.")
    if "all segments typed interviewee_answer" in joined:
        hints.append("Vary segment types per transcript evidence (question, setup, reaction).")
    if not hints:
        return None
    return "## Auto-repairable issues (ITR)\n\n" + "\n".join(f"- {h}" for h in hints)


def boundary_lint_escalation(
    lint_errors: list[str],
    *,
    attempt: int,
    prior_strategy_keys: list[str],
    structural_repair_partial: bool = False,
    oversplit: bool = False,
) -> dict[str, Any]:
    """Escalation ladder for boundary_detection lint retries."""
    joined = " ".join(lint_errors).lower()
    strategy: dict[str, Any] = {}

    if structural_repair_partial:
        strategy["strategy_key"] = "structural_repair_partial"
        if "truncation_requires_decompose" in joined or oversplit:
            strategy["force_decompose"] = True
            strategy["strategy_key"] = "timeline_decompose"
            strategy["strict_appendix"] = _LINT_BOUNDARY_TIMELINE_APPENDIX
        return strategy

    if "truncation_requires_decompose" in joined:
        strategy["force_decompose"] = True
        strategy["strategy_key"] = "truncation_decompose"
        return strategy

    if oversplit and attempt >= 1:
        strategy["force_decompose"] = True
        strategy["strategy_key"] = "proactive_boundary_decompose"
        return strategy

    if "duplicate segment_id" in joined or "manifest times not monotonic" in joined:
        if "timeline_decompose" not in prior_strategy_keys:
            strategy["force_decompose"] = True
            strategy["strict_appendix"] = _LINT_BOUNDARY_TIMELINE_APPENDIX
            strategy["strategy_key"] = "timeline_decompose"
            return strategy

    if "confidence_gte_min" in joined:
        strategy["bump_tier"] = True
        strategy["strategy_key"] = "tier_bump"
        return strategy

    if "micro-segment explosion" in joined:
        strategy["strict_appendix"] = _LINT_BOUNDARY_MERGE_APPENDIX
        strategy["strategy_key"] = "boundary_merge_hint"
        return strategy

    strategy["strategy_key"] = "lint_retry_boundary_detection"
    return strategy


def lint_retry_strategy(
    lint_errors: list[str],
    stage_key: str,
    *,
    attempt: int = 1,
    prior_strategy_keys: list[str] | None = None,
    structural_repair_partial: bool = False,
    oversplit: bool = False,
) -> dict[str, Any]:
    """Map lint failures to retry parameters."""
    strategy: dict[str, Any] = {}
    if not lint_errors:
        return strategy

    if stage_key == "boundary_detection":
        return boundary_lint_escalation(
            lint_errors,
            attempt=attempt,
            prior_strategy_keys=prior_strategy_keys or [],
            structural_repair_partial=structural_repair_partial,
            oversplit=oversplit,
        )

    joined = " ".join(lint_errors).lower()
    if "truncation_requires_decompose" in joined:
        strategy["force_decompose"] = True
        strategy["strategy_key"] = "truncation_decompose"
    if "segment_coverage_ratio" in joined:
        strategy["force_decompose"] = True
        strategy["inject_missing_segment_ids"] = True
        strategy["strict_appendix"] = _LINT_CLASSIFICATION_COVERAGE_APPENDIX
        strategy["strategy_key"] = "coverage_retry"
    if "all segments typed interviewee_answer" in joined:
        strategy["force_decompose"] = True
        strategy["strict_appendix"] = _LINT_CLASSIFICATION_TYPE_APPENDIX
        strategy["strategy_key"] = "type_diversity_decompose"
    if "confidence_gte_min" in joined:
        strategy["bump_tier"] = True
    if stage_key != "boundary_detection" and (
        "manifest times not monotonic" in joined or ("timeline" in joined and "invalid" in joined)
    ):
        strategy["upstream_rerun"] = "boundary_detection"
        strategy["strategy_key"] = "upstream_boundary_rerun"
    if any(
        x in joined
        for x in ("generic theme", "key_claim without evidence", "topic without evidence")
    ):
        strategy["enrich_input"] = True
    if "thesis empty" in joined:
        from interview_mux.llm_stage_routing import _LINT_THESIS_APPENDIX

        strategy["strict_appendix"] = _LINT_THESIS_APPENDIX
    elif strategy.get("enrich_input") and not strategy.get("strict_appendix"):
        from interview_mux.llm_stage_routing import _LINT_EVIDENCE_APPENDIX

        strategy["strict_appendix"] = _LINT_EVIDENCE_APPENDIX
    if not strategy.get("strategy_key"):
        strategy["strategy_key"] = f"lint_retry_{stage_key}"
    return strategy


def format_lint_feedback(
    lint_errors: list[str],
    stage_key: str,
    ctx: RunContext | None = None,
    obligation: dict[str, Any] | None = None,
) -> str:
    lines = ["## Prior attempt failed deterministic lint", ""]
    for err in lint_errors[:8]:
        lines.append(f"- {err}")
    if stage_key == "segment_classification" and obligation and ctx:
        lines.append("")
        lines.append("Missing segment ids must be included in artifacts.segments.")
    if stage_key == "boundary_detection":
        lines.append("")
        lines.append("Unique segment_id, monotonic times, no zero-length boundaries required.")
    lines.append("")
    lines.append("Fix the issues above and return a complete envelope.")
    return "\n".join(lines)
