"""Local MLX structured output: schema appendix, min examples, verification."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.config import merged_config
from interview_mux.openai_structured_output import load_schema_file, schema_to_min_example


def local_structured_outputs_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    llm = (cfg or merged_config()).get("local_llm") or {}
    defaults = {
        "enabled": True,
        "strict": True,
        "fail_open_on_verify": True,
    }
    so = llm.get("structured_outputs") or {}
    return {**defaults, **so}


def local_structured_outputs_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_structured_outputs_cfg(cfg).get("enabled", True))


LOCAL_SCHEMA_FILES: dict[str, str] = {
    "local_framer": "local_framer_response.schema.json",
    "itr_clarification": "itr_clarification_options.schema.json",
}


def resolve_local_interaction(stage_key: str, task_kind: str | None = None) -> str:
    if stage_key.endswith("__itr"):
        return "itr_clarification"
    if task_kind and task_kind.startswith("local_"):
        return "local_framer"
    if stage_key == "_local_framer" or task_kind in (
        "local_primary",
        "local_shard",
        "local_collate",
        "local_specialist",
    ):
        return "local_framer"
    return "local_framer"


def load_local_schema(interaction: str) -> dict[str, Any] | None:
    rel = LOCAL_SCHEMA_FILES.get(interaction)
    if not rel:
        return None
    return load_schema_file(rel)


def min_example_for_local(interaction: str) -> dict[str, Any]:
    schema = load_local_schema(interaction)
    example = schema_to_min_example(schema) if schema else {}
    return example if isinstance(example, dict) else {}


def build_local_schema_appendix(interaction: str, *, cfg: dict[str, Any] | None = None) -> str:
    """Append to system prompt for MLX JSON-only generation."""
    if not local_structured_outputs_enabled(cfg):
        return ""
    schema = load_local_schema(interaction)
    if not schema:
        return ""
    example = min_example_for_local(interaction)
    skel = json.dumps(example, indent=2)
    return (
        "\n\n## Required JSON response\n"
        f"Schema: `{interaction}`\n"
        "Reply with one JSON object only. No markdown fences.\n"
        f"```json\n{skel}\n```"
    )


def verify_local_response(interaction: str, parsed: dict[str, Any]) -> list[str]:
    from interview_mux.llm_response_verify import _validate_against_schema

    schema = load_local_schema(interaction)
    if not schema:
        return []
    return _validate_against_schema(parsed, schema, prefix=interaction)
