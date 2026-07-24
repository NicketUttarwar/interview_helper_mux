"""Prove a shape candidate can actually be built before it costs anything.

Spec: docs/cross-cutting/mastering-feasibility.md
Schema: mastering_feasibility.schema.json
Artifact: mastering/shape/feasibility.json

Deterministic only — no LLM judgement. Mirrors the validation patterns in
artifact_completeness.py, edl_narrative_qc.py, and gap_vo_gates.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext

FEASIBILITY_ARTIFACT = "mastering/shape/feasibility.json"

BLOCKING_CHECKS: frozenset[str] = frozenset(
    {
        "segment_exists",
        "segment_bounds",
        "vo_line_exists",
        "vo_audio_or_synth",
        "sfx_cue_exists",
        "pickup_voice_authorized",
        "speaker_volley_integrity",
        "duration_fits",
        "timeline_collision",
        "edl_representable",
        "cold_open_source",
    }
)

VO_COLD_OPEN_KINDS: frozenset[str] = frozenset({"vo_clone_open", "vo_plus_segment"})
SEGMENT_COLD_OPEN_KINDS: frozenset[str] = frozenset({"segment_hook", "vo_plus_segment"})


@dataclass
class FeasibilityInputs:
    """Everything the compiler needs to judge buildability, resolved up front."""

    segments: dict[str, dict[str, Any]] = field(default_factory=dict)
    vo_lines: dict[str, dict[str, Any]] = field(default_factory=dict)
    sfx_cues: set[str] = field(default_factory=set)
    locked_volleys: list[list[str]] = field(default_factory=list)
    pickup_speaker_id: str | None = None
    clone_authorized: bool = False
    synthesis_available: bool = True
    source_duration_ms: int | None = None
    target_duration_ms: int | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(check_id: str, passed: bool, detail: str = "", refs: list[str] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "check_id": check_id,
        "severity": "blocking" if check_id in BLOCKING_CHECKS else "warn",
        "passed": passed,
    }
    if detail:
        row["detail"] = detail
    if refs:
        row["refs"] = refs
    return row


def check_candidate(
    candidate: dict[str, Any],
    inputs: FeasibilityInputs,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conf = gate_cfg("feasibility", cfg)
    slack = float(conf.get("duration_slack_pct") or 0.15)
    checks: list[dict[str, Any]] = []

    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or [])]
    cold = candidate.get("cold_open") if isinstance(candidate.get("cold_open"), dict) else {}
    cold_kind = str(cold.get("kind") or "none")

    checks.extend(_check_segments(ordered, inputs))
    checks.extend(_check_cold_open(cold, cold_kind, ordered, inputs))
    checks.extend(_check_vo(candidate, cold, cold_kind, inputs))
    checks.append(_check_sfx(candidate, cold, inputs))
    checks.append(_check_volleys(ordered, inputs))
    checks.append(_check_duration(candidate, ordered, inputs, slack))
    checks.append(_check_collisions(candidate))
    checks.append(_check_edl_representable(candidate, ordered, cold_kind))
    checks.extend(_warn_checks(candidate, ordered, cold, cold_kind))

    blocking = [
        c.get("detail") or c["check_id"]
        for c in checks
        if c["severity"] == "blocking" and not c["passed"]
    ]
    warnings = [
        c.get("detail") or c["check_id"] for c in checks if c["severity"] == "warn" and not c["passed"]
    ]
    if blocking:
        verdict = "fail"
    elif warnings:
        verdict = "pass_with_warnings"
    else:
        verdict = "pass"

    return {
        "candidate_id": str(candidate.get("candidate_id") or "candidate"),
        "verdict": verdict,
        "checks": checks,
        "blocking_reasons": blocking,
        "warnings": warnings,
    }


def _check_segments(ordered: list[str], inputs: FeasibilityInputs) -> list[dict[str, Any]]:
    missing = [s for s in ordered if s not in inputs.segments]
    checks = [
        _check(
            "segment_exists",
            not missing,
            f"unknown segment ids: {', '.join(missing)}" if missing else "",
            missing or None,
        )
    ]
    out_of_bounds: list[str] = []
    if inputs.source_duration_ms:
        for sid in ordered:
            seg = inputs.segments.get(sid)
            if not seg:
                continue
            end = seg.get("end_ms")
            start = seg.get("start_ms")
            if start is not None and int(start) < 0:
                out_of_bounds.append(sid)
            elif end is not None and int(end) > int(inputs.source_duration_ms):
                out_of_bounds.append(sid)
    checks.append(
        _check(
            "segment_bounds",
            not out_of_bounds,
            f"segments outside source timeline: {', '.join(out_of_bounds)}" if out_of_bounds else "",
            out_of_bounds or None,
        )
    )
    return checks


def _check_cold_open(
    cold: dict[str, Any], cold_kind: str, ordered: list[str], inputs: FeasibilityInputs
) -> list[dict[str, Any]]:
    if cold_kind == "none":
        return [_check("cold_open_source", True)]
    problems: list[str] = []
    if cold_kind in SEGMENT_COLD_OPEN_KINDS:
        sid = cold.get("segment_id")
        if not sid:
            problems.append(f"{cold_kind} names no segment_id")
        elif str(sid) not in inputs.segments:
            problems.append(f"cold open cites unknown segment {sid}")
    if cold_kind in VO_COLD_OPEN_KINDS:
        line_id = cold.get("vo_line_id")
        if not line_id:
            problems.append(f"{cold_kind} names no vo_line_id")
        elif str(line_id) not in inputs.vo_lines:
            problems.append(f"cold open cites unknown VO line {line_id}")
    return [_check("cold_open_source", not problems, "; ".join(problems))]


def _check_vo(
    candidate: dict[str, Any],
    cold: dict[str, Any],
    cold_kind: str,
    inputs: FeasibilityInputs,
) -> list[dict[str, Any]]:
    line_ids = [str(x) for x in (candidate.get("vo_line_ids") or [])]
    if cold_kind in VO_COLD_OPEN_KINDS and cold.get("vo_line_id"):
        line_ids.append(str(cold["vo_line_id"]))
    line_ids = list(dict.fromkeys(line_ids))

    missing = [lid for lid in line_ids if lid not in inputs.vo_lines]
    checks = [
        _check(
            "vo_line_exists",
            not missing,
            f"unknown VO line ids: {', '.join(missing)}" if missing else "",
            missing or None,
        )
    ]

    unrenderable = [
        lid
        for lid in line_ids
        if lid in inputs.vo_lines
        and not inputs.vo_lines[lid].get("audio_path")
        and not inputs.synthesis_available
    ]
    checks.append(
        _check(
            "vo_audio_or_synth",
            not unrenderable,
            (
                f"no recorded audio and no synthesis path for: {', '.join(unrenderable)}"
                if unrenderable
                else ""
            ),
            unrenderable or None,
        )
    )

    checks.append(_check_pickup_voice(candidate, cold, cold_kind, line_ids, inputs))
    return checks


def _check_pickup_voice(
    candidate: dict[str, Any],
    cold: dict[str, Any],
    cold_kind: str,
    line_ids: list[str],
    inputs: FeasibilityInputs,
) -> dict[str, Any]:
    """New VO must be the pickup-eligible speaker, and cloning needs authorization.

    Guest / content-speaker cloning fails here in every mode — the ban is not
    configurable (docs/cross-cutting/mastering-voice-clone-policy.md).
    """
    problems: list[str] = []
    speakers = {
        str(inputs.vo_lines[lid].get("speaker_id"))
        for lid in line_ids
        if lid in inputs.vo_lines and inputs.vo_lines[lid].get("speaker_id")
    }
    voice_speaker = cold.get("vo_voice_speaker_id") or candidate.get("vo_voice_speaker_id")
    if voice_speaker:
        speakers.add(str(voice_speaker))

    for sid in sorted(speakers):
        if inputs.pickup_speaker_id and sid != inputs.pickup_speaker_id:
            problems.append(
                f"VO attributed to {sid}, which is not the pickup-eligible speaker "
                f"({inputs.pickup_speaker_id})"
            )
        elif not inputs.pickup_speaker_id:
            problems.append(f"VO attributed to {sid} but no pickup-eligible speaker is confirmed")

    if cold_kind in VO_COLD_OPEN_KINDS and not inputs.clone_authorized:
        problems.append(
            f"cold open kind {cold_kind} requires clone consent with cold_open scope"
        )

    return _check("pickup_voice_authorized", not problems, "; ".join(problems))


def _check_sfx(
    candidate: dict[str, Any], cold: dict[str, Any], inputs: FeasibilityInputs
) -> dict[str, Any]:
    refs = [str(x) for x in (candidate.get("sfx_cue_refs") or [])]
    cold_sfx = cold.get("sfx") if isinstance(cold.get("sfx"), dict) else {}
    if cold_sfx.get("enabled") and cold_sfx.get("cue_ref"):
        refs.append(str(cold_sfx["cue_ref"]))
    missing = [r for r in dict.fromkeys(refs) if r not in inputs.sfx_cues]
    return _check(
        "sfx_cue_exists",
        not missing,
        f"unknown SFX cue refs: {', '.join(missing)}" if missing else "",
        missing or None,
    )


def _check_volleys(ordered: list[str], inputs: FeasibilityInputs) -> dict[str, Any]:
    """A locked speaker volley must survive whole or be excluded whole."""
    included = set(ordered)
    split: list[str] = []
    for volley in inputs.locked_volleys:
        present = [s for s in volley if s in included]
        if present and len(present) != len(volley):
            split.append(",".join(volley))
            continue
        if len(present) > 1:
            positions = [ordered.index(s) for s in volley]
            if positions != sorted(positions) or positions[-1] - positions[0] != len(volley) - 1:
                split.append(",".join(volley))
    return _check(
        "speaker_volley_integrity",
        not split,
        f"locked speaker volleys broken: {'; '.join(split)}" if split else "",
    )


def _check_duration(
    candidate: dict[str, Any],
    ordered: list[str],
    inputs: FeasibilityInputs,
    slack: float,
) -> dict[str, Any]:
    target = candidate.get("target_duration_ms") or inputs.target_duration_ms
    if not target:
        return _check("duration_fits", True, "no target duration band declared")
    total = 0
    for sid in ordered:
        seg = inputs.segments.get(sid) or {}
        start, end = seg.get("start_ms"), seg.get("end_ms")
        if start is None or end is None:
            continue
        total += max(0, int(end) - int(start))
    low = int(float(target) * (1 - slack))
    high = int(float(target) * (1 + slack))
    ok = low <= total <= high
    return _check(
        "duration_fits",
        ok,
        "" if ok else f"included duration {total}ms outside target band {low}–{high}ms",
    )


def _check_collisions(candidate: dict[str, Any]) -> dict[str, Any]:
    """Two elements may not claim the same output timeline slot."""
    placements = candidate.get("timeline") or []
    spans: list[tuple[int, int, str]] = []
    for item in placements:
        if not isinstance(item, dict):
            continue
        start, end = item.get("start_ms"), item.get("end_ms")
        if start is None or end is None:
            continue
        spans.append((int(start), int(end), str(item.get("ref") or "element")))
    spans.sort()
    collisions = [
        f"{spans[i][2]} overlaps {spans[i + 1][2]}"
        for i in range(len(spans) - 1)
        if spans[i][1] > spans[i + 1][0]
    ]
    return _check("timeline_collision", not collisions, "; ".join(collisions))


def _check_edl_representable(
    candidate: dict[str, Any], ordered: list[str], cold_kind: str
) -> dict[str, Any]:
    if not ordered and cold_kind == "none":
        return _check("edl_representable", False, "candidate has no body segments and no cold open")
    if not ordered:
        return _check("edl_representable", False, "candidate has a cold open but no body")
    return _check("edl_representable", True)


def _warn_checks(
    candidate: dict[str, Any], ordered: list[str], cold: dict[str, Any], cold_kind: str
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for sid in ordered:
        if sid in seen:
            repeated.add(sid)
        seen.add(sid)
    dupes = sorted(repeated)
    hook_id = str(cold.get("segment_id") or "")
    if (
        cold_kind in SEGMENT_COLD_OPEN_KINDS
        and hook_id
        and hook_id in ordered
        and not cold.get("reprise_later")
    ):
        dupes = sorted(set(dupes) | {hook_id})
    checks = [
        _check(
            "duplicate_segment",
            not dupes,
            f"segments reused without reprise_later: {', '.join(dupes)}" if dupes else "",
            dupes or None,
        )
    ]

    thin = not (candidate.get("evidence_refs") or cold.get("evidence_refs"))
    checks.append(_check("thin_evidence", not thin, "candidate cites no evidence refs" if thin else ""))
    return checks


def build_feasibility_report(
    candidates: list[dict[str, Any]],
    inputs: FeasibilityInputs,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results = [check_candidate(c, inputs, cfg=cfg) for c in candidates]
    eligible = [r["candidate_id"] for r in results if r["verdict"] != "fail"]
    return {
        "version": 1,
        "mode": gate_mode("feasibility", cfg),
        "candidates": results,
        "eligible_candidate_ids": eligible,
        "no_eligible_candidates": not eligible,
        "fallback_applied": None,
        "generated_at": _now(),
    }


def eligible_candidates(
    report: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Filter candidates to the feasibility allow-list (advisory mode passes all through)."""
    if report.get("mode") != "authoritative":
        return list(candidates)
    allowed = set(report.get("eligible_candidate_ids") or [])
    return [c for c in candidates if str(c.get("candidate_id")) in allowed]


def write_feasibility_report(ctx: RunContext, report: dict[str, Any]) -> None:
    ctx.write_json(FEASIBILITY_ARTIFACT, report)
