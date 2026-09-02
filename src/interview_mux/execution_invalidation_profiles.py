"""Bounded invalidation profiles — allowlisted stage_done clears for remediation ladders."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class InvalidationProfile:
    profile_id: str
    allowed_clear: tuple[str, ...]
    forbidden_clear: frozenset[str]
    expand_to_structural_when: str = "order_fingerprint_mismatch"


INVALIDATION_PROFILES: dict[str, InvalidationProfile] = {
    "vo_coverage_heal": InvalidationProfile(
        profile_id="vo_coverage_heal",
        allowed_clear=VO_COVERAGE_HEAL_STAGES,
        forbidden_clear=FORBIDDEN_VO_COVERAGE,
    ),
    "vo_seated_coverage": InvalidationProfile(
        profile_id="vo_seated_coverage",
        allowed_clear=VO_COVERAGE_HEAL_STAGES,
        forbidden_clear=FORBIDDEN_VO_COVERAGE,
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
    ),
    "structural_delivery": InvalidationProfile(
        profile_id="structural_delivery",
        allowed_clear=STRUCTURAL_DELIVERY_STAGES,
        forbidden_clear=frozenset({"nugget_layup_compose"}),
        expand_to_structural_when="always",
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
    return INVALIDATION_PROFILES.get(ec)


def should_expand_to_structural(ctx: RunContext, profile_id: str) -> bool:
    if profile_id == "structural_delivery":
        return True
    try:
        from interview_mux.delivery_guardrails import fingerprints_match_checkpoint, read_checkpoint

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


def apply_bounded_invalidation(
    ctx: RunContext,
    profile_id: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    """Unmark only allowed stages; log forbidden skips."""
    profile = INVALIDATION_PROFILES.get(profile_id)
    if profile is None:
        return {"profile_id": profile_id, "cleared": [], "forbidden_skipped": []}

    if should_expand_to_structural(ctx, profile_id):
        profile = INVALIDATION_PROFILES["structural_delivery"]

    cleared: list[str] = []
    forbidden_skipped: list[str] = []
    for sid in profile.allowed_clear:
        marker = ctx.run_dir / ".stage_done" / sid
        if marker.is_file():
            marker.unlink()
            cleared.append(sid)

    for sid in profile.forbidden_clear:
        if ctx.is_done(sid):
            forbidden_skipped.append(sid)

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
            ctx.write_json("operator/execution_health.json", health, skip_handoff=True)
    except Exception:
        pass

    if cleared:
        try:
            from interview_mux.remediation_framework import reconcile_invalidated_bundle

            reconcile_invalidated_bundle(ctx, cleared, reason=reason or profile.profile_id)
        except Exception:
            pass

    return {
        "profile_id": profile.profile_id,
        "cleared": cleared,
        "forbidden_skipped": forbidden_skipped,
        "reason": reason,
    }
