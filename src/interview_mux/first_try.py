"""First-try reliability mode — cold-start friction collapse helpers.

Never auto-approves write staging silently. Defers mid-phase Save pauses
and auto-clears clean gates when configured.
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config

ANALYSIS_PHASE_STAGES = frozenset(
    {
        "audio_preclean",
        "ingest",
        "transcribe",
        "transcript_review_build",
        "disfluency_extract",
        "source_acoustic_profile",
        "interview_spine_build",
        "speaker_roles",
        "source_topology_build",
        "content_context",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
        "delivery_brief_build",
        "soundscape_policy_build",
        "episode_structure_compose",
    }
)

DELIVERY_PHASE_STAGES = frozenset(
    {
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan",
        "sound_design_vo_finalize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "master_finalize",
    }
)

BLOCKING_G1_SEVERITIES_DEFAULT = frozenset({"high", "critical"})


def journey_ui_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg or merged_config()
    ju = resolved.get("journey_ui") or {}
    return ju if isinstance(ju, dict) else {}


def first_try_mode_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(journey_ui_cfg(cfg).get("first_try_mode", True))


def defer_write_approval_until(cfg: dict[str, Any] | None = None) -> str:
    """Return 'phase_end' | 'off'."""
    ju = journey_ui_cfg(cfg)
    raw = ju.get("defer_write_approval_until")
    if raw in ("phase_end", "off", "never"):
        if raw == "never":
            return "off"
        return str(raw)
    if first_try_mode_enabled(cfg):
        return "phase_end"
    return "off"


def write_approval_deferred(cfg: dict[str, Any] | None = None) -> bool:
    """True when mid-stage write-approval pauses are deferred to phase end."""
    if not bool(journey_ui_cfg(cfg).get("require_write_approval_per_stage", True)):
        return False
    return defer_write_approval_until(cfg) == "phase_end"


def preclean_auto_dismiss_when_green(cfg: dict[str, Any] | None = None) -> bool:
    ju = journey_ui_cfg(cfg)
    if "preclean_auto_dismiss_when_green" in ju:
        return bool(ju.get("preclean_auto_dismiss_when_green"))
    return first_try_mode_enabled(cfg)


def batch_save_phases(cfg: dict[str, Any] | None = None) -> list[str]:
    ju = journey_ui_cfg(cfg)
    raw = ju.get("batch_save_phases")
    if isinstance(raw, list) and raw:
        return [str(x) for x in raw]
    return ["analysis", "delivery"]


def stage_phase(stage_id: str) -> str | None:
    if stage_id in ANALYSIS_PHASE_STAGES:
        return "analysis"
    if stage_id in DELIVERY_PHASE_STAGES:
        return "delivery"
    return None


def segmentation_unified_review_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(journey_ui_cfg(cfg).get("segmentation_unified_review", True))


def should_pause_for_write_approval(stage_id: str, cfg: dict[str, Any] | None = None) -> bool:
    """Whether finishing this stage should raise write-approval pause.

    When deferred, only phase-boundary stages pause (caller may also batch).
    Unified segmentation review defers boundary_detection until segment_classification.
    """
    if not bool(journey_ui_cfg(cfg).get("require_write_approval_per_stage", True)):
        return False
    if segmentation_unified_review_enabled(cfg):
        if stage_id == "boundary_detection":
            return False
        if stage_id == "segment_classification":
            return True
    if not write_approval_deferred(cfg):
        return True
    # Under deferral, intermediate stages do not pause; phase-end batch Save handles commit.
    return False


def transcript_review_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg or merged_config()
    tr = resolved.get("transcript_review") or {}
    return tr if isinstance(tr, dict) else {}


def transcript_auto_complete_when_clean(cfg: dict[str, Any] | None = None) -> bool:
    tr = transcript_review_cfg(cfg)
    if "auto_complete_when_clean" in tr:
        return bool(tr.get("auto_complete_when_clean"))
    return first_try_mode_enabled(cfg)


def low_confidence_threshold(cfg: dict[str, Any] | None = None) -> float:
    tr = transcript_review_cfg(cfg)
    try:
        return float(tr.get("low_confidence_threshold", 0.85))
    except (TypeError, ValueError):
        return 0.85


def g1_blocking_severities(cfg: dict[str, Any] | None = None) -> frozenset[str]:
    resolved = cfg or merged_config()
    analysis = resolved.get("analysis") or {}
    g1 = analysis.get("g1") if isinstance(analysis, dict) else {}
    if not isinstance(g1, dict):
        return BLOCKING_G1_SEVERITIES_DEFAULT
    raw = g1.get("blocking_severities")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).lower() for x in raw)
    return BLOCKING_G1_SEVERITIES_DEFAULT


def line_severity(line: dict[str, Any]) -> str:
    """Normalize gap line severity; missing on delivery=record ⇒ high."""
    sev = str(line.get("severity") or "").strip().lower()
    if sev:
        return sev
    if str(line.get("delivery") or "").lower() == "record":
        return "high"
    return "medium"


def line_requires_vo(line: dict[str, Any], cfg: dict[str, Any] | None = None) -> bool:
    if str(line.get("delivery") or "").lower() != "record":
        return False
    if line.get("blocking") is False:
        return False
    if line.get("blocking") is True:
        return True
    if line.get("skipped_optional"):
        return False
    return line_severity(line) in g1_blocking_severities(cfg)


def first_try_triage_overrides(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Optional overrides under analysis.first_try.artifact_issue_triage."""
    if not first_try_mode_enabled(cfg):
        return {}
    resolved = cfg or merged_config()
    analysis = resolved.get("analysis") or {}
    ft = analysis.get("first_try") if isinstance(analysis, dict) else {}
    if not isinstance(ft, dict):
        return {}
    triage = ft.get("artifact_issue_triage")
    return triage if isinstance(triage, dict) else {}


def sfx_one_regen_on_fail(cfg: dict[str, Any] | None = None) -> bool:
    resolved = cfg or merged_config()
    sd = resolved.get("sound_design") or {}
    if isinstance(sd, dict) and "one_regen_on_fail" in sd:
        return bool(sd.get("one_regen_on_fail"))
    mm = resolved.get("mmaudio") or {}
    if isinstance(mm, dict) and "first_try_one_regen" in mm:
        return bool(mm.get("first_try_one_regen"))
    return first_try_mode_enabled(cfg)


def allow_placeholder_mix(cfg: dict[str, Any] | None = None) -> bool:
    resolved = cfg or merged_config()
    sd = resolved.get("sound_design") or {}
    if isinstance(sd, dict) and "first_try_allow_placeholder_mix" in sd:
        return bool(sd.get("first_try_allow_placeholder_mix"))
    if bool(sd.get("block_mix_on_mmaudio_qa_fail", False)):
        return False
    return first_try_mode_enabled(cfg)


__all__ = [
    "ANALYSIS_PHASE_STAGES",
    "DELIVERY_PHASE_STAGES",
    "allow_placeholder_mix",
    "batch_save_phases",
    "defer_write_approval_until",
    "first_try_mode_enabled",
    "first_try_triage_overrides",
    "g1_blocking_severities",
    "journey_ui_cfg",
    "line_requires_vo",
    "line_severity",
    "low_confidence_threshold",
    "preclean_auto_dismiss_when_green",
    "sfx_one_regen_on_fail",
    "should_pause_for_write_approval",
    "stage_phase",
    "transcript_auto_complete_when_clean",
    "transcript_review_cfg",
    "write_approval_deferred",
]
