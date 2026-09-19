"""Per-line VO adjudication — homunculus 0.1.0+ smart second pass before synth.

9C smart gate: skip adjudicate LLM only when ``line_vo_wav_fresh`` passes.
8B hash-idempotency: re-run LLM only for lines whose input hash changed.
1A full resynth: ``nuke_all_synth_wavs_on_adjudicate_change`` on gap_report mutation.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from interview_mux.config import merged_config
from interview_mux.nugget_layup import (
    PLAN_REL,
    _manifest_segments,
    _overlap,
    _tokens,
    evaluate_nugget_air_coverage,
    rank_open_nuggets_for_target,
    waived_nugget_ids_from_sources,
)
from interview_mux.operator_trace import log_step, logged_step
from interview_mux.run_context import RunContext
from interview_mux.spoken_copy_guard import script_hash
from interview_mux.vo_synthesis_audit import (
    line_vo_wav_fresh,
    nuke_all_synth_wavs_on_adjudicate_change,
    should_skip_adjudicate_for_line,
)

STAGE_ID = "vo_line_adjudicate"
ADJUDICATION_REL = "understanding/vo_line_adjudication.json"
ALLOCATION_REL = "understanding/nugget_allocation_plan.json"
GAP_REL = "understanding/gap_report.json"

__all__ = [
    "STAGE_ID",
    "ADJUDICATION_REL",
    "ALLOCATION_REL",
    "adjudicate_cfg",
    "adjudicate_before_synth_enabled",
    "score_layup_flow_fit",
    "line_adjudication_input_hash",
    "lines_needing_adjudicate",
    "lines_needing_adjudication",
    "run_adjudicate_batches",
    "apply_adjudicate_results",
    "run_intro_compose",
    "run_vo_line_adjudicate_stage",
    "persist_adjudication_skip_stub",
    "nugget_air_coverage",
    "persist_allocation_plan",
    "collect_waived_nugget_ids",
    "body_plan_from_gap_report",
    "synthesize_vo_comprehensibility_errors",
]


def adjudicate_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if isinstance(cfg, dict) else merged_config()
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    gap_vo = analysis.get("gap_vo") if isinstance(analysis.get("gap_vo"), dict) else {}
    nugget_layup = analysis.get("nugget_layup") if isinstance(analysis.get("nugget_layup"), dict) else {}
    return {
        "adjudicate_before_synth": bool(gap_vo.get("adjudicate_before_synth", True)),
        "adjudicate_batch_size": int(gap_vo.get("adjudicate_batch_size", 5)),
        "adjudicate_flow_threshold": float(gap_vo.get("adjudicate_flow_threshold", 0.55)),
        "adjudicate_fail_open": bool(gap_vo.get("adjudicate_fail_open", True)),
        "full_resynth_on_adjudicate_change": bool(
            gap_vo.get("full_resynth_on_adjudicate_change", True)
        ),
        "min_nugget_air_coverage": float(nugget_layup.get("min_nugget_air_coverage", 0.85)),
    }


def adjudicate_before_synth_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(adjudicate_cfg(cfg).get("adjudicate_before_synth", True))


def _target_text(ctx: RunContext, segment_id: str) -> str:
    for row in _manifest_segments(ctx):
        if str(row.get("segment_id") or "") == segment_id:
            return str(row.get("text") or "")
    return ""


def _comprehensible_excerpt(masks: dict[str, Any], segment_id: str) -> str:
    natives = masks.get("natives") if isinstance(masks, dict) else {}
    row = (natives or {}).get(segment_id) if isinstance(natives, dict) else None
    if isinstance(row, dict):
        return str(row.get("comprehensible_text") or "")
    return ""


def score_layup_flow_fit(
    line: dict[str, Any],
    target_native: str,
    masks: dict[str, Any],
    *,
    layup_row: dict[str, Any] | None = None,
    max_target_restate: float = 0.75,
) -> float:
    """Deterministic pre-score: bridge into target T without restating it."""
    text = str(line.get("text") or "")
    layup = layup_row if isinstance(layup_row, dict) else {}
    unlock = str(layup.get("forward_unlock") or line.get("forward_unlock") or "")
    combined = f"{text} {unlock}".strip()
    if not combined or not target_native:
        return 0.0

    target_excerpt = _comprehensible_excerpt(masks, str(line.get("targets_segment_id") or ""))
    target_tokens = _tokens(target_excerpt or target_native)
    line_tokens = _tokens(combined)
    bridge = _overlap(line_tokens, target_tokens)
    restate = _overlap(_tokens(text), target_tokens)
    restate_penalty = max(0.0, restate - max_target_restate) * 1.5 if restate > max_target_restate else 0.0
    unlock_bonus = 0.15 if unlock and len(_tokens(unlock)) >= 4 else 0.0
    return max(0.0, min(1.0, bridge - restate_penalty + unlock_bonus))


def line_adjudication_input_hash(
    line: dict[str, Any],
    layup_row: dict[str, Any] | None = None,
) -> str:
    """8B — canonical hash for idempotent adjudicate skip."""
    layup = layup_row if isinstance(layup_row, dict) else {}
    payload = {
        "line_id": line.get("line_id"),
        "text": line.get("text"),
        "targets_segment_id": line.get("targets_segment_id"),
        "placement": line.get("placement"),
        "nugget_ids": sorted(str(x) for x in (line.get("nugget_ids") or []) if x),
        "forward_unlock": layup.get("forward_unlock") or line.get("forward_unlock"),
        "target_beat": layup.get("target_beat"),
        "listener_need_entering_T": layup.get("listener_need_entering_T"),
        "selected_nugget_ids": sorted(
            str(x) for x in (layup.get("selected_nugget_ids") or layup.get("nugget_ids") or []) if x
        ),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_masks(ctx: RunContext) -> dict[str, Any]:
    rel = "understanding/native_comprehension_masks.json"
    if ctx.artifact_exists(rel):
        doc = ctx.read_json(rel)
        return doc if isinstance(doc, dict) else {}
    return {}


def _load_layup_plan(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists(PLAN_REL):
        doc = ctx.read_json(PLAN_REL)
        return doc if isinstance(doc, dict) else {}
    return {}


def _layup_row_for_line(plan: dict[str, Any], line_id: str) -> dict[str, Any] | None:
    lid = str(line_id or "").strip()
    if not lid:
        return None
    for row in (plan.get("layups") or []) if isinstance(plan, dict) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("line_id") or "") == lid:
            return row
        tid = str(row.get("target_segment_id") or "").strip()
        if tid and lid == f"vo_layup_{tid}":
            return row
    return None


def _prior_adjudication(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists(ADJUDICATION_REL):
        doc = ctx.read_json(ADJUDICATION_REL)
        return doc if isinstance(doc, dict) else {}
    return {}


def _body_synthesize_lines(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if line.get("skipped_optional"):
            continue
        if str(line.get("line_category") or "") == "episode_preface":
            continue
        if str(line.get("delivery") or "").lower() != "synthesize":
            continue
        out.append(line)
    return out


def _synthesize_vo_lines(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    """All seated synthesize VO lines (body + episode_preface intro)."""
    out: list[dict[str, Any]] = []
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if line.get("skipped_optional") or line.get("omit"):
            continue
        if str(line.get("delivery") or "").lower() != "synthesize":
            continue
        out.append(line)
    return out


def synthesize_vo_comprehensibility_errors(
    gap_report: dict[str, Any],
    *,
    min_words: int = 4,
) -> list[str]:
    """Hard-gate: seated synthesize VO must be non-empty, speakable, and reviewed copy.

    Coverage shortfall may still fail-open (``adjudicate_fail_open``). Incomprehensible
    or unreviewed VO text always fails — north-star: no silent thin/junk air.
    """
    from interview_mux.spoken_meta_lint import lint_spoken_text

    errors: list[str] = []
    floor = max(1, int(min_words or 4))
    for line in _synthesize_vo_lines(gap_report):
        lid = str(line.get("line_id") or "line").strip() or "line"
        text = str(line.get("text") or "").strip()
        if not text:
            errors.append(f"{lid}: empty synthesize VO text")
            continue
        words = [w for w in text.split() if w]
        if len(words) < floor:
            errors.append(
                f"{lid}: synthesize VO too thin ({len(words)} words; min {floor})"
            )
        errors.extend(lint_spoken_text(text, label=f"vo[{lid}]"))
        # Bracket / angle placeholders are never speakable air.
        if re.search(r"[\[{<][^\]}>]{0,80}[\]}>]", text):
            errors.append(f"{lid}: synthesize VO has unspeakable placeholder markup")
    return errors


def lines_needing_adjudicate(
    ctx: RunContext,
    gap_report: dict[str, Any],
    *,
    skip_fresh_wav: bool = True,
) -> list[dict[str, Any]]:
    """Body synthesize lines that still need adjudicate LLM (9C-aware)."""
    out: list[dict[str, Any]] = []
    for line in _body_synthesize_lines(gap_report):
        if skip_fresh_wav:
            skip, _reason = should_skip_adjudicate_for_line(ctx, line)
            if skip:
                continue
        out.append(line)
    return out


def lines_needing_adjudication(
    ctx: RunContext,
    gap_report: dict[str, Any],
    layup_plan: dict[str, Any] | None = None,
    *,
    threshold: float | None = None,
    prior: dict[str, Any] | None = None,
) -> list[str]:
    """Line ids needing adjudicate LLM — flow pre-score + 8B hash-idempotency."""
    cfg = adjudicate_cfg()
    flow_threshold = float(threshold if threshold is not None else cfg["adjudicate_flow_threshold"])
    plan = layup_plan if isinstance(layup_plan, dict) else _load_layup_plan(ctx)
    masks = _load_masks(ctx)
    prior_doc = prior if isinstance(prior, dict) else _prior_adjudication(ctx)
    prior_by_id = {
        str(row.get("line_id") or ""): row
        for row in (prior_doc.get("lines") or [])
        if isinstance(row, dict) and row.get("line_id")
    }
    corpus = (
        ctx.read_json("understanding/nugget_corpus.json")
        if ctx.artifact_exists("understanding/nugget_corpus.json")
        else {}
    )
    nuggets = [
        n for n in ((corpus or {}).get("nuggets") or []) if isinstance(n, dict)
    ]

    need: list[str] = []
    for line in _body_synthesize_lines(gap_report):
        lid = str(line.get("line_id") or "")
        if not lid:
            continue
        layup_row = _layup_row_for_line(plan, lid) or {}
        target_id = str(line.get("targets_segment_id") or "")
        target_text = _target_text(ctx, target_id)
        input_hash = line_adjudication_input_hash(line, layup_row)
        prior_row = prior_by_id.get(lid) or {}
        if prior_row.get("input_hash") == input_hash:
            continue
        flow = score_layup_flow_fit(line, target_text, masks, layup_row=layup_row)

        move_candidate = False
        if flow < flow_threshold:
            ranked_here = rank_open_nuggets_for_target(
                target_text,
                nuggets,
                exclude_ids=set(line.get("nugget_ids") or []),
                limit=3,
                slim=True,
            )
            line_nugs = {str(x) for x in (line.get("nugget_ids") or []) if x}
            if line_nugs and ranked_here:
                top = ranked_here[0]
                if top.get("nugget_id") not in line_nugs and float(top.get("relevance_to_target") or 0) > 0.35:
                    move_candidate = True

        if flow < flow_threshold or move_candidate:
            need.append(lid)
    return need


def _intro_nugget_ids(gap_report: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if str(line.get("line_category") or "") != "episode_preface":
            continue
        if line.get("skipped_optional"):
            continue
        for nid in line.get("nugget_ids") or []:
            s = str(nid or "")
            if s and s not in ids:
                ids.append(s)
    return ids


def collect_waived_nugget_ids(
    ctx: RunContext,
    *,
    gap_report: dict[str, Any] | None = None,
    layup_plan: dict[str, Any] | None = None,
) -> set[str]:
    """Waived nuggets from layup plan, omit ledger, and G1-skipped VO lines."""
    from interview_mux.nugget_layup import row_nugget_ids

    plan = layup_plan if isinstance(layup_plan, dict) else _load_layup_plan(ctx)
    waived = waived_nugget_ids_from_sources(plan)
    if ctx.artifact_exists("understanding/omit_ledger.json"):
        try:
            from interview_mux.omit_ledger import OMIT_LEDGER_REL, active_entries

            ledger = ctx.read_json(OMIT_LEDGER_REL)
            for entry in active_entries(ledger if isinstance(ledger, dict) else {}):
                if str(entry.get("kind") or "") != "nugget_waive":
                    continue
                if str(entry.get("decision") or "") != "waive":
                    continue
                nid = str(entry.get("subject_id") or "")
                if nid:
                    waived.add(nid)
        except Exception:
            pass
    report = gap_report if isinstance(gap_report, dict) else (
        ctx.read_json(GAP_REL) if ctx.artifact_exists(GAP_REL) else {}
    )
    if isinstance(report, dict):
        for line in report.get("interviewer_lines") or []:
            if not isinstance(line, dict) or not line.get("skipped_optional"):
                continue
            for nid in row_nugget_ids(line):
                waived.add(nid)
    return waived


def body_plan_from_gap_report(
    gap_report: dict[str, Any],
    layup_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synthetic body plan for coverage math from gap_report body lines."""
    plan = layup_plan if isinstance(layup_plan, dict) else {}
    layups: list[dict[str, Any]] = []
    for line in _body_synthesize_lines(gap_report):
        lid = str(line.get("line_id") or "")
        layup_row = _layup_row_for_line(plan, lid) if lid else None
        row = dict(layup_row) if isinstance(layup_row, dict) else {}
        row.setdefault("target_segment_id", line.get("targets_segment_id"))
        row.setdefault("line_id", lid)
        row["text"] = line.get("text")
        row["nugget_ids"] = list(line.get("nugget_ids") or [])
        row["skip"] = False
        layups.append(row)
    return {"layups": layups, "waived_nugget_ids": list(plan.get("waived_nugget_ids") or [])}


def nugget_air_coverage(
    ctx: RunContext,
    gap_report: dict[str, Any],
    *,
    corpus: dict[str, Any] | None = None,
    waived: list[str] | set[str] | None = None,
) -> tuple[float, set[str], set[str]]:
    """Return (coverage ratio, aired ids, eligible ids)."""
    doc = corpus if isinstance(corpus, dict) else (
        ctx.read_json("understanding/nugget_corpus.json")
        if ctx.artifact_exists("understanding/nugget_corpus.json")
        else {}
    )
    plan = _load_layup_plan(ctx)
    merged_waived = waived_nugget_ids_from_sources(waived, plan)
    merged_waived |= collect_waived_nugget_ids(ctx, gap_report=gap_report, layup_plan=plan)
    body = body_plan_from_gap_report(gap_report, plan)
    intro_ids = _intro_nugget_ids(gap_report)
    result = evaluate_nugget_air_coverage(
        body,
        intro_ids,
        merged_waived,
        doc,
        hard=False,
    )
    from interview_mux.nugget_layup import eligible_nugget_ids

    eligible = eligible_nugget_ids(doc, merged_waived)
    aired = set(result.get("body_aired_nugget_ids") or []) | set(
        result.get("intro_aired_nugget_ids") or []
    )
    return float(result.get("nugget_air_coverage") or 1.0), aired, eligible


def _gap_line_by_id(gap_report: dict[str, Any], line_id: str) -> dict[str, Any] | None:
    for line in gap_report.get("interviewer_lines") or []:
        if isinstance(line, dict) and str(line.get("line_id") or "") == line_id:
            return line
    return None


def apply_adjudicate_results(
    ctx: RunContext,
    gap_report: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    layup_plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Mutate gap_report from adjudicate volley rows; return trace actions."""
    plan = layup_plan if isinstance(layup_plan, dict) else _load_layup_plan(ctx)
    actions: list[dict[str, Any]] = []
    mutated = False
    mutated_line_ids: list[str] = []
    deferred_nuggets: set[str] = set()

    for row in results:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "")
        action = str(row.get("action") or "air").lower()
        line = _gap_line_by_id(gap_report, lid)
        if not line:
            continue
        layup_row = _layup_row_for_line(plan, lid) or {}
        input_hash = line_adjudication_input_hash(line, layup_row)

        if action == "air":
            log_step(
                f"adjudicate air unchanged: {lid}",
                ctx=ctx,
                stage=STAGE_ID,
                detail={"line_id": lid, "action": "air", "input_hash": input_hash[:12]},
            )
            actions.append({"line_id": lid, "action": "air", "input_hash": input_hash})
            continue

        if action == "rewrite":
            new_text = str(row.get("final_text") or row.get("text") or "").strip()
            if new_text:
                from interview_mux.spoken_meta_lint import scrub_spoken_edit_structure

                new_text = scrub_spoken_edit_structure(new_text)
            if new_text and new_text != str(line.get("text") or ""):
                line["text"] = new_text
                line["origin"] = "vo_line_adjudicate"
                mutated = True
                if lid:
                    mutated_line_ids.append(lid)
                log_step(
                    f"adjudicate rewrite: {lid}",
                    ctx=ctx,
                    stage=STAGE_ID,
                    detail={"line_id": lid, "action": "rewrite", "script_hash": script_hash(new_text)[:12]},
                )
                actions.append({"line_id": lid, "action": "rewrite", "input_hash": input_hash})

        elif action == "move_nugget":
            nugget_ids = [str(x) for x in (row.get("nugget_ids") or []) if x]
            if nugget_ids:
                line["nugget_ids"] = nugget_ids
                line["origin"] = "vo_line_adjudicate"
                mutated = True
                if lid:
                    mutated_line_ids.append(lid)
                log_step(
                    f"adjudicate move_nugget: {lid}",
                    ctx=ctx,
                    stage=STAGE_ID,
                    detail={"line_id": lid, "action": "move_nugget", "nugget_ids": nugget_ids[:6]},
                )
                actions.append({"line_id": lid, "action": "move_nugget", "nugget_ids": nugget_ids})

        elif action == "defer_to_intro":
            for nid in line.get("nugget_ids") or []:
                if nid:
                    deferred_nuggets.add(str(nid))
            line["nugget_ids"] = []
            if row.get("final_text"):
                line["text"] = str(row.get("final_text"))
            line["origin"] = "vo_line_adjudicate"
            mutated = True
            if lid:
                mutated_line_ids.append(lid)
            log_step(
                f"adjudicate defer_to_intro: {lid}",
                ctx=ctx,
                stage=STAGE_ID,
                detail={"line_id": lid, "action": "defer_to_intro"},
            )
            actions.append({"line_id": lid, "action": "defer_to_intro", "input_hash": input_hash})

        target_seg = row.get("target_segment_id")
        if target_seg and str(target_seg) != str(line.get("targets_segment_id") or ""):
            line["targets_segment_id"] = str(target_seg)
            mutated = True
            if lid and lid not in mutated_line_ids:
                mutated_line_ids.append(lid)

    if deferred_nuggets:
        gap_report.setdefault("_adjudicate_deferred_nuggets", [])
        existing = {str(x) for x in (gap_report.get("_adjudicate_deferred_nuggets") or []) if x}
        gap_report["_adjudicate_deferred_nuggets"] = sorted(existing | deferred_nuggets)

    if mutated and adjudicate_cfg().get("full_resynth_on_adjudicate_change", True):
        # Only purge lines whose spoken copy / seating actually changed — never
        # wipe transition bridges or untouched layup WAVs (exec_11130).
        nuke_all_synth_wavs_on_adjudicate_change(
            ctx, line_ids=mutated_line_ids or None
        )

    return gap_report, actions


def persist_adjudication_skip_stub(
    ctx: RunContext,
    *,
    skip_reason: str,
    settled_line_ids: list[str] | None = None,
) -> dict[str, Any]:
    """HV-3: schema-valid primary when the LLM batch did not run.

    ``lines`` stays empty unless a prior row already exists for a settled id —
    do not invent air/rewrite actions.
    """
    settled = [str(x) for x in (settled_line_ids or []) if x]
    prior = _prior_adjudication(ctx)
    prior_by = {
        str(row.get("line_id") or ""): row
        for row in (prior.get("lines") or [])
        if isinstance(row, dict) and row.get("line_id")
    }
    lines = [prior_by[lid] for lid in settled if lid in prior_by]
    doc: dict[str, Any] = {
        "version": 1,
        "lines": lines,
        "batch_count": 0,
        "skip_reason": str(skip_reason or "adjudicate_skipped"),
    }
    if settled:
        doc["settled_line_ids"] = settled
    ctx.write_json(ADJUDICATION_REL, doc, stage_key=STAGE_ID)
    return doc


def _heal_adjudicate_mark(ctx: RunContext) -> None:
    from interview_mux.stage_completion import heal_or_refuse_mark

    heal_or_refuse_mark(ctx, STAGE_ID)


def persist_allocation_plan(
    ctx: RunContext,
    gap_report: dict[str, Any],
    *,
    adjudication_rows: list[dict[str, Any]] | None = None,
    intro_nugget_ids: list[str] | None = None,
    waived: list[str] | None = None,
    layup_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = layup_plan if isinstance(layup_plan, dict) else _load_layup_plan(ctx)
    corpus = (
        ctx.read_json("understanding/nugget_corpus.json")
        if ctx.artifact_exists("understanding/nugget_corpus.json")
        else {}
    )
    merged_waived = collect_waived_nugget_ids(ctx, gap_report=gap_report, layup_plan=plan)
    merged_waived |= waived_nugget_ids_from_sources(waived, plan)
    body = body_plan_from_gap_report(gap_report, plan)
    intro = list(intro_nugget_ids or _intro_nugget_ids(gap_report))
    cov = evaluate_nugget_air_coverage(
        body,
        intro,
        merged_waived,
        corpus if isinstance(corpus, dict) else {},
        hard=False,
    )
    body_rows: list[dict[str, Any]] = []
    for line in _body_synthesize_lines(gap_report):
        lid = str(line.get("line_id") or "")
        if not lid:
            continue
        body_rows.append(
            {
                "line_id": lid,
                "target_segment_id": line.get("targets_segment_id"),
                "nugget_ids": list(line.get("nugget_ids") or []),
            }
        )
    doc = {
        "version": 1,
        "body": body_rows,
        "intro": [{"nugget_ids": intro}],
        "waived": sorted(merged_waived),
        "coverage": cov.get("nugget_air_coverage"),
        "eligible_nugget_count": cov.get("eligible_nugget_count"),
        "aired_nugget_count": cov.get("aired_nugget_count"),
        "open_nugget_ids": cov.get("open_nugget_ids") or [],
        "body_aired_nugget_ids": cov.get("body_aired_nugget_ids") or [],
        "intro_aired_nugget_ids": cov.get("intro_aired_nugget_ids") or [],
        "min_nugget_air_coverage": cov.get("min_nugget_air_coverage"),
        "adjudication_rows": adjudication_rows or [],
    }
    ctx.write_json(ALLOCATION_REL, doc, stage_key=STAGE_ID)
    return doc


def run_adjudicate_batches(
    ctx: RunContext,
    line_ids: list[str],
    gap_report: dict[str, Any],
    *,
    llm_runner: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Economy-tier batched adjudicate via ``run_flow_llm_stage`` (mockable)."""
    from interview_mux.stages.analysis_stage import run_flow_llm_stage

    if not line_ids:
        return []

    cfg = adjudicate_cfg()
    batch_size = max(1, int(cfg["adjudicate_batch_size"]))
    plan = _load_layup_plan(ctx)
    masks = _load_masks(ctx)
    all_rows: list[dict[str, Any]] = []
    batch_state: dict[str, list[str]] = {"ids": []}

    def build_input(c: RunContext) -> dict[str, Any]:
        batch = batch_state["ids"]
        lines_packet: list[dict[str, Any]] = []
        for lid in batch:
            line = _gap_line_by_id(gap_report, lid)
            if not line:
                continue
            layup_row = _layup_row_for_line(plan, lid) or {}
            target_id = str(line.get("targets_segment_id") or "")
            lines_packet.append(
                {
                    "line_id": lid,
                    "text": line.get("text"),
                    "targets_segment_id": target_id,
                    "nugget_ids": line.get("nugget_ids") or [],
                    "forward_unlock": layup_row.get("forward_unlock"),
                    "target_beat": layup_row.get("target_beat"),
                    "listener_need_entering_T": layup_row.get("listener_need_entering_T"),
                    "flow_score": score_layup_flow_fit(
                        line,
                        _target_text(c, target_id),
                        masks,
                        layup_row=layup_row,
                    ),
                    "input_hash": line_adjudication_input_hash(line, layup_row),
                }
            )
        content_brief = (
            c.read_json("understanding/content_brief.json")
            if c.artifact_exists("understanding/content_brief.json")
            else {}
        )
        return {
            "lines": lines_packet,
            "content_brief": content_brief,
            "gap_report_excerpt": {
                "line_count": len(gap_report.get("interviewer_lines") or []),
            },
        }

    captured: list[dict[str, Any]] = []

    def persist_batch(c: RunContext, artifacts: dict[str, Any]) -> None:
        rows = artifacts.get("lines") if isinstance(artifacts.get("lines"), list) else []
        for row in rows:
            if isinstance(row, dict):
                captured.append(row)
                all_rows.append(row)

    runner = llm_runner or run_flow_llm_stage
    ordered = list(line_ids)
    for i in range(0, len(ordered), batch_size):
        batch = ordered[i : i + batch_size]
        batch_state["ids"] = batch
        with logged_step(
            f"vo_line_adjudicate/batch_{i // batch_size + 1}",
            ctx=ctx,
            stage=STAGE_ID,
        ):
            runner(
                ctx,
                STAGE_ID,
                "vo/vo-line-adjudicate.system.txt",
                build_input,
                persist_batch,
            )

    prior = _prior_adjudication(ctx)
    prior_lines = list(prior.get("lines") or [])
    by_id = {str(r.get("line_id") or ""): r for r in prior_lines if isinstance(r, dict)}
    for row in all_rows:
        lid = str(row.get("line_id") or "")
        if lid:
            by_id[lid] = row
    ctx.write_json(
        ADJUDICATION_REL,
        {"version": 1, "lines": list(by_id.values()), "batch_count": (len(ordered) + batch_size - 1) // batch_size},
        stage_key=STAGE_ID,
    )
    return all_rows


def run_intro_compose(
    ctx: RunContext,
    gap_report: dict[str, Any],
    *,
    deferred_nugget_ids: list[str] | None = None,
    llm_runner: Callable[..., dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Part B — flagship intro LLM + mint episode_preface at position 0."""
    from interview_mux.nugget_intro_compose import (
        mint_episode_preface_at_position_0,
        run_nugget_intro_compose,
        select_gap_to_85_nuggets,
    )

    deferred = [str(x) for x in (deferred_nugget_ids or gap_report.get("_adjudicate_deferred_nuggets") or []) if x]
    gap_ids = select_gap_to_85_nuggets(ctx, gap_report, deferred_ids=deferred)
    nugget_ids = sorted(set(deferred) | set(gap_ids))
    cfg = adjudicate_cfg()
    coverage, _aired, _eligible = nugget_air_coverage(ctx, gap_report)
    if not nugget_ids and coverage >= cfg["min_nugget_air_coverage"]:
        return gap_report, []

    intro = run_nugget_intro_compose(ctx, gap_report, nugget_ids, llm_runner=llm_runner)
    if not intro:
        return gap_report, []
    gap_report, minted = mint_episode_preface_at_position_0(ctx, gap_report, intro)
    if minted:
        log_step(
            "intro mint episode_preface at position 0",
            ctx=ctx,
            stage=STAGE_ID,
            detail={
                "action": "intro_mint",
                "nugget_ids": intro.get("nugget_ids") or nugget_ids[:8],
                "intro_nugget_recovery": True,
            },
        )
        if adjudicate_cfg().get("full_resynth_on_adjudicate_change", True):
            nuke_all_synth_wavs_on_adjudicate_change(ctx)
    return gap_report, list(intro.get("nugget_ids") or nugget_ids)


def run_vo_line_adjudicate_stage(ctx: RunContext) -> None:
    """Full stage: Part A body adjudicate + Part B intro compose."""
    if not ctx.artifact_exists(GAP_REL):
        ctx.log("vo_line_adjudicate: no gap_report — skip", level="info", stage=STAGE_ID)
        persist_adjudication_skip_stub(ctx, skip_reason="no_gap_report")
        _heal_adjudicate_mark(ctx)
        return

    gap_report = ctx.read_json(GAP_REL)
    if not isinstance(gap_report, dict):
        persist_adjudication_skip_stub(ctx, skip_reason="invalid_gap_report")
        _heal_adjudicate_mark(ctx)
        return

    try:
        from interview_mux.omit_ledger import stamp_gap_report_omit_skips

        stamped = stamp_gap_report_omit_skips(ctx)
        if stamped:
            gap_report = ctx.read_json(GAP_REL)
            ctx.log(
                f"vo_line_adjudicate: stamped {stamped} omit-ledger skip(s) on gap_report",
                level="info",
                stage=STAGE_ID,
            )
    except Exception as exc:
        ctx.log(
            f"vo_line_adjudicate: omit ledger stamp skipped: {exc}",
            level="warning",
            stage=STAGE_ID,
        )

    body_lines = _body_synthesize_lines(gap_report)
    plan = _load_layup_plan(ctx)
    adjudication_rows: list[dict[str, Any]] = []
    intro_nugget_ids: list[str] = []
    skip_reason: str | None = None
    settled_ids: list[str] = []

    if body_lines:
        need_ids = lines_needing_adjudication(ctx, gap_report, plan)
        if need_ids:
            adjudication_rows = run_adjudicate_batches(ctx, need_ids, gap_report)
            gap_report, _actions = apply_adjudicate_results(ctx, gap_report, adjudication_rows, layup_plan=plan)
            ctx.write_json(GAP_REL, gap_report, stage_key=STAGE_ID)
        else:
            skip_reason = "unchanged_or_flow_ok"
            settled_ids = [
                str(row.get("line_id") or "")
                for row in body_lines
                if row.get("line_id")
            ]
            persist_adjudication_skip_stub(
                ctx, skip_reason=skip_reason, settled_line_ids=settled_ids
            )
    else:
        skip_reason = "zero_body_synthesize_lines"
        persist_adjudication_skip_stub(ctx, skip_reason=skip_reason)
        ctx.log(
            "vo_line_adjudicate: zero body synthesize lines — skip Part A (7A)",
            level="info",
            stage=STAGE_ID,
        )

    gap_report, intro_nugget_ids = run_intro_compose(ctx, gap_report)
    if intro_nugget_ids:
        ctx.write_json(GAP_REL, gap_report, stage_key=STAGE_ID)

    allocation = persist_allocation_plan(
        ctx,
        gap_report,
        adjudication_rows=adjudication_rows,
        intro_nugget_ids=intro_nugget_ids,
        layup_plan=plan,
    )

    corpus = (
        ctx.read_json("understanding/nugget_corpus.json")
        if ctx.artifact_exists("understanding/nugget_corpus.json")
        else {}
    )
    waived = collect_waived_nugget_ids(ctx, gap_report=gap_report, layup_plan=plan)
    cov = evaluate_nugget_air_coverage(
        body_plan_from_gap_report(gap_report, plan),
        intro_nugget_ids or _intro_nugget_ids(gap_report),
        waived,
        corpus if isinstance(corpus, dict) else {},
        hard=True,
    )
    if not cov.get("ok"):
        msg = "Nugget air coverage below floor after adjudicate+intro: " + "; ".join(
            str(e) for e in (cov.get("errors") or [])[:4]
        )
        if adjudicate_cfg().get("adjudicate_fail_open"):
            ctx.log(msg, level="warning", stage=STAGE_ID, detail={"allocation": allocation})
        else:
            from interview_mux.loud_fail import raise_loud_failure

            raise_loud_failure(
                ctx,
                msg,
                stage=STAGE_ID,
                reason="nugget_air_coverage_below_floor",
            )

    # Q1A+: coverage may fail-open, but seated synthesize VO must stay comprehensible.
    # Scrub edit-structure nouns left by adjudicate LLM before the hard gate.
    from interview_mux.spoken_meta_lint import scrub_spoken_edit_structure

    scrubbed_any = False
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if str(line.get("delivery") or "").lower() != "synthesize":
            continue
        if line.get("skipped_optional") or line.get("air_script_omit"):
            continue
        text = str(line.get("text") or "")
        cleaned = scrub_spoken_edit_structure(text)
        if cleaned and cleaned != text:
            line["text"] = cleaned
            scrubbed_any = True
    if scrubbed_any:
        ctx.write_json(GAP_REL, gap_report, stage_key=STAGE_ID)

    vo_errs = synthesize_vo_comprehensibility_errors(gap_report)
    if vo_errs:
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Synthesize VO transcript not comprehensible after adjudicate+intro: "
            + "; ".join(vo_errs[:6]),
            stage=STAGE_ID,
            reason="synthesize_vo_incomprehensible",
        )

    if not ctx.artifact_exists(ADJUDICATION_REL):
        persist_adjudication_skip_stub(
            ctx,
            skip_reason=skip_reason or "adjudicate_complete_without_batch",
            settled_line_ids=settled_ids or None,
        )
    _heal_adjudicate_mark(ctx)
