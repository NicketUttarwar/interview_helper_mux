"""Evidence-aware safety guard for every listener-facing synthetic line."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from interview_mux.spoken_meta_lint import lint_spoken_text

_PATH_OR_FILE = re.compile(
    r"(?:^|[\s(\"'])(?:[A-Za-z]:\\|/[\w.-]+/|\.{0,2}/[\w.-]+)|"
    r"\b[\w.-]+\.(?:json|ya?ml|wav|mp3|txt|csv|py|tsx?)\b",
    re.IGNORECASE,
)
_PRODUCTION_JARGON = re.compile(
    r"\b(?:"
    r"edl|edit decision list|timeline|stage|pipeline|artifact|schema|"
    r"quality control|qc(?:\s+pass|\s+fail)?|lint|validator|"
    r"selection order|source segment|native segment|gap report|"
    r"synthesis report|fallback backend|confidence score|"
    r"listener confusion|missing setup|missing question"
    r")\b",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(
    r"(?:\{\{[^{}]+\}\}|\{[A-Za-z_][^{}]*\}|<[^<>]+>|\[[A-Z][A-Z0-9_ -]+\]|"
    r"\b(?:tbd|todo|fixme|lorem ipsum|insert (?:name|topic|text) here)\b)",
    re.IGNORECASE,
)
_MALFORMED_END = re.compile(r"(?:\.\.\.|…|[—–,:;/(\[])\s*$")
_NEXT_WORD = re.compile(r"\b(?:next|then|after that|what followed)\b", re.IGNORECASE)
_GENERIC_FILLER = re.compile(
    r"\b(?:"
    r"what (?:happened|changed|comes) next|what follows|next beat|"
    r"coming up|where does this stretch lead|broader story changing|"
    r"there is more to that story"
    r")\b",
    re.IGNORECASE,
)
_PROPER_NAME = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b")
_TOKEN = re.compile(r"[A-Za-z0-9₹$%]+")
_STOCK = {
    "there is more to that story",
    "and then this next beat",
    "next the focus shifts",
    "meanwhile what happened next",
    "coming up where does this stretch lead",
}
_ENTITY_IGNORE = {
    "And",
    "But",
    "How",
    "In",
    "Let",
    "Moving",
    "Stepping",
    "That",
    "The",
    "This",
    "Turning",
    "What",
    "When",
    "Where",
    "Why",
    "With",
}


def normalize_script(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def script_hash(text: str) -> str:
    return hashlib.sha256(normalize_script(text).encode("utf-8")).hexdigest()


def context_hash(evidence: dict[str, Any] | None) -> str:
    payload = evidence if isinstance(evidence, dict) else {}
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evidence_for_line(line: dict[str, Any] | None) -> dict[str, Any]:
    row = line if isinstance(line, dict) else {}
    prior = row.get("prior_native_context")
    prior = prior if isinstance(prior, dict) else {}
    return {
        "line_id": row.get("line_id"),
        "target_segment_id": row.get("targets_segment_id"),
        "placement": row.get("placement"),
        "line_category": row.get("line_category"),
        "after_segment_id": row.get("after_segment_id"),
        "before_segment_id": row.get("before_segment_id"),
        "before_excerpt": row.get("before_excerpt")
        or prior.get("prior_text")
        or prior.get("quote"),
        "after_excerpt": row.get("after_excerpt"),
        "target_excerpt": row.get("target_excerpt")
        or row.get("target_native_context"),
        "before_topic": row.get("before_topic"),
        "after_topic": row.get("after_topic") or row.get("target_topic"),
        "source_gap_ms": row.get("source_gap_ms"),
        "verified_person": row.get("verified_person"),
        "verified_place": row.get("verified_place"),
        "verified_time": row.get("verified_time"),
        "causal_cue": row.get("causal_cue"),
    }


def shorten_spoken_text(text: str, max_words: int) -> str:
    """Shorten at sentence/word boundaries without shipping a dangling fragment."""
    clean = normalize_script(text)
    if max_words <= 0 or len(clean.split()) <= max_words:
        return clean
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    kept: list[str] = []
    for sentence in sentences:
        proposed = normalize_script(" ".join([*kept, sentence]))
        if len(proposed.split()) > max_words:
            break
        kept.append(sentence)
    if kept:
        result = normalize_script(" ".join(kept))
    else:
        words = clean.split()[:max_words]
        result = " ".join(words).rstrip(" ,;:—–-")
        if result and result[-1] not in ".!?":
            result += "."
    return result


def _safe_context(raw: Any, *, max_words: int = 12) -> str:
    text = normalize_script(str(raw or ""))
    if not text:
        return ""
    if lint_spoken_text(text, label="context") or _PATH_OR_FILE.search(text):
        return ""
    if _PRODUCTION_JARGON.search(text) or _PLACEHOLDER.search(text):
        return ""
    text = re.split(r"[.!?;]", text, maxsplit=1)[0].strip(" ,:—–-")
    return shorten_spoken_text(text, max_words).rstrip(".")


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN.findall(normalize_script(text))
        if len(token) > 2
    }


def _evidence_text(evidence: dict[str, Any]) -> str:
    parts: list[str] = []
    def collect(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, (int, float)):
            parts.append(str(value))

    for key, value in evidence.items():
        if key not in {"strict_grounding", "required", "source_gap_ms", "chronology"}:
            collect(value)
    return " ".join(parts)


def _restates_target(text: str, target: str) -> bool:
    a, b = _tokens(text), _tokens(target)
    if len(a) < 4 or len(b) < 4:
        return False
    return len(a & b) / max(1, min(len(a), len(b))) >= 0.72


def spoken_copy_violations(
    text: str,
    *,
    evidence: dict[str, Any] | None = None,
    seen_texts: Iterable[str] | None = None,
) -> list[str]:
    clean = normalize_script(text)
    if not clean:
        return ["empty_spoken_copy"]
    errors = [
        err.rsplit("(", 1)[-1].rstrip(")")
        for err in lint_spoken_text(clean, label="spoken_copy")
    ]
    if _PATH_OR_FILE.search(clean):
        errors.append("spoken_path_or_filename")
    if _PRODUCTION_JARGON.search(clean):
        errors.append("spoken_production_jargon")
    if _PLACEHOLDER.search(clean):
        errors.append("spoken_placeholder")
    if _MALFORMED_END.search(clean) or clean.count("(") != clean.count(")"):
        errors.append("spoken_malformed_fragment")
    stock_key = re.sub(r"[^a-z0-9 ]+", "", clean.casefold()).strip()
    if stock_key in _STOCK:
        errors.append("spoken_stock_copy")
    seen = {normalize_script(x).casefold() for x in (seen_texts or []) if x}
    if clean.casefold() in seen:
        errors.append("spoken_repeated_copy")

    ev = evidence if isinstance(evidence, dict) else {}
    try:
        source_gap = (
            int(ev["source_gap_ms"]) if ev.get("source_gap_ms") is not None else None
        )
    except (TypeError, ValueError):
        source_gap = None
    if source_gap is not None and source_gap < 0 and _NEXT_WORD.search(clean):
        errors.append("spoken_chronology_mismatch")
    semantic_relative_ok = bool(
        source_gap is not None
        and source_gap >= 0
        and str(ev.get("before_excerpt") or "").strip()
        and str(
            ev.get("after_excerpt")
            or ev.get("target_excerpt")
            or ev.get("next_clip_text")
            or ""
        ).strip()
    )
    if _GENERIC_FILLER.search(clean) and not semantic_relative_ok:
        errors.append("spoken_generic_filler")
    target = str(
        ev.get("after_excerpt")
        or ev.get("target_excerpt")
        or ev.get("next_clip_text")
        or ""
    )
    if target and _restates_target(clean, target):
        errors.append("spoken_next_clip_restatement")

    if bool(ev.get("strict_grounding")):
        corpus = _evidence_text(ev)
        corpus_fold = corpus.casefold()
        unsupported = [
            entity
            for entity in _PROPER_NAME.findall(clean)
            if entity not in _ENTITY_IGNORE and entity.casefold() not in corpus_fold
        ]
        if unsupported:
            errors.append("spoken_unsupported_entity:" + ",".join(unsupported[:3]))
    return list(dict.fromkeys(errors))


def _grounded_fallback(evidence: dict[str, Any]) -> str:
    before_topic = _safe_context(evidence.get("before_topic"))
    after_topic = _safe_context(evidence.get("after_topic"))
    if before_topic and after_topic and before_topic.casefold() != after_topic.casefold():
        return f"Moving from {before_topic} to {after_topic}, what changed?"
    if after_topic:
        return f"Turning to {after_topic}, what changed?"
    if before_topic:
        return f"With {before_topic} established, what changed?"

    person = _safe_context(evidence.get("verified_person"))
    place = _safe_context(evidence.get("verified_place"))
    time = _safe_context(evidence.get("verified_time"))
    cause = _safe_context(evidence.get("causal_cue"))
    if cause:
        return f"With {cause} in place, what changed?"
    if person:
        return f"How did {person} shape what happened?"
    if place:
        return f"What changed in {place}?"
    if time:
        return f"What changed around {time}?"

    before_excerpt = _safe_context(evidence.get("before_excerpt"))
    after_excerpt = _safe_context(
        evidence.get("after_excerpt") or evidence.get("target_excerpt")
    )
    try:
        source_gap = (
            int(evidence["source_gap_ms"])
            if evidence.get("source_gap_ms") is not None
            else None
        )
    except (TypeError, ValueError):
        source_gap = None
    if source_gap is not None and source_gap < 0 and (before_excerpt or after_excerpt):
        return "Stepping back, what set this part of the story in motion?"
    if (
        source_gap is not None
        and source_gap >= 0
        and before_excerpt
        and after_excerpt
    ):
        return "What changed after that?"
    return ""


def grounded_fallback_for_evidence(evidence: dict[str, Any] | None) -> str:
    """Return listener-safe grounded glue, or empty when evidence is insufficient."""
    return _grounded_fallback(dict(evidence or {}))


def guard_spoken_copy(
    text: str,
    *,
    evidence: dict[str, Any] | None = None,
    required: bool,
    purpose: str = "synthetic_vo",
    seen_texts: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Allow safe copy, substitute grounded copy, omit optional, or block required."""
    ev = dict(evidence or {})
    original = normalize_script(text)
    violations = spoken_copy_violations(
        original, evidence=ev, seen_texts=seen_texts
    )
    if not violations:
        return {
            "action": "allow",
            "text": original,
            "violations": [],
            "script_hash": script_hash(original),
            "context_hash": context_hash(ev),
            "purpose": purpose,
        }
    fallback = _grounded_fallback(ev)
    fallback_errors = (
        spoken_copy_violations(fallback, evidence=ev, seen_texts=seen_texts)
        if fallback
        else ["no_grounded_fallback"]
    )
    if fallback and not fallback_errors:
        return {
            "action": "fallback",
            "text": fallback,
            "violations": violations,
            "script_hash": script_hash(fallback),
            "context_hash": context_hash(ev),
            "purpose": purpose,
        }
    return {
        "action": "block" if required else "omit",
        "text": "",
        "violations": [*violations, *fallback_errors],
        "script_hash": script_hash(""),
        "context_hash": context_hash(ev),
        "purpose": purpose,
    }


def assert_guarded_spoken_copy(
    text: str,
    *,
    evidence: dict[str, Any] | None = None,
    purpose: str,
) -> dict[str, Any]:
    decision = guard_spoken_copy(
        text, evidence=evidence, required=True, purpose=purpose
    )
    if decision["action"] == "block":
        raise ValueError(
            f"{purpose} blocked by spoken_copy_guard: "
            + ", ".join(decision["violations"])
        )
    return decision


def artifact_spoken_copy_errors(
    *,
    gap_report: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    grounding_context: Any = None,
) -> list[str]:
    """Validate all persisted listener-facing copy with target-aware evidence."""
    errors: list[str] = []
    by_id = segments_by_id or {}
    seen: list[str] = []
    for row in ((gap_report or {}).get("interviewer_lines") or []):
        if not isinstance(row, dict) or row.get("skipped_optional"):
            continue
        target = str(row.get("targets_segment_id") or "")
        evidence = {
            **evidence_for_line(row),
            "target_excerpt": (by_id.get(target) or {}).get("text")
            or evidence_for_line(row).get("target_excerpt"),
            "grounding_context": grounding_context,
            "strict_grounding": bool(grounding_context or by_id.get(target)),
        }
        violations = spoken_copy_violations(
            str(row.get("text") or ""), evidence=evidence, seen_texts=seen
        )
        if violations:
            errors.append(
                f"gap[{row.get('line_id') or target}]:" + ",".join(violations)
            )
        seen.append(str(row.get("text") or ""))
    for row in ((transitions or {}).get("transitions") or []):
        if not isinstance(row, dict) or not str(row.get("text") or "").strip():
            continue
        a = str(row.get("after_segment_id") or "")
        b = str(row.get("before_segment_id") or "")
        evidence = {
            "before_excerpt": (by_id.get(a) or {}).get("text"),
            "after_excerpt": (by_id.get(b) or {}).get("text"),
            "before_topic": (by_id.get(a) or {}).get("topic"),
            "after_topic": (by_id.get(b) or {}).get("topic"),
            "source_gap_ms": row.get("source_gap_ms"),
            "strict_grounding": True,
        }
        violations = spoken_copy_violations(
            str(row.get("text") or ""), evidence=evidence, seen_texts=seen
        )
        if violations:
            errors.append(f"transition[{a}->{b}]:" + ",".join(violations))
        seen.append(str(row.get("text") or ""))
    return errors
