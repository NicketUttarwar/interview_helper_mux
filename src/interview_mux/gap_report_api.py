"""Gap report line CRUD with pickup voice enforcement."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.run_context import RunContext
from interview_mux.source_topology import pickup_eligible_speaker_id


def _load_report(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("understanding/gap_report.json"):
        return ctx.read_json("understanding/gap_report.json")
    return {"interviewer_lines": []}


def list_lines(ctx: RunContext) -> list[dict[str, Any]]:
    report = _load_report(ctx)
    return list(report.get("interviewer_lines") or [])


def _next_line_id(lines: list[dict[str, Any]]) -> str:
    ids = [str(ln.get("line_id") or "") for ln in lines if isinstance(ln, dict)]
    n = 1
    while f"line_{n:03d}" in ids:
        n += 1
    return f"line_{n:03d}"


def _operator_unlock_if_frozen(ctx: RunContext, *, reason: str) -> bool:
    """B12: gap CRUD after soft freeze is an explicit operator unlock path."""
    try:
        from interview_mux.seat_authority import (
            operator_seat_unlock_note,
            soft_freeze_active,
        )

        if soft_freeze_active(ctx):
            # Operator unlock note — mutation proceeds; caller re-stamps after write.
            operator_seat_unlock_note(ctx, reason=reason)
            return True
    except Exception:
        pass
    return False


def _operator_restamp_after_mutation(
    ctx: RunContext, *, reason: str, was_frozen: bool
) -> None:
    if not was_frozen:
        return
    try:
        from interview_mux.seat_authority import stamp_soft_seat_freeze
        from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

        clamp_hosted_seats_to_rendered_wavs(ctx)
        stamp_soft_seat_freeze(ctx, reason=f"post_{reason}")
    except Exception:
        pass


def add_line(ctx: RunContext, body: dict[str, Any]) -> dict[str, Any]:
    was_frozen = _operator_unlock_if_frozen(ctx, reason="gap_report_api_add")
    report = _load_report(ctx)
    lines = list(report.get("interviewer_lines") or [])
    eligible = pickup_eligible_speaker_id(ctx)
    line: dict[str, Any] = {
        "line_id": body.get("line_id") or _next_line_id(lines),
        "gap_type": str(body.get("gap_type") or "reaction_line"),
        "text": str(body.get("text") or "").strip(),
        "targets_segment_id": str(body.get("targets_segment_id") or "seg_001"),
        "placement": body.get("placement") or "before",
        "delivery": "record",
        "voice_speaker_id": eligible or body.get("voice_speaker_id"),
        # Operator-authored lines are pinned — refinement_accept.py keeps them
        # across gap_framing_recompose as long as their target survives selection.
        "origin": "operator",
    }
    if body.get("act_context") is not None:
        line["act_context"] = int(body["act_context"])
    if body.get("post_preview"):
        line["post_preview"] = True
    if eligible and line.get("voice_speaker_id") != eligible:
        raise ValueError(f"voice_speaker_id must match gap pickup speaker ({eligible})")
    lines.append(line)
    report["interviewer_lines"] = lines
    write_validated_artifact(
        ctx, "understanding/gap_report.json", report, merge_from_disk=False, stage_key="optimal_questions"
    )
    _operator_restamp_after_mutation(ctx, reason="gap_report_api_add", was_frozen=was_frozen)
    return line


def update_line(ctx: RunContext, line_id: str, body: dict[str, Any]) -> dict[str, Any]:
    was_frozen = _operator_unlock_if_frozen(ctx, reason="gap_report_api_update")
    report = _load_report(ctx)
    lines = list(report.get("interviewer_lines") or [])
    eligible = pickup_eligible_speaker_id(ctx)
    for i, ln in enumerate(lines):
        if not isinstance(ln, dict) or str(ln.get("line_id")) != line_id:
            continue
        updated = dict(ln)
        for key in ("text", "gap_type", "targets_segment_id", "placement", "act_context"):
            if key in body and body[key] is not None:
                updated[key] = body[key]
        if body.get("post_preview") is not None:
            updated["post_preview"] = bool(body["post_preview"])
        if updated.get("delivery") == "record" and eligible:
            updated["voice_speaker_id"] = eligible
        # A GUI text edit pins the line so it survives gap_framing_recompose.
        if "text" in body and body["text"] is not None:
            updated["origin"] = "operator"
        lines[i] = updated
        report["interviewer_lines"] = lines
        write_validated_artifact(
            ctx, "understanding/gap_report.json", report, merge_from_disk=False, stage_key="optimal_questions"
        )
        _operator_restamp_after_mutation(
            ctx, reason="gap_report_api_update", was_frozen=was_frozen
        )
        return updated
    raise KeyError(line_id)


def delete_line(ctx: RunContext, line_id: str) -> None:
    was_frozen = _operator_unlock_if_frozen(ctx, reason="gap_report_api_delete")
    report = _load_report(ctx)
    lines = [ln for ln in (report.get("interviewer_lines") or []) if str(ln.get("line_id")) != line_id]
    report["interviewer_lines"] = lines
    write_validated_artifact(
        ctx, "understanding/gap_report.json", report, merge_from_disk=False, stage_key="optimal_questions"
    )
    _operator_restamp_after_mutation(
        ctx, reason="gap_report_api_delete", was_frozen=was_frozen
    )
