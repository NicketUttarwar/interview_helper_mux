"""CSP-05: hollow/invalid OpenAI primary after ≤2 attempts must not soft-heal done.

Operator Q2A binding for at least:
- mastering_research_routing
- mastering_shape_agenda
- topic_coverage_audit
- gap_framing_compose

Disabled / skip / heuristic-default paths (LLM off) remain honest done.
Does not weaken VO WAV honesty or mmaudio omit-all fail.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

# Stages that refuse soft-success on hollow OpenAI primary (CSP-05 Wave 2 pins).
CSP05_OPENAI_PRIMARY_STAGES: frozenset[str] = frozenset(
    {
        "mastering_research_routing",
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "topic_coverage_audit",
        "gap_framing_compose",
    }
)


def hollow_openai_reason(stage_id: str, detail: str) -> str:
    """Stable incompleteness / StageError reason string."""
    detail = (detail or "hollow_or_invalid").strip()
    return (
        f"{stage_id} incomplete: hollow/invalid OpenAI primary after ≤2 attempts — {detail}"
    )


def raise_hollow_openai_primary(stage_id: str, detail: str) -> None:
    """Refuse the stage after exhausted OpenAI attempts (no soft-success heal-done)."""
    from interview_mux.llm_simple import StageError

    raise StageError(stage_id, hollow_openai_reason(stage_id, detail))


def research_routing_llm_failed_incompleteness(doc: dict[str, Any] | None) -> str | None:
    """MRR: llm_failed stub must not seed-complete when research.llm was on."""
    if not isinstance(doc, dict):
        return None
    if doc.get("llm_failed") is True or str(doc.get("skipped") or "") == "llm_failed":
        return hollow_openai_reason(
            "mastering_research_routing",
            str(doc.get("fail_reason") or "llm_failed"),
        )
    return None


def shape_agenda_rubric_llm_failed_incompleteness(
    agenda: dict[str, Any] | None,
    rubric: dict[str, Any] | None,
) -> str | None:
    """MSA: shape.llm path must not heal on hollow rubric / llm_failed agenda."""
    notes: list[str] = []
    if isinstance(agenda, dict):
        notes.extend(str(n) for n in (agenda.get("notes") or []) if n)
        if str(agenda.get("skipped") or "") == "llm_failed" or agenda.get("llm_failed") is True:
            return hollow_openai_reason("mastering_shape_agenda", "agenda_llm_failed")
    if isinstance(rubric, dict):
        notes.extend(str(n) for n in (rubric.get("notes") or []) if n)
        if "rubric_llm_failed" in notes or rubric.get("llm_failed") is True:
            return hollow_openai_reason("mastering_shape_agenda", "rubric_llm_failed")
        if str(rubric.get("source") or "") == "heuristic" and "rubric_llm_failed" in notes:
            return hollow_openai_reason("mastering_shape_agenda", "rubric_llm_failed")
    return None


def coverage_audit_hollow_incompleteness(doc: dict[str, Any] | None) -> str | None:
    """TCA: LLM soft-persist without score/mappings is hollow — not done."""
    if not isinstance(doc, dict):
        return hollow_openai_reason("topic_coverage_audit", "missing_coverage_audit")
    mappings = doc.get("topic_mappings")
    findings = doc.get("findings") or doc.get("topics") or doc.get("coverage")
    has_map = isinstance(mappings, list) and bool(mappings)
    has_findings = (isinstance(findings, list) and bool(findings)) or (
        isinstance(findings, dict) and bool(findings)
    )
    if doc.get("coverage_score") is not None and isinstance(doc.get("missing_coverage"), list):
        return None
    if has_map or has_findings:
        return None
    return hollow_openai_reason(
        "topic_coverage_audit",
        "coverage_score/topic_mappings hollow",
    )


def gap_compose_zero_lines_while_framing(
    doc: dict[str, Any] | None,
    *,
    framing_enabled: bool,
) -> str | None:
    """GFC: framing Yes + zero/hollow interviewer_lines must not complete."""
    if not framing_enabled or not isinstance(doc, dict):
        return None
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    producer = str(meta.get("producer") or meta.get("producer_stage") or "")
    if producer not in {"gap_framing_compose", "optimal_questions"}:
        return None
    lines = [
        row for row in (doc.get("interviewer_lines") or []) if isinstance(row, dict)
    ]
    if lines:
        # Hollow = rows present but no usable spoken text.
        usable = [
            row
            for row in lines
            if str(row.get("text") or row.get("line_text") or row.get("script") or "").strip()
        ]
        if usable:
            return None
        return hollow_openai_reason(
            "gap_framing_compose",
            "hollow interviewer_lines while framing Yes",
        )
    return hollow_openai_reason(
        "gap_framing_compose",
        "zero interviewer_lines while framing Yes",
    )


def ensure_openai_primary_complete(ctx: RunContext, stage_id: str) -> None:
    """Assert primary complete then heal; refuse (raise) on hollow CSP-05 stages."""
    from interview_mux.stage_completion import heal_or_raise

    heal_or_raise(ctx, stage_id, force=True)
