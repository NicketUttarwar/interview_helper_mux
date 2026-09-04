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
    from interview_mux.air_script import gap_line_air_eligible

    # Waived / omitted lines never require synthesis — even if stale seats linger.
    if not gap_line_air_eligible(line):
        return False
    if lid in seated:
        return True
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


def ensure_hosted_framing_vo_seats(ctx: RunContext) -> list[str]:
    """Reseat omitted synthesize layup lines until the G-Framing VO floor is met.

    Air-script Pass B can omit every layup seat while orientation alone remains.
    Hosted framing still requires ``min_synthetic_vo_lines`` active gap lines —
    without a reseat, nugget_layup_compose thrash-fails the incompleteness floor.
    """
    from interview_mux.gap_fill_eligibility import (
        hosted_framing_requires_synthetic_vo,
        min_synthetic_vo_lines,
    )
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID, is_episode_orientation

    if not hosted_framing_requires_synthetic_vo(ctx):
        return []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return []
    need = min_synthetic_vo_lines(ctx)
    lines_in = [dict(r) for r in (gap.get("interviewer_lines") or []) if isinstance(r, dict)]
    changed_ids: list[str] = []

    def _active_count(rows: list[dict[str, Any]]) -> int:
        n = 0
        for ln in rows:
            if ln.get("skipped_optional"):
                continue
            delivery = str(ln.get("delivery") or "synthesize").strip().lower() or "synthesize"
            if delivery in {"synthesize", "record", "voice_clone", "chatterbox"}:
                n += 1
        return n

    for i, row in enumerate(lines_in):
        if not is_episode_orientation(row):
            continue
        try:
            from interview_mux.air_script import _orientation_line_waived

            if _orientation_line_waived(row, gap):
                continue
        except Exception:
            pass
        cleared = ensure_gap_line_on_air(row)
        if cleared.get("skipped_optional") or cleared.get("air_script_omit"):
            continue
        if row.get("skipped_optional") or row.get("air_script_omit"):
            changed_ids.append(str(cleared.get("line_id") or ""))
        lines_in[i] = cleared

    def _has_pickup_wav(row: dict[str, Any]) -> bool:
        return _gap_row_has_pickup_stem(ctx, row)

    while _active_count(lines_in) < need:
        picked = None
        best_rank = 99
        for i, row in enumerate(lines_in):
            if not (row.get("skipped_optional") or row.get("air_script_omit")):
                continue
            if str(row.get("delivery") or "").lower() != "synthesize":
                continue
            if is_episode_orientation(row):
                continue
            lid = str(row.get("line_id") or "").strip()
            if not lid or not str(row.get("text") or "").strip():
                continue
            sev = str(row.get("severity") or "medium").lower()
            # Prefer already-rendered pickups so reseat does not thrash G1 on
            # high-severity omitted lines that still need Chatterbox.
            wav_bonus = 0 if _has_pickup_wav(row) else 2
            rank = (0 if sev in {"high", "critical", "blocking"} else 1) + wav_bonus
            if rank < best_rank:
                best_rank = rank
                picked = i
        if picked is None:
            break
        lines_in[picked] = ensure_gap_line_on_air(lines_in[picked])
        changed_ids.append(str(lines_in[picked].get("line_id") or ""))

    changed_ids = [x for x in dict.fromkeys(changed_ids) if x]
    # Floor already met and nothing cleared — do not rewrite seats/beats (thrash).
    if not changed_ids:
        return []

    out = dict(gap)
    out["interviewer_lines"] = lines_in
    gap_dest = ctx.write_json("understanding/gap_report.json", out)

    if ctx.artifact_exists("mastering/mastering_plan.json"):
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = dict(load_plan_raw(ctx) or {})
        script = dict(plan.get("air_script") or {})
        seats = dict(script.get("vo_seats") or {})
        seated = {
            str(r.get("line_id") or "")
            for r in lines_in
            if not r.get("skipped_optional") and r.get("line_id")
        }
        omitted = {
            str(r.get("line_id") or "")
            for r in lines_in
            if (r.get("skipped_optional") or r.get("air_script_omit")) and r.get("line_id")
        }
        beats = [dict(b) for b in (script.get("beats") or []) if isinstance(b, dict)]
        beat_lids = {str(b.get("line_id") or "") for b in beats if b.get("line_id")}
        by_id = {str(r.get("line_id") or ""): r for r in lines_in if r.get("line_id")}
        for lid in seated:
            if lid in beat_lids:
                continue
            row = by_id.get(lid) or {}
            beats.append(
                {
                    "segment_id": str(row.get("targets_segment_id") or "").strip(),
                    "line_id": lid,
                    "montage_move": "vo_then_clip",
                    "role": "hosted_framing_reseat",
                }
            )
            beat_lids.add(lid)
        orient = next(
            (lid for lid in seated if is_episode_orientation(by_id.get(lid) or {})),
            None,
        )
        seats["seated_line_ids"] = sorted(seated)
        seats["omitted_line_ids"] = sorted(omitted - seated)
        seats["orientation_id"] = orient or (
            seats.get("orientation_id") if seats.get("orientation_id") in seated else None
        )
        if seats["orientation_id"] is None and orient is None and ORIENTATION_LINE_ID in seated:
            seats["orientation_id"] = ORIENTATION_LINE_ID
        script["vo_seats"] = seats
        script["beats"] = beats
        plan["air_script"] = script
        plan_dest = ctx.write_json("mastering/mastering_plan.json", plan)
    else:
        plan_dest = None
    # Keep incomplete-stage pending shadows from re-omitting a newer floor reseat.
    try:
        import shutil

        pending_root = ctx.run_dir / ".pending_writes"
        if pending_root.is_dir():
            for stage_dir in pending_root.iterdir():
                if not stage_dir.is_dir():
                    continue
                for rel, src in (
                    (("understanding", "gap_report.json"), gap_dest),
                    (("mastering", "mastering_plan.json"), plan_dest),
                ):
                    if src is None:
                        continue
                    candidate = stage_dir.joinpath(*rel)
                    if candidate.is_file():
                        shutil.copy2(src, candidate)
    except Exception:
        pass
    return changed_ids


def _gap_row_has_pickup_stem(ctx: RunContext, row: dict[str, Any]) -> bool:
    """True when a vo_pickup stem exists for this line (audit match not required)."""
    lid = str(row.get("line_id") or "").strip()
    seg = str(row.get("targets_segment_id") or "").strip()
    if not lid and not seg:
        return False
    pickup = ctx.final_path("vo_pickup")
    for base in (
        pickup / "matched",
        pickup / "synthesized",
        pickup / "clean",
        pickup / "normalized",
        pickup,
    ):
        if not base.is_dir():
            continue
        for key in (lid, seg):
            if key and (base / f"{key}.wav").is_file():
                return True
    return False


def clamp_hosted_seats_to_rendered_wavs(ctx: RunContext) -> list[str]:
    """When a rendered WAV floor already exists, omit seated lines without pickup.

    Heals and air-script passes can revive high-severity omitted lines into seats.
    Once enough pickup stems exist to meet ``min_synthetic_vo_lines``, prefer those
    and unseat the rest so G1/EDL do not demand fresh Chatterbox mid-delivery.
    """
    from interview_mux.gap_fill_eligibility import (
        hosted_framing_requires_synthetic_vo,
        min_synthetic_vo_lines,
    )
    from interview_mux.opening_orientation import is_episode_orientation

    if not hosted_framing_requires_synthetic_vo(ctx):
        return []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return []
    need = min_synthetic_vo_lines(ctx)
    rows = [dict(r) for r in (gap.get("interviewer_lines") or []) if isinstance(r, dict)]
    with_wav: list[dict[str, Any]] = []
    without_wav: list[dict[str, Any]] = []
    for row in rows:
        if row.get("skipped_optional") or row.get("air_script_omit"):
            continue
        if is_episode_orientation(row):
            continue
        delivery = str(row.get("delivery") or "synthesize").strip().lower() or "synthesize"
        if delivery not in {"synthesize", "record", "voice_clone", "chatterbox"}:
            continue
        if _gap_row_has_pickup_stem(ctx, row):
            with_wav.append(row)
        else:
            without_wav.append(row)
    if len(with_wav) < need or not without_wav:
        return []
    unseated: list[str] = []
    by_id = {str(r.get("line_id") or ""): i for i, r in enumerate(rows) if r.get("line_id")}
    for row in without_wav:
        lid = str(row.get("line_id") or "").strip()
        if not lid:
            continue
        idx = by_id.get(lid)
        if idx is None:
            continue
        rows[idx] = mark_gap_line_not_on_air(row, reason_code="rendered_floor_prefer_wav")
        unseated.append(lid)
    if not unseated:
        return []
    out = dict(gap)
    out["interviewer_lines"] = rows
    ctx.write_json("understanding/gap_report.json", out)
    try:
        from interview_mux.execution_contract import reconcile_execution_contract

        reconcile_execution_contract(ctx, reason="clamp_hosted_seats_to_rendered_wavs")
    except Exception:
        pass
    # Mirror into pending shadows so stale incomplete stages cannot re-expand seats.
    try:
        import shutil

        gap_dest = ctx.path("understanding/gap_report.json")
        plan_dest = (
            ctx.path("mastering/mastering_plan.json")
            if ctx.artifact_exists("mastering/mastering_plan.json")
            else None
        )
        pending_root = ctx.run_dir / ".pending_writes"
        if pending_root.is_dir():
            for stage_dir in pending_root.iterdir():
                if not stage_dir.is_dir():
                    continue
                for rel, src in (
                    (("understanding", "gap_report.json"), gap_dest),
                    (("mastering", "mastering_plan.json"), plan_dest),
                ):
                    if src is None or not src.is_file():
                        continue
                    candidate = stage_dir.joinpath(*rel)
                    if candidate.is_file():
                        shutil.copy2(src, candidate)
    except Exception:
        pass
    return unseated


def sync_vo_contract_after_layup(ctx: RunContext) -> list[str]:
    """R10c: align gap_report, vo_seats, and omit ledger after layup/seams.

    Missing WAVs are expected here — ``vo_synthesize`` renders them. Post-layup
    only fails closed on seat/omit flag drift. When a rendered floor already
    exists, clamp away non-WAV seats so delivery heals cannot expand G1.
    """
    from interview_mux.air_script import persist_air_script_omits_on_gap_report

    persist_air_script_omits_on_gap_report(ctx)
    reseated = ensure_hosted_framing_vo_seats(ctx)
    if reseated:
        ctx.log(
            f"hosted framing reseated {len(reseated)} VO line(s) to meet floor: "
            f"{reseated[:6]}",
            level="info",
            stage="nugget_layup_compose",
        )
    clamped = clamp_hosted_seats_to_rendered_wavs(ctx)
    if clamped:
        ctx.log(
            f"hosted framing clamped {len(clamped)} non-WAV seat(s) after rendered floor: "
            f"{clamped[:6]}",
            level="info",
            stage="nugget_layup_compose",
        )
    violations = validate_vo_contract(ctx)
    if violations:
        # Omit/skip on gap wins over stale seats — unseat, do not force-synth.
        repair_vo_contract_drift(ctx)
        # Floor may reseat *new* lines; already-omitted stay omitted after repair.
        ensure_hosted_framing_vo_seats(ctx)
        clamp_hosted_seats_to_rendered_wavs(ctx)
        violations = validate_vo_contract(ctx)
    return [
        v
        for v in violations
        if "missing WAV" not in v and "missing wav" not in v.lower()
    ]


def repair_vo_contract_drift(ctx: RunContext) -> list[str]:
    """Align seats with gap omit/skip — omit wins; never force-synth omitted lines.

    When gap_report already marks a line skipped/omitted, that is the later decision:
    keep the omit flags and unseat any stale ``vo_seats`` entry. Do not clear omit
    just because seats still list the line.
    """
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    from interview_mux.air_script import gap_line_air_eligible
    from interview_mux.execution_contract import reconcile_execution_contract
    from interview_mux.opening_orientation import is_episode_orientation

    gap = ctx.read_json("understanding/gap_report.json")
    seated, omitted = _load_seated_omitted(ctx)
    changed: list[str] = []
    lines: list[dict[str, Any]] = []
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if not gap_line_air_eligible(row):
            # Preserve omit; unseat via reconcile below when seats still list it.
            kept = dict(row)
            if not (kept.get("skipped_optional") and kept.get("air_script_omit")):
                kept = mark_gap_line_not_on_air(
                    kept, reason_code=str(kept.get("skip_reason_code") or "air_script_omit_sync")
                )
            lines.append(kept)
            if lid and lid in seated:
                changed.append(lid)
            continue
        if lid in omitted and lid not in seated:
            lines.append(
                mark_gap_line_not_on_air(row, reason_code="air_script_omit_sync")
            )
            changed.append(lid)
            continue
        if lid in seated and str(row.get("delivery") or "").lower() == "synthesize":
            # On-air seat with no omit flags — leave as-is.
            lines.append(dict(row))
        elif is_episode_orientation(row) and lid in seated:
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
    if changed or lines:
        out = dict(gap)
        out["interviewer_lines"] = lines
        ctx.write_json("understanding/gap_report.json", out)
    # Rebuild vo_seats from gap so omitted lines are not synthesized downstream.
    try:
        reconcile_execution_contract(ctx, reason="repair_vo_contract_drift_omit_wins")
    except Exception:
        pass
    return list(dict.fromkeys(x for x in changed if x))
