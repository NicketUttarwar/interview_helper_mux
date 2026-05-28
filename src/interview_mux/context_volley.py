"""Stage-selective, conversation-native context for OpenAI Chat API calls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from interview_mux.analysis_memory import (
    drain_open_investigations,
    load_analysis_state,
    load_queue,
)
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

# Pipeline order for "prior conclusions" (assistant turns)
_ANALYSIS_PRIORS = (
    "speaker_roles",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "missing_framing",
)

_FLOW_PRIORS = (
    "content_context",
    "segment_classification",
    "missing_framing",
    "topic_coverage_audit",
    "narrative_arc_plan",
)


@dataclass(frozen=True)
class StageContextPlan:
    """What to include in the message volley for one stage."""

    task_line: str
    prior_stages: tuple[str, ...] = ()
    profile_keys: tuple[str, ...] = ()  # narrative, style, themes, entities, major_questions, operator_notes
    investigation_kinds: frozenset[str] = frozenset()
    include_blocking_investigations: bool = True
    max_investigations: int = 3


STAGE_PLANS: dict[str, StageContextPlan] = {
    "speaker_roles": StageContextPlan(
        task_line="Map diarized speaker IDs to interviewer / interviewee roles.",
        prior_stages=(),
        profile_keys=("operator_notes",),
        max_investigations=0,
    ),
    "content_context": StageContextPlan(
        task_line="Produce the content brief (thesis, topics, claims, beats) from the transcript.",
        prior_stages=("speaker_roles",),
        profile_keys=("operator_notes", "interview_identity"),
        max_investigations=2,
    ),
    "boundary_detection": StageContextPlan(
        task_line="Propose segment boundaries on the timeline.",
        prior_stages=("speaker_roles", "content_context"),
        profile_keys=("themes", "narrative"),
        investigation_kinds=frozenset({"segment_ambiguity", "theme_unmapped"}),
        max_investigations=2,
    ),
    "segment_classification": StageContextPlan(
        task_line="Classify each segment by type and topic tags.",
        prior_stages=("content_context", "boundary_detection"),
        profile_keys=("themes", "narrative", "speakers"),
        investigation_kinds=frozenset({"theme_unmapped", "segment_ambiguity"}),
        max_investigations=3,
    ),
    "sound_design_palettes": StageContextPlan(
        task_line="Define transcript-grounded sound design coherence and theme palettes.",
        prior_stages=("content_context", "segment_classification"),
        profile_keys=("themes", "narrative", "style", "operator_notes"),
        investigation_kinds=frozenset({"theme_unmapped"}),
        max_investigations=2,
    ),
    "missing_framing": StageContextPlan(
        task_line="Evaluate which segments are self-explanatory for listeners; classify gaps only.",
        prior_stages=("segment_classification", "content_context"),
        profile_keys=("narrative", "entities", "major_questions"),
        investigation_kinds=frozenset({"gap_unresolved", "segment_ambiguity"}),
        max_investigations=3,
    ),
    "optimal_questions": StageContextPlan(
        task_line="Write short interviewer VO lines that fix framing gaps.",
        prior_stages=("missing_framing", "content_context"),
        profile_keys=("style", "major_questions", "narrative"),
        investigation_kinds=frozenset({"gap_unresolved"}),
        max_investigations=2,
    ),
    "topic_coverage_audit": StageContextPlan(
        task_line="Audit topic and claim coverage across segments.",
        prior_stages=("content_context", "segment_classification"),
        profile_keys=("themes", "narrative", "major_questions"),
        max_investigations=1,
    ),
    "narrative_arc_plan": StageContextPlan(
        task_line="Plan narrative arc, chapters, and ordering constraints.",
        prior_stages=("topic_coverage_audit", "content_context"),
        profile_keys=("themes", "narrative", "style"),
        max_investigations=1,
    ),
    "full_master_ranking": StageContextPlan(
        task_line="Order segments for the full podcast master.",
        prior_stages=(
            "narrative_arc_plan",
            "topic_coverage_audit",
            "optimal_questions",
            "missing_framing",
        ),
        profile_keys=("themes", "narrative", "style"),
        max_investigations=0,
    ),
    "highlight_selection": StageContextPlan(
        task_line="Select up to five standalone highlight clips.",
        prior_stages=("content_context", "missing_framing"),
        profile_keys=("themes", "narrative", "style", "major_questions"),
        max_investigations=1,
    ),
    "transitions": StageContextPlan(
        task_line="Write short interviewer transitions between ordered segments.",
        prior_stages=("full_master_ranking", "optimal_questions"),
        profile_keys=("style", "narrative"),
        max_investigations=0,
    ),
    "podcast_sfx_brief": StageContextPlan(
        task_line="Specify subtle podcast sound design between chapters/segments.",
        prior_stages=("full_master_ranking", "narrative_arc_plan"),
        profile_keys=("style",),
        max_investigations=0,
    ),
    "sound_design_plan_flow1": StageContextPlan(
        task_line="Plan reusable Flow 1 sound design assets and cue placements.",
        prior_stages=("full_master_ranking", "narrative_arc_plan", "transitions", "optimal_questions"),
        profile_keys=("style", "themes", "narrative"),
        max_investigations=0,
    ),
    "sfx_brief": StageContextPlan(
        task_line="Specify montage SFX between highlight clips.",
        prior_stages=("highlight_selection",),
        profile_keys=("style", "narrative"),
        max_investigations=0,
    ),
    "elevenlabs_prompt_craft": StageContextPlan(
        task_line="Craft one ElevenLabs sound-generation prompt per planned asset_id.",
        prior_stages=("sound_design_plan_flow1", "sound_design_plan_flow2"),
        profile_keys=("style", "themes", "narrative"),
        max_investigations=0,
    ),
    "podcast_show_description": StageContextPlan(
        task_line=(
            "Write a third-person podcast show description (~200 words) grounded in the content brief."
        ),
        prior_stages=(
            "content_context",
            "segment_classification",
            "missing_framing",
            "optimal_questions",
        ),
        profile_keys=("themes", "narrative", "style", "major_questions", "entities"),
        investigation_kinds=frozenset({"show_description_thin_evidence"}),
        max_investigations=2,
    ),
}


def _context_cfg() -> dict[str, Any]:
    return (merged_config().get("analysis") or {}).get("context") or {}


def _char_limit(key: str, default: int) -> int:
    return int(_context_cfg().get(key, default))


def plan_for_stage(stage_key: str) -> StageContextPlan:
    return STAGE_PLANS.get(
        stage_key,
        StageContextPlan(
            task_line=f"Complete stage: {stage_key}.",
            prior_stages=(),
            profile_keys=("narrative", "themes"),
            max_investigations=2,
        ),
    )


def build_message_volley(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    profile: str = "full",
) -> list[dict[str, str]]:
    """
    Build OpenAI messages: system (from caller) + user/assistant volley + final user task.

    Prior work is synthetic assistant prose; only this stage's raw data appears in the last user turn.
    """
    plan = plan_for_stage(stage_key)
    state = load_analysis_state(ctx)
    messages: list[dict[str, str]] = []

    messages.append(
        {
            "role": "user",
            "content": (
                f"## Current task\n{plan.task_line}\n\n"
                f"Volley profile: {profile}\n\n"
                "Below is established context from earlier steps (read only). "
                "Your reply must be the JSON envelope described in the system prompt."
            ),
        }
    )

    prior_stages = plan.prior_stages if profile == "full" else plan.prior_stages[:1]
    prior_text = _format_prior_conclusions(ctx, prior_stages, state)
    if prior_text:
        messages.append({"role": "assistant", "content": prior_text})

    profile_text = _format_profile_slice(state, plan.profile_keys)
    if profile_text:
        verified = (state.get("meta") or {}).get("operator_verified")
        label = "Operator-verified profile" if verified else "Interview profile (draft — may refine)"
        messages.append({"role": "user", "content": f"## {label}\n{profile_text}"})

    inv_text = _format_investigations(ctx, stage_key, plan if profile == "full" else StageContextPlan(task_line=plan.task_line, max_investigations=0))
    if inv_text:
        messages.append({"role": "user", "content": inv_text})

    shaped = _shape_stage_input(stage_key, stage_input)
    data_block = json.dumps(shaped, indent=2, ensure_ascii=False)
    max_data = _char_limit("max_stage_data_chars", 32000)
    if len(data_block) > max_data:
        data_block = data_block[:max_data] + "\n…[stage data truncated]"

    messages.append(
        {
            "role": "user",
            "content": (
                f"## Input data for this stage only\n"
                f"Use this as the primary evidence for `{stage_key}`. "
                f"Do not assume facts not present here or in established context above.\n\n"
                f"```json\n{data_block}\n```"
            ),
        }
    )

    return messages


def volley_char_estimate(messages: list[dict[str, str]]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


def truncation_flags_for_volley(messages: list[dict[str, str]]) -> list[str]:
    flags: list[str] = []
    joined = "\n".join(m.get("content", "") for m in messages)
    if "…[stage data truncated]" in joined:
        flags.append("max_stage_data_chars")
    if "…[truncated]" in joined:
        flags.append("field_truncated")
    return flags


def _format_prior_conclusions(
    ctx: RunContext,
    prior_stages: tuple[str, ...],
    state: dict[str, Any],
) -> str:
    if not prior_stages:
        return ""
    summaries = (state.get("meta") or {}).get("stage_summaries") or {}
    lines = ["## Established conclusions from earlier pipeline steps", ""]
    for stage in prior_stages:
        if stage in summaries and summaries[stage]:
            lines.append(f"**{stage.replace('_', ' ').title()}:** {summaries[stage]}")
            continue
        digest = _artifact_digest(ctx, stage)
        if digest:
            lines.append(f"**{stage.replace('_', ' ').title()}:** {digest}")
    if len(lines) <= 2:
        return ""
    return "\n".join(lines)


def _artifact_digest(ctx: RunContext, stage: str) -> str:
    """One-line fallback when reasoning_summary is missing."""
    try:
        if stage == "speaker_roles" and ctx.artifact_exists("understanding/speakers.json"):
            doc = ctx.read_json("understanding/speakers.json")
            parts = []
            for sp in doc.get("speakers") or []:
                parts.append(f"{sp.get('speaker_id')}={sp.get('role')}")
            return "Speakers: " + ", ".join(parts) if parts else ""
        if stage == "content_context" and ctx.artifact_exists("understanding/content_brief.json"):
            b = ctx.read_json("understanding/content_brief.json")
            topics = [t.get("name", "") for t in (b.get("topics") or [])[:6] if isinstance(t, dict)]
            return f"Thesis: {b.get('thesis', '')[:200]}. Topics: {', '.join(topics)}."
        if stage == "boundary_detection" and ctx.artifact_exists("segments/boundaries.json"):
            b = ctx.read_json("segments/boundaries.json")
            n = len(b.get("boundaries") or [])
            return f"{n} boundary proposals."
        if stage == "segment_classification" and ctx.artifact_exists("segments/manifest.json"):
            m = ctx.read_json("segments/manifest.json")
            segs = m.get("segments") or []
            types: dict[str, int] = {}
            for s in segs:
                t = s.get("type", "unknown")
                types[t] = types.get(t, 0) + 1
            return f"{len(segs)} segments. Types: {types}."
        if stage == "missing_framing" and ctx.artifact_exists("understanding/gap_evaluations.json"):
            ev = ctx.read_json("understanding/gap_evaluations.json")
            evals = ev.get("evaluations") or []
            bad = sum(1 for e in evals if not e.get("self_explanatory"))
            return f"{bad}/{len(evals)} segments need framing."
        if stage == "topic_coverage_audit" and ctx.artifact_exists("flow_1_master/coverage_audit.json"):
            c = ctx.read_json("flow_1_master/coverage_audit.json")
            missing = len(c.get("missing_coverage") or [])
            return f"Coverage score {c.get('coverage_score', '?')}; {missing} gaps."
        if stage == "narrative_arc_plan" and ctx.artifact_exists("flow_1_master/narrative_plan.json"):
            p = ctx.read_json("flow_1_master/narrative_plan.json")
            return (p.get("arc_summary") or "")[:300]
        if stage == "optimal_questions" and ctx.artifact_exists("understanding/gap_report.json"):
            rep = ctx.read_json("understanding/gap_report.json")
            lines = rep.get("interviewer_lines") or []
            record = sum(1 for ln in lines if ln.get("delivery") == "record")
            return f"{len(lines)} interviewer VO lines ({record} to record)."
        if stage == "full_master_ranking" and ctx.artifact_exists("flow_1_master/selection.json"):
            sel = ctx.read_json("flow_1_master/selection.json")
            ordered = sel.get("ordered_segment_ids") or []
            excluded = len(sel.get("excluded_segment_ids") or [])
            return f"Master order: {len(ordered)} segments, {excluded} excluded."
        if stage == "highlight_selection" and ctx.artifact_exists("flow_2_highlights/selection.json"):
            h = ctx.read_json("flow_2_highlights/selection.json")
            n = len(h.get("highlights") or [])
            return f"{n} highlight clips. Reel: {(h.get('reel_thesis') or '')[:120]}."
    except Exception:
        return ""
    return ""


def _format_profile_slice(state: dict[str, Any], keys: tuple[str, ...]) -> str:
    if not keys:
        return ""
    lines: list[str] = []
    if "interview_identity" in keys:
        ident = state.get("interview_identity") or {}
        if ident.get("title"):
            lines.append(f"Title: {ident['title']}")
        if ident.get("one_line_summary"):
            lines.append(f"Summary: {ident['one_line_summary']}")
    if "narrative" in keys:
        n = state.get("narrative") or {}
        if n.get("thesis"):
            lines.append(f"Thesis: {n['thesis']}")
        if n.get("audience"):
            lines.append(f"Audience: {n['audience']}")
    if "themes" in keys:
        themes = state.get("themes") or []
        if themes:
            labels = [f"{t.get('label', t.get('id', ''))}" for t in themes[:12]]
            lines.append("Themes: " + "; ".join(labels))
    if "major_questions" in keys:
        qs = state.get("major_questions") or []
        if qs:
            lines.append(
                "Major questions: "
                + "; ".join(
                    (q.get("question", q) if isinstance(q, dict) else str(q)) for q in qs[:8]
                )
            )
    if "style" in keys:
        st = state.get("style") or {}
        bits = [f"{k}={v}" for k, v in st.items() if v]
        if bits:
            lines.append("Style: " + ", ".join(bits))
    if "entities" in keys:
        ents = state.get("entities") or []
        if ents:
            lines.append(
                "Entities: "
                + "; ".join(
                    f"{e.get('name', '')} ({e.get('plain_definition', '')[:60]})"
                    for e in ents[:10]
                    if isinstance(e, dict)
                )
            )
    if "speakers" in keys:
        sp = state.get("speakers") or []
        if sp:
            lines.append(
                "Speakers: "
                + ", ".join(
                    f"{s.get('speaker_id')}={s.get('role')}" for s in sp[:6] if isinstance(s, dict)
                )
            )
    if "operator_notes" in keys and state.get("operator_notes"):
        lines.append(f"Operator notes: {state['operator_notes']}")
    return "\n".join(lines)


def _format_investigations(ctx: RunContext, stage_key: str, plan: StageContextPlan) -> str:
    if plan.max_investigations <= 0:
        return ""
    open_items = drain_open_investigations(ctx, limit=12)
    selected: list[dict[str, Any]] = []
    for it in open_items:
        if it.get("blocking") and plan.include_blocking_investigations:
            selected.append(it)
            continue
        kind = it.get("kind", "")
        action = it.get("suggested_action") or {}
        if action.get("stage") == stage_key:
            selected.append(it)
            continue
        if plan.investigation_kinds and kind in plan.investigation_kinds:
            if it.get("priority") == "high":
                selected.append(it)
    selected = selected[: plan.max_investigations]
    if not selected:
        return ""
    lines = ["## Open investigations relevant to this step", ""]
    for it in selected:
        lines.append(
            f"- [{it.get('id')}] ({it.get('kind')}) {it.get('question', '')} "
            f"{'[blocking]' if it.get('blocking') else ''}"
        )
    return "\n".join(lines)


def _shape_stage_input(stage_key: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Strip fields each stage does not need — avoid shipping full transcript everywhere."""
    if stage_key == "speaker_roles":
        return {
            "transcript_excerpt": _clip_text(
                raw.get("transcript_excerpt") or _extract_transcript_text(raw),
                _char_limit("transcript_excerpt_chars", 12000),
            ),
            "speakers": raw.get("speakers"),
        }
    if stage_key == "content_context":
        out_cc: dict[str, Any] = {
            "transcript": _clip_text(
                raw.get("transcript") or _extract_transcript_text(raw),
                _char_limit("transcript_full_chars", 36000),
            ),
        }
        if raw.get("transcript_quality"):
            out_cc["transcript_quality"] = raw["transcript_quality"]
        return out_cc
    if stage_key == "boundary_detection":
        out: dict[str, Any] = {
            "speakers": raw.get("speakers"),
            "content_brief": _compact_brief(raw.get("content_brief")),
        }
        tr = raw.get("transcript")
        if isinstance(tr, dict):
            out["transcript"] = {
                "text": _clip_text(tr.get("text", ""), _char_limit("transcript_full_chars", 36000)),
                "items": tr.get("items"),
            }
        else:
            out["transcript"] = _clip_text(tr, _char_limit("transcript_full_chars", 36000))
        if raw.get("transcript_quality"):
            out["transcript_quality"] = raw["transcript_quality"]
        return out
    if stage_key == "segment_classification":
        return {
            "boundaries": raw.get("boundaries"),
            "speakers": raw.get("speakers"),
            "content_brief": _compact_brief(raw.get("content_brief")),
            "transcript": _clip_transcript_for_segments(raw.get("transcript")),
        }
    if stage_key == "sound_design_palettes":
        out_sdp: dict[str, Any] = {
            "content_brief": _compact_brief(raw.get("content_brief")),
            "segments": _compact_segments(raw.get("segments"), max_count=100),
            "sound_design_plan": raw.get("sound_design_plan"),
        }
        state = raw.get("analysis_state")
        if isinstance(state, dict):
            out_sdp["analysis_state"] = {
                "themes": state.get("themes"),
                "narrative": state.get("narrative"),
                "style": state.get("style"),
                "operator_notes": state.get("operator_notes"),
            }
        if raw.get("operator_style_sound_design_notes"):
            out_sdp["operator_style_sound_design_notes"] = raw.get("operator_style_sound_design_notes")
        return out_sdp
    if stage_key == "missing_framing":
        return {
            "content_brief": _compact_brief(raw.get("content_brief")),
            "segments": _compact_segments(raw.get("segments"), for_gaps=True),
        }
    if stage_key == "optimal_questions":
        return {
            "gap_evaluations": _filter_gap_evaluations(raw.get("gap_evaluations")),
            "segments": _compact_segments_for_gaps(raw),
            "content_brief": _compact_brief(raw.get("content_brief")),
        }
    if stage_key == "podcast_show_description":
        out_psd: dict[str, Any] = {
            "content_brief": _compact_brief(raw.get("content_brief")),
            "speakers": raw.get("speakers"),
            "segments": _compact_segments(raw.get("segments"), max_count=80),
        }
        if raw.get("gap_summary"):
            out_psd["gap_summary"] = raw["gap_summary"]
        if raw.get("interviewer_vo_summary"):
            out_psd["interviewer_vo_summary"] = raw["interviewer_vo_summary"]
        return out_psd
    if stage_key in (
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "highlight_selection",
        "transitions",
        "sound_design_plan_flow1",
        "podcast_sfx_brief",
        "sfx_brief",
    ):
        return _slim_flow_input(raw, stage_key)
    return _drop_heavy_keys(raw)


def _slim_flow_input(raw: dict[str, Any], stage_key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "content_brief" in raw:
        out["content_brief"] = _compact_brief(raw["content_brief"])
    if "segments" in raw:
        max_count = 120 if stage_key == "full_master_ranking" else 80
        out["segments"] = _compact_segments(raw["segments"], max_count=max_count)
    if "coverage_audit" in raw:
        out["coverage_audit"] = _compact_coverage_audit(raw["coverage_audit"])
    if "narrative_plan" in raw:
        out["narrative_plan"] = raw["narrative_plan"]
    if "gap_report" in raw:
        out["gap_report"] = _compact_gap_report(raw["gap_report"])
    if "selection" in raw:
        out["selection"] = _compact_selection(raw["selection"], stage_key)
    if "transitions" in raw and stage_key in ("podcast_sfx_brief", "sound_design_plan_flow1"):
        out["transitions"] = raw["transitions"]
    if "interviewer_sample_lines" in raw and stage_key == "transitions":
        out["interviewer_sample_lines"] = raw["interviewer_sample_lines"]
    if "highlights" in raw:
        out["highlights"] = raw["highlights"]
    return out


def _compact_coverage_audit(audit: Any) -> Any:
    if not isinstance(audit, dict):
        return audit
    return {
        "topic_mappings": audit.get("topic_mappings"),
        "claim_mappings": (audit.get("claim_mappings") or [])[:20],
        "missing_coverage": audit.get("missing_coverage"),
        "orphan_segment_ids": audit.get("orphan_segment_ids"),
        "coverage_score": audit.get("coverage_score"),
    }


def _compact_gap_report(report: Any) -> Any:
    if not isinstance(report, dict):
        return report
    lines = report.get("interviewer_lines") or []
    return {
        "interviewer_lines": [
            {
                "line_id": ln.get("line_id"),
                "gap_type": ln.get("gap_type"),
                "text": ln.get("text"),
                "targets_segment_id": ln.get("targets_segment_id"),
                "placement": ln.get("placement"),
                "delivery": ln.get("delivery"),
            }
            for ln in lines[:40]
            if isinstance(ln, dict)
        ]
    }


def _compact_selection(sel: Any, stage_key: str) -> Any:
    if not isinstance(sel, dict):
        return sel
    if stage_key == "highlight_selection" or "highlights" in sel:
        return {
            "highlights": sel.get("highlights"),
            "reel_thesis": sel.get("reel_thesis"),
        }
    return {
        "ordered_segment_ids": sel.get("ordered_segment_ids"),
        "chapters": sel.get("chapters"),
        "excluded_segment_ids": sel.get("excluded_segment_ids"),
        "notes": (sel.get("notes") or "")[:500],
    }


def _compact_brief(brief: Any) -> Any:
    if not isinstance(brief, dict):
        return brief
    return {
        "thesis": brief.get("thesis"),
        "audience": brief.get("audience"),
        "topics": brief.get("topics"),
        "key_claims": (brief.get("key_claims") or [])[:15],
        "jargon_glossary": (brief.get("jargon_glossary") or [])[:12],
    }


def _compact_segments(segments: Any, *, max_count: int = 60, for_gaps: bool = False) -> Any:
    if isinstance(segments, dict):
        segs = segments.get("segments") or []
    elif isinstance(segments, list):
        segs = segments
    else:
        return segments
    max_seg = _char_limit("max_segments_in_context", max_count)
    text_max = _char_limit("segment_text_max_chars", 400)
    slim = []
    for s in segs[:max_seg]:
        if not isinstance(s, dict):
            continue
        slim.append(
            {
                "segment_id": s.get("segment_id"),
                "start_ms": s.get("start_ms"),
                "end_ms": s.get("end_ms"),
                "type": s.get("type"),
                "speaker_role": s.get("speaker_role"),
                "topic_tags": s.get("topic_tags"),
                "flags": s.get("flags"),
                "text": _clip_text(s.get("text", ""), text_max),
            }
        )
    return {"segments": slim}


def _compact_segments_for_gaps(raw: dict[str, Any]) -> Any:
    evals = (raw.get("gap_evaluations") or {}).get("evaluations") or []
    need_ids = {e.get("segment_id") for e in evals if not e.get("self_explanatory")}
    segs = raw.get("segments")
    if isinstance(segs, dict):
        all_segs = segs.get("segments") or []
    else:
        all_segs = segs or []
    filtered = [s for s in all_segs if isinstance(s, dict) and s.get("segment_id") in need_ids]
    if not filtered:
        filtered = all_segs[: _char_limit("max_segments_in_gap_pass", 35)]
    return _compact_segments({"segments": filtered}, for_gaps=True)


def _filter_gap_evaluations(ev: Any) -> Any:
    if not isinstance(ev, dict):
        return ev
    evaluations = ev.get("evaluations") or []
    # Prefer non-OK segments; cap list size
    bad = [e for e in evaluations if not e.get("self_explanatory")]
    ok = [e for e in evaluations if e.get("self_explanatory")]
    cap = _char_limit("max_gap_evaluations", 50)
    return {"evaluations": (bad + ok)[:cap]}


def _clip_transcript_for_segments(transcript: Any) -> Any:
    if isinstance(transcript, dict) and transcript.get("items"):
        return {"items": transcript["items"][:500]}
    return _clip_text(_extract_transcript_text({"transcript": transcript}), 8000)


def _extract_transcript_text(raw: dict[str, Any]) -> str:
    tr = raw.get("transcript")
    if isinstance(tr, str):
        return tr
    if isinstance(tr, dict):
        return str(tr.get("text", ""))
    return str(raw.get("transcript_excerpt", ""))


def _clip_text(text: Any, limit: int) -> str:
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[:limit] + "\n…[truncated]"


def transcript_quality_for_ctx(ctx: RunContext) -> dict[str, Any] | None:
    """Low-confidence STT regions for content/boundary stages."""
    if not ctx.artifact_exists("transcript/review_queue.json"):
        return None
    try:
        queue = ctx.read_json("transcript/review_queue.json")
    except Exception:
        return None
    chunks = queue.get("chunks") or []
    flagged = [
        {
            "chunk_id": c.get("chunk_id"),
            "start_ms": c.get("start_ms"),
            "end_ms": c.get("end_ms"),
            "confidence": c.get("confidence"),
            "text": _clip_text(c.get("text", ""), 120),
        }
        for c in chunks
        if c.get("needs_review") or (c.get("confidence") or 1) < queue.get("low_confidence_threshold", 0.85)
    ][:25]
    if not flagged:
        return None
    return {
        "low_confidence_threshold": queue.get("low_confidence_threshold", 0.85),
        "flagged_chunks": flagged,
        "note": "Lower confidence on flagged regions — avoid inventing facts; flag uncertainty in artifacts.",
    }


def interviewer_sample_lines(ctx: RunContext, *, limit: int | None = None) -> list[str]:
    """Short interviewer utterances from manifest for tone-matching transitions."""
    cap = limit or _char_limit("interviewer_sample_lines", 8)
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    try:
        manifest = ctx.read_json("segments/manifest.json")
        speakers = {}
        if ctx.artifact_exists("understanding/speakers.json"):
            for sp in ctx.read_json("understanding/speakers.json").get("speakers") or []:
                speakers[sp.get("speaker_id")] = sp.get("role")
        lines: list[str] = []
        for seg in manifest.get("segments") or []:
            if speakers.get(seg.get("speaker_id")) != "interviewer" and seg.get("speaker_role") != "interviewer":
                continue
            if seg.get("type") not in (
                "interviewer_question",
                "setup",
                "interviewer_reaction",
            ):
                continue
            text = (seg.get("text") or "").strip()
            if 3 <= len(text.split()) <= 25:
                lines.append(text)
            if len(lines) >= cap:
                break
        return lines
    except Exception:
        return []


def _drop_heavy_keys(raw: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in raw.items():
        if k == "transcript" and isinstance(v, (dict, str)):
            out[k] = _clip_text(_extract_transcript_text({k: v}), 8000)
        else:
            out[k] = v
    return out
