"""Sound design plan cross-artifact validators."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context


def _sdp(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return {}
    doc = ctx.read_json("understanding/sound_design_plan.json")
    return doc if isinstance(doc, dict) else {}


def _manifest_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return set()
    manifest = ctx.read_json("segments/manifest.json")
    segs = manifest.get("segments") or [] if isinstance(manifest, dict) else []
    return {str(s.get("segment_id")) for s in segs if isinstance(s, dict) and s.get("segment_id")}


def _selection_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return set()
    sel = ctx.read_json("master/selection.json")
    return {str(x) for x in (sel.get("ordered_segment_ids") or [])}


def _ordered_selection_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    sel = ctx.read_json("master/selection.json")
    return [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]


def _avoidable_same_loop_runs(
    cues: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    ordered: list[str],
) -> list[str]:
    """Flag only runs that could alternate to an existing optional loop."""
    from interview_mux.music_motif import palette_kind_for_role

    by_id = {
        str(asset.get("asset_id")): asset
        for asset in assets
        if asset.get("asset_id")
    }
    optional_ids = {
        aid
        for aid, asset in by_id.items()
        if str(asset.get("palette_kind") or "")
        == "optional_loop"
        or palette_kind_for_role(
            str(asset.get("role") or ""), energy=str(asset.get("energy") or "") or None
        )
        == "optional_loop"
    }
    if not optional_ids:
        return []

    cfg = merged_config()
    mix = cfg.get("mix") if isinstance(cfg.get("mix"), dict) else {}
    arrangement = (
        mix.get("underbed_arrangement")
        if isinstance(mix.get("underbed_arrangement"), dict)
        else {}
    )
    try:
        max_run = max(1, int(arrangement.get("max_scene_segments", 4)))
    except (TypeError, ValueError):
        max_run = 4

    bed_by_segment: dict[str, str] = {}
    for cue in cues:
        if str(cue.get("placement") or "") != "under_segment":
            continue
        sid = str(cue.get("under_segment_id") or cue.get("segment_id") or "")
        aid = str(cue.get("asset_id") or "")
        asset = by_id.get(aid) or {}
        kind = str(asset.get("palette_kind") or "") or palette_kind_for_role(
            str(asset.get("role") or cue.get("role") or ""),
            energy=str(asset.get("energy") or "") or None,
        )
        if sid and kind in {"underscore_loop", "optional_loop"}:
            bed_by_segment[sid] = aid

    errors: list[str] = []
    run_asset = ""
    run_start = ""
    run_length = 0
    for sid in [*ordered, ""]:
        aid = bed_by_segment.get(sid, "")
        if aid and aid == run_asset:
            run_length += 1
            continue
        if run_asset and run_length > max_run:
            errors.append(
                f"avoidable same-loop run {run_asset} spans {run_length} selected segments "
                f"from {run_start}; optional_loop exists (max {max_run})"
            )
        run_asset = aid
        run_start = sid if aid else ""
        run_length = 1 if aid else 0
    return errors


def validate_post_sound_palettes(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    coherence = sdp.get("coherence") or {}
    if not str(coherence.get("sonic_identity", "")).strip():
        errors.append("SDP coherence.sonic_identity missing")
    manifest_ids = _manifest_ids(ctx)
    for pal in sdp.get("palettes") or []:
        if not isinstance(pal, dict):
            continue
        seg_ids = pal.get("segment_ids") or []
        if not seg_ids:
            errors.append(f"palette {pal.get('palette_id')} has no segment_ids")
        for sid in seg_ids:
            if manifest_ids and str(sid) not in manifest_ids:
                errors.append(f"palette segment {sid} not in manifest")
    return errors


def validate_post_sound_plan(ctx: RunContext) -> list[str]:
    """Validate podcast SDP assets/cues against selection; unique-asset caps are soft only."""
    errors: list[str] = []
    sdp = _sdp(ctx)
    cfg = merged_config()
    sd = cfg.get("sound_design") or {}
    enforce_cap = bool(sd.get("enforce_unique_asset_cap", False))
    fallback = int(sd.get("max_assets", sd.get("max_assets_flow1", 24)))
    cap = _asset_cap(ctx, fallback=fallback)
    dens: dict[str, int] = {}
    underscore = "normal"
    bed_range: list[float] | None = None
    from interview_mux.soundscape_policy import load_policy, role_bucket, strict_slots

    policy = load_policy(ctx)
    if policy:
        dens_raw = policy.get("sfx_density") if isinstance(policy.get("sfx_density"), dict) else {}
        dens = {
            "max_beds": int(dens_raw.get("max_beds") or 0),
            "max_punctuators": int(dens_raw.get("max_punctuators") or 0),
            "max_foley": int(dens_raw.get("max_foley") or 0),
        }
        policy_cap = sum(dens.values())
        if policy_cap > 0 and enforce_cap:
            cap = min(cap, policy_cap) if cap else policy_cap
        underscore = str(policy.get("underscore_policy") or "normal")
        mc = policy.get("mix_contract") if isinstance(policy.get("mix_contract"), dict) else {}
        if isinstance(mc.get("bed_level_db_range"), list) and len(mc["bed_level_db_range"]) == 2:
            bed_range = [float(mc["bed_level_db_range"][0]), float(mc["bed_level_db_range"][1])]
    elif ctx.artifact_exists("understanding/delivery_brief.json"):
        brief = ctx.read_json("understanding/delivery_brief.json")
        if isinstance(brief, dict):
            dens_raw = brief.get("sfx_density") if isinstance(brief.get("sfx_density"), dict) else {}
            dens = {
                "max_beds": int(dens_raw.get("max_beds") or 0),
                "max_punctuators": int(dens_raw.get("max_punctuators") or 0),
                "max_foley": int(dens_raw.get("max_foley") or 0),
            }
            brief_cap = sum(dens.values())
            if brief_cap > 0 and enforce_cap:
                cap = min(cap, brief_cap) if cap else brief_cap
    assets = sdp.get("assets") or []
    asset_ids = {str(a.get("asset_id")) for a in assets if isinstance(a, dict) and a.get("asset_id")}
    if enforce_cap and len(asset_ids) > cap:
        errors.append(f"asset count {len(asset_ids)} > cap {cap}")
    # Per-role unique-asset counts are soft guidance only (reuse cues freely).
    _ = dens
    _ = role_bucket
    selection_ids = _selection_ids(ctx)
    palette_seg_ids: set[str] = set()
    for pal in sdp.get("palettes") or []:
        if isinstance(pal, dict):
            palette_seg_ids.update(str(x) for x in (pal.get("segment_ids") or []))
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    if not flow and isinstance(flow_plans.get("flow1"), dict):
        flow = flow_plans["flow1"]
    cues = (flow.get("cues") or []) if isinstance(flow.get("cues"), list) else []
    sonic = load_sonic_context(ctx) or {}
    flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
    overlap_high = {str(x) for x in (flags.get("overlap_high") or [])}
    trauma_adjacent = {str(x) for x in (flags.get("trauma_adjacent") or [])}
    slot_by_seg: dict[str, set[str]] = {}
    if policy:
        for slot in policy.get("cue_slots") or []:
            if not isinstance(slot, dict):
                continue
            sid = str(slot.get("segment_id") or "")
            if sid:
                slot_by_seg.setdefault(sid, set()).update(str(r) for r in (slot.get("allowed_roles") or []))
    assets_by_id = {
        str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
    }
    under_seg_count = 0
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        for key in ("segment_id", "after_segment_id", "before_segment_id"):
            sid = cue.get(key)
            if sid and selection_ids and str(sid) not in selection_ids:
                errors.append(f"cue {cue.get('cue_id')}: {key}={sid} not in selection")
        if cue.get("placement") == "under_segment" and palette_seg_ids:
            seg = cue.get("segment_id")
            if seg and str(seg) not in palette_seg_ids:
                errors.append(f"bed cue segment {seg} outside palettes")
        if cue.get("placement") == "under_segment":
            under_seg_count += 1
            seg = str(cue.get("segment_id") or "")
            if underscore in {"skip", "sparse_or_skip"}:
                errors.append(f"under_segment cue {cue.get('cue_id')} forbidden when underscore={underscore}")
            if seg and seg in overlap_high:
                errors.append(f"bed cue segment {seg} banned for overlap_high")
            if seg and seg in trauma_adjacent:
                errors.append(f"bed cue segment {seg} banned for trauma_adjacent")
            if bed_range and cue.get("level_db") is not None:
                level = float(cue["level_db"])
                lo, hi = bed_range[0], bed_range[1]
                if level < min(lo, hi) - 0.5 or level > max(lo, hi) + 0.5:
                    errors.append(
                        f"bed cue {cue.get('cue_id')} level_db {level} outside bed_level_db_range {bed_range}"
                    )
            if policy and strict_slots() and seg:
                allowed = slot_by_seg.get(seg) or set()
                aid = str(cue.get("asset_id") or "")
                role = str((assets_by_id.get(aid) or {}).get("role") or cue.get("role") or "theme_underscore")
                # Music-only beds are interchangeable with legacy ambient_bed slots.
                compatible = set(allowed)
                if "ambient_bed" in allowed:
                    compatible.add("theme_underscore")
                if "theme_underscore" in allowed:
                    compatible.add("ambient_bed")
                if "chapter_stinger" in allowed:
                    compatible.update({"theme_chapter_resolve", "theme_transition", "theme_emphasis"})
                if not allowed or role not in compatible:
                    errors.append(
                        f"cue {cue.get('cue_id')} role {role} not in soundscape cue_slots for {seg}"
                    )
    # Stinger rate is soft — hinge coverage ratios enforce density instead of /min caps.
    _ = under_seg_count
    from interview_mux.creative_delivery import (
        validate_creative_density,
        validate_cue_segment_anchors,
    )

    errors.extend(validate_cue_segment_anchors(cues, selection_ids))
    errors.extend(validate_creative_density(ctx, sdp))
    from interview_mux.music_lane import validate_music_cue_coherence

    errors.extend(validate_music_cue_coherence(cues, [a for a in assets if isinstance(a, dict)]))
    errors.extend(
        _avoidable_same_loop_runs(
            [cue for cue in cues if isinstance(cue, dict)],
            [asset for asset in assets if isinstance(asset, dict)],
            _ordered_selection_ids(ctx),
        )
    )
    return errors


# Backward-compat aliases
validate_post_sound_plan_flow1 = validate_post_sound_plan
validate_post_sound_plan_flow2 = validate_post_sound_plan


def _role_duration_gate_error(
    aid: str, role: str, craft_d: float, plan_d: float
) -> str | None:
    """Hard-fail duration only when it cannot sit in the role band after clamp.

    Craft vs plan equality (0.25s) is not a ship gate — a 5s plan / 6s role-floor
    bump is in-band and legal.
    """
    from interview_mux.deterministic_lint import ROLE_DURATION_BANDS

    if craft_d <= 0 and plan_d <= 0:
        return f"duration missing for {aid}"
    band = ROLE_DURATION_BANDS.get(str(role or ""))
    if not band:
        return None
    lo, hi = float(band[0]), float(band[1])

    def in_band(value: float) -> bool:
        from interview_mux.stages.sound_design_stages import sdp_duration_allowed_for_role

        return sdp_duration_allowed_for_role(
            str(role or ""),
            value,
            band=(lo, hi),
        )

    if in_band(craft_d) and in_band(plan_d):
        return None
    if abs(craft_d - plan_d) <= 1.0 + 1e-9:
        return None
    clamped_craft = max(lo, min(hi, craft_d)) if craft_d > 0 else lo
    clamped_plan = max(lo, min(hi, plan_d)) if plan_d > 0 else lo
    if in_band(clamped_craft) and in_band(clamped_plan):
        return None
    return (
        f"duration outside role band for {aid}: craft={craft_d} plan={plan_d} "
        f"band={lo}-{hi}"
    )


def validate_pre_sfx_generation(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    # MU5: refuse MusicGen/GPU when creative density is thin (before acquire).
    try:
        from interview_mux.creative_delivery import validate_creative_density

        if isinstance(sdp, dict):
            errors.extend(validate_creative_density(ctx, sdp))
    except Exception:
        pass
    assets = sdp.get("assets") or []
    if not assets:
        errors.append("SDP assets[] empty before MMAudio craft")
    assets_by_id: dict[str, dict] = {
        str(a["asset_id"]): a
        for a in assets
        if isinstance(a, dict) and a.get("asset_id")
    }
    if not ctx.artifact_exists("sound_design/sfx_prompts.json"):
        errors.append("sfx_prompts.json missing")
    else:
        prompts = ctx.read_json("sound_design/sfx_prompts.json")
        rows = prompts.get("prompts") if isinstance(prompts, dict) else prompts
        if not rows:
            errors.append("no crafted prompts on disk")
        elif len(rows) < len(assets):
            errors.append("fewer prompts than SDP assets")
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            aid = str(row.get("asset_id") or "")
            if aid and aid not in assets_by_id:
                errors.append(f"crafted prompt for unknown asset_id {aid}")
            plan_asset = assets_by_id.get(aid)
            if plan_asset and row.get("duration_seconds") is not None:
                plan_d = float(plan_asset.get("duration_seconds") or 0)
                craft_d = float(row.get("duration_seconds") or 0)
                role = str(plan_asset.get("role") or row.get("role") or "")
                dur_err = _role_duration_gate_error(aid, role, craft_d, plan_d)
                if dur_err:
                    errors.append(dur_err)
    return errors


def _sdp_asset_backend_unusable(ctx: RunContext, aid: str, wav: Path) -> str | None:
    """Return reason when a present WAV is stub/silence/skipped and must count as missing."""
    for meta_path in (
        wav.with_suffix(".gen.json"),
        wav.parent / f"{aid}.gen.json",
    ):
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        backend = str(meta.get("backend") or "").strip().lower()
        if backend in {
            "musical_stub",
            "music_stub",
            "sine_stub",
            "skipped_cold_open",
            "music_omitted",
            "musicgen_failed",
            "silence",
        }:
            return backend
        if meta.get("music_omitted"):
            return "music_omitted"
    # Tiny / empty WAV ≈ silence placeholder only when gen meta says so or file empty.
    try:
        if wav.is_file() and wav.stat().st_size == 0:
            return "silence"
    except OSError:
        return "silence"
    return None


def missing_sdp_asset_wavs(ctx: RunContext) -> list[str]:
    """Referenced SDP asset_ids that do not yet have sound_design/assets/<id>.wav.

    E3 lazy MusicGen only generates cue/mix-referenced theme slots. Epoch and
    pre-mix gates must match that set — unreferenced palette rows are recorded
    as ``avoided_musicgen`` and must not block mix. When no references exist
    yet, fall back to every SDP asset (early / empty-cue plans).

    Checks the committed run dir as well as the active read path so mix
    staging cannot hide already-generated theme WAVs.

    MU1/MU8: stub / skipped_cold_open / silence backends count as missing.
    Honest ``operator/music_omitted.json`` / run_meta limbo omits do **not**.
    """
    omitted_ids: set[str] = set()
    try:
        if ctx.artifact_exists("operator/music_omitted.json"):
            doc = ctx.read_json("operator/music_omitted.json")
            for row in (doc.get("omitted") or []) if isinstance(doc, dict) else []:
                if isinstance(row, dict) and row.get("asset_id"):
                    omitted_ids.add(str(row["asset_id"]))
    except Exception:
        pass
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict):
                for aid in meta.get("music_omitted_asset_ids") or []:
                    if aid:
                        omitted_ids.add(str(aid))
    except Exception:
        pass

    required: set[str] | None = None
    try:
        from interview_mux.delivery_guardrails import referenced_musicgen_asset_ids

        refs = referenced_musicgen_asset_ids(ctx)
        if refs:
            required = {str(a) for a in refs if a}
    except Exception:
        required = None

    missing: list[str] = []
    for asset in _sdp(ctx).get("assets") or []:
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("asset_id") or "")
        if not aid:
            continue
        if aid in omitted_ids:
            continue
        if required is not None and aid not in required:
            continue
        wav = ctx.read_path("sound_design", "assets", f"{aid}.wav")
        if not wav.is_file():
            try:
                committed = ctx.final_path("sound_design", "assets", f"{aid}.wav")
            except Exception:
                committed = ctx.run_dir / "sound_design" / "assets" / f"{aid}.wav"
            if committed.is_file():
                wav = committed
            else:
                missing.append(aid)
                continue
        bad = _sdp_asset_backend_unusable(ctx, aid, wav)
        if bad:
            missing.append(aid)
            continue
        # Speech-free beds: stub-sized / digital-silence WAVs count as missing.
        try:
            from interview_mux.theme_slot_integrity import (
                is_speech_free_theme_role,
                wav_is_audible,
            )

            role = str(asset.get("role") or "")
            if is_speech_free_theme_role(role) and not wav_is_audible(wav):
                missing.append(aid)
        except Exception:
            pass
    return missing


def validate_pre_mix(ctx: RunContext, flow: str = "podcast") -> list[str]:
    _ = flow  # podcast-only delivery
    from interview_mux.edl_source_contract import (
        EDL_REL,
        edl_source_path_ghosts,
        persist_sanitized_edl,
    )

    persist_sanitized_edl(ctx)
    errors: list[str] = list(validate_post_mmaudio_qa(ctx))
    if ctx.artifact_exists(EDL_REL):
        try:
            edl = ctx.read_json(EDL_REL)
        except Exception:
            edl = None
        leftover = edl_source_path_ghosts(ctx, edl if isinstance(edl, dict) else None)
        if leftover:
            errors.append(
                "master/edl.json source_path names missing files: " + ", ".join(leftover[:4])
            )
        # EM5: speech clip order must equal selection ordered_segment_ids.
        if isinstance(edl, dict) and ctx.artifact_exists("master/selection.json"):
            try:
                from interview_mux.order_hash import assert_selection_leads_edl

                sel = ctx.read_json("master/selection.json")
                if isinstance(sel, dict):
                    assert_selection_leads_edl(sel, edl)
            except Exception as exc:
                errors.append(f"pre_mix speech/selection order: {exc}")
    for aid in missing_sdp_asset_wavs(ctx):
        errors.append(f"missing WAV for asset_id {aid}")
    return errors


def validate_pre_master(ctx: RunContext, flow: str = "podcast") -> list[str]:
    """Cross-check assembly readiness before loudnorm (mix completeness + QC + listen gate)."""
    errors: list[str] = list(validate_pre_mix(ctx, flow))
    from interview_mux.gates import check_post_listen_gate_pending
    from interview_mux.mix_completeness import _missing_sfx_from_mmaudio_qa

    for aid in sorted(_missing_sfx_from_mmaudio_qa(ctx)):
        msg = f"mmaudio_qa placeholder/failed for {aid}"
        if msg not in errors:
            errors.append(msg)

    cfg = merged_config()
    mix_cfg = cfg.get("mix") or {}
    intel_cfg = mix_cfg.get("intelligibility_qc") if isinstance(mix_cfg.get("intelligibility_qc"), dict) else {}
    if bool(intel_cfg.get("enabled", False)):
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        summaries = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
        intel = summaries.get("mix_intelligibility")
        if isinstance(intel, dict) and intel.get("passed") is False:
            errors.append("mix_intelligibility QC failed")

    failed_listen = check_post_listen_gate_pending(ctx)
    if failed_listen:
        errors.append(f"post_listen failed for: {', '.join(failed_listen[:6])}")

    return errors


def _asset_cap(ctx: RunContext, *, fallback: int) -> int:
    cfg = merged_config()
    sound = cfg.get("sound_design") or {}
    if not bool(sound.get("use_adaptive_caps", False)):
        return fallback
    sonic = load_sonic_context(ctx) or {}
    mix_policy = sonic.get("mix_policy") if isinstance(sonic.get("mix_policy"), dict) else {}
    val = mix_policy.get("adaptive_max_assets")
    if val is None:
        val = mix_policy.get("adaptive_max_assets_flow1")
    if val is None:
        return fallback
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return fallback


def validate_post_sonic_context(ctx: RunContext) -> list[str]:
    """Cross-check sonic_context after sonic_context_build (BUILD-SFX-01)."""
    from interview_mux.prompt_validation import validate_sonic_context

    rel = "understanding/sonic_context.json"
    if not ctx.artifact_exists(rel):
        return [f"{rel} missing"]
    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return [f"{rel} is not an object"]
    errors = [f"sonic_context.{e}" for e in validate_sonic_context(doc)]
    if errors:
        return errors
    registry = doc.get("tag_registry") or []
    if not registry and not doc.get("sparse_mode"):
        errors.append("sonic_context.tag_registry empty without sparse_mode")
    return errors


def validate_post_mmaudio_qa(ctx: RunContext) -> list[str]:
    """Cross-check mmaudio_qa after generation (BUILD-SFX-01)."""
    from interview_mux.prompt_validation import validate_mmaudio_qa

    rel = "sound_design/mmaudio_qa.json"
    if not ctx.artifact_exists(rel):
        return []
    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return [f"{rel} is not an object"]
    errors = [f"mmaudio_qa.{e}" for e in validate_mmaudio_qa(doc)]
    for row in doc.get("assets") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("generation_status") or "").lower()
        verdict = str(row.get("verdict") or "").lower()
        if status in {"failed", "placeholder"} and verdict == "pass":
            aid = row.get("asset_id", "?")
            errors.append(f"mmaudio_qa asset {aid}: generation_status={status} but verdict=pass")
        if row.get("silence_detected") is True and verdict == "pass":
            aid = row.get("asset_id", "?")
            errors.append(f"mmaudio_qa asset {aid}: silence_detected with verdict=pass")
        reasons = [str(r) for r in (row.get("reasons") or [])]
        if verdict == "pass" and any(
            r in reasons for r in ("room_timbre_mismatch", "trauma_percussive_transient", "spectral_bucket_mismatch")
        ):
            aid = row.get("asset_id", "?")
            flagged = [r for r in reasons if r in ("room_timbre_mismatch", "trauma_percussive_transient", "spectral_bucket_mismatch")]
            errors.append(f"mmaudio_qa asset {aid}: verdict=pass with reasons {flagged}")
    return errors
