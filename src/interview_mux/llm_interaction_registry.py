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
    "boundary_detection": "OA-03",
    "segment_classification": "OA-04",
    "content_brief_reanchor": "OA-05",
    "sound_design_palettes": "OA-06",
    "missing_framing": "OA-07",
    "optimal_questions": "OA-08",
    "topic_coverage_audit": "OF-01",
    "narrative_arc_plan": "OF-02",
    "full_master_ranking": "OF-03",
    "transitions": "OF-04",
    "sound_design_plan_flow1": "OF-05",
    "edl_narrative_audit": "OF-06",
    "sfx_prompt_craft": "OF-07",
    "highlight_selection": "OF-08",
    "sound_design_plan_flow2": "OF-09",
    "podcast_show_description": "OF-10",
    "podcast_sfx_brief": "OF-L1",
    "sfx_brief": "OF-L2",
    "sfx_prompt_refine": "OF-L3",
}

SPECIALIST_IDS: dict[str, str] = {
    "comprehension_risk_blind": "OS-01",
    "theme_coverage_pass": "OS-02",
    "emphasis_coverage_pass": "OS-03",
}

META_TASK_IDS: dict[str, str] = {
    "primary": "OM-01",
    "arbiter": "OM-02",
    "shard": "OM-03",
    "collate": "OM-04",
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
        "boundary_detection": ("segmentation.run_boundaries", "segmentation/boundary-detection.system.txt", "full/shard/collate", "standard"),
        "segment_classification": ("segmentation.run_classification", "segmentation/segment-classification.system.txt", "full/shard/collate", "standard"),
        "content_brief_reanchor": ("understanding.run_content_brief_reanchor", "understanding/content-brief-reanchor.system.txt", "full/shard/collate", "standard"),
        "sound_design_palettes": ("sound_design_stages.run_sound_design_palettes", "sound_design/theme-palettes.system.txt", "full", "standard"),
        "missing_framing": ("gaps.run_missing_framing", "interviewer-gap/missing-framing.system.txt", "full/shard/collate", "standard"),
        "optimal_questions": ("gaps.run_optimal_questions", "interviewer-gap/optimal-questions.system.txt", "full", "standard"),
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
        "topic_coverage_audit": ("analysis_flow1_extended.run_topic_coverage", "selection/topic-coverage-audit", "full/shard/collate"),
        "narrative_arc_plan": ("analysis_flow1_extended.run_narrative_arc", "selection/narrative-arc-plan", "full"),
        "full_master_ranking": ("selection_flow1.run_full_master_ranking", "selection/full-master-ranking", "full/shard/collate"),
        "transitions": ("selection_flow1.run_transitions", "assembly/transitions", "full"),
        "sound_design_plan_flow1": ("sound_design_stages.run_sound_design_plan_flow1", "sound_design/plan-flow1", "full"),
        "edl_narrative_audit": ("edl_narrative_audit.run_edl_narrative_audit", "selection/edl-narrative-audit", "full"),
        "sfx_prompt_craft": ("sound_design_stages.run_sfx_prompt_craft", "sound_design/sfx-prompt-craft", "full"),
        "highlight_selection": ("selection_flow2.run_highlight_selection", "selection/highlight-selection", "full/shard/collate"),
        "sound_design_plan_flow2": ("sound_design_stages.run_sound_design_plan_flow2", "sound_design/plan-flow2", "full"),
        "podcast_show_description": ("publishing_flow3.run_podcast_show_description", "publishing/podcast-show-description", "full"),
        "podcast_sfx_brief": ("selection_flow1.run_podcast_sfx_brief", "selection/podcast-sfx-brief", "full"),
        "sfx_brief": ("selection_flow2.run_sfx_brief", "selection/sfx-brief", "full"),
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
        entrypoint="llm_stage_routing.run_llm_stage_with_routing",
        prompt_rel="(per stage)",
        volley_profile="full|shard|collate",
        response_schema="composed envelope+artifact",
        verify="validate_envelope + validate_stage_artifacts",
        on_verify_fail="volley_retry",
        goal="Produce stage artifacts",
        model_tier="flagship|standard|economy",
    )
    reg["OM-02"] = _entry(
        id="OM-02",
        provider="openai",
        interaction="arbiter",
        stage_key="_arbiter",
        task_kind="arbiter",
        trigger="After primary parse",
        entrypoint="llm_arbiter.run_llm_arbiter",
        prompt_rel="_shared/arbiter.system.txt",
        volley_profile="single user blob",
        response_schema="arbiter_verdict.schema.json",
        verify="arbiter_verdict schema",
        on_verify_fail="enqueue_investigation",
        goal="accept / uptier / decompose / investigate",
        model_tier="economy",
    )
    reg["OM-03"] = _entry(
        id="OM-03",
        provider="openai",
        interaction="shard",
        stage_key="(parent)",
        task_kind="shard",
        trigger="Decompose verdict or proactive shard",
        entrypoint="llm_subtasks.run_shards_then_collate",
        prompt_rel="(parent prompt)",
        volley_profile="shard",
        response_schema="same as primary",
        verify="validate_envelope + validate_stage_artifacts",
        on_verify_fail="blocked",
        goal="Partial artifact for segment batch",
        model_tier="economy",
    )
    reg["OM-04"] = _entry(
        id="OM-04",
        provider="openai",
        interaction="collate",
        stage_key="(parent)",
        task_kind="collate",
        trigger="After ≥1 shard",
        entrypoint="llm_subtasks.run_shards_then_collate",
        prompt_rel="(parent prompt)",
        volley_profile="collate",
        response_schema="same as primary",
        verify="validate_envelope + validate_stage_artifacts",
        on_verify_fail="collate_retry",
        goal="Merge shard envelopes",
        model_tier="economy",
    )
    reg["OM-05"] = _entry(
        id="OM-05",
        provider="openai",
        interaction="collate_retry",
        stage_key="(parent)",
        task_kind="collate",
        trigger="Collate schema/lint fail",
        entrypoint="llm_subtasks L151",
        prompt_rel="(parent prompt)",
        volley_profile="collate+feedback",
        response_schema="same as primary",
        verify="validate_envelope + validate_stage_artifacts",
        on_verify_fail="blocked",
        goal="Second collate attempt",
        model_tier="economy",
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

    reg["LX-02"] = _entry(
        id="LX-02",
        provider="local_mlx",
        interaction="itr_clarification",
        stage_key="{stage}__itr",
        task_kind="itr",
        trigger="Open blocking issue + local_llm_for_important",
        entrypoint="artifact_clarification_llm.infer_options_local_llm",
        prompt_rel="_shared/specialists/artifact-clarification.system.txt",
        volley_profile="single user blob",
        response_schema="itr_clarification_options.schema.json",
        verify="itr_clarification_options schema",
        on_verify_fail="fail_open",
        goal="Suggest repair options for operator/autopilot",
        model_tier="local",
    )
    reg["LX-02a"] = {**reg["LX-02"], "id": "LX-02a", "trigger": "collect_issues → options empty"}

    return reg


_OA_GOALS: dict[str, str] = {
    "speaker_roles": "Map diarization IDs → interviewer/interviewee",
    "content_context": "Thesis, topics, key_claims",
    "boundary_detection": "Non-overlapping segment timeline",
    "segment_classification": "Type every required segment_id",
    "content_brief_reanchor": "Anchor topics to segment_ids",
    "sound_design_palettes": "Palettes + sonic identity",
    "missing_framing": "Per-segment gap eval",
    "optimal_questions": "VO lines for record gaps",
}

_OF_GOALS: dict[str, str] = {
    "topic_coverage_audit": "Theme coverage score",
    "narrative_arc_plan": "Chapter arc",
    "full_master_ranking": "Ordered segment_ids",
    "transitions": "Short bridge VO",
    "sound_design_plan_flow1": "Cues + assets flow1",
    "edl_narrative_audit": "Narrative QC verdict",
    "sfx_prompt_craft": "MMAudio prompt rows",
    "highlight_selection": "Highlight clips",
    "sound_design_plan_flow2": "Montage SDP",
    "podcast_show_description": "Show blurb",
    "podcast_sfx_brief": "v1 SFX brief (legacy)",
    "sfx_brief": "Montage brief (legacy)",
    "sfx_prompt_refine": "Patch failed asset prompts",
}

_OS_GOALS: dict[str, str] = {
    "comprehension_risk_blind": "Blind comprehension risk scores",
    "theme_coverage_pass": "Fix unmapped topic tags",
    "emphasis_coverage_pass": "Acoustic emphasis vs beats",
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
    """Map a gateway call to catalog id."""
    if provider == "local_mlx":
        if stage_key.endswith("__itr"):
            return "LX-02"
        tk = task_kind.removeprefix("local_") if task_kind.startswith("local_") else task_kind
        return LOCAL_FRAMER_IDS.get(tk, "LX-01")

    if task_kind == "arbiter":
        return "OM-02"
    if task_kind == "shard":
        return "OM-03"
    if task_kind == "collate":
        return "OM-05" if volley_retry_index > 0 else "OM-04"
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
            "llm_stage_routing",
            "llm_subtasks",
            "llm_arbiter",
            "llm_specialists",
            "llm_runner",
        ),
        "generate_local_chat": (
            "local_volley_framer",
            "artifact_clarification_llm",
            "local_llm_runner",
        ),
    }
