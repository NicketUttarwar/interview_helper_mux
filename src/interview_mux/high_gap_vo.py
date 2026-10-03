"""Secondary succinct VO generator for uncovered high-severity gaps."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

from interview_mux.run_context import RunContext

PROMPT_REL = "interviewer-gap/high-gap-vo-fill.system.txt"

_CHILD_SUFFIX_RE = re.compile(r"^(seg_\d+)([a-z]+)$", re.IGNORECASE)
_SEG_IN_TEXT_RE = re.compile(r"(seg_\d+[a-z]*)", re.IGNORECASE)

HighGapIntent = Literal["compose_persist", "repair", "heal_floor_protect", "playbook"]
_HIGH_GAP_INTENTS = frozenset(
    {"compose_persist", "repair", "heal_floor_protect", "playbook"}
)


@dataclass(frozen=True)
class HighGapSeat:
    """One authoritative high-gap coverage decision."""

    segment_id: str
    on_air: bool
    selected: bool
    action: Literal["covered", "demoted", "floor_protected"]
    reason: str


@dataclass(frozen=True)
class HighGapSeatLedger:
    """Result of resolving every currently-high gap exactly once."""

    intent: HighGapIntent
    seats: tuple[HighGapSeat, ...]
    demoted: int = 0
    floor_protected: int = 0
    floor_unmet: bool = False


def parent_id_of_segment(sid: str) -> str | None:
    m = _CHILD_SUFFIX_RE.match(str(sid or "").strip())
    return m.group(1) if m else None


def expand_targeted_with_parents(
    targeted: set[str],
    ctx: RunContext | None = None,
) -> set[str]:
    """Treat a child target as covering its parent (and vice versa)."""
    out = {str(s) for s in targeted if s}
    for sid in list(out):
        parent = parent_id_of_segment(sid)
        if parent:
            out.add(parent)
    if ctx is None or not ctx.artifact_exists("segments/manifest.json"):
        return out
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return out
    for row in (man or {}).get("segments") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        parent = str(row.get("parent_segment_id") or "") or (parent_id_of_segment(sid) or "")
        if not sid or not parent:
            continue
        if sid in out:
            out.add(parent)
        if parent in out:
            out.add(sid)
    return out


def targeted_segment_ids(
    lines: list[Any] | None,
    ctx: RunContext | None = None,
) -> set[str]:
    """Segment ids already covered by interviewer lines (targets, seeds, supports)."""
    targeted: set[str] = set()
    for ln in lines or []:
        if not isinstance(ln, dict):
            continue
        # Coverage means audible copy, not a stale target/reference.  Omitted,
        # optional-skipped, and blank rows own no high-gap seat.
        if (
            ln.get("skipped_optional")
            or ln.get("air_script_omit")
            or not str(ln.get("text") or "").strip()
        ):
            continue
        for key in ("targets_segment_id", "segment_id"):
            sid = str(ln.get(key) or "")
            if sid:
                targeted.add(sid)
        lid = str(ln.get("line_id") or "")
        if lid.startswith("vo_seed_") and len(lid) > len("vo_seed_"):
            targeted.add(lid[len("vo_seed_") :])
        if lid.startswith("vo_fill_") and len(lid) > len("vo_fill_"):
            targeted.add(lid[len("vo_fill_") :])
        for hit in _SEG_IN_TEXT_RE.findall(lid):
            targeted.add(hit)
        for sid in ln.get("supports_segment_ids") or []:
            if sid:
                targeted.add(str(sid))
        extracted = ln.get("extracted_from")
        if isinstance(extracted, dict):
            path = str(extracted.get("path") or "")
            if path.startswith("repair_seed:"):
                targeted.add(path.split(":", 1)[1].strip())
    return expand_targeted_with_parents(targeted, ctx)


def _selected_segment_ids(ctx: RunContext) -> set[str] | None:
    if not ctx.artifact_exists("master/selection.json"):
        return None
    try:
        selection = ctx.read_json("master/selection.json")
        if isinstance(selection, dict):
            ordered = {
                str(s) for s in (selection.get("ordered_segment_ids") or []) if s
            }
            return ordered or None
    except Exception:
        pass
    return None


def _hosted_floor_state(
    ctx: RunContext, report: dict[str, Any]
) -> tuple[bool, int, int]:
    try:
        from interview_mux.gap_fill_eligibility import (
            hosted_framing_requires_synthetic_vo,
            min_synthetic_vo_lines,
        )

        if not hosted_framing_requires_synthetic_vo(ctx):
            return False, 0, 0
        need = min_synthetic_vo_lines(ctx)
    except Exception:
        return False, 0, 0
    active = 0
    for row in report.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        if (
            row.get("skipped_optional")
            or row.get("air_script_omit")
            or not str(row.get("text") or "").strip()
        ):
            continue
        delivery = str(row.get("delivery") or "synthesize").strip().lower()
        if delivery in {"synthesize", "record", "voice_clone", "chatterbox", "mlx_audio"}:
            active += 1
    return active < need, need, active


def _fill_is_budgeted(ctx: RunContext) -> bool:
    """A fill is actionable only with credentials and remaining identity budget."""
    if not str(os.environ.get("OPENAI_API_KEY") or "").strip():
        return False
    try:
        from interview_mux.homunculus.budget import identity_exhausted

        return not identity_exhausted(ctx, "high_gap_vo_fill")
    except Exception:
        return False


def _stamp_or_top_up_floor(
    ctx: RunContext, *, report: dict[str, Any], need: int, active: int
) -> bool:
    """Try the layup seat path, then leave a sticky floor-unmet pin."""
    try:
        from interview_mux.vo_contract import ensure_hosted_framing_vo_seats

        ensure_hosted_framing_vo_seats(ctx)
    except Exception:
        pass
    # The resolver may be operating on a pre-persist repair document, so its
    # on-air count remains authoritative for deciding whether green is legal.
    under, need_after, active_after = _hosted_floor_state(ctx, report)
    if not under:
        return False
    try:
        from interview_mux.vo_contract import _record_hosted_floor_unmet

        _record_hosted_floor_unmet(
            ctx,
            need=need_after or need,
            active=active_after if need_after else active,
        )
    except Exception:
        pass
    return True


def resolve_seats(
    ctx: RunContext,
    *,
    intent: HighGapIntent,
    gap_report: dict[str, Any] | None = None,
) -> HighGapSeatLedger:
    """Resolve high-gap coverage/demotion from one intent-driven policy."""
    if intent not in _HIGH_GAP_INTENTS:
        raise ValueError(f"unknown high-gap seat intent: {intent}")
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return HighGapSeatLedger(intent=intent, seats=())
    try:
        evaluations = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return HighGapSeatLedger(intent=intent, seats=())
    if not isinstance(evaluations, dict):
        return HighGapSeatLedger(intent=intent, seats=())
    report = gap_report
    if report is None:
        try:
            loaded = ctx.read_json("understanding/gap_report.json")
            report = loaded if isinstance(loaded, dict) else {}
        except Exception:
            report = {}
    targeted = targeted_segment_ids(
        report.get("interviewer_lines")
        if isinstance(report.get("interviewer_lines"), list)
        else [],
        ctx,
    )
    selected_ids = _selected_segment_ids(ctx)
    floor_under, floor_need, floor_active = _hosted_floor_state(ctx, report)
    protect_floor = (
        intent == "heal_floor_protect" and floor_under and _fill_is_budgeted(ctx)
    )
    rows: list[dict[str, Any]] = []
    seats: list[HighGapSeat] = []
    demoted = 0
    protected = 0
    for original in evaluations.get("evaluations") or []:
        if not isinstance(original, dict):
            continue
        row = original
        sid = str(row.get("segment_id") or "")
        if not sid or str(row.get("severity") or "").lower() != "high":
            rows.append(row)
            continue
        selected = selected_ids is None or sid in selected_ids
        if sid in targeted:
            seats.append(HighGapSeat(sid, True, selected, "covered", "on_air"))
        elif protect_floor and selected:
            protected += 1
            seats.append(
                HighGapSeat(
                    sid,
                    False,
                    True,
                    "floor_protected",
                    "fill_budget_remaining",
                )
            )
        else:
            row = dict(row)
            row["severity"] = "medium"
            reason = f"high_gap_seat:{intent}" + (":off_air" if not selected else "")
            row["severity_demotion_reason"] = reason
            demoted += 1
            seats.append(HighGapSeat(sid, False, selected, "demoted", reason))
        rows.append(row)
    if demoted:
        out = dict(evaluations)
        out["evaluations"] = rows
        try:
            from interview_mux.artifact_writes import write_validated_artifact

            write_validated_artifact(
                ctx,
                "understanding/gap_evaluations.json",
                out,
                merge_from_disk=False,
                stage_key="missing_framing",
            )
        except Exception:
            ctx.write_json("understanding/gap_evaluations.json", out)
    floor_unmet = False
    if floor_under and not protect_floor:
        floor_unmet = _stamp_or_top_up_floor(
            ctx, report=report, need=floor_need, active=floor_active
        )
    return HighGapSeatLedger(
        intent=intent,
        seats=tuple(seats),
        demoted=demoted,
        floor_protected=protected,
        floor_unmet=floor_unmet,
    )


def _seg_text(ctx: RunContext, sid: str) -> str:
    if not sid or not ctx.artifact_exists("segments/manifest.json"):
        return ""
    try:
        man = ctx.read_json("segments/manifest.json")
        for row in (man or {}).get("segments") or []:
            if isinstance(row, dict) and str(row.get("segment_id") or "") == sid:
                return str(row.get("text") or "")[:400]
    except Exception:
        return ""
    return ""


def demote_uncovered_high_gaps(
    ctx: RunContext,
    *,
    gap_report: dict[str, Any] | None = None,
    origin: str = "uncovered_after_fill",
) -> int:
    """Compatibility shim; new production callers use typed ``resolve_seats``."""
    intent: HighGapIntent = (
        "heal_floor_protect"
        if origin in {"e2e_heal_lint_dirty", "post_commit_uncovered_high"}
        else "compose_persist"
    )
    return resolve_seats(
        ctx,
        intent=intent,
        gap_report=gap_report,
    ).demoted


def _deterministic_high_gap_line(ctx: RunContext, row: dict[str, Any]) -> str:
    """Structural seed when LLM fill is unavailable or empty (R1).

    Speakable courtesy copy only — never paste listener_confusion / mission
    into on-air text (those are QC prose and trip spoken_edit_structure_ref,
    e.g. "the clip cuts off…"). Mission stays in rationale at the call site.
    """
    from interview_mux.gap_framing import GAP_TYPE_TO_CATEGORY
    from interview_mux.gap_vo_prior_context import courtesy_seed_text
    from interview_mux.spoken_meta_lint import scrub_spoken_edit_structure

    sid = str(row.get("segment_id") or "").strip()
    gap_type = str(row.get("gap_type") or "missing_setup").strip() or "missing_setup"
    category = GAP_TYPE_TO_CATEGORY.get(gap_type, "story_bridge")
    text = courtesy_seed_text(None, category=category, target_segment_id=sid or None)
    text = scrub_spoken_edit_structure(text)
    words = text.split()
    if len(words) > 28:
        text = " ".join(words[:28]).rstrip(",;") + "?"
    return text


def seed_uncovered_high_gaps_deterministic(
    ctx: RunContext,
    out: dict[str, Any],
    *,
    applied: list[dict[str, Any]],
    origin: str = "high_gap_vo_seed",
    limit: int = 24,
) -> int:
    """Append required synthesize lines for every still-uncovered high gap."""
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return 0
    try:
        evals = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return 0
    lines = out.setdefault("interviewer_lines", [])
    if not isinstance(lines, list):
        lines = []
        out["interviewer_lines"] = lines
    targeted = targeted_segment_ids(lines, ctx)
    high = [
        r
        for r in (evals.get("evaluations") or [])
        if isinstance(r, dict)
        and str(r.get("severity") or "").lower() in {"high", "critical"}
        and str(r.get("segment_id") or "")
        and str(r.get("segment_id")) not in targeted
    ]
    added = 0
    for row in high[: max(1, int(limit))]:
        sid = str(row.get("segment_id") or "")
        if not sid or sid in targeted:
            continue
        text = _deterministic_high_gap_line(ctx, row)
        confusion = str(row.get("listener_confusion") or row.get("why") or "").strip()
        rationale = "Auto-seeded for high-severity gap missing an interviewer line."
        if confusion:
            rationale = f"{rationale} Mission: {confusion[:160]}"
        # An earlier pass may have left an inactive row under the same id (omitted,
        # skipped or blank). Appending beside it made dedupe_line_ids keep that
        # first, inactive row and drop the new seed, so the high gap stayed
        # uncovered on every attempt (exec_002 vo_seed_seg_021).
        seed_id = f"vo_seed_{sid}"
        lines[:] = [
            ln
            for ln in lines
            if not (isinstance(ln, dict) and str(ln.get("line_id") or "") == seed_id)
        ]
        lines.append(
            {
                "line_id": f"vo_seed_{sid}",
                "text": text,
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": sid,
                "gap_type": row.get("gap_type") or "missing_setup",
                "origin": origin,
                "required": True,
                "category": "story_bridge",
                "line_category": "story_bridge",
                "rationale": rationale,
            }
        )
        targeted.add(sid)
        added += 1
        applied.append(
            {"action": "high_gap_vo_seed", "segment_id": sid, "origin": origin}
        )
    return added


def fill_uncovered_high_gaps(
    ctx: RunContext,
    out: dict[str, Any],
    *,
    applied: list[dict[str, Any]],
    origin: str = "high_gap_vo_fill",
) -> int:
    """Append interviewer lines for high-severity evals with no targeting line.

    R1: LLM fill when possible; always fall back to deterministic seeds so
    framing Yes + uncovered highs never soft-green into pre-flush block.
    """
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return 0
    try:
        evals = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return 0
    lines = out.setdefault("interviewer_lines", [])
    if not isinstance(lines, list):
        lines = []
        out["interviewer_lines"] = lines
    targeted = targeted_segment_ids(lines, ctx)
    high = [
        r
        for r in (evals.get("evaluations") or [])
        if isinstance(r, dict)
        and str(r.get("severity") or "").lower() == "high"
        and str(r.get("segment_id") or "")
        and str(r.get("segment_id")) not in targeted
    ]
    if not high:
        return 0
    try:
        from interview_mux.homunculus.budget import (
            LimitExhausted,
            identity_exhausted,
            mark_identity_exhausted,
        )
        from interview_mux.stages.llm_runner import run_prompt_envelope
    except Exception:
        return seed_uncovered_high_gaps_deterministic(
            ctx, out, applied=applied, origin=f"{origin}_no_llm"
        )

    fill_identity = "high_gap_vo_fill"
    if identity_exhausted(ctx, fill_identity):
        applied.append({"action": "high_gap_vo_fill_skip", "reason": "limit_exhausted"})
        # Do not demote — seed instead so high_gap_unframed cannot greenwash.
        return seed_uncovered_high_gaps_deterministic(
            ctx, out, applied=applied, origin=f"{origin}_budget_seed"
        )

    if not str(os.environ.get("OPENAI_API_KEY") or "").strip():
        return seed_uncovered_high_gaps_deterministic(
            ctx, out, applied=applied, origin=f"{origin}_no_key"
        )
    added = 0
    llm_empties = 0
    for row in high[:12]:
        sid = str(row.get("segment_id") or "")
        if not sid or sid in targeted:
            continue
        payload = {
            "task": "Write one succinct interviewer line covering this high-severity gap.",
            "segment_id": sid,
            "gap_type": row.get("gap_type"),
            "severity": "high",
            "listener_confusion": str(row.get("listener_confusion") or "")[:240],
            "segment_excerpt": _seg_text(ctx, sid),
            "word_caps": {"question": 60, "setup": 20, "bridge": 50},
        }
        text = ""
        from_llm = False
        for tier in ("standard", "economy"):
            try:
                env = run_prompt_envelope(
                    "high_gap_vo_fill",
                    PROMPT_REL,
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    ctx=ctx,
                    include_preamble=False,
                    task_kind="advisory",
                    explicit_tier=tier,
                    response_format={"type": "json_object"},
                )
            except LimitExhausted:
                mark_identity_exhausted(ctx, fill_identity)
                applied.append(
                    {"action": "high_gap_vo_fill_skip", "reason": "limit_exhausted"}
                )
                added += seed_uncovered_high_gaps_deterministic(
                    ctx, out, applied=applied, origin=f"{origin}_budget_seed"
                )
                return added
            except Exception:
                continue
            arts = env.get("artifacts") if isinstance(env, dict) else None
            if isinstance(arts, dict):
                text = str(arts.get("text") or arts.get("line") or "").strip()
            if not text and isinstance(env, dict):
                text = str(env.get("text") or "").strip()
            if text:
                from_llm = True
                break
        if not text:
            llm_empties += 1
            applied.append({"action": "high_gap_vo_fill_empty", "segment_id": sid})
            text = _deterministic_high_gap_line(ctx, row)
            applied.append({"action": "high_gap_vo_seed_fallback", "segment_id": sid})
        lid = f"vo_fill_{sid}" if from_llm else f"vo_seed_{sid}"
        confusion = str(row.get("listener_confusion") or row.get("why") or "").strip()
        rationale = (
            "LLM fill for high-severity gap missing an interviewer line."
            if from_llm
            else "Auto-seeded for high-severity gap missing an interviewer line."
        )
        if confusion:
            rationale = f"{rationale} Mission: {confusion[:160]}"
        lines.append(
            {
                "line_id": lid,
                "text": text,
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": sid,
                "gap_type": row.get("gap_type") or "missing_setup",
                "origin": origin if from_llm else f"{origin}_seed",
                "required": True,
                "category": "story_bridge",
                "line_category": "story_bridge",
                "rationale": rationale,
            }
        )
        targeted.add(sid)
        added += 1
        applied.append(
            {
                "action": "high_gap_vo_fill" if from_llm else "high_gap_vo_seed",
                "segment_id": sid,
                "tier_origin": origin,
            }
        )
        # After two consecutive empty LLM answers, stop calling the model and seed rest.
        if llm_empties >= 2 and not from_llm:
            added += seed_uncovered_high_gaps_deterministic(
                ctx, out, applied=applied, origin=f"{origin}_abort_seed"
            )
            return added
        if from_llm:
            llm_empties = 0
    added += seed_uncovered_high_gaps_deterministic(
        ctx, out, applied=applied, origin=f"{origin}_remainder_seed"
    )
    return added
