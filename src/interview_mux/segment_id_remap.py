"""Shared ``seg_*`` rewrite walker for hitch, connector fuse, and diarization fuse.

Map-replace (never orphan-drop). Hitch and fuse must call the same helper so a
consumed id cannot linger in gap_report, narrative, EDL, or VO pickup names.
"""
from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

SEGMENT_ID_KEYS = frozenset(
    {
        "segment_id",
        "suggested_open_segment_id",
        "before_segment_id",
        "after_segment_id",
        "targets_segment_id",
        "drop_segment_id",
        "survivor_segment_id",
        "open_segment_id",
        "hook_segment_id",
        "primary_segment_id",
    }
)
SEGMENT_ID_LIST_KEYS = frozenset(
    {
        "segment_ids",
        "ordered_segment_ids",
        "excluded_segment_ids",
        "must_keep_segment_ids",
        "high_value_segment_ids",
        "bound_segment_ids",
        "evidence_segment_ids",
        "fused_from",
        "orphan_segment_ids",
        "vernacular_must_keep_segment_ids",
        "must_keep_ids",
        "overlap_segment_ids",
        "source_segment_ids",
        "segment_ids_touched",
        "split_into",
        "sequence_order",
    }
)

# Artifacts that store live ``seg_*`` ids. Hitch adds intent_plan separately.
SHARED_REMAP_RELS = (
    "understanding/content_brief.json",
    "understanding/talking_points.json",
    "understanding/ideal_cuts.json",
    "understanding/ideal_cuts_materialized.json",
    "understanding/ideal_cuts_selection_seed.json",
    "analysis/low_conf_must_keep.json",
    "analysis/high_value_speech_boosts.json",
    "analysis/high_value_speech_islands.json",
    "analysis/stt_lexicon_island_boosts.json",
    "segments/nle_edits.json",
    "operator/must_keep.json",
    "understanding/analysis_state.json",
    "understanding/investigation_queue.json",
    "understanding/context_index.json",
    "understanding/omit_ledger.json",
    "understanding/gap_report.json",
    "understanding/gap_evaluations.json",
    "understanding/nugget_layup_plan.json",
    "understanding/episode_structure.json",
    "vo_pickup/synthesis_report.json",
    "master/selection.json",
    "master/narrative_plan.json",
    "master/transitions.json",
    "master/coverage_audit.json",
    "master/edl.json",
    "transcripts/index.json",
)


def rewrite_embedded_segment_ids(text: str, mapping: dict[str, str]) -> str:
    """Rewrite exact ids and embedded tokens (``vo_seed_seg_001``, evidence refs)."""
    if not mapping or not text:
        return text
    if text in mapping:
        return mapping[text]
    pairs = sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
    out = text
    for old, new in pairs:
        if not old or old == new or old not in out:
            continue
        out = re.sub(rf"(?<![0-9A-Za-z]){re.escape(old)}(?![0-9A-Za-z])", new, out)
    return out


def compose_segment_maps(*maps: dict[str, str]) -> dict[str, str]:
    """Chain old→mid→live maps so leftover hitch ids and original ids both resolve."""
    combined: dict[str, str] = {}
    for mapping in maps:
        if not mapping:
            continue
        chained = {old: mapping.get(new, new) for old, new in combined.items()}
        combined = chained
        for old, new in mapping.items():
            if old and new:
                combined[str(old)] = str(new)
    return combined


def apply_segment_id_map(value: Any, mapping: dict[str, str]) -> Any:
    """Rewrite segment ids in nested JSON. Map replace, not orphan-drop."""
    if not mapping:
        return value
    if isinstance(value, str):
        return rewrite_embedded_segment_ids(value, mapping)
    if isinstance(value, list):
        return [apply_segment_id_map(v, mapping) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k in SEGMENT_ID_KEYS and isinstance(v, str):
                out[k] = rewrite_embedded_segment_ids(v, mapping)
            elif k in SEGMENT_ID_LIST_KEYS and isinstance(v, list):
                mapped: list[Any] = []
                seen_ids: set[str] = set()
                for item in v:
                    if isinstance(item, str):
                        rewritten = rewrite_embedded_segment_ids(item, mapping)
                        if rewritten in seen_ids:
                            continue
                        seen_ids.add(rewritten)
                        mapped.append(rewritten)
                    else:
                        mapped.append(apply_segment_id_map(item, mapping))
                out[k] = mapped
            elif k == "source_path":
                # File pointers are not segment-id fields. Rewriting tokens inside
                # ``tr_seg_055_seg_061.wav`` would invent a missing ``…058…`` name.
                out[k] = v
            else:
                out[k] = apply_segment_id_map(v, mapping)
        return out
    return value


def _pop_transition_source_paths(edl: dict[str, Any]) -> dict[str, Any]:
    """Drop transition file pointers after neighbor ids change (never reuse old-pair WAVs)."""
    clips: list[Any] = []
    changed = False
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or str(clip.get("type") or "") != "transition":
            clips.append(clip)
            continue
        if "source_path" not in clip:
            clips.append(clip)
            continue
        row = dict(clip)
        row.pop("source_path", None)
        row["duration_ms"] = 0
        clips.append(row)
        changed = True
    if not changed:
        return edl
    out = dict(edl)
    out["clips"] = clips
    return out


def _clear_stale_vo_stage_done(ctx: RunContext) -> None:
    for sid in ("vo_synthesize", "edl", "mix"):
        marker = ctx.final_path(".stage_done", sid)
        if marker.is_file():
            try:
                marker.unlink()
            except OSError:
                pass


def _resync_current_transition_audio(ctx: RunContext) -> None:
    """Generate current-pair WAVs and restamp EDL paths after neighbor ids change."""
    from interview_mux.transition_vo import (
        commit_current_transition_wavs,
        restamp_edl_transition_source_paths,
    )

    if ctx.artifact_exists("master/transitions.json"):
        try:
            commit_current_transition_wavs(ctx)
        except Exception as exc:
            ctx.log(
                f"segment remap VO resync: {exc}",
                level="warning",
                stage="segment_id_remap",
            )
    try:
        restamp_edl_transition_source_paths(ctx)
    except Exception as exc:
        ctx.log(
            f"segment remap EDL restamp: {exc}",
            level="warning",
            stage="segment_id_remap",
        )
    _clear_stale_vo_stage_done(ctx)


def _preserve_prior_producer_stage(
    prior: Any, rewritten: Any
) -> Any:
    """Integrity remaps must not flip shared-path ``_meta.producer_stage`` (S2)."""
    if not isinstance(prior, dict) or not isinstance(rewritten, dict):
        return rewritten
    prior_meta = prior.get("_meta") if isinstance(prior.get("_meta"), dict) else {}
    prior_prod = str(prior_meta.get("producer_stage") or "").strip()
    if not prior_prod:
        return rewritten
    out = dict(rewritten)
    meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
    meta["producer_stage"] = prior_prod
    out["_meta"] = meta
    return out


def rewrite_artifact_segment_refs(
    ctx: RunContext,
    mapping: dict[str, str],
    *,
    extra_rels: tuple[str, ...] | list[str] = (),
    skip_handoff: bool = True,
    stage_key: str | None = None,
) -> list[str]:
    """Rewrite every known ``seg_*`` consumer present on disk."""
    updated: list[str] = []
    if not mapping:
        return updated
    seen: set[str] = set()
    rels = list(SHARED_REMAP_RELS) + [str(r) for r in extra_rels]
    for rel in rels:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        rewritten = apply_segment_id_map(doc, mapping)
        rewritten = _preserve_prior_producer_stage(doc, rewritten)
        if rel == "master/edl.json" and isinstance(rewritten, dict):
            rewritten = _pop_transition_source_paths(rewritten)
        if rewritten != doc:
            if rel == "master/edl.json" and isinstance(rewritten, dict):
                from interview_mux.air_order import write_live_edl

                write_live_edl(ctx, rewritten, source=stage_key or "segment_id_remap")
                updated.append(rel)
                continue
            kwargs: dict[str, Any] = {
                "skip_handoff": skip_handoff,
                "mutation_class": "segment_id_remap",
            }
            if stage_key:
                kwargs["stage_key"] = stage_key
            if rel == "understanding/gap_report.json":
                # The gap report body has a sole-writer rule. An id remap that
                # only relabels targets passes on mutation_class alone, but a
                # remap after a merge can fold two lines onto one target, and
                # that counts as a body change: the hitch's own key was refused
                # with "gap_body_writers:gap_framing_compose|nugget_layup_compose"
                # and delivery cascaded. Name the owner the check itself
                # suggests, keyed off the prior doc exactly as it keys.
                kwargs["stage_key"] = gap_report_remap_owner(doc)
            ctx.write_json(rel, rewritten, **kwargs)
            updated.append(rel)
    return updated


def gap_report_remap_owner(prior: Any) -> str:
    """The stage assert_gap_report_body_sole_writer accepts for a remap write.

    After ``nugget_layup_authority`` layup is the sole body writer; before it,
    compose is the writer the check suggests. Mirrors the check rather than
    guessing, and keys off the prior on-disk doc because that is what it reads.
    """
    from interview_mux.artifact_ownership import gap_report_body_owner

    return gap_report_body_owner(prior)


def apply_full_segment_id_remap(
    ctx: RunContext,
    mapping: dict[str, str],
    *,
    extra_rels: tuple[str, ...] | list[str] = (),
    stage_key: str | None = None,
    skip_handoff: bool = True,
    rebind_vo: bool = True,
) -> list[str]:
    """Walker + optional ``vo_pickup`` filename rebind."""
    updated = rewrite_artifact_segment_refs(
        ctx,
        mapping,
        extra_rels=extra_rels,
        skip_handoff=skip_handoff,
        stage_key=stage_key,
    )
    if rebind_vo and mapping and hasattr(ctx, "final_path"):
        from interview_mux.chapter_close_hitch import rebind_vo_pickup_files

        updated.extend(rebind_vo_pickup_files(ctx, mapping))
    vo_artifacts = {"master/transitions.json", "master/edl.json"}
    if mapping and vo_artifacts.intersection(updated):
        _resync_current_transition_audio(ctx)
    return updated
