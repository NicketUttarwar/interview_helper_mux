"""Seed policy table — freeze/epoch sticky stages for seed-order.

When the domain is sealed (**hard** seat freeze + honest EDL done), listed
stages are treated as satisfied: force-mark done and never raise
seed_order_prereq for them.

A4 thorough + footguns 1–7:
- Soft freeze never sticky-completes seed stages (fingerprint alone never qualifies).
- Probe + happy path share ``freeze_artifact_proves_hard`` / ``hard_freeze_active``.
- Sticky set = core ∪ config extras (extras allowlisted; critical stages denied).
- EDL gate requires ``.stage_done/edl`` **and** non-empty ``master/edl.json``.
- ``FREEZE_STICKY_SEED_STAGES`` resolves via ``__getattr__`` to the live set.
"""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.run_context import RunContext

# Core stages that are intentional no-ops under hard seat freeze once EDL is done.
# Future stages: add here **or** list under ``seed_policy.freeze_sticky_extra_stages``
# (extras must pass allowlist — see ``_extra_stage_allowed``).
FREEZE_STICKY_SEED_STAGES_CORE: frozenset[str] = frozenset(
    {
        "selection_framing_apply",
        "gap_framing_recompose",
        # Layup compose is frozen history after EDL — do not seed-rewind mix
        # into LLM re-compose (exec_13159 shard/sanitary thrash under seal).
        "nugget_layup_compose",
        # SDP already consumed by VO finalize + EDL + music — sticky under seal.
        "sound_design_plan",
        # Soft-freeze era seal no-ops (pre-hard); incomplete markers must not
        # rewind seed after hard+EDL.
        "air_script_seams",
        "air_contract_sanitize",
        "sound_design_palettes",
    }
)

# Never sticky via config extras (or mistaken CORE edits) — must still run.
FREEZE_STICKY_STAGE_DENY: frozenset[str] = frozenset(
    {
        "edl",
        "edl_narrative_audit",
        "vo_synthesize",
        "vo_line_adjudicate",
        "sound_design_vo_finalize",
        "assembly_preview",
        "listen_delight_audit",
        "mmaudio_sfx",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "master_transcript_build",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
        "transcribe",
        "audio_preclean",
    }
)


def _known_pipeline_stages() -> frozenset[str]:
    try:
        from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

        return frozenset(ANALYSIS_ORDER) | frozenset(DELIVERY_ORDER)
    except Exception:
        return frozenset(FREEZE_STICKY_SEED_STAGES_CORE)


def _extra_stage_allowed(stage_id: str) -> bool:
    sid = str(stage_id or "").strip()
    if not sid or sid in FREEZE_STICKY_STAGE_DENY:
        return False
    if sid in FREEZE_STICKY_SEED_STAGES_CORE:
        return True
    return sid in _known_pipeline_stages()


def freeze_sticky_seed_stages() -> frozenset[str]:
    """Resolved sticky set: core ∪ validated config extras."""
    stages = {s for s in FREEZE_STICKY_SEED_STAGES_CORE if s not in FREEZE_STICKY_STAGE_DENY}
    try:
        from interview_mux.config import merged_config

        cfg = merged_config()
        block = (cfg.get("seed_policy") or {}) if isinstance(cfg, dict) else {}
        extra = block.get("freeze_sticky_extra_stages") if isinstance(block, dict) else None
        if isinstance(extra, (list, tuple, set, frozenset)):
            for raw in extra:
                sid = str(raw or "").strip()
                if _extra_stage_allowed(sid):
                    stages.add(sid)
    except Exception:
        pass
    return frozenset(stages)


def is_freeze_sticky_stage(stage_id: str) -> bool:
    return str(stage_id or "").strip() in freeze_sticky_seed_stages()


def freeze_artifact_proves_hard(fr: Any) -> bool:
    """Re-export seat_authority SSOT (tests / callers)."""
    from interview_mux.seat_authority import freeze_artifact_proves_hard as _prove

    return _prove(fr)


def _edl_honestly_done(ctx: RunContext) -> bool:
    """A4: refuse hollow ``.stage_done/edl`` without a real EDL spine.

    Requires done marker + ``master/edl.json`` with version=1 and either
    non-empty ``ordered_segment_ids`` or at least one typed clip — not a bare
    ``{}`` / junk dict. Still weaker than full ``edl_ready`` (no mix-era QA).
    """
    try:
        if not ctx.is_done("edl"):
            return False
    except Exception:
        return False
    try:
        if not ctx.artifact_exists("master/edl.json"):
            return False
        doc = ctx.read_json("master/edl.json")
        if not isinstance(doc, dict) or not doc:
            return False
        if doc.get("version") != 1:
            return False
        ids = doc.get("ordered_segment_ids")
        clips = doc.get("clips")
        if isinstance(ids, list) and any(str(x or "").strip() for x in ids):
            return True
        if isinstance(clips, list):
            for clip in clips:
                if isinstance(clip, dict) and str(clip.get("type") or "").strip():
                    return True
        return False
    except Exception:
        return False


def _hard_freeze_and_edl_done(ctx: RunContext) -> bool:
    """Happy path and probe share hard-evidence + honest EDL."""
    try:
        from interview_mux.seat_authority import hard_freeze_active

        return bool(hard_freeze_active(ctx) and _edl_honestly_done(ctx))
    except Exception as exc:
        edl_done = _edl_honestly_done(ctx)
        freeze_art = False
        try:
            from interview_mux.seat_authority import (
                freeze_artifact_proves_hard,
                read_seat_freeze,
            )

            freeze_art = freeze_artifact_proves_hard(read_seat_freeze(ctx))
        except Exception:
            freeze_art = False
        if edl_done and freeze_art:
            try:
                ctx.log(
                    f"seed_policy: hard_freeze probe failed — sticky via edl+hard freeze artifact ({exc})",
                    level="warning",
                    stage="seed_policy",
                )
            except Exception:
                pass
            return True
        import os

        if str(os.environ.get("MUX_FORENSICS") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            raise RuntimeError(
                f"seed_policy: hard_freeze probe failed without edl+hard freeze evidence ({exc})"
            ) from exc
        return False


def seed_stage_satisfied_by_policy(ctx: RunContext, stage_id: str) -> bool:
    """True when seed-order should treat ``stage_id`` as complete without work."""
    sid = str(stage_id or "").strip()
    if not sid or sid in FREEZE_STICKY_STAGE_DENY:
        return False
    if is_freeze_sticky_stage(sid) and _hard_freeze_and_edl_done(ctx):
        return True
    return False


def ensure_sticky_seed_mark(ctx: RunContext, stage_id: str) -> bool:
    """Force-mark stage done when policy says satisfied. Returns True if marked/done.

    Expanded WS2 O18: sticky mark only when heal succeeds (seed-complete or
    refuse leaves unfinished). Never leave a hollow .stage_done alone.
    """
    sid = str(stage_id or "").strip()
    if not sid or not seed_stage_satisfied_by_policy(ctx, sid):
        return False
    try:
        from interview_mux.delivery_guardrails import seed_stage_complete

        if seed_stage_complete(ctx, sid):
            return True
    except Exception:
        # Do not treat bare is_done as success (hollow marker footgun).
        pass
    try:
        from interview_mux.refinement_passes import persist_pass2_skip_stub

        persist_pass2_skip_stub(ctx, sid, skip_reason="hard_freeze_edl")
    except Exception:
        pass
    try:
        from interview_mux.stage_completion import heal_or_refuse_mark

        out = heal_or_refuse_mark(ctx, sid, force=True)
        if out.get("refused"):
            return False
    except Exception:
        return False
    try:
        from interview_mux.delivery_guardrails import seed_stage_complete

        return bool(seed_stage_complete(ctx, sid))
    except Exception:
        return False


def seal_freeze_sticky_stages(ctx: RunContext) -> list[str]:
    """Mark all freeze-sticky stages done when hard freeze + honest EDL sealed.

    Single law for freeze no-ops — call from seed walk and pre_mix (not from
    ``stamp_hard_seat_freeze``; sealing is walk-driven so tests can neutralize).
    Soft freeze alone never seals.
    """
    if not _hard_freeze_and_edl_done(ctx):
        return []
    sealed: list[str] = []
    for sid in sorted(freeze_sticky_seed_stages()):
        if ensure_sticky_seed_mark(ctx, sid):
            sealed.append(sid)
    if sealed:
        try:
            ctx.write_json(
                "operator/seed_sanitized.json",
                {
                    "reason": "hard_freeze_sticky_noop",
                    "sealed_stages": sealed,
                    "edl_done": True,
                },
                skip_handoff=True,
            )
        except Exception:
            pass
    return sealed


def apply_seed_policy_skips(
    ctx: RunContext,
    earlier: str,
    *,
    mark: Callable[[RunContext, str], bool] | None = None,
) -> bool:
    """If ``earlier`` is policy-satisfied, sticky-mark and return True (caller continue)."""
    if not seed_stage_satisfied_by_policy(ctx, earlier):
        return False
    if mark is not None:
        mark(ctx, earlier)
    else:
        ensure_sticky_seed_mark(ctx, earlier)
    return True


def __getattr__(name: str) -> Any:
    """``FREEZE_STICKY_SEED_STAGES`` resolves to the live set (core ∪ extras)."""
    if name == "FREEZE_STICKY_SEED_STAGES":
        return freeze_sticky_seed_stages()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
