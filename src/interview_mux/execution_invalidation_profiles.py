"""Bounded invalidation profiles — allowlisted stage_done clears for remediation ladders."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

STRUCTURAL_DELIVERY_STAGES: tuple[str, ...] = (
    "vo_synthesize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
    "listen_delight_audit",
    "music_palette_compose",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "junction_snip_qa",
    "master_finalize",
)

VO_COVERAGE_HEAL_STAGES: tuple[str, ...] = (
    "vo_synthesize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
)

FORBIDDEN_VO_COVERAGE: frozenset[str] = frozenset(
    {
        "nugget_layup_compose",
        "vo_line_adjudicate",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "listen_delight_audit",
    }
)

FORBIDDEN_VO_CONTRACT_TIER_A: frozenset[str] = frozenset(STRUCTURAL_DELIVERY_STAGES)

VO_CONTRACT_TIER_C_STAGES: tuple[str, ...] = (
    "vo_line_adjudicate",
    "vo_synthesize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
)

VO_CONTRACT_TIER_B_STAGES: tuple[str, ...] = (
    "gap_framing_recompose",
    "gap_framing_compose",
    "vo_line_adjudicate",
    "vo_synthesize",
)

# Analysis consumers of boundaries — never delivery/EDL/mix (B-01 / Wave 0.1).
SEG_RESPLIT_HEAL_STAGES: tuple[str, ...] = (
    "segment_classification",
    "content_brief_reanchor",
    "framing_posture_decide",
    "vernacular_segment_sanitize",
    "low_conf_island_scan",
    "connector_fuse_pass",
    "sonic_context_build",
    "sound_design_palettes",
)

# Hitch ID remap / listen restage — analysis remap window only (B-05).
HITCH_ANALYSIS_REMAP_STAGES: tuple[str, ...] = (
    "segment_classification",
    "content_brief_reanchor",
    "framing_posture_decide",
    "boundary_topic_resplit",
    "vernacular_segment_sanitize",
    "low_conf_island_scan",
    "connector_fuse_pass",
    "sonic_context_build",
    "sound_design_palettes",
    "missing_framing",
    "gap_framing_compose",
    "delivery_brief_build",
    "soundscape_policy_build",
    "episode_structure_compose",
)

FORBIDDEN_HITCH_LATE: frozenset[str] = frozenset(
    {
        "edl",
        "edl_narrative_audit",
        "assembly_preview",
        "mix",
        "mmaudio_sfx",
        "music_palette_compose",
        "sfx_prompt_craft",
        "junction_snip_qa",
        "master_finalize",
        "vo_synthesize",
    }
)

FUSE_JUNCTION_HEAL_STAGES: tuple[str, ...] = (
    "connector_fuse_pass",
    "connector_fuse_pass_pre_ranking",
    "junction_snip_qa",
)

# B-07 axis → producer law (listen_delight_remutate._DIM_STAGES).
DELIGHT_AXIS_STORY_STAGES: tuple[str, ...] = (
    "air_script_seams",
    "transitions",
    "vo_line_adjudicate",
    "edl",
    "mix",
    "listen_delight_audit",
)

DELIGHT_AXIS_CUT_STAGES: tuple[str, ...] = (
    "edl",
    "junction_snip_qa",
    "mix",
    "listen_delight_audit",
)

DELIGHT_AXIS_SONIC_STAGES: tuple[str, ...] = (
    "music_palette_compose",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "sound_design_plan",
    "mix",
    "listen_delight_audit",
)

SHARED_PATH_RESTAMP_STAGES: tuple[str, ...] = (
    "content_context",
    "content_brief_reanchor",
    "boundary_detection",
    "boundary_topic_resplit",
    "sound_design_palettes",
    "sound_design_plan",
)

_INVOCATION_COUNTS_REL = "operator/invalidation_profile_invocations.json"


@dataclass(frozen=True)
class InvalidationProfile:
    profile_id: str
    allowed_clear: tuple[str, ...]
    forbidden_clear: frozenset[str]
    # Empty = never auto-expand. Named intents: "order_fingerprint_mismatch" | "always".
    expand_to_structural_when: str = ""
    archive_allowlist: tuple[str, ...] = ()
    pending_clear: tuple[str, ...] = ()
    max_invocations: int | None = None
    require_fingerprint_flip: bool = False


INVALIDATION_PROFILES: dict[str, InvalidationProfile] = {
    "vo_coverage_heal": InvalidationProfile(
        profile_id="vo_coverage_heal",
        allowed_clear=VO_COVERAGE_HEAL_STAGES,
        forbidden_clear=FORBIDDEN_VO_COVERAGE,
        expand_to_structural_when="order_fingerprint_mismatch",
    ),
    "vo_seated_coverage": InvalidationProfile(
        profile_id="vo_seated_coverage",
        allowed_clear=VO_COVERAGE_HEAL_STAGES,
        forbidden_clear=FORBIDDEN_VO_COVERAGE,
        expand_to_structural_when="order_fingerprint_mismatch",
    ),
    "vo_contract_tier_a": InvalidationProfile(
        profile_id="vo_contract_tier_a",
        allowed_clear=(),
        forbidden_clear=FORBIDDEN_VO_CONTRACT_TIER_A,
    ),
    "vo_contract_tier_b": InvalidationProfile(
        profile_id="vo_contract_tier_b",
        allowed_clear=VO_CONTRACT_TIER_B_STAGES,
        forbidden_clear=frozenset(
            {
                "mix",
                "mmaudio_sfx",
                "music_palette_compose",
                "sfx_prompt_craft",
                "master_finalize",
                "junction_snip_qa",
            }
        ),
        expand_to_structural_when="order_fingerprint_mismatch",
    ),
    "vo_contract_tier_c": InvalidationProfile(
        profile_id="vo_contract_tier_c",
        allowed_clear=VO_CONTRACT_TIER_C_STAGES,
        forbidden_clear=frozenset(
            {
                "nugget_layup_compose",
                "mix",
                "mmaudio_sfx",
                "music_palette_compose",
                "master_finalize",
            }
        ),
        expand_to_structural_when="order_fingerprint_mismatch",
    ),
    "structural_delivery": InvalidationProfile(
        profile_id="structural_delivery",
        allowed_clear=STRUCTURAL_DELIVERY_STAGES,
        forbidden_clear=frozenset({"nugget_layup_compose"}),
        expand_to_structural_when="always",
    ),
    "seg_resplit_heal": InvalidationProfile(
        profile_id="seg_resplit_heal",
        allowed_clear=SEG_RESPLIT_HEAL_STAGES,
        forbidden_clear=frozenset(STRUCTURAL_DELIVERY_STAGES)
        | frozenset(
            {
                "edl",
                "mix",
                "topic_coverage_audit",
                "narrative_arc_plan",
                "full_master_ranking",
                "nugget_layup_compose",
            }
        ),
        # Markers-only for the brief: nested content_brief_reanchor must still
        # read understanding/content_brief.json. Archiving it hollows
        # content_context and seed-order-blocks missing_framing (forensics).
        archive_allowlist=("segments/boundaries.json",),
        pending_clear=SEG_RESPLIT_HEAL_STAGES,
        max_invocations=2,
        require_fingerprint_flip=True,
    ),
    "hitch_id_churn": InvalidationProfile(
        profile_id="hitch_id_churn",
        allowed_clear=HITCH_ANALYSIS_REMAP_STAGES,
        forbidden_clear=FORBIDDEN_HITCH_LATE,
        archive_allowlist=(),
        pending_clear=HITCH_ANALYSIS_REMAP_STAGES,
        max_invocations=1,
        require_fingerprint_flip=True,
    ),
    "hitch_listen_restage": InvalidationProfile(
        profile_id="hitch_listen_restage",
        allowed_clear=HITCH_ANALYSIS_REMAP_STAGES + ("listen_delight_audit",),
        forbidden_clear=FORBIDDEN_HITCH_LATE - {"listen_delight_audit"},
        archive_allowlist=(),
        pending_clear=HITCH_ANALYSIS_REMAP_STAGES,
        max_invocations=1,
        require_fingerprint_flip=True,
    ),
    "fuse_junction_heal": InvalidationProfile(
        profile_id="fuse_junction_heal",
        allowed_clear=FUSE_JUNCTION_HEAL_STAGES,
        forbidden_clear=frozenset(
            {
                "edl",
                "mix",
                "mmaudio_sfx",
                "music_palette_compose",
                "master_finalize",
                "nugget_layup_compose",
                "boundary_detection",
            }
        ),
        pending_clear=FUSE_JUNCTION_HEAL_STAGES,
        max_invocations=8,
        require_fingerprint_flip=True,
    ),
    "delight_axis_story": InvalidationProfile(
        profile_id="delight_axis_story",
        allowed_clear=DELIGHT_AXIS_STORY_STAGES,
        forbidden_clear=frozenset(
            {
                "music_palette_compose",
                "sfx_prompt_craft",
                "mmaudio_sfx",
                "master_finalize",
                "full_master_ranking",
                "nugget_layup_compose",
            }
        ),
        pending_clear=DELIGHT_AXIS_STORY_STAGES,
        max_invocations=3,
        require_fingerprint_flip=True,
    ),
    "delight_axis_cut": InvalidationProfile(
        profile_id="delight_axis_cut",
        allowed_clear=DELIGHT_AXIS_CUT_STAGES,
        forbidden_clear=frozenset(
            {
                "music_palette_compose",
                "sfx_prompt_craft",
                "mmaudio_sfx",
                "air_script_seams",
                "transitions",
                "master_finalize",
            }
        ),
        pending_clear=DELIGHT_AXIS_CUT_STAGES,
        max_invocations=3,
        require_fingerprint_flip=True,
    ),
    "delight_axis_sonic": InvalidationProfile(
        profile_id="delight_axis_sonic",
        allowed_clear=DELIGHT_AXIS_SONIC_STAGES,
        forbidden_clear=frozenset(
            {
                "edl",
                "assembly_preview",
                "air_script_seams",
                "transitions",
                "vo_line_adjudicate",
                "master_finalize",
                "nugget_layup_compose",
            }
        ),
        pending_clear=DELIGHT_AXIS_SONIC_STAGES,
        max_invocations=3,
        require_fingerprint_flip=True,
    ),
    "shared_path_restamp": InvalidationProfile(
        profile_id="shared_path_restamp",
        allowed_clear=SHARED_PATH_RESTAMP_STAGES,
        forbidden_clear=frozenset(STRUCTURAL_DELIVERY_STAGES)
        | frozenset({"edl", "mix", "nugget_layup_compose"}),
        archive_allowlist=(
            "understanding/content_brief.json",
            "segments/boundaries.json",
            "understanding/sound_design_plan.json",
        ),
        pending_clear=SHARED_PATH_RESTAMP_STAGES,
        max_invocations=None,
        require_fingerprint_flip=False,
    ),
}


def resolve_invalidation_profile(
    ctx: RunContext,
    error_class: str,
    *,
    tier: str = "",
) -> InvalidationProfile | None:
    ec = str(error_class or "").strip()
    tier_l = str(tier or "").lower()
    if ec in {"vo_seated_coverage", "edl_vo_coverage_repair"}:
        return INVALIDATION_PROFILES["vo_coverage_heal"]
    if ec == "vo_contract_repair":
        if "tier_b" in tier_l or tier == "tier_b_gap_recompose":
            return INVALIDATION_PROFILES["vo_contract_tier_b"]
        if "tier_c" in tier_l or tier == "tier_c_opening_omit_unseat":
            return INVALIDATION_PROFILES["vo_contract_tier_c"]
        if "tier_a" in tier_l or tier == "tier_a_publish_orientation":
            return INVALIDATION_PROFILES["vo_contract_tier_a"]
        return INVALIDATION_PROFILES["vo_contract_tier_c"]
    if ec == "hitch_listen_restage":
        return INVALIDATION_PROFILES["hitch_listen_restage"]
    if ec in {"hitch_id_churn", "chapter_close_hitch"}:
        return INVALIDATION_PROFILES["hitch_id_churn"]
    return INVALIDATION_PROFILES.get(ec)


def should_expand_to_structural(ctx: RunContext, profile_id: str) -> bool:
    """Expand only when the profile opts in via ``expand_to_structural_when``.

    Hitch / resplit / fuse / delight profiles leave the field empty so a
    vo_coverage fingerprint mismatch cannot auto-nuke them into structural_delivery.
    """
    profile = INVALIDATION_PROFILES.get(str(profile_id or "").strip())
    if profile is None:
        return False
    intent = str(profile.expand_to_structural_when or "").strip()
    if not intent:
        return False
    if intent == "always" or profile.profile_id == "structural_delivery":
        return True
    if intent == "order_fingerprint_mismatch":
        try:
            from interview_mux.delivery_guardrails import (
                fingerprints_match_checkpoint,
                read_checkpoint,
            )

            if read_checkpoint(ctx) and not fingerprints_match_checkpoint(ctx):
                return True
        except Exception:
            pass
    return False


def profile_allows_clear(profile: InvalidationProfile | None, stage_id: str) -> bool:
    if profile is None:
        return True
    sid = str(stage_id or "").strip()
    if sid in profile.forbidden_clear:
        return False
    if not profile.allowed_clear:
        return False
    return sid in profile.allowed_clear


def _read_invocation_counts(ctx: RunContext) -> dict[str, int]:
    if not ctx.artifact_exists(_INVOCATION_COUNTS_REL):
        return {}
    try:
        raw = ctx.read_json(_INVOCATION_COUNTS_REL)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    counts = raw.get("counts") if isinstance(raw.get("counts"), dict) else raw
    out: dict[str, int] = {}
    if isinstance(counts, dict):
        for k, v in counts.items():
            try:
                out[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
    return out


def _bump_invocation_count(ctx: RunContext, profile_id: str) -> int:
    counts = _read_invocation_counts(ctx)
    n = int(counts.get(profile_id) or 0) + 1
    counts[profile_id] = n
    try:
        ctx.write_json(
            _INVOCATION_COUNTS_REL,
            {"version": 1, "counts": counts},
            skip_handoff=True,
        )
    except Exception:
        pass
    return n


def _archive_allowlisted_paths(
    ctx: RunContext,
    allowlist: tuple[str, ...],
    *,
    profile_id: str,
    reason: str = "",
) -> list[str]:
    """Move only allowlisted relative paths into ``.archived/{ts}/``."""
    rels = [str(r).strip().replace("\\", "/") for r in allowlist if str(r).strip()]
    if not rels:
        return []
    to_archive = [rel for rel in rels if ctx.final_path(*rel.split("/")).is_file()]
    if not to_archive:
        return []
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = f".archived/{ts}"
    archive_root = ctx.run_dir / archive_dir
    archive_root.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []
    for rel in to_archive:
        src = ctx.final_path(*rel.split("/"))
        if not src.is_file():
            continue
        dest = archive_root.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        archived.append(rel)
    if not archived:
        if archive_root.is_dir() and not any(archive_root.rglob("*")):
            shutil.rmtree(archive_root, ignore_errors=True)
        return []
    try:
        entry = {
            "profile_id": profile_id,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archive_dir": archive_dir,
            "paths": archived,
            "reason": str(reason or ""),
        }

        def _patch(meta: dict[str, Any]) -> None:
            history = list(meta.get("invalidation_archive") or [])
            history.append(entry)
            meta["invalidation_archive"] = history

        ctx.mutate_run_meta(_patch)
    except Exception:
        pass
    return archived


def apply_bounded_invalidation(
    ctx: RunContext,
    profile_id: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    """Unmark only allowed stages; archive only ``archive_allowlist`` paths.

    Empty ``archive_allowlist`` → markers/pending only (no artifact archive).
    Unknown ``profile_id`` raises ``ValueError`` (never silent ``cleared: []``).
    """
    pid = str(profile_id or "").strip()
    profile = INVALIDATION_PROFILES.get(pid)
    if profile is None:
        raise ValueError(f"unknown invalidation profile_id: {profile_id!r}")

    if should_expand_to_structural(ctx, pid):
        profile = INVALIDATION_PROFILES["structural_delivery"]

    invocation = _bump_invocation_count(ctx, profile.profile_id)
    max_n = profile.max_invocations
    if max_n is not None and invocation > int(max_n):
        return {
            "profile_id": profile.profile_id,
            "cleared": [],
            "forbidden_skipped": [],
            "archived": [],
            "reason": reason,
            "capped": True,
            "invocation": invocation,
            "max_invocations": max_n,
        }

    cleared: list[str] = []
    forbidden_skipped: list[str] = []
    pending_cleared: list[str] = []

    for sid in profile.allowed_clear:
        try:
            from interview_mux.delivery_guardrails import music_clear_blocked

            if music_clear_blocked(ctx, sid, source=profile.profile_id):
                forbidden_skipped.append(sid)
                continue
        except Exception:
            pass
        marker = ctx.run_dir / ".stage_done" / sid
        if marker.is_file():
            marker.unlink()
            cleared.append(sid)

    for sid in profile.forbidden_clear:
        if ctx.is_done(sid):
            forbidden_skipped.append(sid)

    for sid in profile.pending_clear:
        try:
            from interview_mux.write_staging import discard_stage_writes

            discard_stage_writes(ctx, sid)
            pending_cleared.append(sid)
        except Exception:
            pass

    # B-06: archive only explicit allowlist paths; empty = markers/pending only.
    archived: list[str] = []
    if profile.archive_allowlist:
        archived = _archive_allowlisted_paths(
            ctx,
            profile.archive_allowlist,
            profile_id=profile.profile_id,
            reason=reason,
        )

    try:
        from interview_mux.remediation_framework import append_invalidation_log, update_execution_health

        append_invalidation_log(
            ctx,
            stage=cleared[0] if cleared else profile_id,
            invalidated_artifacts=cleared,
            reconcile_status="bounded",
            profile_id=profile.profile_id,
            forbidden_skipped=forbidden_skipped,
        )
        update_execution_health(
            ctx,
            remediation_in_progress=True,
            automated_blocker="",
        )
        health = {}
        if ctx.artifact_exists("operator/execution_health.json"):
            health = ctx.read_json("operator/execution_health.json")
        if isinstance(health, dict):
            health = dict(health)
            health["invalidation_profile"] = profile.profile_id
            health["last_invalidation_reason"] = str(reason or "")
            health["invalidation_invocation"] = invocation
            ctx.write_json("operator/execution_health.json", health, skip_handoff=True)
    except Exception:
        pass

    if cleared:
        try:
            from interview_mux.remediation_framework import reconcile_invalidated_bundle

            # Bounded profiles already express the exact clear set. Do not run the
            # full G3 hollow-delivery reconcile afterward — that would unmark
            # forbidden stages that are only hollow fixture stamps (or still
            # needed producers like layup/mix).
            reconcile_invalidated_bundle(
                ctx,
                cleared,
                reason=reason or profile.profile_id,
                skip_delivery_batch=True,
                skip_invariants=True,
            )
        except Exception:
            pass

    return {
        "profile_id": profile.profile_id,
        "cleared": cleared,
        "forbidden_skipped": forbidden_skipped,
        "pending_cleared": pending_cleared,
        "archived": archived,
        "archive_allowlist": list(profile.archive_allowlist),
        "require_fingerprint_flip": bool(profile.require_fingerprint_flip),
        "reason": reason,
        "invocation": invocation,
        "max_invocations": max_n,
        "capped": False,
    }
