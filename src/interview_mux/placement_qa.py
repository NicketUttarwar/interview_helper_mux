"""Deterministic post-generation placement QA — outputs adjustment hints for mix."""

from __future__ import annotations

import copy
import json
from typing import Any

from interview_mux.config import merged_config
from interview_mux.mmaudio_asset_qa import load_mmaudio_qa
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

OUTPUT_PATH = "sound_design/placement_adjustments.json"

# Remaster / junction-owned keys: regenerate must merge, never wipe.
_REMASTER_NUMERIC_FLOOR_KEYS = (
    "suggested_crossfade_ms",
    "suggested_pad_ms",
    "pad_ms",
    "pad_before_ms",
    "pad_after_ms",
    "suggested_trim_ms",
)
_REMASTER_PRESERVE_KEYS = (
    *_REMASTER_NUMERIC_FLOOR_KEYS,
    "suggested_level_db_delta",
    "snip_override",
    "snip_overrides",
    "placement_hint",
    "music_placement",
    "suggested_placement",
    "music_placement_hint",
)
# Mix apply_placement_adjustments reads these — detect=apply parity.
_MIX_APPLY_HINT_KEYS = (
    "suggested_level_db_delta",
    "suggested_crossfade_ms",
    "suggested_trim_ms",
    "suggested_pad_ms",
    "pad_ms",
    "pad_before_ms",
    "pad_after_ms",
    "snip_override",
    "snip_overrides",
    "placement_hint",
    "music_placement",
    "suggested_placement",
    "music_placement_hint",
    "action",
)
_REMASTER_KEEP_ACTIONS = frozenset(
    {
        "adjust_crossfade",
        "adjust_music_fade",
        "adjust_pad",
        "adjust_snip",
        "adjust_placement",
        "skip",
        "skip_cue",
    }
)


def placement_qa_enabled(cfg: dict[str, Any] | None = None) -> bool:
    c = cfg if cfg is not None else merged_config()
    return bool((c.get("sound_design") or {}).get("placement_qa_enabled", False))


def load_placement_adjustments(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(OUTPUT_PATH):
        return {"adjustments": []}
    doc = ctx.read_json(OUTPUT_PATH)
    return doc if isinstance(doc, dict) else {"adjustments": []}


def _mmaudio_qa_adjustments(ctx: RunContext) -> list[dict[str, Any]]:
    qa = load_mmaudio_qa(ctx)
    out: list[dict[str, Any]] = []
    for row in qa.get("assets") or []:
        if not isinstance(row, dict) or not row.get("asset_id"):
            continue
        aid = str(row["asset_id"])
        verdict = str(row.get("verdict") or "pass")
        if verdict == "pass" and not row.get("suggested_level_db_delta"):
            if row.get("suggested_crossfade_ms") is None:
                continue
        adj: dict[str, Any] = {
            "asset_id": aid,
            "role": row.get("role"),
            "mmaudio_qa_verdict": verdict,
            "provenance": {
                "rule_id": "mmaudio_qa",
                "source_artifact": "sound_design/mmaudio_qa.json",
                "detail": "Imported deterministic QA suggestion.",
            },
            "adaptive_level_source": "mmaudio_qa",
        }
        if row.get("reasons"):
            adj["reason"] = "; ".join(str(r) for r in row["reasons"])
        if row.get("action"):
            adj["action"] = row["action"]
        if row.get("suggested_level_db_delta") is not None:
            adj["suggested_level_db_delta"] = float(row["suggested_level_db_delta"])
        if row.get("suggested_crossfade_ms") is not None:
            adj["suggested_crossfade_ms"] = int(row["suggested_crossfade_ms"])
        if row.get("suggested_trim_ms") is not None:
            adj["suggested_trim_ms"] = int(row["suggested_trim_ms"])
        out.append(adj)
    return out


def run_placement_qa(ctx: RunContext) -> dict[str, Any]:
    """
    Inspect generated assets vs SDP cues; emit conservative level/timing hints.
    Merges mmaudio_qa.json when present.
    """
    adjustments: list[dict[str, Any]] = []
    mmaudio_adj = _mmaudio_qa_adjustments(ctx)
    by_asset = {str(a["asset_id"]): a for a in mmaudio_adj}

    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        doc = {"version": 1, "adjustments": mmaudio_adj}
        _write_placement_doc(ctx, doc)
        return doc

    sdp = ctx.read_json("understanding/sound_design_plan.json")
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    bucket = str(scenario.get("atlas_bucket") or "")
    flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
    overlap_high = {str(x) for x in (flags.get("overlap_high") or [])}
    trauma_adjacent = {str(x) for x in (flags.get("trauma_adjacent") or [])}
    flow1_cues = (
        ((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
        if isinstance(sdp, dict)
        else []
    )
    cue_by_asset: dict[str, dict[str, Any]] = {}
    for cue in flow1_cues:
        if isinstance(cue, dict) and cue.get("asset_id"):
            cue_by_asset[str(cue.get("asset_id"))] = cue
    assets_dir = ctx.final_path("sound_design", "assets")
    for asset in sdp.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("asset_id", ""))
        if not aid:
            continue
        if aid in by_asset:
            adjustments.append(by_asset[aid])
            continue
        wav = ctx.read_path("sound_design", "assets", f"{aid}.wav")
        role = str(asset.get("role", ""))
        row: dict[str, Any] = {"asset_id": aid, "role": role}
        cue = cue_by_asset.get(aid) or {}
        if not wav.is_file():
            row["action"] = "placeholder_silence"
            row["reason"] = "missing_wav"
            row["provenance"] = {
                "rule_id": "asset_missing",
                "source_artifact": "sound_design/assets",
                "detail": "WAV missing for asset_id.",
            }
            row["adaptive_level_source"] = "default"
            adjustments.append(row)
            continue
        try:
            size = wav.stat().st_size
            if size < 1000:
                row["action"] = "regenerate"
                row["reason"] = "suspiciously_small_wav"
                row["provenance"] = {
                    "rule_id": "asset_small",
                    "source_artifact": "sound_design/assets",
                    "detail": "Generated WAV size below safe threshold.",
                }
                row["adaptive_level_source"] = "default"
                adjustments.append(row)
        except OSError:
            row["action"] = "regenerate"
            row["reason"] = "unreadable_wav"
            row["provenance"] = {
                "rule_id": "asset_unreadable",
                "source_artifact": "sound_design/assets",
                "detail": "Failed to stat/read generated WAV.",
            }
            row["adaptive_level_source"] = "default"
            adjustments.append(row)
            continue
        if role == "ambient_bed":
            row["suggested_level_db_delta"] = -2.0
            row["reason"] = "default_speech_first_bed_lower"
            row["provenance"] = {
                "rule_id": "ambient_default_lower",
                "source_artifact": "understanding/source_acoustic_profile.json",
                "detail": "Speech-first default bed ducking.",
            }
            row["adaptive_level_source"] = "sap_percentile"
            seg_id = str(cue.get("segment_id") or "")
            if seg_id and (seg_id in overlap_high or seg_id in trauma_adjacent):
                row["action"] = "skip"
                row["scenario_override"] = True
                row["reason"] = "scenario_segment_ban"
                row["provenance"] = {
                    "rule_id": "sonic_context_segment_ban",
                    "source_artifact": "understanding/sonic_context.json",
                    "detail": f"segment_id={seg_id} flagged overlap/trauma.",
                }
            elif bucket in {"panel", "trauma_adjacent", "noisy_room"}:
                row["suggested_level_db_delta"] = float(row["suggested_level_db_delta"]) - 2.0
                row["scenario_override"] = True
                row["provenance"] = {
                    "rule_id": "sonic_context_bucket_override",
                    "source_artifact": "understanding/sonic_context.json",
                    "detail": f"atlas_bucket={bucket}",
                }
            adjustments.append(row)
        elif role == "chapter_stinger":
            row["suggested_crossfade_ms"] = 120
            row["provenance"] = {
                "rule_id": "chapter_stinger_crossfade",
                "source_artifact": "sound_design/sound_design_plan.json",
                "detail": "Default chapter stinger smoothing.",
            }
            row["adaptive_level_source"] = "default"
            adjustments.append(row)

    for aid, adj in by_asset.items():
        if aid not in {a.get("asset_id") for a in adjustments}:
            adjustments.append(adj)

    adjustments = _ensure_theme_bookend_crossfade_floors(adjustments, flow1_cues)
    # Remaster mix re-runs placement_qa and must not clobber junction remaster
    # fields (exec_13161: adjust_music_fade applied → mix wipe → oscillation_halt).
    adjustments = _merge_preserve_remaster_fields(ctx, adjustments)

    doc = {"version": 1, "adjustments": adjustments}
    _write_placement_doc(ctx, doc)
    return doc


def _theme_soft_crossfade_ms() -> int:
    try:
        return int(
            ((merged_config().get("junction_snip_qa") or {}).get("music_soft_crossfade_ms"))
            or 180
        )
    except (TypeError, ValueError):
        return 180


def _cue_needs_theme_soft_crossfade(cue: dict[str, Any], role: str) -> bool:
    placement = str(cue.get("placement") or "")
    if role in {"theme_cold_open", "theme_outro", "theme_emphasis"}:
        return True
    return bool(
        role.startswith("theme_") and placement in {"before_segment", "after_segment"}
    )


def _ensure_theme_bookend_crossfade_floors(
    adjustments: list[dict[str, Any]],
    cues: list[Any],
) -> list[dict[str, Any]]:
    """Guarantee soft XF hints for theme bookends/stingers (incl. mmaudio rows)."""
    soft_xf = _theme_soft_crossfade_ms()
    by_aid: dict[str, dict[str, Any]] = {}
    for row in adjustments:
        if isinstance(row, dict) and row.get("asset_id"):
            by_aid[str(row["asset_id"])] = dict(row)

    for cue in cues:
        if not isinstance(cue, dict):
            continue
        aid = str(cue.get("asset_id") or "")
        if not aid:
            continue
        role = str(cue.get("role") or (by_aid.get(aid) or {}).get("role") or "")
        if not _cue_needs_theme_soft_crossfade(cue, role):
            continue
        cue_xf = cue.get("crossfade_ms")
        try:
            cue_i = int(cue_xf) if cue_xf is not None else None
        except (TypeError, ValueError):
            cue_i = None
        if cue_i is not None and cue_i >= soft_xf:
            continue
        row = by_aid.get(aid) or {"asset_id": aid, "role": role}
        try:
            have = int(row["suggested_crossfade_ms"]) if row.get("suggested_crossfade_ms") is not None else None
        except (TypeError, ValueError):
            have = None
        if have is not None and have >= soft_xf:
            by_aid[aid] = row
            continue
        row = dict(row)
        row["suggested_crossfade_ms"] = soft_xf
        row.setdefault("action", "adjust_crossfade")
        row.setdefault("reason", "theme_bookend_soft_crossfade")
        row.setdefault(
            "provenance",
            {
                "rule_id": "theme_bookend_crossfade",
                "source_artifact": "understanding/sound_design_plan.json",
                "detail": f"role={role} placement={cue.get('placement')}",
            },
        )
        row.setdefault("adaptive_level_source", "default")
        if role and not row.get("role"):
            row["role"] = role
        by_aid[aid] = row

    # Preserve order: prior adjustments first, then any cue-only additions.
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in adjustments:
        if not isinstance(row, dict) or not row.get("asset_id"):
            continue
        aid = str(row["asset_id"])
        out.append(by_aid.get(aid) or row)
        seen.add(aid)
    for aid, row in by_aid.items():
        if aid not in seen:
            out.append(row)
    return out


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_has_remaster_fields(row: dict[str, Any]) -> bool:
    if any(row.get(k) is not None for k in _REMASTER_PRESERVE_KEYS):
        return True
    action = str(row.get("action") or "")
    if action in _REMASTER_KEEP_ACTIONS:
        return True
    reason = str(row.get("reason") or "")
    prov = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    return "junction" in reason or str(prov.get("rule_id") or "").startswith("junction")


def _merge_preserve_remaster_fields(
    ctx: RunContext, adjustments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge-only remaster fields: XF floors, pads, snip overrides, music hints.

    Pattern: load prior → apply new deltas → keep floors / non-touched ids.
    Alias retained for callers: ``_merge_preserve_crossfade_floors``.
    """
    prev = load_placement_adjustments(ctx)
    prev_by: dict[str, dict[str, Any]] = {}
    for row in prev.get("adjustments") or []:
        if isinstance(row, dict) and row.get("asset_id"):
            prev_by[str(row["asset_id"])] = row
    if not prev_by:
        return adjustments

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in adjustments:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("asset_id") or "")
        if not aid:
            out.append(row)
            continue
        seen.add(aid)
        old = prev_by.get(aid) or {}
        merged = dict(row)
        for key in _REMASTER_NUMERIC_FLOOR_KEYS:
            old_i = _as_int(old.get(key))
            new_i = _as_int(merged.get(key))
            if old_i is not None and (new_i is None or new_i < old_i):
                merged[key] = old_i
        for key in _REMASTER_PRESERVE_KEYS:
            if key in _REMASTER_NUMERIC_FLOOR_KEYS:
                continue
            if merged.get(key) is None and old.get(key) is not None:
                merged[key] = old.get(key)
        old_action = str(old.get("action") or "")
        if old_action in _REMASTER_KEEP_ACTIONS and not merged.get("action"):
            merged["action"] = old_action
        if old.get("reason") and not merged.get("reason"):
            merged["reason"] = old.get("reason")
        prov = old.get("provenance")
        if isinstance(prov, dict) and str(prov.get("rule_id") or "").startswith(
            "junction"
        ):
            if not isinstance(merged.get("provenance"), dict) or str(
                (merged.get("provenance") or {}).get("rule_id") or ""
            ).startswith("junction"):
                merged["provenance"] = prov
            elif old_action in _REMASTER_KEEP_ACTIONS:
                merged["provenance"] = prov
        out.append(merged)

    for aid, old in prev_by.items():
        if aid in seen:
            continue
        if _row_has_remaster_fields(old):
            out.append(dict(old))
    return out


# Back-compat alias (i4 tests / callers).
_merge_preserve_crossfade_floors = _merge_preserve_remaster_fields


def music_repair_would_apply(ctx: RunContext, hint: dict[str, Any] | None) -> bool:
    """True when a music/junction repair hint is durable and mix would apply it.

    Detect-only without an apply path must not be marked ``applied``.
    """
    if not isinstance(hint, dict):
        return False
    aid = str(hint.get("asset_id") or "")
    if not aid:
        detail = hint.get("detail") if isinstance(hint.get("detail"), dict) else {}
        aid = str(detail.get("asset_id") or "")
    if not aid:
        return False

    # Normalize repair finding → adjustment-shaped hint.
    detail = hint.get("detail") if isinstance(hint.get("detail"), dict) else {}
    candidate = dict(hint)
    if detail:
        for k in (*_MIX_APPLY_HINT_KEYS, "suggested_crossfade_ms"):
            if candidate.get(k) is None and detail.get(k) is not None:
                candidate[k] = detail.get(k)
    candidate["asset_id"] = aid

    has_apply_field = any(
        candidate.get(k) is not None for k in _MIX_APPLY_HINT_KEYS if k != "action"
    )
    action = str(candidate.get("action") or "")
    if action in {"skip", "skip_cue", "adjust_crossfade", "adjust_music_fade", "adjust_pad", "adjust_snip", "adjust_placement", "adjust_level"}:
        has_apply_field = True
    if not has_apply_field:
        return False

    doc = load_placement_adjustments(ctx)
    durable: dict[str, Any] | None = None
    for row in doc.get("adjustments") or []:
        if isinstance(row, dict) and str(row.get("asset_id") or "") == aid:
            durable = row
            break
    if durable is None:
        return False

    # Hint values must be present on the durable row (or floors already higher).
    for key in _MIX_APPLY_HINT_KEYS:
        if key == "action":
            continue
        want = candidate.get(key)
        if want is None:
            continue
        have = durable.get(key)
        if have is None:
            return False
        if key in _REMASTER_NUMERIC_FLOOR_KEYS:
            want_i = _as_int(want)
            have_i = _as_int(have)
            if want_i is not None and have_i is not None and have_i < want_i:
                return False
        elif have != want and str(have) != str(want):
            # Placement / snip hints: durable must match.
            if key in {"placement_hint", "music_placement", "suggested_placement", "music_placement_hint", "snip_override"}:
                return False

    # Mix consumer path: apply_placement_adjustments must mutate this asset.
    probe = [{"asset_id": aid, "level_db": -24.0, "crossfade_ms": 0}]
    applied = apply_placement_adjustments(ctx, probe)
    if not applied or not isinstance(applied[0], dict):
        return False
    cue = applied[0]
    if cue.get("skip"):
        return True
    if cue.get("crossfade_ms") is not None and int(cue.get("crossfade_ms") or 0) > 0:
        return True
    if cue.get("trim_tail_ms") is not None:
        return True
    if cue.get("pad_ms") is not None or cue.get("pad_before_ms") is not None or cue.get("pad_after_ms") is not None:
        return True
    if cue.get("placement_hint") or cue.get("music_placement") or cue.get("snip_override"):
        return True
    if float(cue.get("level_db") or -24.0) != -24.0:
        return True
    # Durable skip/level-only with zero delta still counts if action is skip.
    if str(durable.get("action") or "") in {"skip", "skip_cue"}:
        return True
    if durable.get("suggested_crossfade_ms") is not None:
        return int(cue.get("crossfade_ms") or 0) >= int(durable["suggested_crossfade_ms"])
    return False


def _write_placement_doc(ctx: RunContext, doc: dict[str, Any]) -> None:
    out = ctx.path(*OUTPUT_PATH.split("/"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    adjustments = doc.get("adjustments") or []
    if adjustments:
        ctx.log(
            f"placement_qa: {len(adjustments)} adjustment hint(s) → {OUTPUT_PATH}",
            level="info",
            stage="mix",
        )


def apply_placement_adjustments(
    ctx: RunContext,
    cues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply level/crossfade/pad/snip/placement hints from placement_adjustments.json."""
    doc = load_placement_adjustments(ctx)
    by_asset: dict[str, dict[str, Any]] = {}
    for row in doc.get("adjustments") or []:
        if isinstance(row, dict) and row.get("asset_id"):
            by_asset[str(row["asset_id"])] = row
    if not by_asset:
        return cues
    out: list[dict[str, Any]] = []
    level_applied = 0
    crossfade_applied = 0
    for cue in cues:
        if not isinstance(cue, dict):
            out.append(cue)
            continue
        cue_copy = copy.deepcopy(cue)
        aid = str(cue_copy.get("asset_id") or "")
        adj = by_asset.get(aid)
        if adj:
            if str(adj.get("action") or "") in {"skip", "skip_cue"}:
                cue_copy["skip"] = True
            elif str(adj.get("action") or "") == "adjust_level" and adj.get("suggested_level_db_delta") is None:
                adj = {**adj, "suggested_level_db_delta": -2.0}
            delta = adj.get("suggested_level_db_delta")
            if delta is not None:
                cue_copy["level_db"] = float(cue_copy.get("level_db", -24.0)) + float(delta)
                level_applied += 1
            if adj.get("suggested_crossfade_ms") is not None:
                cue_copy["crossfade_ms"] = int(adj["suggested_crossfade_ms"])
                crossfade_applied += 1
            if adj.get("suggested_trim_ms") is not None:
                cue_copy["trim_tail_ms"] = int(adj["suggested_trim_ms"])
            for pad_key in ("suggested_pad_ms", "pad_ms", "pad_before_ms", "pad_after_ms"):
                if adj.get(pad_key) is not None:
                    out_key = "pad_ms" if pad_key == "suggested_pad_ms" else pad_key
                    cue_copy[out_key] = int(adj[pad_key])
            if adj.get("snip_override") is not None:
                cue_copy["snip_override"] = adj["snip_override"]
            if adj.get("snip_overrides") is not None:
                cue_copy["snip_overrides"] = adj["snip_overrides"]
            for place_key in (
                "placement_hint",
                "music_placement",
                "suggested_placement",
                "music_placement_hint",
            ):
                if adj.get(place_key) is not None:
                    cue_copy[place_key] = adj[place_key]
        out.append(cue_copy)
    if level_applied or crossfade_applied:
        ctx.log(
            f"placement_qa: applied level to {level_applied} cue(s), crossfade to {crossfade_applied} cue(s)",
            level="info",
            stage="mix",
        )
    return out


def maybe_run_placement_qa(ctx: RunContext) -> None:
    if placement_qa_enabled():
        run_placement_qa(ctx)
