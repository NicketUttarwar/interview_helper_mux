from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from interview_mux.mmaudio_asset_qa import run_mmaudio_asset_qa
from interview_mux.mmaudio_runner import (
    MMAudioUnavailable,
    clamp_duration_seconds,
    generate_text_to_audio,
    mmaudio_cfg,
)
from interview_mux.run_context import RunContext
from interview_mux.sfx_prompt_review import require_sfx_generation
from interview_mux.journey_log import log_journey

logger = logging.getLogger(__name__)


def _log_sfx_event(
    ctx: RunContext,
    message: str,
    *,
    stage: str,
    level: str = "info",
    **detail: Any,
) -> None:
    log_journey(ctx, "sfx", message, level=level, stage=stage, category="sfx", **detail)

_ROLE_INFLUENCE: dict[str, float] = {
    "ambient_bed": 0.30,
    "chapter_stinger": 0.38,
    "transition_stinger": 0.40,
    "cold_open": 0.42,
    "vo_bridge": 0.32,
    "accent_foley": 0.35,
}


def run_sfx_generation(ctx: RunContext, *, profile: str) -> None:
    """Generate sound-design WAVs via local MMAudio text-to-audio."""
    if profile == "podcast":
        brief_path = "flow_1_master/podcast_sfx_brief.json"
        out_rel = "flow_1_master/sfx"
        stage = "mmaudio_sfx_flow1"
    else:
        brief_path = "flow_2_highlights/sfx_brief.json"
        out_rel = "flow_2_highlights/sfx"
        stage = "mmaudio_sfx_flow2"
    out_dir = ctx.path(out_rel)
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    from interview_mux.llm_flow_hardening import require_spend_artifacts_complete

    require_spend_artifacts_complete(ctx, stage)
    require_sfx_generation(ctx)
    cues = _load_fallback_cues(ctx=ctx, brief_path=brief_path, profile=profile)

    crafted = _load_crafted_prompts(ctx)
    generation_items = _collect_generation_items(ctx=ctx, profile=profile, fallback_cues=cues)
    regen_ids = _read_regen_asset_ids(ctx)
    if regen_ids:
        generation_items = [item for item in generation_items if item["asset_id"] in regen_ids]

    generation_meta: dict[str, Any] = {}
    generation_failures: list[dict[str, Any]] = []
    for item in generation_items:
        asset_id = item["asset_id"]
        out_file = assets_dir / f"{asset_id}.wav"
        prompt_row = crafted.get(asset_id) if crafted else None
        params = _resolve_generation_params(item, prompt_row)
        sonic_hash = _sonic_context_hash(ctx)
        plan_hash = _hash_generation_plan(item, prompt_row, params, sonic_context_hash=sonic_hash)
        if _should_skip_generation(ctx, asset_id, plan_hash, out_file, regen_ids):
            ctx.log(
                f"MMAudio skipped {asset_id}.wav (plan hash unchanged)",
                level="info",
                stage=stage,
            )
            _log_sfx_event(
                ctx,
                f"MMAudio skipped {asset_id} (plan hash unchanged)",
                stage=stage,
                asset_id=asset_id,
                event="skip",
            )
            generation_meta[asset_id] = {
                "generation_status": "pass",
                "plan_hash": plan_hash,
                "sonic_context_hash": sonic_hash,
                "skipped_generation": True,
            }
            continue
        try:
            meta = _generate_with_retry(
                ctx=ctx,
                stage=stage,
                asset_id=asset_id,
                params=params,
                out_file=out_file,
            )
            _trim_wav_to_duration(out_file, params["duration_seconds"])
            meta["generation_status"] = "pass"
            meta["plan_hash"] = plan_hash
            meta["sonic_context_hash"] = sonic_hash
            meta["prompt_text"] = params["prompt"]
            generation_meta[asset_id] = meta
            ctx.log(
                "info",
                f"MMAudio generated {asset_id}.wav",
                stage=stage,
                detail={
                    "asset_id": asset_id,
                    "duration_seconds": params["duration_seconds"],
                    "clamped_duration_seconds": meta.get("duration_seconds"),
                    "prompt_influence": params.get("prompt_influence"),
                    "cfg_strength": meta.get("cfg_strength"),
                    "num_steps": meta.get("num_steps"),
                    "seed": meta.get("seed"),
                    "variant": meta.get("variant"),
                    "provider": "mmaudio",
                    "model_id": meta.get("model_id"),
                    "artifact": f"sound_design/assets/{asset_id}.wav",
                },
            )
            _log_sfx_event(
                ctx,
                f"MMAudio generated {asset_id}",
                stage=stage,
                asset_id=asset_id,
                event="generate",
            )
        except MMAudioUnavailable as exc:
            logger.warning("MMAudio failed for %s: %s", asset_id, exc)
            ctx.log(
                "warning",
                f"MMAudio SFX failed for {asset_id}; wrote silence placeholder",
                stage=stage,
                detail={"provider": "mmaudio", "asset_id": asset_id, "error": str(exc)[:200]},
            )
            _write_silent_wav(out_file, duration_ms=int(params["duration_seconds"] * 1000))
            generation_meta[asset_id] = {
                "generation_status": "placeholder",
                "plan_hash": plan_hash,
                "sonic_context_hash": sonic_hash,
                "error": str(exc)[:200],
                "placeholder": True,
            }
            generation_failures.append({"asset_id": asset_id, "error": str(exc)[:200], "type": "mmaudio_unavailable"})
        except Exception as exc:
            logger.warning("MMAudio generation failed for %s: %s", asset_id, exc)
            ctx.log(
                f"MMAudio SFX failed for {asset_id}; wrote silence placeholder ({exc})",
                level="warning",
                stage=stage,
                detail={"asset_id": asset_id, "error": str(exc)[:200]},
            )
            _write_silent_wav(out_file, duration_ms=int(params["duration_seconds"] * 1000))
            generation_meta[asset_id] = {
                "generation_status": "placeholder",
                "plan_hash": plan_hash,
                "sonic_context_hash": sonic_hash,
                "error": str(exc)[:200],
                "placeholder": True,
            }
            generation_failures.append({"asset_id": asset_id, "error": str(exc)[:200], "type": "generation_error"})

    if generation_meta:
        _persist_generation_meta(ctx, generation_meta, generation_failures)
    if regen_ids:
        _clear_regen_asset_ids(ctx)

    if generation_items:
        _mirror_assets_to_flow_dir(
            ctx=ctx,
            asset_ids=[item["asset_id"] for item in generation_items],
            target_dir=out_dir,
        )

    run_mmaudio_asset_qa(ctx)
    _log_sfx_event(ctx, "MMAudio QA completed", stage=stage, event="qa")
    from interview_mux.gates import sync_post_listen_gate_state
    from interview_mux.operator_snapshots import persist_operator_mmaudio_snapshots

    sync_post_listen_gate_state(ctx)
    persist_operator_mmaudio_snapshots(ctx, source="mmaudio_sfx_flow")
    maybe_auto_refine(ctx, stage)
    persist_operator_mmaudio_snapshots(ctx, source="mmaudio_sfx_flow_post_refine")

    manifest = {
        "profile": profile,
        "files": [p.name for p in sorted(assets_dir.glob("*.wav"))],
        "asset_paths": [f"sound_design/assets/{p.name}" for p in sorted(assets_dir.glob("*.wav"))],
        "provider": "mmaudio",
    }
    ctx.write_json(f"{out_rel}/manifest.json", manifest)
    from interview_mux.placement_qa import maybe_run_placement_qa

    maybe_run_placement_qa(ctx)
    ctx.mark_done(stage)


def grant_auto_refine_override(ctx: RunContext, asset_ids: list[str]) -> None:
    """Record operator/auto consent to refine trauma-adjacent assets."""
    ids = [str(aid) for aid in asset_ids if str(aid).strip()]
    if not ids:
        return

    def patch(meta: dict) -> None:
        overrides = meta.get("sfx_auto_refine_override") or {}
        if not isinstance(overrides, dict):
            overrides = {}
        for aid in ids:
            overrides[aid] = True
        meta["sfx_auto_refine_override"] = overrides

    ctx.mutate_run_meta(patch)


def maybe_auto_refine(ctx: RunContext, stage: str) -> list[str]:
    cfg = mmaudio_cfg()
    if not bool(cfg.get("auto_refine_enabled", False)):
        return []
    from interview_mux.mmaudio_asset_qa import load_mmaudio_qa
    from interview_mux.sonic_context import load_sonic_context
    from interview_mux.stages.sound_design_stages import run_sfx_prompt_refine

    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    atlas = str(scenario.get("atlas_bucket") or "")
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    overrides = meta.get("sfx_auto_refine_override") or {}
    if not isinstance(overrides, dict):
        overrides = {}

    qa = load_mmaudio_qa(ctx)
    failed: set[str] = set()
    if bool(cfg.get("auto_refine_on_qa_fail", True)):
        for row in qa.get("assets") or []:
            if isinstance(row, dict) and row.get("verdict") == "fail":
                aid = str(row.get("asset_id") or "")
                if aid:
                    failed.add(aid)
    if bool(cfg.get("auto_refine_on_listen_fail", True)):
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        listen = meta.get("sfx_listen_results") or []
        latest: dict[str, str] = {}
        for entry in listen:
            if isinstance(entry, dict) and entry.get("asset_id"):
                latest[str(entry["asset_id"])] = str(entry.get("result") or "")
        for aid, result in latest.items():
            if result == "fail":
                failed.add(aid)
    if not failed:
        return []

    max_attempts = int(cfg.get("auto_refine_max_attempts_per_asset", 2))
    eligible = [aid for aid in failed if _refine_attempts(ctx, aid) < max_attempts]
    if atlas == "trauma_adjacent":
        auto_trauma = bool(cfg.get("auto_refine_on_trauma", True))
        if auto_trauma:
            grant_auto_refine_override(ctx, eligible)
        else:
            eligible = [aid for aid in eligible if bool(overrides.get(aid))]
            if not eligible and failed:
                ctx.log(
                    "auto_refine: skipped for trauma_adjacent — operator override required per asset",
                    level="info",
                    stage=stage,
                )
                return []
    if not eligible:
        return []

    ctx.log(
        f"auto_refine: attempting refine for {len(eligible)} asset(s)",
        level="info",
        stage=stage,
        detail={"asset_ids": eligible},
    )
    _log_sfx_event(
        ctx,
        f"auto_refine for {len(eligible)} asset(s)",
        stage=stage,
        event="refine",
        asset_ids=eligible,
    )
    run_sfx_prompt_refine(ctx, asset_ids=eligible)
    _regenerate_assets_after_refine(ctx, stage, eligible, crafted=_load_crafted_prompts(ctx), generation_items=_collect_generation_items_for_regen(ctx, stage))
    return eligible


def _collect_generation_items_for_regen(ctx: RunContext, stage: str) -> list[dict]:
    profile = "podcast" if stage.endswith("flow1") else "montage"
    brief_path = (
        "flow_1_master/podcast_sfx_brief.json"
        if profile == "podcast"
        else "flow_2_highlights/sfx_brief.json"
    )
    cues = _load_fallback_cues(ctx=ctx, brief_path=brief_path, profile=profile)
    return _collect_generation_items(ctx=ctx, profile=profile, fallback_cues=cues)


def _regenerate_assets_after_refine(
    ctx: RunContext,
    stage: str,
    asset_ids: list[str],
    *,
    crafted: dict[str, dict],
    generation_items: list[dict],
) -> None:
    assets_dir = ctx.path("sound_design", "assets")
    generation_meta: dict[str, Any] = {}
    items_by_id = {str(i["asset_id"]): i for i in generation_items}
    for aid in asset_ids:
        item = items_by_id.get(aid)
        if not item:
            continue
        out_file = assets_dir / f"{aid}.wav"
        prompt_row = crafted.get(aid)
        params = _resolve_generation_params(item, prompt_row)
        try:
            meta = generate_text_to_audio(
                prompt=params["prompt"],
                negative_prompt=params["negative_prompt"],
                duration_seconds=params["duration_seconds"],
                output_wav=out_file,
                prompt_influence=params.get("prompt_influence"),
                cfg_strength=params.get("cfg_strength"),
                num_steps=params.get("num_steps"),
                seed=params.get("seed"),
                variant=params.get("variant"),
                role=params.get("role"),
                asset_id=aid,
                run_id=ctx.run_id,
                ctx=ctx,
            )
            _trim_wav_to_duration(out_file, params["duration_seconds"])
            generation_meta[aid] = meta
        except MMAudioUnavailable as exc:
            logger.warning("MMAudio regen failed for %s: %s", aid, exc)
            _write_silent_wav(out_file, duration_ms=int(params["duration_seconds"] * 1000))
    if generation_meta:
        _persist_generation_meta(ctx, generation_meta, [])
    run_mmaudio_asset_qa(ctx)
    _log_sfx_event(ctx, "MMAudio QA completed after refine regen", stage=stage, event="qa")
    from interview_mux.operator_snapshots import persist_operator_mmaudio_snapshots

    persist_operator_mmaudio_snapshots(ctx, source="mmaudio_sfx_refine_regen")


def _refine_attempts(ctx: RunContext, asset_id: str) -> int:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    attempts = meta.get("sfx_refine_attempts") or {}
    if isinstance(attempts, dict):
        return int(attempts.get(asset_id, 0))
    return 0


def _read_regen_asset_ids(ctx: RunContext) -> set[str]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    ids = meta.get("sfx_regen_asset_ids") or []
    if not isinstance(ids, list):
        return set()
    return {str(x) for x in ids if x}


def _set_regen_asset_ids(ctx: RunContext, asset_ids: list[str]) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}

    def patch(m: dict[str, Any]) -> None:
        m["sfx_regen_asset_ids"] = sorted(set(asset_ids))

    if meta:
        ctx.mutate_run_meta(patch)
    else:
        patch(meta)
        ctx.write_json("run_meta.json", meta)


def _clear_regen_asset_ids(ctx: RunContext) -> None:
    def patch(m: dict[str, Any]) -> None:
        m.pop("sfx_regen_asset_ids", None)

    ctx.mutate_run_meta(patch)


def _persist_generation_meta(
    ctx: RunContext,
    generation_meta: dict[str, Any],
    generation_failures: list[dict[str, Any]],
) -> None:
    def patch(m: dict[str, Any]) -> None:
        existing = m.get("sfx_generation_meta") or {}
        if not isinstance(existing, dict):
            existing = {}
        existing.update(generation_meta)
        m["sfx_generation_meta"] = existing
        hashes = m.get("sfx_generation_plan_hashes") or {}
        if not isinstance(hashes, dict):
            hashes = {}
        for aid, row in generation_meta.items():
            if isinstance(row, dict) and row.get("plan_hash"):
                hashes[aid] = str(row.get("plan_hash"))
        m["sfx_generation_plan_hashes"] = hashes
        if generation_failures:
            prior = m.get("sfx_generation_failures") or []
            if not isinstance(prior, list):
                prior = []
            prior.extend(generation_failures)
            m["sfx_generation_failures"] = prior[-200:]

    ctx.mutate_run_meta(patch)


def _sonic_context_hash(ctx: RunContext) -> str:
    from interview_mux.sonic_context import load_sonic_context

    doc = load_sonic_context(ctx)
    if isinstance(doc, dict) and doc.get("sonic_context_hash"):
        return str(doc["sonic_context_hash"])
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    stored = meta.get("sonic_context_hash")
    return str(stored) if stored else ""


def _generate_with_retry(
    *,
    ctx: RunContext,
    stage: str,
    asset_id: str,
    params: dict[str, Any],
    out_file: Path,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return generate_text_to_audio(
                prompt=params["prompt"],
                negative_prompt=params["negative_prompt"],
                duration_seconds=params["duration_seconds"],
                output_wav=out_file,
                prompt_influence=params.get("prompt_influence"),
                cfg_strength=params.get("cfg_strength"),
                num_steps=params.get("num_steps"),
                seed=params.get("seed"),
                variant=params.get("variant"),
                role=params.get("role"),
                asset_id=asset_id,
                run_id=ctx.run_id,
                ctx=ctx,
            )
        except MMAudioUnavailable as exc:
            last_exc = exc
            if attempt == 0:
                ctx.log(
                    "mmaudio_retry",
                    level="warning",
                    stage=stage,
                    detail={"asset_id": asset_id, "attempt": attempt + 1, "error": str(exc)[:200]},
                )
                continue
            raise
    if last_exc:
        raise last_exc
    raise MMAudioUnavailable("MMAudio generation failed after retry")


def _hash_generation_plan(
    item: dict[str, Any],
    prompt_row: dict[str, Any] | None,
    params: dict[str, Any],
    *,
    sonic_context_hash: str = "",
) -> str:
    payload = {
        "sonic_context_hash": sonic_context_hash,
        "item": item,
        "prompt_row": prompt_row or {},
        "params": {
            "duration_seconds": params.get("duration_seconds"),
            "prompt": params.get("prompt"),
            "negative_prompt": params.get("negative_prompt"),
            "prompt_influence": params.get("prompt_influence"),
            "cfg_strength": params.get("cfg_strength"),
            "num_steps": params.get("num_steps"),
            "seed": params.get("seed"),
            "variant": params.get("variant"),
            "role": params.get("role"),
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _should_skip_generation(
    ctx: RunContext,
    asset_id: str,
    plan_hash: str,
    out_file: Path,
    regen_ids: set[str],
) -> bool:
    if not bool((mmaudio_cfg()).get("plan_hash_skip_enabled", False)):
        return False
    if asset_id in regen_ids:
        return False
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    hashes = meta.get("sfx_generation_plan_hashes") or {}
    if not isinstance(hashes, dict):
        return False
    return out_file.is_file() and str(hashes.get(asset_id) or "") == plan_hash


def _load_crafted_prompts(ctx: RunContext) -> dict[str, dict]:
    path = ctx.path("sound_design/sfx_prompts.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = data.get("prompts") or data.get("artifacts", {}).get("prompts") or []
    return {row["asset_id"]: row for row in rows if row.get("asset_id")}


def _resolve_generation_params(
    cue: dict,
    prompt_row: dict | None,
) -> dict[str, Any]:
    duration_seconds = _plan_duration_seconds(cue)
    role = cue.get("role") or "chapter_stinger"
    influence = _ROLE_INFLUENCE.get(role, 0.35)
    prompt = cue.get("description") or cue.get("mood") or "short podcast stinger"
    negative_prompt = "no vocals, no speech, no lyrics, no humming, no drum loop"
    cfg_strength = None
    num_steps = None
    seed = None
    variant = None

    if prompt_row:
        prompt = prompt_row.get("sfx_prompt") or prompt
        negative_prompt = str(prompt_row.get("negative_prompt") or negative_prompt)
        if "prompt_influence" in prompt_row:
            influence = float(prompt_row["prompt_influence"])
        if prompt_row.get("cfg_strength") is not None:
            cfg_strength = float(prompt_row["cfg_strength"])
        if prompt_row.get("num_steps") is not None:
            num_steps = int(prompt_row["num_steps"])
        if prompt_row.get("seed") is not None:
            seed = int(prompt_row["seed"])
        variant = prompt_row.get("mmaudio_variant")

    return {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration_seconds": duration_seconds,
        "prompt_influence": influence,
        "cfg_strength": cfg_strength,
        "num_steps": num_steps,
        "seed": seed,
        "variant": variant,
        "role": role,
    }


def _plan_duration_seconds(cue: dict) -> float:
    if cue.get("duration_seconds") is not None:
        return float(cue["duration_seconds"])
    duration_ms = cue.get("duration_ms")
    if duration_ms is not None:
        return float(duration_ms) / 1000.0
    return 2.0


def _collect_generation_items(
    *,
    ctx: RunContext,
    profile: str,
    fallback_cues: list[dict],
) -> list[dict]:
    plan = _load_sound_design_plan(ctx)
    if not plan:
        return _dedupe_fallback_cues(fallback_cues)

    flow_key = "flow1" if profile == "podcast" else "flow2"
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow = flow_plans.get(flow_key) if isinstance(flow_plans.get(flow_key), dict) else {}
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    assets_by_id = {
        str(asset.get("asset_id")): asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id")
    }

    ordered_asset_ids: list[str] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        aid = str(cue.get("asset_id") or "")
        if not aid or aid not in assets_by_id or aid in ordered_asset_ids:
            continue
        ordered_asset_ids.append(aid)

    if not ordered_asset_ids:
        return _dedupe_fallback_cues(fallback_cues)

    return [assets_by_id[aid] for aid in ordered_asset_ids]


def _load_sound_design_plan(ctx: RunContext) -> dict:
    path = ctx.path("understanding/sound_design_plan.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_fallback_cues(*, ctx: RunContext, brief_path: str, profile: str) -> list[dict]:
    """Fallback cues for runs without sound design plan asset definitions."""
    if ctx.path(brief_path).is_file():
        brief = ctx.read_json(brief_path)
        return _collect_cues(brief, profile)
    return [{"description": "short neutral stinger", "duration_ms": 1500, "role": "chapter_stinger"}]


def _dedupe_fallback_cues(cues: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for i, cue in enumerate(cues):
        asset_id = str(cue.get("asset_id") or f"sfx_{i+1:03d}")
        if asset_id in seen:
            continue
        seen.add(asset_id)
        out.append({**cue, "asset_id": asset_id})
    return out


def _mirror_assets_to_flow_dir(*, ctx: RunContext, asset_ids: list[str], target_dir: Path) -> None:
    """Copy canonical sound_design/assets WAVs into flow-specific sfx/ for v1 paths."""
    source_dir = ctx.path("sound_design", "assets")
    target_dir.mkdir(parents=True, exist_ok=True)
    for asset_id in asset_ids:
        src = source_dir / f"{asset_id}.wav"
        if not src.is_file():
            continue
        dst = target_dir / f"{asset_id}.wav"
        dst.write_bytes(src.read_bytes())


def _collect_cues(brief: dict, profile: str) -> list[dict]:
    cues: list[dict] = []
    if profile == "podcast":
        for item in brief.get("chapter_stingers") or []:
            cues.append({**item, "role": "chapter_stinger", "description": item.get("description", item.get("mood", "soft stinger"))})
        for item in brief.get("bridges") or []:
            cues.append({**item, "role": "vo_bridge", "description": item.get("description", "light bridge")})
        for item in brief.get("beds") or []:
            cues.append({**item, "role": "ambient_bed", "description": item.get("description", item.get("mood", "quiet bed"))})
    else:
        for item in brief.get("transitions") or []:
            cues.append({**item, "role": "transition_stinger"})
        if brief.get("cold_open"):
            cues.insert(0, {**brief["cold_open"], "role": "cold_open"})
        if brief.get("outro"):
            cues.append({**brief["outro"], "role": "cold_open"})
    if not cues:
        cues.append({"description": "short neutral stinger", "duration_ms": 1500, "role": "chapter_stinger"})
    return cues


def _trim_wav_to_duration(path: Path, duration_seconds: float) -> None:
    """Trim generated output when plan duration is below MMAudio minimum."""
    from interview_mux.operator_subprocess import run_command

    target_sec = float(duration_seconds)
    api_min_sec = clamp_duration_seconds(target_sec)
    if target_sec >= api_min_sec - 0.05:
        return
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-t",
            str(target_sec),
            "-ar",
            "48000",
            "-ac",
            "1",
            str(path.with_suffix(".trim.wav")),
        ],
        stage="mmaudio_sfx_flow1",
        label=f"ffmpeg trim {path.name}",
        capture_output=True,
    )
    trimmed = path.with_suffix(".trim.wav")
    trimmed.replace(path)


def _write_silent_wav(path: Path, duration_ms: int = 1500) -> None:
    from interview_mux.operator_subprocess import run_command

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=48000:cl=mono",
            "-t",
            str(duration_ms / 1000.0),
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        stage="mmaudio_sfx_flow1",
        label=f"ffmpeg silent wav {path.name}",
        capture_output=True,
    )
