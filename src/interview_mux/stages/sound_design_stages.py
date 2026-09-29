from __future__ import annotations

from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.acoustic_profile import compact_for_volley as acoustic_compact_for_volley, load_profile
from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.config import merged_config
from interview_mux.prompt_validation import (
    validate_sound_design_plan as _sdp_schema_errors,
    validate_stage_artifacts,
)
from interview_mux.operator_trace import logged_step
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import (
    align_palette_keywords_to_sonic_context,
    build_palette_keyword_catalog,
    compact_for_volley as sonic_compact_for_volley,
    load_sonic_context,
)
from interview_mux.stage_enrichment import compact_manifest_for_volley, compact_value_features_summary
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, run_flow_llm_stage
from interview_mux.stage_completion import heal_or_refuse_mark

_SOUND_DESIGN_PLAN_REL = "understanding/sound_design_plan.json"

# Delivery writers whose SDP body is paid work; palettes never overwrites them.
_PAID_SDP_PRODUCERS = frozenset(
    {"sound_design_plan", "music_palette_compose", "sfx_prompt_craft", "sound_design_vo_finalize"}
)


def _delivery_sdp_paid_by(ctx: RunContext) -> str:
    """Producer of a plan that already carries delivery work, else "".

    The producer stamp alone is not proof: a bare write of the scaffold is
    stamped ``sound_design_plan`` by the one-writer default. Paid means a
    delivery writer stamped it *and* it holds assets, cues or palettes.
    """
    try:
        sdp = ctx.read_json(_SOUND_DESIGN_PLAN_REL)
    except Exception:
        return ""
    if not isinstance(sdp, dict):
        return ""
    meta = sdp.get("_meta") if isinstance(sdp.get("_meta"), dict) else {}
    producer = str(meta.get("producer_stage") or "")
    if producer not in _PAID_SDP_PRODUCERS:
        return ""
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    palettes = [p for p in (sdp.get("palettes") or []) if isinstance(p, dict)]
    flow = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
    cues = [c for c in (podcast.get("cues") or []) if isinstance(c, dict)]
    return producer if (assets or palettes or cues) else ""


def run_sound_design_palettes(ctx: RunContext) -> None:
    if not _sound_design_enabled(ctx):
        _mark_skipped(ctx, "sound_design_palettes")
        return

    # Simplification: defer palette inventing to sound_design_plan (single musical decision site).
    sd_cfg = merged_config().get("sound_design") or {}
    if not bool(sd_cfg.get("early_palettes_llm", False)):
        # A re-run after delivery already paid the plan must not restamp the
        # shared path as ours: that unlands sound_design_plan and re-invokes
        # its LLM volley (ISSUES entry 46). Keep the paid document, mark done.
        paid_by = _delivery_sdp_paid_by(ctx)
        if paid_by:
            ctx.log(
                "sound_design_palettes: delivery SDP already paid "
                f"(producer={paid_by}); leaving it untouched",
                level="info",
                stage="sound_design_palettes",
            )
            heal_or_refuse_mark(ctx, "sound_design_palettes", force=True)
            return
        sdp = _load_sound_design_plan(ctx)
        if not isinstance(sdp.get("palettes"), list):
            sdp["palettes"] = []
        coherence = sdp.get("coherence") if isinstance(sdp.get("coherence"), dict) else {}
        coherence.setdefault(
            "notes",
            "early palettes deferred — sound_design_plan owns musical direction",
        )
        # Keep a provisional identity from sonic_context so later stages have a seed.
        if not str(coherence.get("sonic_identity") or "").strip():
            sonic = load_sonic_context(ctx) or {}
            atlas = str(
                (sonic.get("atlas_bucket") if isinstance(sonic, dict) else None) or ""
            ).strip()
            tags = [
                str(t.get("label") or t.get("tag_id") or "").strip()
                for t in ((sonic.get("tag_registry") or []) if isinstance(sonic, dict) else [])
                if isinstance(t, dict)
            ]
            seed = atlas or (tags[0] if tags else "")
            coherence["sonic_identity"] = seed or "deferred_to_sound_design_plan"
            coherence["deferred_early_palettes"] = True
            coherence["invent_obligation"] = "sound_design_plan"
            coherence["deferred_ok"] = True
        sdp["coherence"] = coherence
        sdp.setdefault("_meta", {})
        if isinstance(sdp["_meta"], dict):
            sdp["_meta"]["deferred_early_palettes"] = True
            sdp["_meta"]["invent_obligation"] = "sound_design_plan"
        _validate_sound_design_plan(sdp)
        write_validated_artifact(
            ctx, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_palettes"
        )
        ctx.log(
            "sound_design_palettes: skipped early LLM (sound_design.early_palettes_llm=false)",
            level="info",
            stage="sound_design_palettes",
        )
        heal_or_refuse_mark(ctx, "sound_design_palettes", force=True)
        return

    def build_input(c: RunContext) -> dict:
        manifest = c.read_json("segments/manifest.json")
        payload: dict = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}),
            "analysis_state": c.read_json("understanding/analysis_state.json"),
        }
        sdp = _load_sound_design_plan(c)
        payload["sound_design_plan"] = {
            "version": sdp.get("version", 1),
            "coherence": sdp.get("coherence", {}),
            "palettes": sdp.get("palettes", []),
        }
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
            payload["palette_keyword_catalog"] = build_palette_keyword_catalog(sonic_context)
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf

        style = (payload["analysis_state"].get("style") or {}) if isinstance(payload["analysis_state"], dict) else {}
        notes = style.get("sound_design_notes")
        if notes:
            payload["operator_style_sound_design_notes"] = notes
        return attach_adaptation_to_payload(c, payload)

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = _load_sound_design_plan(c)
        if "coherence" in artifacts:
            sdp["coherence"] = artifacts["coherence"]
        if "palettes" in artifacts:
            palettes = artifacts["palettes"]
            palette_list = palettes if isinstance(palettes, list) else []
            sonic = load_sonic_context(c)
            if sonic and palette_list:
                palette_list = align_palette_keywords_to_sonic_context(palette_list, sonic)
            sdp["palettes"] = _attach_palette_provenance(c, palette_list)
        _validate_sound_design_plan(sdp)
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_palettes"
        )

    with logged_step("sound_design_palettes/llm_stage", ctx=ctx, stage="sound_design_palettes"):
        run_analysis_llm_stage(
            ctx,
            "sound_design_palettes",
            prompt_variant("sound_design/theme-palettes.system.txt", ctx),
            build_input,
            persist,
        )

def _mix_seat_active(ctx: RunContext) -> bool:
    """True when mix (or later) has seated — narrative_plan metadata align is frozen."""
    try:
        from interview_mux.artifact_ownership import current_epoch

        if str(current_epoch(ctx) or "") in {"mix_seated", "junction_committed"}:
            return True
    except Exception:
        pass
    try:
        return bool(ctx.artifact_exists("master/assembly.wav"))
    except Exception:
        return False


def _sdp_delivery_ready_for_mix_skip(ctx: RunContext) -> bool:
    """True when a delivery SDP is already paid (safe to skip invent under mix seat)."""
    if not ctx.artifact_exists(_SOUND_DESIGN_PLAN_REL):
        return False
    try:
        from interview_mux.homunculus.agenda import delivery_sdp_present

        if delivery_sdp_present(ctx):
            return True
    except Exception:
        pass
    try:
        sdp = ctx.read_json(_SOUND_DESIGN_PLAN_REL)
    except Exception:
        return False
    if not isinstance(sdp, dict):
        return False
    meta = sdp.get("_meta") if isinstance(sdp.get("_meta"), dict) else {}
    if str(meta.get("producer_stage") or "") != "sound_design_plan":
        return False
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    flow = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
    cues = [c for c in (podcast.get("cues") or []) if isinstance(c, dict)]
    return bool(assets) or bool(cues)


def _finalize_existing_sdp_under_mix_seat(ctx: RunContext) -> None:
    """Restamp producer + mark done — do not invent on drifted order under mix seat."""
    from interview_mux.artifact_lifecycle import restamp_committed_artifact
    from interview_mux.homunculus.agenda import _sdp_producer_stage

    try:
        if _sdp_producer_stage(ctx) != "sound_design_plan":
            restamp_committed_artifact(
                ctx, _SOUND_DESIGN_PLAN_REL, producer_stage="sound_design_plan"
            )
    except Exception as exc:
        ctx.log(
            f"sound_design_plan: mix-seat restamp skipped ({exc})",
            level="warning",
            stage="sound_design_plan",
        )
    # Paid delivery SDP may predate completeness bars (e.g. sonic_identity).
    # Seed the minimum so heal_or_refuse can land without raw_stamp bypass.
    try:
        sdp = ctx.read_json(_SOUND_DESIGN_PLAN_REL)
        if isinstance(sdp, dict):
            coherence = sdp.get("coherence") if isinstance(sdp.get("coherence"), dict) else {}
            coherence = dict(coherence)
            changed = False
            if not str(coherence.get("sonic_identity") or "").strip():
                coherence["sonic_identity"] = "mix_seat_delivery"
                changed = True
            if changed:
                sdp["coherence"] = coherence
                ctx.write_json(
                    _SOUND_DESIGN_PLAN_REL, sdp, stage_key="sound_design_plan"
                )
    except Exception as exc:
        ctx.log(
            f"sound_design_plan: mix-seat coherence seed skipped ({exc})",
            level="warning",
            stage="sound_design_plan",
        )
    ctx.log(
        "sound_design_plan: skip invent — mix seated with delivery SDP already present",
        level="info",
        stage="sound_design_plan",
    )
    # Delivery SDP already paid → incompleteness gates clear; honest heal/refuse only.
    heal_or_refuse_mark(ctx, "sound_design_plan", force=True)


class _SdpMixSeatSkip(Exception):
    """Abort invent when mix seat + delivery SDP already paid (caught by run_sound_design_plan)."""


def _selection_narrative_drift(ctx: RunContext) -> list[str]:
    """Read-only selection↔narrative conflicts (no narrative_plan mutate)."""
    from interview_mux.order_reconcile import material_order_conflicts

    if not ctx.artifact_exists("master/selection.json"):
        return []
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return []
    if not isinstance(sel, dict):
        return []
    ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    if not ordered:
        return []
    plan: dict = {}
    if ctx.artifact_exists("master/narrative_plan.json"):
        try:
            raw = ctx.read_json("master/narrative_plan.json")
        except Exception:
            raw = None
        if isinstance(raw, dict):
            plan = raw
    return list(material_order_conflicts(ordered, plan) or [])


def run_sound_design_plan(ctx: RunContext) -> None:
    if not _sound_design_enabled(ctx):
        _mark_skipped(ctx, "sound_design_plan")
        return

    # Mix-seated + delivery SDP already paid: never invent on drifted order
    # (exec_13177 i15 — order_reconcile deny under narrative_metadata_align freeze).
    if _mix_seat_active(ctx) and _sdp_delivery_ready_for_mix_skip(ctx):
        _finalize_existing_sdp_under_mix_seat(ctx)
        return

    def build_input(c: RunContext) -> dict:
        from interview_mux.soundscape_policy import (
            compact_for_volley as soundscape_compact,
            load_policy,
        )

        # Read-only drift check — refuse invent; do not mutate narrative/selection.
        drift = _selection_narrative_drift(c)
        if drift:
            if _mix_seat_active(c):
                if _sdp_delivery_ready_for_mix_skip(c):
                    c.log(
                        "sound_design_plan: selection/narrative drift under mix seat — skip invent",
                        level="warning",
                        stage="sound_design_plan",
                        detail={"conflicts": drift[:6]},
                    )
                    raise _SdpMixSeatSkip("selection_narrative_drift")
                raise RuntimeError(
                    "sound_design_plan: selection/narrative drift under mix seat with "
                    "incomplete SDP (resume stamp/repair, not invent): "
                    + "; ".join(drift[:4])
                )
            if _sdp_fail_closed_reconcile(c):
                raise RuntimeError(
                    "sound_design_plan: refuse invent on drifted selection/narrative "
                    "(resume order_reconcile / ranking): "
                    + "; ".join(drift[:4])
                )
            c.log(
                "selection/narrative drift before sound_design_plan (fail-open): "
                + "; ".join(drift[:4]),
                level="warning",
                stage="sound_design_plan",
            )

        from interview_mux.episode_structure import (
            attach_episode_structure_to_payload,
            refresh_episode_structure_compact_only,
            structure_enabled,
        )

        if structure_enabled():
            try:
                refresh_episode_structure_compact_only(c)
            except Exception as exc:
                c.log(
                    f"episode_structure compact refresh skipped: {exc}",
                    level="warning",
                    stage="sound_design_plan",
                )
        manifest = c.read_json("segments/manifest.json")
        payload = {
            "sound_design_plan": _load_sound_design_plan(c),
            "selection": c.read_json("master/selection.json"),
            "narrative_plan": c.read_json("master/narrative_plan.json"),
            "transitions": c.read_json("master/transitions.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}),
        }
        from interview_mux.gap_framing import framing_vo_for_sound_design

        framing_vo = framing_vo_for_sound_design(c)
        if framing_vo:
            payload["framing_vo_lines"] = framing_vo
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        policy = load_policy(c)
        if policy:
            payload["soundscape_policy"] = soundscape_compact(policy)
        from interview_mux.music_motif import build_music_brief, default_motif_family

        brief = build_music_brief(c)
        c.write_json("understanding/music_brief.json", brief)
        payload["music_brief"] = brief
        sdp_partial = payload.get("sound_design_plan")
        if isinstance(sdp_partial, dict) and not isinstance(sdp_partial.get("motif_family"), dict):
            payload["motif_family_seed"] = default_motif_family(brief)
        return attach_disfluency_context(
            attach_episode_structure_to_payload(
                c,
                __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                    c, attach_adaptation_to_payload(c, payload)
                ),
            ),
            c,
        )

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = _load_sound_design_plan(c)
        assets = artifacts.get("assets")
        flow_plans = artifacts.get("flow_plans")
        if isinstance(assets, list):
            sdp["assets"] = assets
        if isinstance(flow_plans, dict):
            existing = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            merged = dict(existing or {})
            merged.update(flow_plans)
            # Prefer podcast; drop empty flow2 scaffold
            if not merged.get("podcast") and merged.get("flow1"):
                merged["podcast"] = merged["flow1"]
            sdp["flow_plans"] = {k: v for k, v in merged.items() if k != "flow2" or v}

        _normalize_sound_design_assets(sdp)
        _normalize_chapter_stinger_reuse(sdp)
        from interview_mux.music_motif import (
            analysis_palette_counts,
            build_music_brief,
            ensure_motif_on_plan,
        )

        brief = build_music_brief(c)
        c.write_json("understanding/music_brief.json", brief)
        if isinstance(artifacts.get("motif_family"), dict):
            sdp["motif_family"] = artifacts["motif_family"]
        counts = analysis_palette_counts(c)
        sdp = ensure_motif_on_plan(sdp, brief, ctx=c, counts=counts)
        invent_errs = _lint_sdp_invent(sdp)
        if invent_errs:
            raise ValueError(
                "sound_design_plan invent lint failed: " + "; ".join(invent_errs[:6])
            )
        # S6: cue/palette placement owned by music_palette_compose — invent commits
        # assets + motif only, with an empty deferred podcast cue list.
        if not isinstance(sdp.get("flow_plans"), dict):
            sdp["flow_plans"] = {}
        podcast = (
            sdp["flow_plans"].get("podcast")
            if isinstance(sdp["flow_plans"].get("podcast"), dict)
            else {}
        )
        podcast = dict(podcast)
        podcast["profile"] = str(podcast.get("profile") or "podcast") or "podcast"
        podcast["cues"] = []
        podcast["compose_deferred"] = True
        sdp["flow_plans"]["podcast"] = podcast

        # Clear invent obligation — delivery invent paid (assets; cues deferred).
        _clear_sdp_invent_obligation(sdp)

        # Clamp durations before commit so craft/preflight do not thrash later.
        _clamp_sdp_asset_durations_inplace(sdp)

        _validate_sound_design_plan(sdp)
        _validate_flow1_asset_links(sdp)
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_plan"
        )
        # Completeness requires _meta.producer_stage == sound_design_plan.
        # Hard-fail restamp — warn-only left palettes-shaped files incomplete forever.
        from interview_mux.artifact_lifecycle import restamp_committed_artifact

        restamp_committed_artifact(
            c, _SOUND_DESIGN_PLAN_REL, producer_stage="sound_design_plan"
        )

    with logged_step("sound_design_plan/llm_stage", ctx=ctx, stage="sound_design_plan"):
        try:
            run_flow_llm_stage(
                ctx,
                "sound_design_plan",
                prompt_variant("sound_design/plan-flow1.system.txt", ctx),
                build_input,
                persist,
            )
        except _SdpMixSeatSkip:
            _finalize_existing_sdp_under_mix_seat(ctx)
            return


def _repair_sdp_asset_durations(ctx: RunContext) -> bool:
    """Clamp SDP asset durations to role bands before prompt craft / generation.

    Prefer ``mmaudio.duration_bands_by_role`` from config (same as preflight),
    then fall back to ``ROLE_DURATION_BANDS`` / MMAudio global clamp.
    """
    from interview_mux.config import merged_config
    from interview_mux.deterministic_lint import ROLE_DURATION_BANDS
    from interview_mux.mmaudio_runner import clamp_duration_seconds

    sdp = _load_sound_design_plan(ctx)
    assets = sdp.get("assets") or []
    mcfg = merged_config().get("mmaudio") or {}
    by_role = mcfg.get("duration_bands_by_role") if isinstance(mcfg.get("duration_bands_by_role"), dict) else {}
    changed = False
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        dur = asset.get("duration_seconds")
        if dur is None:
            continue
        role = str(asset.get("role") or "")
        band = None
        cfg_band = by_role.get(role)
        if isinstance(cfg_band, (list, tuple)) and len(cfg_band) >= 2:
            band = (float(cfg_band[0]), float(cfg_band[1]))
        elif role in ROLE_DURATION_BANDS:
            band = ROLE_DURATION_BANDS.get(role)
        if role in ROLE_DURATION_BANDS:
            lint_lo, lint_hi = ROLE_DURATION_BANDS[role]
            if band:
                band = (max(float(band[0]), float(lint_lo)), max(float(band[1]), float(lint_hi)))
            else:
                band = (float(lint_lo), float(lint_hi))
        clamped = float(dur)
        if band:
            lo, hi = float(band[0]), float(band[1])
            val = float(dur)
            if val < lo:
                clamped = lo
            elif val > hi:
                # Soft stretch for long beds/opens — keep as-is (preflight must match).
                if role in _SDP_DURATION_SOFT_STRETCH_ROLES or str(
                    asset.get("palette_kind") or ""
                ) in {"full_bed", "motif"}:
                    clamped = val
                else:
                    clamped = hi
        else:
            clamped = clamp_duration_seconds(float(dur), role=role, ctx=ctx)
        if clamped != float(dur):
            asset["duration_seconds"] = clamped
            changed = True
    if changed:
        # Ownership + seat freeze: SDP is a frozen seat doc after VO hard freeze.
        # Bare/stage_key-only writes skip-write under freeze (exec_13170: clamp
        # reported changed but committed SDP stayed short). End-A reason lets
        # duration-band clamp persist without seat/omit expansion.
        try:
            from interview_mux.artifact_sanitize.one_writer import (
                commit_sound_design_plan_doc,
            )

            commit_sound_design_plan_doc(
                ctx,
                sdp,
                stage_key="sfx_prompt_craft",
                reason="sdp_duration_band_repair",
                skip_handoff=True,
            )
        except Exception as exc:
            ctx.log(
                f"sdp duration repair write refused: {exc}",
                level="warning",
                stage="sfx_prompt_craft",
            )
            return False
        # Verify persist — freeze skip-write returns silently without raising.
        try:
            committed = _load_sound_design_plan(ctx)
            c_assets = {
                str(a.get("asset_id") or a.get("id") or ""): a
                for a in (committed.get("assets") or [])
                if isinstance(a, dict)
            }
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                aid = str(asset.get("asset_id") or asset.get("id") or "")
                want = float(asset.get("duration_seconds") or 0)
                got_row = c_assets.get(aid) or {}
                got = float(got_row.get("duration_seconds") or 0) if got_row else 0.0
                if aid and abs(got - want) > 0.05:
                    ctx.log(
                        f"sdp duration repair did not persist for {aid}: "
                        f"want={want} got={got}",
                        level="warning",
                        stage="sfx_prompt_craft",
                    )
                    return False
        except Exception:
            pass
        ctx.log(
            "Repaired sound_design_plan asset durations to role bands",
            level="info",
            stage="sfx_prompt_craft",
        )
    return changed


# Roles allowed to exceed the configured hi band (MusicGen theme stems / beds).
_SDP_DURATION_SOFT_STRETCH_ROLES: frozenset[str] = frozenset(
    {
        "theme_cold_open",
        "theme_outro",
        "full_bed",
        "motif",
    }
)


def sdp_duration_allowed_for_role(
    role: str,
    duration_sec: float,
    *,
    palette_kind: str | None = None,
    band: tuple[float, float] | None = None,
) -> bool:
    """True when duration is inside the role band or a soft-stretch bed/open."""
    if band is None:
        return True
    lo, hi = float(band[0]), float(band[1])
    d = float(duration_sec)
    if d < lo - 0.1:
        return False
    if d <= hi + 0.1:
        return True
    if str(role or "") in _SDP_DURATION_SOFT_STRETCH_ROLES:
        return True
    if str(palette_kind or "") in {"full_bed", "motif"}:
        return True
    return False


def run_sfx_prompt_craft(ctx: RunContext) -> None:
    if not _sound_design_enabled(ctx):
        _mark_skipped(ctx, "sfx_prompt_craft")
        return

    # SPC-B3: refuse default/empty SDP before LLM — no soft-hollow craft spend.
    # Missing plan soft-defaults to empty assets via `_load_sound_design_plan`;
    # both paths must refuse here (preflight already mirrors the empty check).
    sdp_probe = _load_sound_design_plan(ctx)
    if not (sdp_probe.get("assets") or []):
        raise RuntimeError("SDP assets[] empty before prompt craft")

    _repair_sdp_asset_durations(ctx)

    def build_input(c: RunContext) -> dict:
        sdp = _load_sound_design_plan(c)
        payload: dict = {
            "coherence": sdp.get("coherence", {}),
            "assets": sdp.get("assets", []),
        }
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = profile
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        from interview_mux.soundscape_policy import compact_for_volley as soundscape_compact, load_policy

        policy = load_policy(c)
        if policy:
            payload["soundscape_policy"] = soundscape_compact(policy)
        if c.artifact_exists("understanding/analysis_state.json"):
            state = c.read_json("understanding/analysis_state.json")
            style = state.get("style") if isinstance(state, dict) else None
            if isinstance(style, dict) and style.get("sound_design_notes"):
                payload["operator_style_sound_design_notes"] = style["sound_design_notes"]
        return __import__(
            "interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]
        ).attach_delivery_brief_to_payload(c, attach_adaptation_to_payload(c, payload))

    def persist(c: RunContext, artifacts: dict) -> None:
        prompts = artifacts.get("prompts")
        if not isinstance(prompts, list):
            raise ValueError("sfx_prompt_craft: missing artifacts.prompts list")
        sdp = _load_sound_design_plan(c)
        normalized = _normalize_sfx_prompts(sdp, prompts, ctx=c)
        payload = {"prompts": normalized}
        schema_errors = validate_stage_artifacts("sfx_prompt_craft", payload)
        if schema_errors:
            raise ValueError(f"Invalid SFX prompts artifact: {schema_errors[0]}")
        # Replace, do not merge_from_disk: list-merge concatenates prompt rows and
        # duplicates asset_ids on re-craft (doubles MusicGen work forever).
        write_validated_artifact(
            c,
            "sound_design/sfx_prompts.json",
            payload,
            merge_from_disk=False,
            stage_key="sfx_prompt_craft",
        )
        # Preserve producer_stage via commit path (bare write_json dropped meta).
        from interview_mux.artifact_sanitize.one_writer import commit_sound_design_plan_doc
        from interview_mux.artifact_lifecycle import restamp_committed_artifact

        prior_meta = sdp.get("_meta") if isinstance(sdp.get("_meta"), dict) else {}
        prior_producer = str(prior_meta.get("producer_stage") or "") or "sound_design_plan"
        commit_sound_design_plan_doc(
            c,
            sdp,
            stage_key="sfx_prompt_craft",
            reason="sfx_prompt_craft_sdp_sync",
        )
        restamp_committed_artifact(
            c, _SOUND_DESIGN_PLAN_REL, producer_stage=prior_producer
        )
        from interview_mux.sfx_prompt_review import maybe_auto_approve_prompt_review

        maybe_auto_approve_prompt_review(c)

    with logged_step("sfx_prompt_craft/llm_stage", ctx=ctx, stage="sfx_prompt_craft"):
        run_flow_llm_stage(
            ctx,
            "sfx_prompt_craft",
            prompt_variant("sound_design/sfx-prompt-craft.system.txt", ctx),
            build_input,
            persist,
        )

def run_sfx_prompt_refine(ctx: RunContext, asset_ids: list[str] | None = None) -> None:
    """LLM refine pass for failed MMAudio assets — not in default FLOW order."""

    def build_input(c: RunContext) -> dict:
        sdp = _load_sound_design_plan(c)
        crafted = {}
        if c.artifact_exists("sound_design/sfx_prompts.json"):
            data = c.read_json("sound_design/sfx_prompts.json")
            rows = data.get("prompts") or []
            crafted = {str(r["asset_id"]): r for r in rows if isinstance(r, dict) and r.get("asset_id")}
        qa_rows: list[dict] = []
        if c.artifact_exists("sound_design/mmaudio_qa.json"):
            qa_doc = c.read_json("sound_design/mmaudio_qa.json")
            qa_rows = [r for r in (qa_doc.get("assets") or []) if isinstance(r, dict)]
        listen: list[dict] = []
        if c.artifact_exists("run_meta.json"):
            meta = c.read_json("run_meta.json")
            listen = [r for r in (meta.get("sfx_listen_results") or []) if isinstance(r, dict)]

        target_ids = set(asset_ids or [])
        if not target_ids:
            for row in qa_rows:
                if row.get("verdict") == "fail" and row.get("asset_id"):
                    target_ids.add(str(row["asset_id"]))
            latest_listen: dict[str, str] = {}
            for entry in listen:
                aid = str(entry.get("asset_id") or "")
                if aid:
                    latest_listen[aid] = str(entry.get("result") or "")
            for aid, res in latest_listen.items():
                if res == "fail":
                    target_ids.add(aid)

        failed_assets: list[dict] = []
        for aid in sorted(target_ids):
            failed_assets.append(
                {
                    "asset_id": aid,
                    "original_prompt_row": crafted.get(aid, {}),
                    "qa_report": next((r for r in qa_rows if str(r.get("asset_id")) == aid), {}),
                    "listen_entries": [e for e in listen if str(e.get("asset_id")) == aid],
                }
            )

        payload: dict = {
            "coherence": sdp.get("coherence", {}),
            "failed_assets": failed_assets,
            "mmaudio_qa": qa_rows,
            "listen_results": listen,
        }
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        updates = artifacts.get("prompts")
        if not isinstance(updates, list) or not updates:
            raise ValueError("sfx_prompt_refine: missing artifacts.prompts list")
        path = "sound_design/sfx_prompts.json"
        existing_rows: list[dict] = []
        if c.artifact_exists(path):
            data = c.read_json(path)
            existing_rows = [r for r in (data.get("prompts") or []) if isinstance(r, dict)]
        by_id = {str(r["asset_id"]): dict(r) for r in existing_rows if r.get("asset_id")}
        for row in updates:
            if not isinstance(row, dict) or not row.get("asset_id"):
                continue
            aid = str(row["asset_id"])
            merged = {**by_id.get(aid, {}), **row, "asset_id": aid}
            by_id[aid] = merged
        sdp = _load_sound_design_plan(c)
        normalized = _normalize_sfx_prompts(sdp, list(by_id.values()), ctx=c)
        payload = {"prompts": normalized}
        schema_errors = validate_stage_artifacts("sfx_prompt_craft", payload)
        if schema_errors:
            raise ValueError(f"Invalid refined SFX prompts: {schema_errors[0]}")
        write_validated_artifact(
            c,
            path,
            payload,
            merge_from_disk=False,
            stage_key="sfx_prompt_refine",
        )
        _increment_refine_attempts(c, [str(r["asset_id"]) for r in updates if r.get("asset_id")])
        meta = c.read_json("run_meta.json") if c.artifact_exists("run_meta.json") else {}
        review = meta.get("sfx_prompt_review") or {}
        if isinstance(review, dict):
            review["approved"] = False
            review["approved_by"] = None
            review["approved_at"] = None
            meta["sfx_prompt_review"] = review
            c.write_json("run_meta.json", meta)
        c.log(
            "sfx_prompts_refined",
            level="info",
            stage="sfx_prompt_refine",
            detail={"asset_ids": [r.get("asset_id") for r in updates]},
        )

    with logged_step("sfx_prompt_refine/llm_stage", ctx=ctx, stage="sfx_prompt_refine"):
        run_flow_llm_stage(
            ctx,
            "sfx_prompt_refine",
            "sound_design/sfx-prompt-refine.system.txt",
            build_input,
            persist,
        )

def _increment_refine_attempts(ctx: RunContext, asset_ids: list[str]) -> None:
    def patch(m: dict) -> None:
        attempts = dict(m.get("sfx_refine_attempts") or {})
        for aid in asset_ids:
            attempts[aid] = int(attempts.get(aid, 0)) + 1
        m["sfx_refine_attempts"] = attempts

    ctx.mutate_run_meta(patch)

def _load_sound_design_plan(ctx: RunContext) -> dict:
    if ctx.artifact_exists(_SOUND_DESIGN_PLAN_REL):
        doc = ctx.read_json(_SOUND_DESIGN_PLAN_REL)
        if isinstance(doc, dict):
            return doc
    return default_sound_design_plan()

def _sound_design_enabled(ctx: RunContext | None = None) -> bool:
    """Return whether sound design stages run.

    Full-auto / production parity forces enabled=true (R6-A) so silence cannot
    quietly starve music/SFX. Lab runs may still disable via config when not
    full-auto, or via an explicit music_omitted contract.
    """
    cfg_on = bool((merged_config().get("sound_design") or {}).get("enabled", True))
    if cfg_on:
        return True
    if ctx is None:
        return False
    try:
        from interview_mux.automation_run import is_full_auto_run

        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if not isinstance(meta, dict):
            meta = {}
        production = bool(meta.get("production") or meta.get("full_auto_production_parity"))
        if is_full_auto_run(meta) or production:
            # Explicit lab omit contract is the only escape hatch.
            if ctx.artifact_exists("operator/music_omitted.json"):
                return False
            ctx.log(
                "sound_design.enabled=false overridden for full-auto/production "
                "(force enabled — refuse silent-music masters)",
                level="warning",
                stage="sound_design_plan",
            )
            return True
    except Exception:
        pass
    return False


def _sdp_fail_closed_reconcile(ctx: RunContext) -> bool:
    """True when order_reconcile must refuse invent on drift (full-auto / production)."""
    try:
        from interview_mux.automation_run import is_full_auto_run

        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if not isinstance(meta, dict):
            return False
        if is_full_auto_run(meta):
            return True
        return bool(meta.get("production") or meta.get("full_auto_production_parity"))
    except Exception:
        return False


def _lint_sdp_invent(sdp: dict) -> list[str]:
    """Deterministic invent lint — refuse illegal/hollow music invent before commit."""
    from interview_mux.music_motif import (
        BANNED_SFX_ROLES,
        asset_id_is_banned,
        is_banned_role,
        text_has_banned_texture,
    )

    errs: list[str] = []
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    if len(assets) < 1:
        errs.append("assets_empty")
        return errs
    roles = {str(a.get("role") or "") for a in assets}
    kinds = {str(a.get("palette_kind") or "") for a in assets}
    if "theme_cold_open" not in roles and "motif" not in kinds and "full_bed" not in kinds:
        errs.append("missing_theme_cold_open_or_motif")
    if "theme_underscore" not in roles and "underscore_loop" not in kinds:
        errs.append("missing_theme_underscore")
    accent = roles & {
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_transition",
        "theme_outro",
    } or kinds & {"stinger", "full_bed"}
    if not accent:
        errs.append("missing_accent_or_outro")
    for a in assets:
        role = str(a.get("role") or "")
        aid = str(a.get("asset_id") or "")
        if is_banned_role(role) or role in BANNED_SFX_ROLES:
            errs.append(f"banned_role:{role or '?'}")
        if asset_id_is_banned(aid):
            errs.append(f"banned_asset_id:{aid}")
        blob = " ".join(
            str(a.get(k) or "") for k in ("description", "prompt", "prompt_dna", "notes")
        )
        if text_has_banned_texture(blob):
            errs.append(f"banned_texture:{aid or role or '?'}")
    motif = sdp.get("motif_family") if isinstance(sdp.get("motif_family"), dict) else {}
    if not str(motif.get("prompt_dna") or "").strip():
        errs.append("missing_motif_prompt_dna")
    elif text_has_banned_texture(str(motif.get("prompt_dna") or "")):
        errs.append("banned_texture:motif_prompt_dna")
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for e in errs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _safe_placeholder_bed_segment(ctx: RunContext, ordered: list[str]) -> str:
    """Pick first ordered seg that is not banned; prefer existing theme_underscore slots."""
    if not ordered:
        raise ValueError("ordered_segment_ids empty")
    banned: set[str] = set()
    try:
        from interview_mux.sonic_context import load_sonic_context

        sonic = load_sonic_context(ctx) or {}
        flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
        banned |= {str(x) for x in (flags.get("overlap_high") or [])}
        banned |= {str(x) for x in (flags.get("trauma_adjacent") or [])}
    except Exception:
        pass
    slot_prefs: list[str] = []
    try:
        from interview_mux.soundscape_policy import load_policy

        policy = load_policy(ctx) or {}
        for slot in policy.get("cue_slots") or []:
            if not isinstance(slot, dict):
                continue
            roles = [str(r) for r in (slot.get("allowed_roles") or [])]
            if "theme_underscore" in roles or "ambient_bed" in roles:
                sid = str(slot.get("segment_id") or "")
                if sid and sid in ordered and sid not in banned:
                    slot_prefs.append(sid)
    except Exception:
        pass
    for sid in slot_prefs:
        return sid
    for sid in ordered:
        if sid not in banned:
            return sid
    return ordered[0]


def _ensure_placeholder_palette(sdp: dict, bed_anchor: str) -> None:
    """Peeled: compose owns cues/slots; invent must not mint placeholder palettes."""
    raise RuntimeError(
        "sound_design_plan:_ensure_placeholder_palette peeled — compose owns palettes"
    )


def _clear_sdp_invent_obligation(sdp: dict) -> None:
    coherence = sdp.get("coherence") if isinstance(sdp.get("coherence"), dict) else {}
    coherence = dict(coherence)
    coherence["invent_obligation"] = ""
    coherence["invent_waived"] = False
    coherence["musical_direction_complete"] = True
    coherence["deferred_ok"] = False
    if not str(coherence.get("sonic_identity") or "").strip():
        coherence["sonic_identity"] = "delivery_invent"
    sdp["coherence"] = coherence
    meta = sdp.get("_meta") if isinstance(sdp.get("_meta"), dict) else {}
    meta = dict(meta)
    meta["invent_obligation"] = ""
    meta["musical_direction_complete"] = True
    sdp["_meta"] = meta


def _clamp_sdp_asset_durations_inplace(sdp: dict) -> None:
    """Clamp asset duration_seconds to role bands (same bands as craft repair)."""
    from interview_mux.config import merged_config
    from interview_mux.deterministic_lint import ROLE_DURATION_BANDS
    from interview_mux.mmaudio_runner import clamp_duration_seconds

    assets = sdp.get("assets") or []
    if not isinstance(assets, list):
        return
    mcfg = merged_config().get("mmaudio") or {}
    by_role = (
        mcfg.get("duration_bands_by_role")
        if isinstance(mcfg.get("duration_bands_by_role"), dict)
        else {}
    )
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        dur = asset.get("duration_seconds")
        if dur is None:
            continue
        role = str(asset.get("role") or "")
        band = None
        if role and role in by_role and isinstance(by_role[role], (list, tuple)) and len(by_role[role]) == 2:
            band = (float(by_role[role][0]), float(by_role[role][1]))
        elif role in ROLE_DURATION_BANDS:
            band = ROLE_DURATION_BANDS[role]
        try:
            d = float(dur)
        except (TypeError, ValueError):
            continue
        if band:
            lo, hi = float(band[0]), float(band[1])
            if d < lo or d > hi:
                asset["duration_seconds"] = max(lo, min(hi, d))
        else:
            asset["duration_seconds"] = float(clamp_duration_seconds(d))


def _mark_skipped(ctx: RunContext, stage_key: str) -> None:
    ctx.log(
        f"{stage_key}: skipped (sound_design.enabled=false)",
        level="info",
        stage=stage_key,
    )
    heal_or_refuse_mark(ctx, stage_key, force=True)

def _attach_palette_provenance(ctx: RunContext, palettes: list[dict]) -> list[dict]:
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    bucket = str(scenario.get("atlas_bucket") or "").strip()
    tag_lineage = [
        str(row.get("tag_id"))
        for row in (sonic.get("tag_registry") or [])
        if isinstance(row, dict) and row.get("tag_id")
    ][:8]
    out: list[dict] = []
    for row in palettes:
        if not isinstance(row, dict):
            continue
        merged = dict(row)
        if bucket and not merged.get("scenario_bucket"):
            merged["scenario_bucket"] = bucket
        if tag_lineage and not merged.get("tag_lineage"):
            merged["tag_lineage"] = tag_lineage
        out.append(merged)
    return out

def _normalize_chapter_stinger_reuse(sdp: dict) -> None:
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow1 = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = flow1.get("cues") if isinstance(flow1.get("cues"), list) else []
    chapter_cues = [
        c
        for c in cues
        if isinstance(c, dict) and str(c.get("placement") or "") in {"after_segment", "before_segment"}
    ]
    if len(chapter_cues) <= 1:
        return
    first_aid = str(chapter_cues[0].get("asset_id") or "")
    if not first_aid:
        return
    for cue in chapter_cues[1:]:
        cue["asset_id"] = first_aid


def _normalize_sound_design_assets(sdp: dict) -> None:
    palettes = sdp.get("palettes") if isinstance(sdp.get("palettes"), list) else []
    default_palette = ""
    for row in palettes:
        if isinstance(row, dict) and row.get("palette_id"):
            default_palette = str(row["palette_id"])
            break
    if not default_palette:
        default_palette = "palette_default"
    assets = sdp.get("assets")
    if not isinstance(assets, list):
        return
    for item in assets:
        if not isinstance(item, dict):
            continue
        if not item.get("palette_id"):
            item["palette_id"] = default_palette


def _validate_sound_design_plan(plan: dict) -> None:
    errors = _sdp_schema_errors(plan)
    if not errors:
        return
    raise ValueError(f"Invalid sound design plan: {errors[0]}")

def _validate_flow1_asset_links(plan: dict) -> None:
    assets = plan.get("assets")
    flow_plans = plan.get("flow_plans")
    if not isinstance(assets, list) or not isinstance(flow_plans, dict):
        return
    flow1 = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = flow1.get("cues") if isinstance(flow1.get("cues"), list) else []
    asset_ids = {str(item.get("asset_id")) for item in assets if isinstance(item, dict) and item.get("asset_id")}
    missing = [
        str(cue.get("cue_id", ""))
        for cue in cues
        if isinstance(cue, dict) and str(cue.get("asset_id", "")) not in asset_ids
    ]
    if missing:
        raise ValueError(
            "Invalid sound design plan flow1: cues reference unknown asset_id values for "
            f"cue_id(s) {missing}"
        )

def _normalize_sfx_prompts(plan: dict, prompts: list[dict], ctx: RunContext | None = None) -> list[dict]:
    """One crafted row per SDP asset; compile_musicgen_prompt is authoritative."""
    assets = plan.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError(
            "sfx_prompt_craft requires assets in understanding/sound_design_plan.json; "
        )
    assets_by_id: dict[str, dict] = {
        str(item["asset_id"]): item
        for item in assets
        if isinstance(item, dict) and item.get("asset_id")
    }
    if not assets_by_id:
        raise ValueError("sfx_prompt_craft: sound design plan assets lack asset_id values")

    from interview_mux.artifact_repairs import heal_sfx_prompt_row, _sonic_keyword_tokens
    from interview_mux.music_motif import (
        compile_musicgen_prompt,
        default_motif_family,
        validate_theme_prompt,
    )
    from interview_mux.musicgen_runner import clamp_music_duration

    sonic_kws = _sonic_keyword_tokens(ctx) if ctx is not None else []
    brief: dict = {}
    if ctx is not None and ctx.artifact_exists("understanding/music_brief.json"):
        raw = ctx.read_json("understanding/music_brief.json")
        brief = raw if isinstance(raw, dict) else {}
    motif = plan.get("motif_family") if isinstance(plan.get("motif_family"), dict) else {}
    if not motif.get("prompt_dna"):
        motif = default_motif_family(brief)

    by_id: dict[str, dict] = {}
    for row in prompts:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("asset_id") or "")
        if not aid or aid not in assets_by_id:
            continue
        merged = {**row, "asset_id": aid}
        asset = assets_by_id[aid]
        role = str(asset.get("role") or merged.get("role") or "")
        kind = str(asset.get("palette_kind") or "") or None
        energy = str(asset.get("energy") or "") or None
        plan_duration = asset.get("duration_seconds")
        if plan_duration is not None:
            merged["duration_seconds"] = clamp_music_duration(
                float(plan_duration), role=role or "theme_underscore"
            )
        # Authoritative succinct recipe — overwrite long LLM prose.
        pos, neg = compile_musicgen_prompt(
            brief=brief,
            motif=motif,
            role=role or "theme_underscore",
            palette_kind=kind,
            energy=energy,
        )
        llm_prompt = str(merged.get("sfx_prompt") or "").strip()
        if not llm_prompt or len(llm_prompt) > 280 or validate_theme_prompt(llm_prompt):
            merged["sfx_prompt"] = pos
        merged["negative_prompt"] = neg
        heal_sfx_prompt_row(
            merged,
            role=role or "theme_underscore",
            duration_seconds=float(merged["duration_seconds"])
            if merged.get("duration_seconds") is not None
            else (float(plan_duration) if plan_duration is not None else None),
            sonic_keywords=sonic_kws,
        )
        # Re-assert succinct compile after heal (heal may expand).
        if len(str(merged.get("sfx_prompt") or "")) > 320 or validate_theme_prompt(
            str(merged.get("sfx_prompt") or "")
        ):
            merged["sfx_prompt"] = pos
            merged["negative_prompt"] = neg
        by_id[aid] = merged

    # Fill any missing assets from compile (LLM may omit).
    for aid, asset in assets_by_id.items():
        if aid in by_id:
            continue
        role = str(asset.get("role") or "theme_underscore")
        pos, neg = compile_musicgen_prompt(
            brief=brief,
            motif=motif,
            role=role,
            palette_kind=str(asset.get("palette_kind") or "") or None,
            energy=str(asset.get("energy") or "") or None,
        )
        dur = asset.get("duration_seconds")
        row = {
            "asset_id": aid,
            "sfx_prompt": pos,
            "negative_prompt": neg,
            "duration_seconds": clamp_music_duration(float(dur or 10), role=role)
            if dur is not None
            else 10.0,
        }
        by_id[aid] = row

    missing = sorted(set(assets_by_id) - set(by_id))
    if missing:
        raise ValueError(
            "sfx_prompt_craft: missing crafted prompt for asset_id(s) "
            + ", ".join(missing)
        )
    extra = sorted(set(by_id) - set(assets_by_id))
    if extra:
        raise ValueError(
            "sfx_prompt_craft: prompts reference unknown asset_id(s) "
            + ", ".join(extra)
        )
    # Craft may raise short stems to the MusicGen/role floor. Keep SDP in lockstep
    # so post-commit craft-vs-plan duration checks cannot loop.
    for aid, row in by_id.items():
        asset = assets_by_id.get(aid)
        if not isinstance(asset, dict):
            continue
        craft_d = row.get("duration_seconds")
        if craft_d is None:
            continue
        plan_d = asset.get("duration_seconds")
        if plan_d is None or abs(float(plan_d) - float(craft_d)) > 0.01:
            asset["duration_seconds"] = float(craft_d)
    return [by_id[aid] for aid in sorted(by_id)]

def _validate_flow2_asset_links(plan: dict) -> None:
    assets = plan.get("assets")
    flow_plans = plan.get("flow_plans")
    if not isinstance(assets, list) or not isinstance(flow_plans, dict):
        return
    flow2 = flow_plans.get("flow2") if isinstance(flow_plans.get("flow2"), dict) else {}
    cues = flow2.get("cues") if isinstance(flow2.get("cues"), list) else []
    asset_ids = {str(item.get("asset_id")) for item in assets if isinstance(item, dict) and item.get("asset_id")}
    missing = [
        str(cue.get("cue_id", ""))
        for cue in cues
        if isinstance(cue, dict) and str(cue.get("asset_id", "")) not in asset_ids
    ]
    if missing:
        raise ValueError(
            "Invalid sound design plan flow2: cues reference unknown asset_id values for "
            f"cue_id(s) {missing}"
        )
