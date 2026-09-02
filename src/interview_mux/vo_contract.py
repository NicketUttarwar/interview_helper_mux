"""VO air contract — seated/synthesize/omit alignment (execution-flow hardening R2/R10)."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _load_seated_omitted(ctx: RunContext) -> tuple[set[str], set[str]]:
    from interview_mux.air_script import omitted_vo_line_ids, seated_vo_line_ids
    from interview_mux.mastering_plan_loader import load_plan_raw

    plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
    return seated_vo_line_ids(plan), omitted_vo_line_ids(plan)


def mark_gap_line_not_on_air(
    line: dict[str, Any],
    *,
    reason_code: str,
    compensating_path: str | None = None,
) -> dict[str, Any]:
    """Atomically mark a gap line as not on air (skip + omit flags)."""
    row = dict(line)
    row["skipped_optional"] = True
    row["air_script_omit"] = True
    row["blocking"] = False
    row["skip_reason_code"] = str(reason_code or "not_on_air")
    if compensating_path:
        row["compensating_path"] = compensating_path
    notes = list(row.get("omit_notes") or [])
    note = f"vo_contract:{reason_code}"
    if note not in notes:
        notes.append(note)
    row["omit_notes"] = notes
    return row


def ensure_gap_line_on_air(line: dict[str, Any]) -> dict[str, Any]:
    """Clear skip/omit flags so a seated synthesize line stays on air."""
    row = dict(line)
    row.pop("skipped_optional", None)
    row.pop("air_script_omit", None)
    row.pop("skip", None)
    row.pop("skip_reason_code", None)
    row["blocking"] = bool(row.get("required"))
    return row


def gap_line_requires_synthesis(
    line: dict[str, Any],
    seated: set[str],
) -> bool:
    """True when a gap line must have a synthesize WAV (synth_always policy)."""
    if not isinstance(line, dict):
        return False
    if str(line.get("delivery") or "").lower() != "synthesize":
        return False
    lid = str(line.get("line_id") or "").strip()
    if not lid:
        return False
    if lid in seated:
        return True
    from interview_mux.air_script import gap_line_air_eligible

    if not gap_line_air_eligible(line):
        return False
    from interview_mux.opening_orientation import is_episode_orientation

    return is_episode_orientation(line) or bool(line.get("required"))


def seated_vo_missing_ids(ctx: RunContext) -> list[str]:
    """Seated synthesize line_ids with no matching WAV on disk."""
    from interview_mux.vo_synthesis_audit import synthesis_entry_matches_line
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    seated, _omitted = _load_seated_omitted(ctx)
    missing: list[str] = []
    for line in gap.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if not gap_line_requires_synthesis(line, seated):
            continue
        lid = str(line.get("line_id") or "")
        path = resolve_vo_pickup_path(ctx, line)
        matches, _reason = synthesis_entry_matches_line(ctx, line)
        if path is None or not path.is_file() or not matches:
            missing.append(lid)
    return [x for x in missing if x]


def assert_seated_vo_rendered(ctx: RunContext) -> None:
    """Fail closed when seated synthesize lines lack WAV."""
    missing = seated_vo_missing_ids(ctx)
    if missing:
        raise RuntimeError(
            "vo_synthesize: seated synthesize VO not rendered: "
            + ", ".join(missing[:8])
        )


def validate_vo_contract(ctx: RunContext) -> list[str]:
    """Return human-readable contract violations (empty = pass)."""
    issues: list[str] = []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return issues
    gap = ctx.read_json("understanding/gap_report.json")
    seated, omitted = _load_seated_omitted(ctx)
    by_line: dict[str, dict] = {}
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if lid:
            by_line[lid] = row
    for lid in sorted(seated):
        row = by_line.get(lid)
        if row is None:
            issues.append(f"seated line {lid} missing from gap_report")
            continue
        if str(row.get("delivery") or "").lower() != "synthesize":
            continue
        if row.get("skipped_optional") or row.get("air_script_omit"):
            issues.append(f"seated synthesize {lid} has skip/omit flags")
    for lid in sorted(omitted):
        row = by_line.get(lid)
        if row is None:
            continue
        if lid in seated:
            issues.append(f"line {lid} is both seated and omitted")
        elif not (row.get("skipped_optional") or row.get("air_script_omit")):
            issues.append(f"omitted {lid} lacks skip/omit flags in gap_report")
    missing = seated_vo_missing_ids(ctx)
    for lid in missing:
        issues.append(f"seated synthesize {lid} missing WAV")
    return issues


def sync_vo_contract_after_layup(ctx: RunContext) -> list[str]:
    """R10c: align gap_report, vo_seats, and omit ledger after layup/seams."""
    from interview_mux.air_script import persist_air_script_omits_on_gap_report

    persist_air_script_omits_on_gap_report(ctx)
    violations = validate_vo_contract(ctx)
    if violations:
        repair_vo_contract_drift(ctx)
        violations = validate_vo_contract(ctx)
    return violations


def repair_vo_contract_drift(ctx: RunContext) -> list[str]:
    """Clear skip flags on seated synthesize lines; stamp omits for unseated skipped."""
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    seated, omitted = _load_seated_omitted(ctx)
    changed: list[str] = []
    lines: list[dict[str, Any]] = []
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if lid in seated and str(row.get("delivery") or "").lower() == "synthesize":
            if row.get("skipped_optional") or row.get("air_script_omit"):
                lines.append(ensure_gap_line_on_air(row))
                changed.append(lid)
            else:
                lines.append(dict(row))
        elif lid in omitted or lid not in seated:
            if not row.get("skipped_optional"):
                lines.append(
                    mark_gap_line_not_on_air(row, reason_code="air_script_omit_sync")
                )
                changed.append(lid)
            else:
                lines.append(dict(row))
        else:
            lines.append(dict(row))
    if changed:
        out = dict(gap)
        out["interviewer_lines"] = lines
        ctx.write_json("understanding/gap_report.json", out)
    return changed
