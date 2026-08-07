"""
Authoritative catalog of every LLM interaction (OpenAI + local MLX).

Mirrored by docs/cross-cutting/llm-interaction-catalog.md.
CI: tests/test_llm_interaction_registry_complete.py
"""

from __future__ import annotations

from typing import Any, Literal

from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

Provider = Literal["openai", "local_mlx"]

# stage_key -> primary catalog id (OA-* / OF-*)
STAGE_PRIMARY_IDS: dict[str, str] = {
    "speaker_roles": "OA-01",
    "content_context": "OA-02",
    "talking_points_compose": "OA-09",
    "ideal_cuts_propose": "OA-10",
    "boundary_detection": "OA-03",
    "boundary_topic_resplit": "OA-03",
    "segment_classification": "OA-04",
    "content_brief_reanchor": "OA-05",
    "sound_design_palettes": "OA-06",
    "missing_framing": "OA-07",
    "gap_framing_compose": "OA-08",
    "optimal_questions": "OA-08",
    "topic_coverage_audit": "OF-01",
    "narrative_arc_plan": "OF-02",
    "full_master_ranking": "OF-03",
    "transitions": "OF-04",
    "sound_design_plan": "OF-05",
    "edl_narrative_audit": "OF-06",
    "sfx_prompt_craft": "OF-07",
    "podcast_sfx_brief": "OF-L1",
    "sfx_brief": "OF-L2",
    "sfx_prompt_refine": "OF-L3",
    "junction_feel_audit": "OH-J1",
}

SPECIALIST_IDS: dict[str, str] = {
    "comprehension_risk_blind": "OS-01",
    "theme_coverage_pass": "OS-02",
    "emphasis_coverage_pass": "OS-03",
    "stt_lexicon_island_verify": "OS-04",
}

META_TASK_IDS: dict[str, str] = {
    "primary": "OM-01",
}

LOCAL_FRAMER_IDS: dict[str, str] = {
    "primary": "LX-01a",
    "shard": "LX-01b",
    "collate": "LX-01c",
    "specialist": "LX-01d",
}

def _entry(
    *,
    id: str,
    provider: Provider,
    interaction: str,
    stage_key: str,
    task_kind: str,
    trigger: str,
    entrypoint: str,
    prompt_rel: str,
    volley_profile: str,
    response_schema: str,
    verify: str,
    on_verify_fail: str,
    goal: str,
    model_tier: str = "standard",
) -> dict[str, Any]:
    return {
        "id": id,
        "provider": provider,
        "interaction": interaction,
        "stage_key": stage_key,
        "task_kind": task_kind,
        "trigger": trigger,
        "entrypoint": entrypoint,
        "prompt_rel": prompt_rel,
        "volley_profile": volley_profile,
        "response_schema": response_schema,
        "verify": verify,
        "on_verify_fail": on_verify_fail,
        "goal": goal,
        "model_tier": model_tier,
    }

def _build_registry() -> dict[str, dict[str, Any]]:
    reg: dict[str, dict[str, Any]] = {}

    _OA_META = {
        "speaker_roles": ("understanding.run_speaker_roles", "understanding/speaker-roles.system.txt", "full", "flagship"),
        "content_context": ("understanding.run_content_context", "understanding/content-context.system.txt", "full/shard/collate", "standard"),
        "talking_points_compose": ("understanding.run_talking_points_compose", "understanding/talking-points-compose.system.txt", "full/shard/collate", "standard"),
        "ideal_cuts_propose": ("understanding.run_ideal_cuts_propose", "understanding/ideal-cuts-propose.system.txt", "full/shard/collate", "standard"),
        "boundary_detection": ("segmentation.run_boundaries", "segmentation/boundary-detection.system.txt", "full/shard/collate", "standard"),
        "boundary_topic_resplit": ("segmentation.run_boundary_topic_resplit", "segmentation/boundary-detection-refine.system.txt", "full/shard/collate", "standard"),
        "segment_classification": ("segmentation.run_classification", "segmentation/segment-classification.system.txt", "full/shard/collate", "standard"),
        "content_brief_reanchor": ("understanding.run_content_brief_reanchor", "understanding/content-brief-reanchor.system.txt", "full/shard/collate", "standard"),
        "sound_design_palettes": ("sound_design_stages.run_sound_design_palettes", "sound_design/theme-palettes.system.txt", "full", "standard"),
        "missing_framing": ("gaps.run_missing_framing", "interviewer-gap/missing-framing.system.txt", "full/shard/collate", "standard"),
        "gap_framing_compose": ("gaps.run_gap_framing_compose", "interviewer-gap/gap-framing-compose.system.txt", "full", "standard"),
        "optimal_questions": ("gaps.run_gap_framing_compose", "interviewer-gap/gap-framing-compose.system.txt", "full", "standard"),
    }
    for sk, (ep, prompt, volley, tier) in _OA_META.items():
        cid = STAGE_PRIMARY_IDS[sk]
        schema = STAGE_ARTIFACT_SCHEMAS.get(sk, "")
        reg[cid] = _entry(
            id=cid,
            provider="openai",
            interaction=f"{sk}_primary",
            stage_key=sk,
            task_kind="primary",
            trigger=f"pipeline ANALYSIS_ORDER — {sk}",
            entrypoint=ep,
            prompt_rel=prompt,
            volley_profile=volley,
            response_schema=f"composed/envelope+{schema}",
            verify="validate_envelope + validate_stage_artifacts",
            on_verify_fail="volley_retry",
            goal=_OA_GOALS.get(sk, sk),
            model_tier=tier,
        )

    _OF_META = {
        "topic_coverage_audit": ("analysis_extended.run_topic_coverage", "selection/topic-coverage-audit", "full/shard/collate"),
        "narrative_arc_plan": ("analysis_extended.run_narrative_arc", "selection/narrative-arc-plan", "full"),
        "full_master_ranking": ("selection.run_full_master_ranking", "selection/full-master-ranking", "full/shard/collate"),
        "transitions": ("selection.run_transitions", "assembly/transitions", "full"),
        "sound_design_plan": ("sound_design_stages.run_sound_design_plan", "sound_design/plan-flow1", "full"),
        "edl_narrative_audit": ("edl_narrative_audit.run_edl_narrative_audit", "selection/edl-narrative-audit", "full"),
        "sfx_prompt_craft": ("sound_design_stages.run_sfx_prompt_craft", "sound_design/sfx-prompt-craft", "full"),
        "podcast_sfx_brief": ("selection.run_podcast_sfx_brief", "selection/podcast-sfx-brief", "full"),
        "sfx_prompt_refine": ("sound_design_stages.run_sfx_prompt_refine", "sound_design/sfx-prompt-refine", "full"),
    }
    for sk, (ep, prompt, volley) in _OF_META.items():
        cid = STAGE_PRIMARY_IDS[sk]
        schema = STAGE_ARTIFACT_SCHEMAS.get(sk, "")
        reg[cid] = _entry(
            id=cid,
            provider="openai",
            interaction=f"{sk}_primary",
            stage_key=sk,
            task_kind="primary",
            trigger=f"pipeline FLOW — {sk}",
            entrypoint=ep,
            prompt_rel=prompt,
            volley_profile=volley,
            response_schema=f"composed/envelope+{schema}",
            verify="validate_envelope + validate_stage_artifacts",
            on_verify_fail="volley_retry",
            goal=_OF_GOALS.get(sk, sk),
        )

    reg["OM-01"] = _entry(
        id="OM-01",
        provider="openai",
        interaction="primary",
        stage_key="*",
        task_kind="primary",
        trigger="Every stage attempt default path",
        entrypoint="llm_simple.run_llm_stage_simple",
        prompt_rel="(per stage)",
        volley_profile="full",
        response_schema="composed envelope+artifact",
        verify="validate_envelope + validate_stage_artifacts",
        on_verify_fail="volley_retry",
        goal="Produce stage artifacts",
        model_tier="flagship|standard|economy",
    )

    for sk, cid in SPECIALIST_IDS.items():
        reg[cid] = _entry(
            id=cid,
            provider="openai",
            interaction=sk,
            stage_key=f"{{parent}}__{sk}",
            task_kind="specialist",
            trigger="maybe_run_*_specialists",
            entrypoint="llm_specialists",
            prompt_rel=f"_shared/specialists/{sk.replace('_', '-')}.system.txt",
            volley_profile="shard",
            response_schema=f"specialists/{sk}.schema.json",
            verify="envelope + specialist artifact",
            on_verify_fail="blocked",
            goal=_OS_GOALS[sk],
            model_tier="economy",
        )

    reg["LX-01"] = _entry(
        id="LX-01",
        provider="local_mlx",
        interaction="local_framer",
        stage_key="(parent)",
        task_kind="local_*",
        trigger="local_llm.enabled + should_frame_task_kind",
        entrypoint="local_volley_framer.prepare_volley_for_llm",
        prompt_rel="_shared/local-volley-framer.system.txt",
        volley_profile="pre-OpenAI",
        response_schema="local_framer_response.schema.json",
        verify="local_framer_response schema",
        on_verify_fail="fail_open",
        goal="Compress volley; set escalate",
        model_tier="local",
    )
    for tk, lid in LOCAL_FRAMER_IDS.items():
        reg[lid] = {**reg["LX-01"], "id": lid, "task_kind": f"local_{tk}"}

    reg["OM-F01"] = _entry(
        id="OM-F01",
        provider="openai",
        interaction="field_fabricate_batch",
        stage_key="*",
        task_kind="fabricate",
        trigger="llm_output_normalizer — fabricatable null paths",
        entrypoint="llm_fabricate.fabricate_field_values",
        prompt_rel="llm-fabricate/generic.system.txt",
        volley_profile="batched field patch",
        response_schema="artifacts partial",
        verify="validate_stage_artifacts",
        on_verify_fail="normalize_then_verify",
        goal="Benign fabricated values for low-risk null fields",
        model_tier="mid",
    )

    for cid, meta in _OH_META.items():
        entrypoint, prompt, schema, tier, goal, interaction = meta
        reg[cid] = _entry(
            id=cid,
            provider="openai",
            interaction=interaction,
            stage_key="mastering",
            task_kind="primary",
            trigger="Mastering quality-hardening gate (mode != off)",
            entrypoint=entrypoint,
            prompt_rel=prompt,
            volley_profile="full",
            response_schema=schema,
            verify="validate_envelope + artifact schema",
            on_verify_fail="volley_retry",
            goal=goal,
            model_tier=tier,
        )

    return reg

# Mastering quality-hardening interactions (docs/cross-cutting/mastering-quality-hardening.md).
# id -> (entrypoint, prompt_rel, response_schema, model_tier, goal, interaction)
_OH_META: dict[str, tuple[str, str, str, str, str, str]] = {
    "OH-02": (
        "mastering_shape_gates.emit_eval_rubric",
        "mastering/eval-rubric-mint.system.txt",
        "mastering_eval_rubric.schema.json",
        "flagship",
        "Per-run style rubric every critic scores against",
        "eval_rubric_mint",
    ),
    "OH-03": (
        "mastering_semantic_integrity.merge_llm_findings",
        "mastering/semantic-integrity.system.txt",
        "mastering_semantic_integrity.schema.json",
        "standard",
        "Confirm or clear deterministic fabrication flags",
        "semantic_integrity_confirm",
    ),
    "OH-C1": (
        "mastering_critics.build_critic_packets",
        "mastering/critics/narrative-editor.system.txt",
        "mastering_critic_report.schema.json",
        "standard",
        "L4 critic — arc, clarity, information conveyance",
        "critic_narrative_editor",
    ),
    "OH-C2": (
        "mastering_critics.build_critic_packets",
        "mastering/critics/engagement-listener.system.txt",
        "mastering_critic_report.schema.json",
        "standard",
        "L4 critic — hook strength, momentum, fatigue",
        "critic_engagement_listener",
    ),
    "OH-C3": (
        "mastering_critics.build_critic_packets",
        "mastering/critics/audio-intelligibility.system.txt",
        "mastering_critic_report.schema.json",
        "standard",
        "L4 critic — masking, ducking, loudness swings",
        "critic_audio_intelligibility",
    ),
    "OH-C4": (
        "mastering_critics.build_critic_packets",
        "mastering/critics/integrity.system.txt",
        "mastering_critic_report.schema.json",
        "standard",
        "L4 critic — fabrication; the only hard-fail critic",
        "critic_integrity",
    ),
    "OH-C5": (
        "mastering_critics.build_critic_packets",
        "mastering/critics/pacing-repetition.system.txt",
        "mastering_critic_report.schema.json",
        "standard",
        "L4 critic — density, dead air, repeated gestures",
        "critic_pacing_repetition",
    ),
    "OH-C6": (
        "mastering_critics.build_critic_packets",
        "mastering/critics/style-fit.system.txt",
        "mastering_critic_report.schema.json",
        "standard",
        "L4 critic — fit against the per-run rubric",
        "critic_style_fit",
    ),
    "OH-A1": (
        "mastering_critics.merge_panel",
        "mastering/critics/l4-arbiter.system.txt",
        "mastering_cross_critique.schema.json",
        "flagship",
        "Merge the critic panel; enforce integrity kills",
        "l4_arbiter",
    ),
    "OH-J1": (
        "junction_snip_qa.run_junction_feel_audit",
        "mastering/junction-feel-audit.system.txt",
        "junction_feel_audit.schema.json",
        "standard",
        "Single final feel audit of assembled master junctions",
        "junction_feel_audit",
    ),
}

_OA_GOALS: dict[str, str] = {
    "speaker_roles": "Map diarization IDs → interviewer/interviewee",
    "content_context": "Thesis, topics, key_claims",
    "talking_points_compose": "Holistic must/should-keep talking points",
    "ideal_cuts_propose": "Ideal native cut windows per talking point",
    "boundary_detection": "Non-overlapping segment timeline",
    "boundary_topic_resplit": "Topic-aligned resplit of overloaded segments",
    "segment_classification": "Type every required segment_id",
    "content_brief_reanchor": "Anchor topics to segment_ids",
    "sound_design_palettes": "Palettes + sonic identity",
    "missing_framing": "Per-segment gap eval",
    "gap_framing_compose": "Framing script (questions, summaries, prefaces)",
    "optimal_questions": "VO lines for record gaps",
}

_OF_GOALS: dict[str, str] = {
    "topic_coverage_audit": "Theme coverage score",
    "narrative_arc_plan": "Chapter arc",
    "full_master_ranking": "Ordered segment_ids",
    "transitions": "Short bridge VO",
    "sound_design_plan": "Cues + assets flow1",
    "edl_narrative_audit": "Narrative QC verdict",
    "sfx_prompt_craft": "MMAudio prompt rows",
    "podcast_sfx_brief": "v1 SFX brief (legacy)",
    "sfx_brief": "Montage brief (legacy)",
    "sfx_prompt_refine": "Patch failed asset prompts",
}

_OS_GOALS: dict[str, str] = {
    "comprehension_risk_blind": "Blind comprehension risk scores",
    "theme_coverage_pass": "Fix unmapped topic tags",
    "emphasis_coverage_pass": "Acoustic emphasis vs beats",
    "stt_lexicon_island_verify": "Soft prefer-include for STT lexicon/code-switch/passion islands",
}

LLM_INTERACTION_REGISTRY: dict[str, dict[str, Any]] = _build_registry()

def resolve_interaction_id(
    *,
    stage_key: str,
    task_kind: str,
    record_stage_key: str | None = None,
    volley_retry_index: int = 0,
    provider: Provider = "openai",
) -> str:
    """Map a gateway call to catalog id.

    `volley_retry_index` is accepted for gateway call compatibility; v2 has no
    collate-retry id to distinguish, so every retry keeps the primary id.
    """
    if provider == "local_mlx":
        tk = task_kind.removeprefix("local_") if task_kind.startswith("local_") else task_kind
        return LOCAL_FRAMER_IDS.get(tk, "LX-01")

    if task_kind == "specialist":
        sk = resolve_specialist_key_from_stage(stage_key)
        if sk and sk in SPECIALIST_IDS:
            return SPECIALIST_IDS[sk]
        return "OS-01"

    parent = record_stage_key or stage_key
    if parent in STAGE_PRIMARY_IDS:
        return STAGE_PRIMARY_IDS[parent]
    return "OM-01"

def resolve_specialist_key_from_stage(stage_key: str) -> str | None:
    if "__" not in stage_key:
        return None
    return stage_key.split("__", 1)[1]

def all_openai_stage_keys() -> frozenset[str]:
    return frozenset(STAGE_ARTIFACT_SCHEMAS.keys())

def registry_ids() -> frozenset[str]:
    return frozenset(LLM_INTERACTION_REGISTRY.keys())

def expected_gateway_sites() -> dict[str, tuple[str, ...]]:
    """Call-site patterns enforced by CI (module.function)."""
    return {
        "run_prompt_envelope": (
            "llm_specialists",
            "llm_runner",
            "llm_simple",
            "junction_snip_qa",
            "podcast_publish",
            "timeline_optimizer",
        ),
        "generate_local_chat": (
            "local_volley_framer",
            "local_llm_runner",
        ),
    }
