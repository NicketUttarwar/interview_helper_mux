"""Refinement pass catalog — blacklist default deny, whitelist consider, succession."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.refinement_identity import register_builtin_cfis

register_builtin_cfis()

ELIGIBLE_CLASS_VOCAB = frozenset(
    {
        "gap_vo",
        "narrative",
        "ranking",
        "transitions",
        "sdp_intent",
        "edl_narrative",
        "cold_open",
    }
)

# pass_id -> catalog row
PASS_CATALOG: list[dict[str, Any]] = [
    {
        "pass_id": "gap_framing_recompose",
        "class_id": "gap_vo",
        "stage_id": "gap_framing_recompose",
        "insert_after": "full_master_ranking",
        "refines_pass_id": "gap_framing_compose",
        "required_artifacts": [
            "understanding/gap_report.draft.json",
            "master/selection.json",
        ],
        "semantic_role": "recompose",
        "listener_rationale": "Host VO against kept order",
    },
    {
        "pass_id": "selection_framing_apply",
        "class_id": "gap_vo",
        "stage_id": "selection_framing_apply",
        "insert_after": "gap_framing_recompose",
        "refines_pass_id": None,
        "required_artifacts": ["understanding/gap_framing_plan.json", "master/selection.json"],
        "semantic_role": "apply",
        "listener_rationale": "Apply framing excludes after recompose",
    },
    {
        "pass_id": "narrative_arc_refine",
        "class_id": "narrative",
        "stage_id": "narrative_arc_refine",
        "insert_after": "gap_framing_recompose",
        "refines_pass_id": "narrative_arc_plan",
        "required_artifacts": ["master/narrative_plan.json", "master/selection.json"],
        "semantic_role": "refine",
        "listener_rationale": "Chapters match what will air",
    },
    {
        "pass_id": "ranking_refine",
        "class_id": "ranking",
        "stage_id": "ranking_refine",
        "insert_after": "gap_framing_recompose",
        "refines_pass_id": "full_master_ranking",
        "required_artifacts": ["master/selection.json", "master/coverage_audit.json"],
        "semantic_role": "refine",
        "listener_rationale": "Topic survival and pacing",
    },
    {
        "pass_id": "transitions_refine",
        "class_id": "transitions",
        "stage_id": "transitions_refine",
        "insert_after": "transitions",
        "refines_pass_id": "transitions",
        "required_artifacts": ["master/transitions.json", "understanding/gap_report.json"],
        "semantic_role": "refine",
        "listener_rationale": "No duplicate host bridges",
    },
    {
        "pass_id": "sdp_intent_refine",
        "class_id": "sdp_intent",
        "stage_id": "sdp_intent_refine",
        "insert_after": "sound_design_plan",
        "refines_pass_id": "sound_design_plan",
        "required_artifacts": ["understanding/sound_design_plan.json"],
        "semantic_role": "refine",
        "listener_rationale": "SFX restraint for final timeline",
    },
    {
        "pass_id": "edl_narrative_refine",
        "class_id": "edl_narrative",
        "stage_id": "edl_narrative_refine",
        "insert_after": "edl_narrative_audit",
        "refines_pass_id": "edl_narrative_audit",
        "required_artifacts": ["master/edl_narrative_audit.json"],
        "semantic_role": "refine",
        "listener_rationale": "Last editorial sanity before EDL",
    },
]

_DEFAULT_BLACKLIST_STAGES = [
    "audio_preclean",
    "ingest",
    "transcribe",
    "transcript_review_build",
    "transcript_review",
    "source_acoustic_profile",
    "interview_spine_build",
    "sonic_context_build",
    "edl",
    "assembly_preview",
    "mmaudio_sfx",
    "mix",
    "master_finalize",
    "master_transcript_build",
    "g1_vo_pickup",
    "vo_ingest",
]

_DEFAULT_BLACKLIST_PREFIXES = [
    "interview_mux.stages.sfx_mmaudio",
    "interview_mux.stages.mastering",
    "interview_mux.stages.audio_preclean",
    "interview_mux.stages.ingest",
    "interview_mux.stages.transcribe_local",
]

_DEFAULT_WHITELIST = [p["pass_id"] for p in PASS_CATALOG]


def refinement_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    raw = analysis.get("refinement_passes")
    defaults: dict[str, Any] = {
        "enabled": True,
        "max_second_runs_per_cfi": 1,
        # Off by default — ASSETS/refinement_priors/priors.json never lands in
        # Full-auto; opt in via analysis.refinement_passes.priors.enabled.
        "priors": {"enabled": False},
        "shadow_score": {"enabled": True},
        "full_auto": True,
        "blacklist": {
            "stage_ids": list(_DEFAULT_BLACKLIST_STAGES),
            "cfi_ids": [],
            "module_path_prefixes": list(_DEFAULT_BLACKLIST_PREFIXES),
        },
        "whitelist": {"pass_ids": ["gap_framing_recompose", "selection_framing_apply"]},
        "succession": {
            "unlocks": [],
            "mutex": [],
            "priority": [
                "gap_framing_recompose",
                "selection_framing_apply",
            ],
        },
    }
    if isinstance(raw, dict):
        out = {**defaults, **raw}
        bl = dict(defaults["blacklist"])
        if isinstance(raw.get("blacklist"), dict):
            bl.update(raw["blacklist"])
        out["blacklist"] = bl
        wl = dict(defaults["whitelist"])
        if isinstance(raw.get("whitelist"), dict):
            wl.update(raw["whitelist"])
        out["whitelist"] = wl
        return out
    return defaults


def get_pass(pass_id: str) -> dict[str, Any] | None:
    for row in PASS_CATALOG:
        if row["pass_id"] == pass_id:
            return dict(row)
    return None


def passes_after(insert_after: str) -> list[dict[str, Any]]:
    return [dict(p) for p in PASS_CATALOG if p.get("insert_after") == insert_after]


def is_blacklisted(
    *,
    stage_id: str | None = None,
    cfi_id: str | None = None,
    module_path: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> bool:
    block = refinement_cfg(cfg).get("blacklist") or {}
    if stage_id and stage_id in set(block.get("stage_ids") or []):
        return True
    if cfi_id and cfi_id in set(block.get("cfi_ids") or []):
        return True
    if module_path:
        for prefix in block.get("module_path_prefixes") or []:
            if module_path.startswith(str(prefix)):
                return True
    return False


def is_whitelisted(pass_id: str, cfg: dict[str, Any] | None = None) -> bool:
    if is_blacklisted(stage_id=pass_id, cfg=cfg):
        return False
    allowed = set((refinement_cfg(cfg).get("whitelist") or {}).get("pass_ids") or [])
    return pass_id in allowed


def class_for_pass(pass_id: str) -> str | None:
    row = get_pass(pass_id)
    return str(row["class_id"]) if row else None
