from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.prompt_validation import validate_stage_artifacts
from interview_mux.run_context import RunContext

PROMPTS_PATH = "sound_design/sfx_prompts.json"
SDP_PATH = "understanding/sound_design_plan.json"

G15_BLOCK_MESSAGE = (
    "G1.5 prompt approval required before SFX generation. "
    "Review and approve sound_design/sfx_prompts.json in the GUI panel."
)


def g15_required(cfg: dict[str, Any] | None = None) -> bool:
    c = cfg if cfg is not None else merged_config()
    return bool(c.get("g1_5_require_prompt_approval", False))


def can_run_sfx_generation(ctx: RunContext) -> tuple[bool, str]:
    if not g15_required():
        return True, ""
    if not ctx.artifact_exists(PROMPTS_PATH):
        return False, G15_BLOCK_MESSAGE
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    review = meta.get("sfx_prompt_review")
    if not isinstance(review, dict) or not review.get("approved"):
        return False, G15_BLOCK_MESSAGE
    return True, ""


def validate_prompts_payload(data: dict[str, Any]) -> list[str]:
    return validate_stage_artifacts("sfx_prompt_craft", data)


def _collect_sdp_asset_ids(sdp: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for asset in sdp.get("assets") or []:
        if isinstance(asset, dict) and asset.get("asset_id"):
            ids.add(str(asset["asset_id"]))
    for flow_key in ("flow1", "flow2"):
        plan = (sdp.get("flow_plans") or {}).get(flow_key) or {}
        for cue in plan.get("cues") or []:
            if isinstance(cue, dict) and cue.get("asset_id"):
                ids.add(str(cue["asset_id"]))
    return ids


def sdp_asset_id_warnings(ctx: RunContext, prompts: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if not ctx.artifact_exists(SDP_PATH):
        warnings.append("sound_design_plan.json missing — cannot verify asset_id alignment.")
        return warnings
    sdp = ctx.read_json(SDP_PATH)
    expected = _collect_sdp_asset_ids(sdp if isinstance(sdp, dict) else {})
    prompt_ids = {str(row.get("asset_id")) for row in prompts if isinstance(row, dict) and row.get("asset_id")}
    if not prompt_ids:
        warnings.append("No asset_id values in crafted prompts.")
        return warnings
    if expected:
        missing_in_prompts = sorted(expected - prompt_ids)
        extra_in_prompts = sorted(prompt_ids - expected)
        if missing_in_prompts:
            warnings.append(f"SDP asset_ids missing from prompts: {', '.join(missing_in_prompts[:8])}")
        if extra_in_prompts:
            warnings.append(f"Prompt asset_ids not in SDP: {', '.join(extra_in_prompts[:8])}")
    return warnings


def prompt_completeness_warnings(ctx: RunContext, prompts: list[dict[str, Any]]) -> list[str]:
    warnings = sdp_asset_id_warnings(ctx, prompts)
    if not prompts:
        warnings.append("No prompt rows found.")
        return warnings
    for row in prompts:
        if not isinstance(row, dict):
            warnings.append("Prompt row is not an object.")
            continue
        aid = str(row.get("asset_id") or "")
        if not aid:
            warnings.append("Prompt row missing asset_id.")
        if not str(row.get("sfx_prompt") or "").strip():
            warnings.append(f"{aid or '(unknown asset)'} missing sfx_prompt.")
        if not str(row.get("negative_prompt") or "").strip():
            warnings.append(f"{aid or '(unknown asset)'} missing negative_prompt.")
        if row.get("duration_seconds") is None:
            warnings.append(f"{aid or '(unknown asset)'} missing duration_seconds.")
    # Keep warning payload small for the panel.
    deduped: list[str] = []
    seen: set[str] = set()
    for row in warnings:
        key = row.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped[:20]


def require_sfx_generation(ctx: RunContext) -> None:
    ok, message = can_run_sfx_generation(ctx)
    if not ok:
        raise RuntimeError(message)
