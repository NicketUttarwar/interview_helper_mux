"""Detect edits that fabricate meaning out of authentic clips.

Spec: docs/cross-cutting/mastering-semantic-integrity.md
Schema: mastering_semantic_integrity.schema.json
Artifact: mastering/shape/semantic_integrity.json

Deterministic scans run first and are cheap; the LLM confirm pass (see
docs/prompts/mastering/semantic-integrity.system.txt) reviews only what is flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext

INTEGRITY_ARTIFACT = "mastering/shape/semantic_integrity.json"

CRITICAL_CLASSES: frozenset[str] = frozenset(
    {
        "quote_out_of_context",
        "causality_reversal",
        "false_reaction_adjacency",
        "fabricated_exchange",
        "vo_overstates_claim",
        "vernacular_evidence_dropped",
    }
)

# Markers that invert or qualify meaning when the surrounding context is dropped.
_NEGATION_MARKERS = (
    "not", "never", "no one", "nobody", "don't", "doesn't", "didn't", "isn't",
    "wasn't", "won't", "can't", "cannot", "hardly", "far from",
)
_CONDITIONAL_MARKERS = (
    "if", "unless", "suppose", "hypothetically", "imagine", "what if", "in theory",
    "some people say", "they claim", "the argument goes", "critics say",
)
_CAUSAL_MARKERS = ("because", "so that", "therefore", "that's why", "which is why", "as a result")
_ANAPHORA = re.compile(
    r"^\s*(?:and\s+|but\s+|so\s+)?(that|those|these|this|it|they|he|she|there)\b",
    re.IGNORECASE,
)


@dataclass
class IntegrityInputs:
    """Source-side facts the scans compare the plan against."""

    segments: dict[str, dict[str, Any]] = field(default_factory=dict)
    turn_index: dict[str, int] = field(default_factory=dict)
    reaction_segment_ids: set[str] = field(default_factory=set)
    vo_lines: dict[str, dict[str, Any]] = field(default_factory=dict)
    claims: list[dict[str, Any]] = field(default_factory=list)
    vernacular_must_keep_segment_ids: set[str] = field(default_factory=set)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding(
    class_id: str,
    detail: str,
    *,
    segment_id: str | None = None,
    related: list[str] | None = None,
    vo_line_id: str | None = None,
    repair: str | None = None,
    confidence: float = 0.8,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "class_id": class_id,
        "severity": "critical" if class_id in CRITICAL_CLASSES else "warn",
        "detail": detail,
        "source": "deterministic",
        "confidence": confidence,
    }
    if segment_id:
        out["segment_id"] = segment_id
    if related:
        out["related_segment_ids"] = related
    if vo_line_id:
        out["vo_line_id"] = vo_line_id
    if repair:
        out["repair_directive"] = repair
    return out


def _text(inputs: IntegrityInputs, segment_id: str) -> str:
    seg = inputs.segments.get(segment_id) or {}
    return str(seg.get("text") or "")


def _contains(text: str, markers: tuple[str, ...]) -> str | None:
    lowered = f" {text.lower()} "
    for marker in markers:
        if f" {marker} " in lowered or lowered.strip().startswith(f"{marker} "):
            return marker
    return None


def scan_hook_context(candidate: dict[str, Any], inputs: IntegrityInputs) -> list[dict[str, Any]]:
    """A lifted hook can invert meaning when its qualifying context stays behind."""
    cold = candidate.get("cold_open") if isinstance(candidate.get("cold_open"), dict) else {}
    hook_id = cold.get("segment_id")
    if not hook_id:
        return []
    hook_id = str(hook_id)
    seg = inputs.segments.get(hook_id)
    if not seg:
        return []

    findings: list[dict[str, Any]] = []
    context_before = str(seg.get("context_before") or "")
    marker = _contains(context_before, _NEGATION_MARKERS) or _contains(
        context_before, _CONDITIONAL_MARKERS
    )
    if marker:
        findings.append(
            _finding(
                "quote_out_of_context",
                f"Hook {hook_id} is preceded by '{marker}', which qualifies or inverts it",
                segment_id=hook_id,
                confidence=0.65,
            )
        )
    if seg.get("starts_mid_clause") or seg.get("ends_mid_clause"):
        findings.append(
            _finding(
                "quote_out_of_context",
                f"Hook {hook_id} is lifted mid-clause, so its meaning may not survive the cut",
                segment_id=hook_id,
                confidence=0.6,
            )
        )
    return findings


def scan_causality(candidate: dict[str, Any], inputs: IntegrityInputs) -> list[dict[str, Any]]:
    """Flag reorders that put an effect before the cause it names."""
    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or [])]
    findings: list[dict[str, Any]] = []
    for i, sid in enumerate(ordered):
        marker = _contains(_text(inputs, sid), _CAUSAL_MARKERS)
        if not marker:
            continue
        source_pos = inputs.turn_index.get(sid)
        if source_pos is None:
            continue
        for other in ordered[:i]:
            other_pos = inputs.turn_index.get(other)
            if other_pos is None or other_pos <= source_pos:
                continue
            findings.append(
                _finding(
                    "causality_reversal",
                    (
                        f"{sid} states a cause with '{marker}' but now follows {other}, "
                        "which came later in the source"
                    ),
                    segment_id=sid,
                    related=[other],
                    confidence=0.6,
                )
            )
            break
    return findings


def scan_reaction_adjacency(
    candidate: dict[str, Any], inputs: IntegrityInputs, *, max_turns: int
) -> list[dict[str, Any]]:
    """A reaction placed against something it never answered is a fabrication."""
    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or [])]
    findings: list[dict[str, Any]] = []
    for i, sid in enumerate(ordered):
        if sid not in inputs.reaction_segment_ids or i == 0:
            continue
        prev = ordered[i - 1]
        a, b = inputs.turn_index.get(prev), inputs.turn_index.get(sid)
        if a is None or b is None:
            continue
        if abs(b - a) > max_turns or b < a:
            findings.append(
                _finding(
                    "false_reaction_adjacency",
                    (
                        f"Reaction {sid} now answers {prev}, which it never responded to "
                        f"in the source ({abs(b - a)} turns apart)"
                    ),
                    segment_id=sid,
                    related=[prev],
                    confidence=0.7,
                )
            )
    return findings


def scan_orphaned_referents(
    candidate: dict[str, Any], inputs: IntegrityInputs
) -> list[dict[str, Any]]:
    """A retained clip pointing at a removed antecedent leaves the listener stranded."""
    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or [])]
    included = set(ordered)
    findings: list[dict[str, Any]] = []
    for i, sid in enumerate(ordered):
        match = _ANAPHORA.match(_text(inputs, sid))
        if not match:
            continue
        antecedent = (inputs.segments.get(sid) or {}).get("antecedent_segment_id")
        if not antecedent:
            continue
        antecedent = str(antecedent)
        if antecedent in included and ordered.index(antecedent) < i:
            continue
        findings.append(
            _finding(
                "orphaned_referent",
                (
                    f"{sid} opens with '{match.group(1)}' but its antecedent {antecedent} "
                    "is excluded or comes later"
                ),
                segment_id=sid,
                related=[antecedent],
                repair=f"Include {antecedent} before {sid}, add a VO bridge, or drop {sid}",
                confidence=0.75,
            )
        )
    return findings


def scan_reprise(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """The same clip in two places implies it was said twice unless declared a reprise."""
    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or [])]
    cold = candidate.get("cold_open") if isinstance(candidate.get("cold_open"), dict) else {}
    hook_id = str(cold.get("segment_id") or "")
    findings: list[dict[str, Any]] = []
    if hook_id and hook_id in ordered and not cold.get("reprise_later"):
        findings.append(
            _finding(
                "reprise_implies_repeat",
                f"Hook {hook_id} replays in the body without reprise_later, implying it was said twice",
                segment_id=hook_id,
                repair=f"Set cold_open.reprise_later or drop {hook_id} from the body order",
                confidence=0.9,
            )
        )
    return findings


def scan_chronology(candidate: dict[str, Any], inputs: IntegrityInputs) -> list[dict[str, Any]]:
    """Unsignposted time jumps confuse without necessarily lying."""
    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or [])]
    bridged = {str(b) for b in (candidate.get("bridged_segment_ids") or [])}
    jumps: list[str] = []
    for i in range(1, len(ordered)):
        prev, cur = inputs.turn_index.get(ordered[i - 1]), inputs.turn_index.get(ordered[i])
        if prev is None or cur is None:
            continue
        if cur < prev and ordered[i] not in bridged:
            jumps.append(ordered[i])
    if not jumps:
        return []
    return [
        _finding(
            "chronology_scramble",
            f"Unsignposted backward time jumps at: {', '.join(jumps)}",
            related=jumps,
            repair="Add a signposting bridge before each jump or restore source order",
            confidence=0.6,
        )
    ]


def scan_vernacular_evidence_dropped(
    candidate: dict[str, Any], inputs: IntegrityInputs
) -> list[dict[str, Any]]:
    """Authoritative vernacular must_keep children missing from the candidate order."""
    must = {str(s) for s in (inputs.vernacular_must_keep_segment_ids or set()) if s}
    if not must:
        return []
    ordered = {str(s) for s in (candidate.get("ordered_segment_ids") or []) if s}
    missing = sorted(must - ordered)
    if not missing:
        return []
    return [
        _finding(
            "vernacular_evidence_dropped",
            f"Vernacular must_keep segments omitted from candidate: {', '.join(missing[:12])}",
            related=missing,
            repair=f"Include {', '.join(missing[:8])} or demote vernacular enforcement with recorded override",
            confidence=0.95,
        )
    ]


def check_candidate(
    candidate: dict[str, Any],
    inputs: IntegrityInputs,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conf = gate_cfg("semantic_integrity", cfg)
    max_turns = int(conf.get("adjacency_max_turns") or 3)

    findings: list[dict[str, Any]] = []
    findings.extend(scan_hook_context(candidate, inputs))
    findings.extend(scan_causality(candidate, inputs))
    findings.extend(scan_reaction_adjacency(candidate, inputs, max_turns=max_turns))
    findings.extend(scan_orphaned_referents(candidate, inputs))
    findings.extend(scan_reprise(candidate))
    findings.extend(scan_chronology(candidate, inputs))
    findings.extend(scan_vernacular_evidence_dropped(candidate, inputs))

    critical = [f for f in findings if f["severity"] == "critical"]
    if critical:
        verdict = "fail"
    elif findings:
        verdict = "pass_with_warnings"
    else:
        verdict = "pass"
    return {
        "candidate_id": str(candidate.get("candidate_id") or "candidate"),
        "verdict": verdict,
        "findings": findings,
    }


def build_integrity_report(
    candidates: list[dict[str, Any]],
    inputs: IntegrityInputs,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conf = gate_cfg("semantic_integrity", cfg)
    results = [check_candidate(c, inputs, cfg=cfg) for c in candidates]
    return {
        "version": 1,
        "mode": gate_mode("semantic_integrity", cfg),
        "llm_confirm_applied": False,
        "candidates": results,
        "clean_candidate_ids": [r["candidate_id"] for r in results if r["verdict"] != "fail"],
        "generated_at": _now(),
        "_llm_confirm_requested": bool(conf.get("llm_confirm", True)) and any(r["findings"] for r in results),
    }


def flagged_windows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Findings the LLM confirm pass should review, so it never scans the whole transcript."""
    windows: list[dict[str, Any]] = []
    for cand in report.get("candidates") or []:
        for finding in cand.get("findings") or []:
            windows.append({"candidate_id": cand.get("candidate_id"), **finding})
    return windows


def merge_llm_findings(
    report: dict[str, Any], llm_findings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Fold confirm-pass output back in; the LLM may clear a flag by omitting it."""
    by_candidate: dict[str, list[dict[str, Any]]] = {}
    for finding in llm_findings:
        cid = str(finding.get("candidate_id") or "")
        payload = {k: v for k, v in finding.items() if k != "candidate_id"}
        payload.setdefault("source", "llm")
        by_candidate.setdefault(cid, []).append(payload)

    merged = dict(report)
    merged["llm_confirm_applied"] = True
    merged.pop("_llm_confirm_requested", None)
    candidates: list[dict[str, Any]] = []
    for cand in report.get("candidates") or []:
        cid = str(cand.get("candidate_id"))
        findings = by_candidate.get(cid, [])
        critical = [f for f in findings if f.get("severity") == "critical"]
        if critical:
            verdict = "fail"
        elif findings:
            verdict = "pass_with_warnings"
        else:
            verdict = "pass"
        candidates.append({"candidate_id": cid, "verdict": verdict, "findings": findings})
    merged["candidates"] = candidates
    merged["clean_candidate_ids"] = [c["candidate_id"] for c in candidates if c["verdict"] != "fail"]
    return merged


def clean_candidates(
    report: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop critically non-integral candidates (advisory mode passes all through)."""
    if report.get("mode") != "authoritative":
        return list(candidates)
    allowed = set(report.get("clean_candidate_ids") or [])
    return [c for c in candidates if str(c.get("candidate_id")) in allowed]


def write_integrity_report(ctx: RunContext, report: dict[str, Any]) -> None:
    payload = {k: v for k, v in report.items() if not k.startswith("_")}
    ctx.write_json(INTEGRITY_ARTIFACT, payload)
    failed = [
        c.get("candidate_id")
        for c in (report.get("candidates") or [])
        if isinstance(c, dict) and c.get("verdict") == "fail"
    ]
    if failed:
        try:
            from interview_mux.homunculus.issues import ingest_catch

            ingest_catch(
                ctx,
                kind="semantic_integrity",
                source="mastering_semantic_integrity",
                implicated=["mastering_shape_candidates"],
                evidence={"failed_candidate_ids": failed[:12]},
            )
        except Exception:
            pass
