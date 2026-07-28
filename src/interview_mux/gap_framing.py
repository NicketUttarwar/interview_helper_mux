"""Gap framing taxonomy, succinct-master plan, and compose-stage helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.source_topology import pickup_eligible_speaker_id

GAP_FRAMING_PLAN_REL = "understanding/gap_framing_plan.json"

LINE_CATEGORIES = frozenset(
    {
        "framing_question",
        "context_setup",
        "segment_summary",
        "episode_preface",
        "story_bridge",
        "extracted_context",
    }
)

GAP_TYPE_TO_CATEGORY: dict[str, str] = {
    "missing_question": "framing_question",
    "missing_setup": "context_setup",
    "missing_callback": "story_bridge",
    "missing_definition": "extracted_context",
    "missing_followup": "framing_question",
    "ok_with_light_bridge": "story_bridge",
}


def _analysis_block(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return (cfg or merged_config()).get("analysis") or {}


def gap_framing_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _analysis_block(cfg).get("gap_framing") or {}
    defaults = {
        "interviewer_question_max_words": 60,
        "interviewer_setup_max_words": 20,
        "interviewer_summary_max_words": 80,
        "interviewer_preface_max_words": 110,
        "interviewer_bridge_max_words": 50,
        "interviewer_context_max_words": 70,
        "max_preface_lines_per_act": 1,
        "allow_replace_source_segments": True,
        "max_exclusion_ratio": 0.15,
        "never_exclude_primary_impact": True,
        "require_topic_survival": True,
        "require_framing_before_impact": True,
        "words_per_second_estimate": 2.5,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def gap_vo_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _analysis_block(cfg).get("gap_vo") or {}
    defaults = {
        "default_delivery": "chatterbox",
        "allowed_delivery": ["chatterbox", "record"],
        "synthesis_backend": "chatterbox",
        "fallback_backend": "mlx_audio",
        "fail_open": False,
        "min_reference_sec": 3.0,
        "auto_fallback_on_qc_fail": False,
        "fallback_to_manual_on_failure": False,
        "timbre_match": {
            "enabled": True,
            "max_eq_db": 6.0,
        },
    }
    if isinstance(raw, dict):
        merged = {**defaults, **raw}
        tm = raw.get("timbre_match")
        if isinstance(tm, dict):
            merged["timbre_match"] = {**defaults["timbre_match"], **tm}
        return merged
    return defaults


FRAMING_BRIDGE_CATEGORIES = frozenset(
    {"segment_summary", "story_bridge", "episode_preface", "extracted_context"}
)

CATEGORY_TO_CUE_ROLE: dict[str, str] = {
    "episode_preface": "vo_preface",
    "segment_summary": "vo_summary",
    "story_bridge": "vo_bridge",
    "framing_question": "vo_question",
    "extracted_context": "vo_context",
    "context_setup": "vo_context",
}


def word_limit_for_category(category: str, cfg: dict[str, Any] | None = None) -> int:
    block = gap_framing_cfg(cfg)
    mapping = {
        "framing_question": block["interviewer_question_max_words"],
        "context_setup": block["interviewer_setup_max_words"],
        "segment_summary": block["interviewer_summary_max_words"],
        "episode_preface": block["interviewer_preface_max_words"],
        "story_bridge": block["interviewer_bridge_max_words"],
        "extracted_context": block["interviewer_context_max_words"],
    }
    return int(mapping.get(category, block["interviewer_setup_max_words"]))


def infer_line_category(line: dict[str, Any]) -> str:
    explicit = str(line.get("line_category") or "").strip()
    if explicit in LINE_CATEGORIES:
        return explicit
    gap_type = str(line.get("gap_type") or "").strip()
    return GAP_TYPE_TO_CATEGORY.get(gap_type, "framing_question")


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def normalize_interviewer_line(line: dict[str, Any], *, eligible: str | None, delivery: str) -> dict[str, Any]:
    out = dict(line)
    category = infer_line_category(out)
    out["line_category"] = category
    if eligible and not out.get("voice_speaker_id"):
        out["voice_speaker_id"] = eligible
    out["delivery"] = delivery if delivery in {"record", "synthesize"} else "record"
    supports = out.get("supports_segment_ids")
    if not supports:
        tgt = str(out.get("targets_segment_id") or "").strip()
        out["supports_segment_ids"] = [tgt] if tgt else []
    if not out.get("estimated_duration_sec"):
        wps = float(gap_framing_cfg().get("words_per_second_estimate", 2.5))
        out["estimated_duration_sec"] = round(_word_count(str(out.get("text") or "")) / max(wps, 0.5), 1)
    return out


def validate_line_word_limits(lines: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        category = infer_line_category(line)
        limit = word_limit_for_category(category)
        count = _word_count(str(line.get("text") or ""))
        if count > limit:
            errors.append(
                f"{line.get('line_id')}: {category} has {count} words (max {limit})"
            )
    return errors


def build_gap_framing_plan(ctx: RunContext, lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic succinct-master plan from interviewer lines."""
    blocks: list[dict[str, Any]] = []
    preface_line_id: str | None = None
    for line in lines:
        if not isinstance(line, dict):
            continue
        category = infer_line_category(line)
        lid = str(line.get("line_id") or "")
        if category == "episode_preface" and lid:
            preface_line_id = lid
            continue
        source_ids = [
            str(s)
            for s in (line.get("supports_segment_ids") or [])
            if str(s).strip()
        ]
        if not source_ids:
            tgt = str(line.get("targets_segment_id") or "").strip()
            if tgt:
                source_ids = [tgt]
        replaces = [
            str(s)
            for s in (line.get("replaces_source_segments") or [])
            if str(s).strip()
        ]
        blocks.append(
            {
                "framing_line_ids": [lid] if lid else [],
                "source_segment_ids": source_ids,
                "excluded_redundant_segment_ids": replaces,
                "rationale": str(line.get("rationale") or ""),
            }
        )
    return {
        "succinct_master_intent": True,
        "acts": [
            {
                "act_id": "act_1",
                "preface_line_id": preface_line_id,
                "impact_blocks": blocks,
            }
        ],
    }


def persist_gap_framing_companion_artifacts(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    delivery: str | None = None,
) -> None:
    from interview_mux.gap_vo_gates import resolve_gap_vo_delivery

    lines = list(artifacts.get("interviewer_lines") or [])
    eligible = pickup_eligible_speaker_id(ctx)
    chosen_delivery = delivery or resolve_gap_vo_delivery(ctx)
    if chosen_delivery == "chatterbox":
        from interview_mux.synthesis_fallback import ensure_chatterbox_or_manual

        ensure_chatterbox_or_manual(ctx, stage="gap_framing_compose")
        chosen_delivery = resolve_gap_vo_delivery(ctx)
    if chosen_delivery == "chatterbox":
        vo_delivery = "synthesize"
    else:
        vo_delivery = "record"
    normalized: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            continue
        row = dict(line)
        if "line_id" not in row:
            row["line_id"] = f"line_{i+1:03d}"
        if not row.get("placement"):
            row["placement"] = "before"
        normalized.append(normalize_interviewer_line(row, eligible=eligible, delivery=vo_delivery))
    plan = build_gap_framing_plan(ctx, normalized)
    ctx.write_json(GAP_FRAMING_PLAN_REL, plan)
    _write_interviewer_script(ctx, normalized)
    artifacts["interviewer_lines"] = normalized


def _write_interviewer_script(ctx: RunContext, lines: list[dict]) -> None:
    rows = [
        "# Interviewer framing script — vo_pickup/{line_id}.wav or synthesize at G1",
        "",
    ]
    for line in lines:
        lid = line.get("line_id", "line_unknown")
        category = infer_line_category(line)
        rows.append(f"## {lid} ({category}, {line.get('delivery', 'record')})")
        rows.append(
            f"Target: {line.get('targets_segment_id', '')} — {line.get('gap_type', '')}"
        )
        supports = line.get("supports_segment_ids") or []
        if supports:
            rows.append(f"Supports: {', '.join(str(s) for s in supports)}")
        replaces = line.get("replaces_source_segments") or []
        if replaces:
            rows.append(f"Replaces source: {', '.join(str(s) for s in replaces)}")
        rows.append(str(line.get("text") or ""))
        rows.append("")
    ctx.path("understanding", "interviewer_script.txt").write_text("\n".join(rows), encoding="utf-8")


def load_gap_framing_plan(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(GAP_FRAMING_PLAN_REL):
        return None
    doc = ctx.read_json(GAP_FRAMING_PLAN_REL)
    return doc if isinstance(doc, dict) else None


def ranking_exclude_segment_ids(ctx: RunContext) -> set[str]:
    """Segments that succinct-master framing replaces in ranking."""
    if not gap_framing_cfg().get("allow_replace_source_segments", True):
        return set()
    plan = load_gap_framing_plan(ctx)
    if not plan:
        return set()
    out: set[str] = set()
    for act in plan.get("acts") or []:
        if not isinstance(act, dict):
            continue
        for block in act.get("impact_blocks") or []:
            if not isinstance(block, dict):
                continue
            for sid in block.get("excluded_redundant_segment_ids") or []:
                if sid:
                    out.add(str(sid))
    report = ctx.read_json("understanding/gap_report.json") if ctx.artifact_exists("understanding/gap_report.json") else {}
    for line in (report.get("interviewer_lines") or []) if isinstance(report, dict) else []:
        if isinstance(line, dict):
            for sid in line.get("replaces_source_segments") or []:
                if sid:
                    out.add(str(sid))
    return out


def attach_framing_to_ranking_payload(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    plan = load_gap_framing_plan(ctx)
    if plan:
        payload["gap_framing_plan"] = plan
    excludes = sorted(ranking_exclude_segment_ids(ctx))
    if excludes:
        payload["framing_covered_segment_ids"] = excludes
    return payload


def framing_vo_for_sound_design(ctx: RunContext) -> list[dict[str, Any]]:
    """Compact framing VO rows for sound-design planning (category + duration)."""
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    report = ctx.read_json("understanding/gap_report.json")
    rows: list[dict[str, Any]] = []
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        category = infer_line_category(line)
        rows.append(
            {
                "line_id": line.get("line_id"),
                "line_category": category,
                "cue_role": CATEGORY_TO_CUE_ROLE.get(category, "vo_bridge"),
                "targets_segment_id": line.get("targets_segment_id"),
                "placement": line.get("placement") or "before",
                "estimated_duration_sec": line.get("estimated_duration_sec"),
                "delivery": line.get("delivery"),
            }
        )
    return rows


def transition_redundant_with_framing(
    gap_report: dict[str, Any] | None,
    after_segment_id: str,
    before_segment_id: str,
) -> bool:
    """True when a framing VO line already bridges this segment pair."""
    if not gap_report or not isinstance(gap_report, dict):
        return False
    after = str(after_segment_id or "").strip()
    before = str(before_segment_id or "").strip()
    if not after or not before:
        return False
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        category = infer_line_category(line)
        if category not in FRAMING_BRIDGE_CATEGORIES:
            continue
        target = str(line.get("targets_segment_id") or "").strip()
        placement = str(line.get("placement") or "before").strip()
        if placement == "before" and target == before:
            return True
        if placement == "after" and target == after:
            return True
    return False


def dedupe_transitions_for_framing(
    gap_report: dict[str, Any] | None,
    transitions_doc: dict[str, Any],
) -> dict[str, Any]:
    """Drop spoken transitions redundant with segment_summary / story_bridge VO."""
    items = list(transitions_doc.get("transitions") or [])
    if not items:
        return transitions_doc
    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        after = str(item.get("after_segment_id") or "")
        before = str(item.get("before_segment_id") or "")
        if transition_redundant_with_framing(gap_report, after, before):
            dropped += 1
            continue
        kept.append(item)
    if dropped:
        out = dict(transitions_doc)
        out["transitions"] = kept
        out["framing_deduped_count"] = dropped
        return out
    return transitions_doc
