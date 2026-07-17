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
from interview_mux.interview_spine.constants import BOUNDARY_VOLLEY_MAX_SPINE_EVENTS
from interview_mux.coverage_limits import ratio_cap_from_context_key, spread_sample, volley_spine_event_cap, segments_in_context_cap, coherence_risk_cap
from interview_mux.context_selector import maybe_select_context_segments
from interview_mux.stage_enrichment import compact_value_features_summary
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import compact_for_volley as compact_sonic_context

# Pipeline order for "prior conclusions" (assistant turns)
_ANALYSIS_PRIORS = (
    "speaker_roles",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
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
        task_line="Map diarized speaker IDs to roles, conversation profile, and gap sensitivity.",
        prior_stages=(),
        profile_keys=("operator_notes", "conversation_profile", "gap_sensitivity"),
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
    "content_brief_reanchor": StageContextPlan(
        task_line="Re-anchor content brief topics and claims to segment_ids; add topic relationships.",
        prior_stages=("content_context", "segment_classification"),
        profile_keys=("themes", "narrative", "hypotheses"),
        investigation_kinds=frozenset({"theme_unmapped", "topic_drift", "claim_contradiction"}),
        max_investigations=2,
    ),
    "sound_design_palettes": StageContextPlan(
        task_line="Define transcript-grounded sound design coherence and theme palettes.",
        prior_stages=("content_context", "content_brief_reanchor", "segment_classification"),
        profile_keys=("themes", "narrative", "style", "operator_notes"),
        investigation_kinds=frozenset({"theme_unmapped"}),
        max_investigations=2,
    ),
    "missing_framing": StageContextPlan(
        task_line="Evaluate which segments are self-explanatory for listeners; classify gaps only.",
        prior_stages=("segment_classification", "content_brief_reanchor", "content_context"),
        profile_keys=("narrative", "entities", "major_questions", "hypotheses", "gap_sensitivity"),
        investigation_kinds=frozenset({"gap_unresolved", "segment_ambiguity", "topic_drift", "missing_callback"}),
        max_investigations=3,
    ),
    "optimal_questions": StageContextPlan(
        task_line="Write short interviewer VO lines that fix framing gaps.",
        prior_stages=("missing_framing", "content_context"),
        profile_keys=("style", "major_questions", "narrative", "gap_sensitivity"),
        investigation_kinds=frozenset({"gap_unresolved"}),
        max_investigations=2,
    ),
    "topic_coverage_audit": StageContextPlan(
        task_line="Audit topic and claim coverage across segments.",
        prior_stages=(
            "content_context",
            "segment_classification",
            "missing_framing",
            "optimal_questions",
            "delivery_brief_build",
        ),
        profile_keys=("themes", "narrative", "major_questions"),
        investigation_kinds=frozenset({"theme_unmapped", "missing_callback", "topic_drift"}),
        max_investigations=2,
    ),
    "narrative_arc_plan": StageContextPlan(
        task_line="Plan narrative arc, chapters, and ordering constraints.",
        prior_stages=(
            "topic_coverage_audit",
            "optimal_questions",
            "missing_framing",
            "content_context",
            "delivery_brief_build",
        ),
        profile_keys=("themes", "narrative", "style", "major_questions", "hypotheses"),
        investigation_kinds=frozenset({"topic_drift", "missing_callback"}),
        max_investigations=1,
    ),
    "full_master_ranking": StageContextPlan(
        task_line="Order segments for the full podcast master.",
        prior_stages=(
            "narrative_arc_plan",
            "topic_coverage_audit",
            "optimal_questions",
            "missing_framing",
            "delivery_brief_build",
        ),
        profile_keys=("themes", "narrative", "style"),
        max_investigations=0,
    ),
    "transitions": StageContextPlan(
        task_line="Write short interviewer transitions between ordered segments.",
        prior_stages=("full_master_ranking", "optimal_questions", "delivery_brief_build"),
        profile_keys=("style", "narrative"),
        max_investigations=0,
    ),
    "podcast_sfx_brief": StageContextPlan(
        task_line="Specify subtle podcast sound design between chapters/segments.",
        prior_stages=("full_master_ranking", "narrative_arc_plan", "delivery_brief_build"),
        profile_keys=("style",),
        max_investigations=0,
    ),
    "sound_design_plan": StageContextPlan(
        task_line="Plan reusable podcast sound design assets and cue placements.",
        prior_stages=(
            "full_master_ranking",
            "narrative_arc_plan",
            "transitions",
            "optimal_questions",
            "delivery_brief_build",
        ),
        profile_keys=("style", "themes", "narrative"),
        max_investigations=0,
    ),
    "edl_narrative_audit": StageContextPlan(
        task_line="Audit whether the planned EDL preserves narrative arc, coverage, transitions, and VO gap clarity.",
        prior_stages=(
            "full_master_ranking",
            "narrative_arc_plan",
            "topic_coverage_audit",
            "transitions",
            "missing_framing",
            "sound_design_plan",
            "delivery_brief_build",
        ),
        profile_keys=("style", "themes", "narrative", "major_questions"),
        max_investigations=1,
    ),
    "sfx_prompt_craft": StageContextPlan(
        task_line="Craft one MMAudio text-to-audio prompt per asset_id (positive + negative + mix role).",
        prior_stages=("sound_design_plan", "delivery_brief_build"),
        profile_keys=("style", "themes", "narrative"),
        max_investigations=0,
    ),
    "sfx_prompt_refine": StageContextPlan(
        task_line="Refine failed MMAudio prompts for specific asset_ids using QA and listen feedback.",
        prior_stages=("sfx_prompt_craft",),
        profile_keys=("style", "themes", "narrative"),
        max_investigations=0,
    ),
}


def _context_cfg() -> dict[str, Any]:
    return (merged_config().get("analysis") or {}).get("context") or {}


def _char_limit(key: str, default: int, *, field_clip: bool = False) -> int:
    from interview_mux.truncation_policy import apply_context_cap_boost

    base = int(_context_cfg().get(key, default))
    # Field clips (segment/transcript excerpts) participate in clear-field escalation.
    clip_keys = {
        "segment_text_max_chars",
        "transcript_excerpt_chars",
        "transcript_full_chars",
        "speaker_roles_sample_chars",
        "classification_excerpt_max_chars",
        "max_stage_data_chars",
    }
    return apply_context_cap_boost(
        base,
        field_clip=field_clip or key in clip_keys,
    )


def plan_for_stage(stage_key: str, ctx: RunContext | None = None) -> StageContextPlan:
    if ctx is not None:
        try:
            from interview_mux.context_resolver import context_index_enabled, load_context_index

            if context_index_enabled():
                idx = load_context_index(ctx, write=False)
                raw = (idx.get("stage_plans") or {}).get(stage_key)
                if raw:
                    return StageContextPlan(
                        task_line=str(raw.get("task_line") or f"Complete stage: {stage_key}."),
                        prior_stages=tuple(raw.get("prior_stages") or ()),
                        profile_keys=tuple(raw.get("profile_keys") or ()),
                        investigation_kinds=frozenset(raw.get("investigation_kinds") or []),
                        max_investigations=int(raw.get("max_investigations", 2)),
                    )
        except Exception:
            pass
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
    max_stage_data_chars_override: int | None = None,
) -> list[dict[str, str]]:
    """
    Build OpenAI messages: system (from caller) + user/assistant volley + final user task.

    Prior work is synthetic assistant prose; only this stage's raw data appears in the last user turn.
    """
    plan = plan_for_stage(stage_key, ctx)
    state = load_analysis_state(ctx)
    messages: list[dict[str, str]] = []

    resolved = None
    try:
        from interview_mux.context_resolver import resolve_volley_context

        resolved = resolve_volley_context(
            ctx, stage_key, stage_input, profile=profile, task_kind="primary"
        )
    except Exception:
        resolved = None
    use_index = bool(resolved and resolved.get("use_index") and resolved.get("middle_turns"))

    if profile == "collate" and stage_input.get("mode") == "collate":
        messages.extend(_build_collate_volley(ctx, stage_key, plan, stage_input, state))
        return messages

    messages.append(
        {
            "role": "user",
            "content": (
                f"## Current task\n{plan.task_line}\n\n"
                f"Volley profile: {profile}\n\n"
                "Below is established context from earlier steps (read only). "
                "Your reply must be one JSON **envelope** object with keys: "
                "status, artifacts, memory_updates, needs, follow_up_investigations, "
                "confidence, reasoning_summary."
            ),
        }
    )

    if profile == "shard":
        parent_line = _parent_reasoning_one_liner(ctx, stage_key)
        if parent_line:
            messages.append({"role": "assistant", "content": parent_line})

    if use_index and resolved:
        messages.extend(resolved["middle_turns"])
    else:
        prior_stages = plan.prior_stages if profile == "full" else plan.prior_stages[:1]
        prior_text = _format_prior_conclusions(ctx, prior_stages, state)
        if prior_text:
            messages.append({"role": "assistant", "content": prior_text})

        profile_text = _format_profile_slice(state, plan.profile_keys)
        if profile_text and profile == "full":
            verified = (state.get("meta") or {}).get("operator_verified")
            label = "Operator-verified profile" if verified else "Interview profile (draft — may refine)"
            messages.append({"role": "user", "content": f"## {label}\n{profile_text}"})

        inv_plan = plan if profile == "full" else StageContextPlan(task_line=plan.task_line, max_investigations=0)
        inv_text = _format_investigations(ctx, stage_key, inv_plan)
        if inv_text:
            messages.append({"role": "user", "content": inv_text})

    shaped = _shape_stage_input(stage_key, stage_input)
    upstream_note = _upstream_resilience_summary(ctx, stage_key)
    if upstream_note:
        shaped = {**shaped, "upstream_resilience": upstream_note}
    from interview_mux.null_field_policy import null_policy_enabled, strip_null_leaves_for_volley

    if null_policy_enabled():
        shaped = strip_null_leaves_for_volley(shaped)
    gap_fc = shaped.get("gap_fill_context") if isinstance(shaped.get("gap_fill_context"), dict) else None
    data_block = json.dumps(shaped, indent=2, ensure_ascii=False)
    max_data = max_stage_data_chars_override or _char_limit("max_stage_data_chars", 32000)
    if len(data_block) > max_data:
        data_block = data_block[:max_data] + "\n…[stage data truncated]"

    from interview_mux.required_response_format import volley_format_footer

    format_footer = volley_format_footer(
        stage_key,
        profile=profile,
        task_kind="primary",
        gap_fill_context=gap_fc,
    )
    messages.append(
        {
            "role": "user",
            "content": (
                f"## Input data for this stage only\n"
                f"Use this as the primary evidence for `{stage_key}`. "
                f"Do not assume facts not present here or in established context above.\n\n"
                f"```json\n{data_block}\n```\n\n"
                f"{format_footer}"
            ),
        }
    )

    return messages


def _build_collate_volley(
    ctx: RunContext,
    stage_key: str,
    plan: StageContextPlan,
    stage_input: dict[str, Any],
    state: dict[str, Any],
) -> list[dict[str, str]]:
    """One assistant turn per shard summary, then merge instruction + compact shard payloads."""
    messages: list[dict[str, str]] = []
    shard_outputs = stage_input.get("shard_outputs") or []
    messages.append(
        {
            "role": "user",
            "content": (
                f"## Collate task\n{plan.task_line}\n\n"
                f"Merge {len(shard_outputs)} shard result(s) into one JSON envelope for `{stage_key}`. "
                "Read each shard summary below, then produce a single coherent artifact set."
            ),
        }
    )
    for idx, shard in enumerate(shard_outputs, start=1):
        env = shard.get("envelope") if isinstance(shard.get("envelope"), dict) else {}
        artifacts = env.get("artifacts") or {}
        counts = {k: len(v) if isinstance(v, list) else 1 for k, v in artifacts.items()}
        label = shard.get("label") or f"shard_{idx}"
        from interview_mux.segment_timeline_standard import format_shard_identity

        identity = format_shard_identity(shard if isinstance(shard, dict) else {}, stage_key, env)
        summary = env.get("reasoning_summary") or "(no summary)"
        messages.append(
            {
                "role": "assistant",
                "content": (
                    f"**Shard {label}** — {identity}\n"
                    f"Summary: {summary}\n"
                    f"Artifact keys: {list(artifacts.keys())}; counts: {counts}"
                ),
            }
        )
    prior_text = _format_prior_conclusions(ctx, plan.prior_stages, state)
    if prior_text:
        messages.append({"role": "user", "content": prior_text})

    compact_shards = []
    for shard in shard_outputs:
        env = shard.get("envelope") if isinstance(shard.get("envelope"), dict) else {}
        compact_shards.append(
            {
                "label": shard.get("label"),
                "segment_ids": shard.get("segment_ids"),
                "status": env.get("status"),
                "artifacts": env.get("artifacts"),
            }
        )
    data_block = json.dumps(
        {"shard_outputs": compact_shards, "instruction": stage_input.get("instruction")},
        indent=2,
        ensure_ascii=False,
    )
    max_data = _char_limit("max_stage_data_chars", 32000)
    if len(data_block) > max_data:
        data_block = data_block[:max_data] + "\n…[stage data truncated]"
    from interview_mux.required_response_format import volley_format_footer

    format_footer = volley_format_footer(stage_key, profile="collate", task_kind="collate")
    messages.append(
        {
            "role": "user",
            "content": (
                f"## Shard payloads to merge\n"
                f"```json\n{data_block}\n```\n\n"
                f"{format_footer}"
            ),
        }
    )
    return messages


def _parent_reasoning_one_liner(ctx: RunContext, stage_key: str) -> str:
    """Parent attempt reasoning for shard profile.

    Skips blocked/truncation summaries so shard retries are not polluted by prior
    hard-blocks (which themselves contain truncation markers).
    """
    base = ctx.path("understanding", "stage_runs", stage_key)
    if not base.is_dir():
        return ""
    attempts = sorted(base.glob("attempt_*.json"), reverse=True)
    skip_tokens = (
        "truncated llm input",
        "truncation hard-block",
        "collate skipped",
        "evidence truncated",
    )
    for path in attempts:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            env = doc.get("envelope") or {}
            if str(env.get("status") or "").strip() == "blocked":
                continue
            summary = (env.get("reasoning_summary") or "").strip()
            if not summary:
                continue
            low = summary.lower()
            if any(tok in low for tok in skip_tokens):
                continue
            return f"## Parent pass context\n{summary[:500]}"
        except Exception:
            continue
    return ""


def volley_char_estimate(messages: list[dict[str, str]]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


def truncation_flags_for_volley(messages: list[dict[str, str]]) -> list[str]:
    from interview_mux.truncation_policy import MARKER_FLAG_MAP

    flags: list[str] = []
    joined = "\n".join(m.get("content", "") for m in messages)
    for marker, flag in MARKER_FLAG_MAP.items():
        if marker in joined and flag not in flags:
            flags.append(flag)
    return flags


def apply_local_framing_to_volley(
    base_volley: list[dict[str, str]],
    framed_turns: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    Replace middle turns (prior conclusions, profile, investigations) with local-framed turns.
    Keeps the first user turn (task) and last user turn (stage evidence) when present.
    """
    if not framed_turns or not base_volley:
        return base_volley
    clean: list[dict[str, str]] = []
    for turn in framed_turns:
        role = str(turn.get("role", "")).strip().lower()
        content = str(turn.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            clean.append({"role": role, "content": content})
    if not clean:
        return base_volley
    if len(base_volley) == 1:
        return [*base_volley, *clean]
    first = base_volley[0]
    last = base_volley[-1]
    if first.get("role") == "user" and last.get("role") == "user" and len(base_volley) >= 2:
        return [first, *clean, last]
    return [first, *clean, *base_volley[1:]]


def _summary_from_accepted_attempt(
    ctx: RunContext,
    stage: str,
    accepted: dict[str, Any],
) -> str:
    attempt_n = accepted.get(stage) if isinstance(accepted, dict) else None
    if not attempt_n:
        return ""
    base = ctx.path("understanding", "stage_runs", stage)
    path = base / f"attempt_{int(attempt_n):03d}.json"
    if not path.is_file():
        return ""
    try:
        from interview_mux.analysis_memory import should_merge_envelope

        doc = json.loads(path.read_text(encoding="utf-8"))
        env = doc.get("envelope") or {}
        arbiter_result = doc.get("arbiter_result") or {}
        routing = env.get("_routing_meta") or {}
        routed_via_collate = bool(doc.get("routed_via_collate") or routing.get("routed_via_collate"))
        if not should_merge_envelope(arbiter_result, env, routed_via_collate=routed_via_collate):
            return ""
        return (env.get("reasoning_summary") or "")[:500]
    except Exception:
        return ""


def _format_prior_conclusions(
    ctx: RunContext,
    prior_stages: tuple[str, ...],
    state: dict[str, Any],
) -> str:
    if not prior_stages:
        return ""
    summaries = (state.get("meta") or {}).get("stage_summaries") or {}
    accepted = (state.get("meta") or {}).get("last_accepted_attempt") or {}
    lines = ["## Established conclusions from earlier pipeline steps", ""]
    for stage in prior_stages:
        if stage in summaries and summaries[stage]:
            lines.append(f"**{stage.replace('_', ' ').title()}:** {summaries[stage]}")
            continue
        from_attempt = _summary_from_accepted_attempt(ctx, stage, accepted)
        if from_attempt:
            lines.append(f"**{stage.replace('_', ' ').title()}:** {from_attempt}")
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
            profile = doc.get("conversation_profile") or {}
            fc = profile.get("format_class_candidate")
            hyp_count = len(doc.get("conversation_hypotheses") or [])
            suffix = ""
            if fc:
                suffix = f"; format={fc}"
            if hyp_count:
                suffix += f"; {hyp_count} hypothesis(es)"
            return ("Speakers: " + ", ".join(parts) if parts else "") + suffix
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
        if stage == "sound_design_palettes" and ctx.artifact_exists("understanding/sound_design_plan.json"):
            sdp = ctx.read_json("understanding/sound_design_plan.json")
            coh = sdp.get("coherence") if isinstance(sdp.get("coherence"), dict) else {}
            palettes = sdp.get("palettes") or []
            mood = coh.get("primary_mood", "")
            density = coh.get("density", "")
            labels = [
                p.get("theme_label", "")
                for p in palettes[:4]
                if isinstance(p, dict) and p.get("theme_label")
            ]
            return (
                f"{len(palettes)} palette(s); mood={mood or '?'}, density={density or '?'}"
                + (f"; themes: {', '.join(labels)}" if labels else "")
            )
        if stage == "missing_framing" and ctx.artifact_exists("understanding/gap_evaluations.json"):
            ev = ctx.read_json("understanding/gap_evaluations.json")
            evals = ev.get("evaluations") or []
            bad = sum(1 for e in evals if not e.get("self_explanatory"))
            return f"{bad}/{len(evals)} segments need framing."
        if stage == "topic_coverage_audit" and ctx.artifact_exists("master/coverage_audit.json"):
            c = ctx.read_json("master/coverage_audit.json")
            missing = len(c.get("missing_coverage") or [])
            return f"Coverage score {c.get('coverage_score', '?')}; {missing} gaps."
        if stage == "narrative_arc_plan" and ctx.artifact_exists("master/narrative_plan.json"):
            p = ctx.read_json("master/narrative_plan.json")
            return (p.get("arc_summary") or "")[:300]
        if stage == "optimal_questions" and ctx.artifact_exists("understanding/gap_report.json"):
            rep = ctx.read_json("understanding/gap_report.json")
            lines = rep.get("interviewer_lines") or []
            record = sum(1 for ln in lines if ln.get("delivery") == "record")
            return f"{len(lines)} interviewer VO lines ({record} to record)."
        if stage == "full_master_ranking" and ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
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
    if "hypotheses" in keys:
        hyps = state.get("hypotheses") or []
        open_hyps = [h for h in hyps if isinstance(h, dict) and h.get("status") == "open"]
        if open_hyps:
            lines.append(
                "Open hypotheses: "
                + "; ".join(
                    f"{h.get('id', '')}: {str(h.get('statement', ''))[:80]}"
                    for h in open_hyps[:6]
                )
            )
    if "conversation_profile" in keys:
        cp = state.get("conversation_profile") or {}
        bits = []
        if cp.get("format_class_candidate"):
            bits.append(f"format={cp['format_class_candidate']}")
        if cp.get("tone_class_candidate"):
            bits.append(f"tone={cp['tone_class_candidate']}")
        if cp.get("format_confidence") is not None:
            bits.append(f"format_confidence={cp['format_confidence']}")
        if bits:
            lines.append("Conversation profile: " + ", ".join(bits))
        conv_hyps = state.get("conversation_hypotheses") or []
        if conv_hyps:
            lines.append(
                "Conversation hypotheses: "
                + "; ".join(
                    f"{h.get('id', '')} ({h.get('format_class', '')})"
                    for h in conv_hyps[:4]
                    if isinstance(h, dict)
                )
            )
    if "gap_sensitivity" in keys:
        gs = state.get("gap_sensitivity") or {}
        if gs.get("notes"):
            lines.append(f"Gap sensitivity: {str(gs['notes'])[:200]}")
        pri = gs.get("priority_gap_types") or []
        if pri:
            lines.append("Priority gap types: " + ", ".join(str(x) for x in pri[:6]))
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


def _upstream_resilience_summary(ctx: RunContext, stage_key: str) -> dict[str, Any] | None:
    """Note when immediate upstream artifact was saved in degraded partial mode."""
    from interview_mux.llm_flow_hardening import producer_artifact_path, resolve_llm_upstream_stage

    upstream = resolve_llm_upstream_stage(ctx, stage_key)
    if not upstream:
        return None
    rel = producer_artifact_path(upstream)
    if not rel or not ctx.artifact_exists(rel):
        return None
    raw = ctx.read_json(rel)
    if not isinstance(raw, dict):
        return None
    resilience = (raw.get("_meta") or {}).get("resilience")
    if not isinstance(resilience, dict) or not resilience.get("partial"):
        return None
    report = resilience.get("report") if isinstance(resilience.get("report"), dict) else {}
    return {
        "upstream_stage": upstream,
        "artifact_path": rel,
        "summary": resilience.get("summary") or report.get("summary"),
        "stripped_count": resilience.get("stripped_count"),
        "generated_count": resilience.get("generated_count"),
        "kept_paths": resilience.get("kept_paths") or report.get("kept_paths"),
    }


def _shape_stage_input(stage_key: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Strip fields each stage does not need — avoid shipping full transcript everywhere."""
    if stage_key == "speaker_roles":
        samples = raw.get("transcript_samples")
        if isinstance(samples, dict) and samples:
            clipped = {
                k: _clip_text(v, _char_limit("speaker_roles_sample_chars", 24000) // max(len(samples), 1))
                for k, v in samples.items()
                if v
            }
            return {"transcript_samples": clipped, "speakers": raw.get("speakers")}
        return {
            "transcript_excerpt": _clip_text(
                raw.get("transcript_excerpt") or _extract_transcript_text(raw),
                _char_limit("transcript_excerpt_chars", 24000),
            ),
            "speakers": raw.get("speakers"),
        }
    if stage_key == "content_context":
        out_cc: dict[str, Any] = {
            "transcript": _clip_text(
                raw.get("transcript") or _extract_transcript_text(raw),
                _char_limit("transcript_full_chars", 72000),
            ),
        }
        if raw.get("transcript_quality"):
            out_cc["transcript_quality"] = raw["transcript_quality"]
        if raw.get("interview_spine"):
            out_cc["interview_spine"] = _compact_interview_spine(raw["interview_spine"], stage_key)
        return out_cc
    if stage_key == "content_brief_reanchor":
        out_ra: dict[str, Any] = {
            "content_brief": _compact_brief(raw.get("content_brief")),
            "segments": _compact_segments(raw.get("segments"), max_count=100),
            "speakers": raw.get("speakers"),
        }
        if raw.get("boundaries"):
            out_ra["boundaries"] = raw.get("boundaries")
        if raw.get("coherence_summary"):
            out_ra["coherence_summary"] = _compact_coherence_summary(raw["coherence_summary"], stage_key)
        return out_ra
    if stage_key == "boundary_detection":
        out: dict[str, Any] = {
            "speakers": raw.get("speakers"),
            "content_brief": _compact_brief(raw.get("content_brief")),
        }
        tr = raw.get("transcript")
        if isinstance(tr, dict):
            out["transcript"] = {
                "text": _clip_text(tr.get("text", ""), _char_limit("transcript_full_chars", 72000)),
                "items": tr.get("items"),
            }
        else:
            out["transcript"] = _clip_text(tr, _char_limit("transcript_full_chars", 72000))
        if raw.get("transcript_quality"):
            out["transcript_quality"] = raw["transcript_quality"]
        if raw.get("pause_ladder_hints"):
            out["pause_ladder_hints"] = raw["pause_ladder_hints"]
        sap = raw.get("source_acoustic_profile")
        if isinstance(sap, dict):
            pacing = sap.get("pacing") if isinstance(sap.get("pacing"), dict) else {}
            if pacing.get("pace_class"):
                out["source_acoustic_profile"] = {"pacing": {"pace_class": pacing["pace_class"]}}
        if raw.get("interview_spine"):
            out["interview_spine"] = _compact_interview_spine(raw["interview_spine"], stage_key)
        vf = raw.get("value_features_summary") or compact_value_features_summary_from_raw(raw)
        if vf:
            out["value_features_summary"] = vf
        for key in ("itr_repair_hint", "lint_retry_hint", "lint_feedback"):
            if raw.get(key):
                out[key] = raw.get(key)
        return out
    if stage_key == "segment_classification":
        from interview_mux.classification_obligation import classification_context_cfg

        out: dict[str, Any] = {
            "boundaries": raw.get("boundaries"),
            "speakers": raw.get("speakers"),
            "content_brief": _compact_brief(raw.get("content_brief")),
        }
        if classification_context_cfg().get("classification_obligation_enabled", True):
            if raw.get("classification_obligation"):
                out["classification_obligation"] = raw.get("classification_obligation")
            if raw.get("classification_obligation_retry"):
                out["classification_obligation_retry"] = raw.get("classification_obligation_retry")
        else:
            out["transcript"] = _clip_transcript_for_segments(raw.get("transcript"))
        if raw.get("interview_spine"):
            out["interview_spine"] = _compact_interview_spine(raw["interview_spine"], stage_key)
        if raw.get("lint_retry_hint"):
            out["lint_retry_hint"] = raw.get("lint_retry_hint")
        return out
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
        sap = _compact_source_acoustic_profile(raw.get("source_acoustic_profile"))
        if sap:
            out_sdp["source_acoustic_profile"] = sap
        sonic = raw.get("sonic_context")
        if isinstance(sonic, dict) and sonic:
            out_sdp["sonic_context"] = sonic
        catalog = raw.get("palette_keyword_catalog")
        if isinstance(catalog, list) and catalog:
            out_sdp["palette_keyword_catalog"] = catalog
        if raw.get("lint_retry_hint"):
            out_sdp["lint_retry_hint"] = raw.get("lint_retry_hint")
        if raw.get("lint_feedback"):
            out_sdp["lint_feedback"] = raw.get("lint_feedback")
        return out_sdp
    if stage_key == "missing_framing":
        out_mf: dict[str, Any] = {
            "content_brief": _compact_brief(raw.get("content_brief")),
            "segments": _compact_segments(raw.get("segments"), for_gaps=True),
        }
        if raw.get("comprehension_risks"):
            out_mf["comprehension_risks"] = raw["comprehension_risks"][:25]
        if raw.get("interview_spine"):
            out_mf["interview_spine"] = _compact_interview_spine(raw["interview_spine"], stage_key)
        if raw.get("coherence_summary"):
            out_mf["coherence_summary"] = _compact_coherence_summary(raw["coherence_summary"], stage_key)
        return out_mf
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
        if raw.get("coherence_summary"):
            out_psd["coherence_summary"] = _compact_coherence_summary(raw["coherence_summary"], stage_key)
        return out_psd
    if stage_key in (
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "highlight_selection",
        "transitions",
        "sound_design_plan",
        "sound_design_plan_flow2",
        "podcast_sfx_brief",
        "sfx_brief",
    ):
        return _slim_flow_input(raw, stage_key)
    if stage_key in ("sfx_prompt_craft", "sfx_prompt_refine"):
        return _slim_sfx_input(raw, stage_key)
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
    if "delivery_brief" in raw:
        from interview_mux.delivery_brief import compact_delivery_brief_for_volley

        compact = compact_delivery_brief_for_volley(raw.get("delivery_brief"))
        if compact:
            out["delivery_brief"] = compact
    if "selection" in raw:
        out["selection"] = _compact_selection(raw["selection"], stage_key)
    if "sound_design_plan" in raw and stage_key in ("sound_design_plan", "sound_design_plan_flow2"):
        out["sound_design_plan"] = _compact_sound_design_plan_for_flow(raw["sound_design_plan"])
        if "sonic_context" in raw and isinstance(raw["sonic_context"], dict):
            compact = compact_sonic_context(raw["sonic_context"])
            if compact:
                out["sonic_context"] = compact
    if "transitions" in raw and stage_key in ("podcast_sfx_brief", "sound_design_plan"):
        out["transitions"] = raw["transitions"]
    if "interviewer_sample_lines" in raw and stage_key == "transitions":
        out["interviewer_sample_lines"] = raw["interviewer_sample_lines"]
    if "highlights" in raw:
        out["highlights"] = raw["highlights"]
    if raw.get("emphasis_regions") and stage_key in ("topic_coverage_audit", "narrative_arc_plan"):
        out["emphasis_regions"] = raw["emphasis_regions"][:24]
    if raw.get("quotability_signals") and stage_key == "highlight_selection":
        out["quotability_signals"] = raw["quotability_signals"][:30]
    if raw.get("interview_spine") and stage_key in (
        "highlight_selection",
        "full_master_ranking",
        "missing_framing",
        "content_context",
        "segment_classification",
    ):
        out["interview_spine"] = _compact_interview_spine(raw["interview_spine"], stage_key)
    vf = raw.get("value_features_summary")
    if vf:
        out["value_features_summary"] = vf
    if stage_key in ("missing_framing", "optimal_questions") and raw.get("value_features_summary"):
        out["value_features_summary"] = raw["value_features_summary"]
    if stage_key in ("sound_design_plan", "sound_design_plan_flow2"):
        sap = raw.get("source_acoustic_profile")
        if isinstance(sap, dict):
            out["source_acoustic_profile"] = sap
    if stage_key in ("podcast_sfx_brief", "sfx_brief"):
        sap = raw.get("source_acoustic_profile")
        if isinstance(sap, dict):
            out["source_acoustic_profile"] = sap
    if raw.get("coherence_summary") and stage_key in (
        "topic_coverage_audit",
        "narrative_arc_plan",
    ):
        out["coherence_summary"] = _compact_coherence_summary(raw["coherence_summary"], stage_key)
    return out


def _compact_coherence_summary(summary: Any, stage_key: str) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    risks = summary.get("risks") or []
    if isinstance(risks, list):
        cap = coherence_risk_cap(len(risks))
        risks = spread_sample(risks, cap, time_key=lambda r: int(r.get("time_ms") or 0) if isinstance(r, dict) else 0)
    return {
        "activated": bool(summary.get("activated")),
        "summary": summary.get("summary") or {},
        "risks": risks,
    }


def _slim_sfx_input(raw: dict[str, Any], stage_key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "coherence" in raw:
        out["coherence"] = raw.get("coherence")
    if stage_key == "sfx_prompt_craft":
        out["assets"] = raw.get("assets") or []
    if stage_key == "sfx_prompt_refine":
        out["failed_assets"] = raw.get("failed_assets") or []
        out["mmaudio_qa"] = raw.get("mmaudio_qa") or []
        out["listen_results"] = raw.get("listen_results") or []
    sap = _compact_source_acoustic_profile(raw.get("source_acoustic_profile"))
    if sap:
        out["source_acoustic_profile"] = sap
    if "sonic_context" in raw and isinstance(raw["sonic_context"], dict):
        compact = compact_sonic_context(raw["sonic_context"])
        if compact:
            out["sonic_context"] = compact
    if raw.get("operator_style_sound_design_notes"):
        out["operator_style_sound_design_notes"] = raw.get("operator_style_sound_design_notes")
    return out


def compact_value_features_summary_from_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    vf = raw.get("value_features_summary")
    return vf if isinstance(vf, dict) else None


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


def _compact_sound_design_plan_for_flow(plan: Any) -> dict[str, Any]:
    """Palettes + coherence for flow plan stages (assets/cues are stage output)."""
    if not isinstance(plan, dict):
        return {}
    return {
        "version": plan.get("version", 1),
        "coherence": plan.get("coherence", {}),
        "palettes": plan.get("palettes", []),
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


def _compact_interview_spine(spine: Any, stage_key: str) -> dict[str, Any]:
    if not isinstance(spine, dict):
        return {}
    max_events = volley_spine_event_cap(
        len(spine.get("top_boundary_events") or spine.get("boundary_events") or []),
    )
    stage_caps = {
        "boundary_detection": max_events,
        "segment_classification": 10,
        "missing_framing": 15,
        "content_context": 8,
        "highlight_selection": 12,
        "full_master_ranking": 10,
    }
    max_events = min(max_events, stage_caps.get(stage_key, 8))
    windows = spine.get("windows_sample") or spine.get("windows") or []
    if isinstance(windows, list):
        windows = spread_sample(
            windows,
            min(5, len(windows)),
            time_key=lambda w: int(w.get("start_ms") or 0) if isinstance(w, dict) else 0,
        )
    events = spine.get("top_boundary_events") or spine.get("boundary_events") or []
    if isinstance(events, list):
        events = spread_sample(
            events,
            max_events,
            time_key=lambda e: int(e.get("start_ms") or e.get("time_ms") or 0) if isinstance(e, dict) else 0,
        )
    stats = spine.get("speaker_stats") or []
    if isinstance(stats, list) and len(stats) > 4:
        stats = stats[:4]
    return {
        "retrieval_enabled": bool(spine.get("retrieval_enabled")),
        "window_count": spine.get("window_count"),
        "windows_sample": windows,
        "top_boundary_events": events,
        "speaker_stats": stats,
    }


def _compact_source_acoustic_profile(profile: Any) -> dict[str, Any] | None:
    """Slice pacing + mix contract for palette stage volley (~500 token budget)."""
    from interview_mux.acoustic_profile import compact_for_volley

    if not isinstance(profile, dict):
        return None
    out = compact_for_volley(profile)
    if not out:
        return None
    energy = profile.get("energy") if isinstance(profile.get("energy"), dict) else {}
    tokens = profile.get("prompt_tokens") if isinstance(profile.get("prompt_tokens"), dict) else {}
    pacing = profile.get("pacing") if isinstance(profile.get("pacing"), dict) else {}
    if pacing.get("speech_active_ratio") is not None:
        out["speech_active_ratio"] = pacing["speech_active_ratio"]
    if energy.get("room_timbre_hint"):
        out["room_timbre_hint"] = energy["room_timbre_hint"]
    if tokens:
        out["prompt_tokens"] = {
            k: tokens[k] for k in ("bed_style", "stinger_style", "mix_summary") if k in tokens
        }
    return out or None


def _compact_brief(brief: Any) -> Any:
    if not isinstance(brief, dict):
        return brief
    claims = brief.get("key_claims") or []
    rels = brief.get("topic_relationships") or []
    glossary = brief.get("jargon_glossary") or []
    return {
        "thesis": brief.get("thesis"),
        "audience": brief.get("audience"),
        "topics": brief.get("topics"),
        "key_claims": spread_sample(claims, min(25, len(claims))) if isinstance(claims, list) else claims,
        "topic_relationships": spread_sample(rels, min(20, len(rels))) if isinstance(rels, list) else rels,
        "jargon_glossary": spread_sample(glossary, min(12, len(glossary))) if isinstance(glossary, list) else glossary,
    }


def _compact_segments(segments: Any, *, max_count: int = 60, for_gaps: bool = False, ctx: RunContext | None = None, stage_key: str | None = None) -> Any:
    if isinstance(segments, dict):
        segs = segments.get("segments") or []
    elif isinstance(segments, list):
        segs = segments
    else:
        return segments
    max_seg = segments_in_context_cap(len(segs)) if segs else _char_limit("max_segments_in_context", max_count)
    if ctx is not None and len(segs) > max_seg:
        segs, _meta = maybe_select_context_segments(ctx, segs, cap=max_seg, stage_key=stage_key)
    else:
        segs = spread_sample(
            segs,
            max_seg,
            time_key=lambda s: int(s.get("start_ms") or 0) if isinstance(s, dict) else 0,
        )
    text_max = _char_limit("segment_text_max_chars", 400, field_clip=True)
    slim = []
    for s in segs:
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
        cap = ratio_cap_from_context_key(
            len(all_segs),
            "max_segments_in_gap_pass",
            default_ceiling=50,
            ratio_key="gap_pass_segments_max_ratio",
        )
        filtered = spread_sample(all_segs, cap, time_key=lambda s: int(s.get("start_ms") or 0))
    return _compact_segments({"segments": filtered}, for_gaps=True)


def _filter_gap_evaluations(ev: Any) -> Any:
    if not isinstance(ev, dict):
        return ev
    evaluations = ev.get("evaluations") or []
    # Prefer non-OK segments; cap list size
    bad = [e for e in evaluations if not e.get("self_explanatory")]
    ok = [e for e in evaluations if e.get("self_explanatory")]
    cap = ratio_cap_from_context_key(
        len(bad) + len(ok),
        "max_gap_evaluations",
        default_ceiling=50,
        ratio_key="gap_evaluations_max_ratio",
    )
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
