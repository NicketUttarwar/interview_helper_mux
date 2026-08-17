"""Load conductor / perspective system prompts and the prompt stock loop."""

from __future__ import annotations

from typing import Any

from interview_mux.config import repo_root
from interview_mux.run_context import RunContext

CONDUCTOR = "docs/prompts/homunculus/conductor/system.txt"
STACK_REL = "mastering/homunculus/prompt_stack.json"
PROMOTIONS_REL = "mastering/homunculus/promotions.json"

ATTACH_ALWAYS = (
    "docs/prompts/homunculus/perspectives/direct_listener_monetization.system.txt",
)

RANKING_AIR_SHAPE = frozenset(
    {
        "full_master_ranking",
        "air_script_compose",
        "air_script_seams",
        "mastering_plan_synthesize",
        "mastering_shape_agenda",
        "mastering_shape_candidates",
    }
)


def load_conductor_system(runtime: str = "openai") -> str:
    if runtime == "mlx":
        mlx = repo_root() / "docs/prompts/homunculus/conductor/mlx.system.txt"
        if mlx.is_file():
            return mlx.read_text(encoding="utf-8")
    path = repo_root() / CONDUCTOR
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        "You are the mastering homunculus. Select tools. Admit every output. "
        "Pack volleys by fact IDs only. Cite docs. Do not invent dialogue. "
        "Tape-only packets. Hard limits: max 3 per function, one analysis per issue."
    )


def load_module(rel: str) -> str:
    path = repo_root() / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def perspective_block_for_stage(stage_key: str) -> str:
    if stage_key not in RANKING_AIR_SHAPE and stage_key != "end_judgment":
        return ""
    bits = [load_module(rel) for rel in ATTACH_ALWAYS]
    return "\n\n".join(b for b in bits if b)


def stack_module(ctx: RunContext, module: str) -> dict[str, Any]:
    stack = {"modules": []}
    if ctx.artifact_exists(STACK_REL):
        raw = ctx.read_json(STACK_REL)
        if isinstance(raw, dict):
            stack = raw
            stack.setdefault("modules", [])
    mods = list(stack.get("modules") or [])
    if module and module not in mods:
        mods.append(module)
    stack["modules"] = mods
    ctx.write_json(STACK_REL, stack)
    return stack


def mint_prompt(ctx: RunContext, mint_id: str, body: str, *, runtime: str = "openai") -> dict[str, Any]:
    rel = f"mastering/homunculus/mints/{mint_id}.json"
    doc = {"mint_id": mint_id, "runtime": runtime, "body": body, "promoted": False}
    ctx.write_json(rel, doc)
    return {"ok": True, "rel": rel, "mint_id": mint_id}


def promote_prompt(ctx: RunContext, mint_id: str, *, corpus_ok: bool) -> dict[str, Any]:
    if not corpus_ok:
        return {"ok": False, "error": "corpus_thresholds_failed", "mint_id": mint_id}
    doc = {"promotions": []}
    if ctx.artifact_exists(PROMOTIONS_REL):
        raw = ctx.read_json(PROMOTIONS_REL)
        if isinstance(raw, dict):
            doc = raw
            doc.setdefault("promotions", [])
    rows = list(doc.get("promotions") or [])
    rows.append({"mint_id": mint_id, "ok": True})
    doc["promotions"] = rows
    ctx.write_json(PROMOTIONS_REL, doc)
    return {"ok": True, "mint_id": mint_id}
