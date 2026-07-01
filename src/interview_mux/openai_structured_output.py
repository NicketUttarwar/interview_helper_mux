"""OpenAI strict json_schema composition, response_format resolution, and min examples."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from interview_mux.openai_schema_lint import assert_openai_strict_schema
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

SPECIALIST_SCHEMA_FILES: dict[str, str] = {
    "comprehension_risk_blind": "specialists/comprehension_risk_blind.schema.json",
    "theme_coverage_pass": "specialists/theme_coverage_pass.schema.json",
    "emphasis_coverage_pass": "specialists/emphasis_coverage_pass.schema.json",
}

SPECIALIST_STAGE_SUFFIXES: dict[str, str] = {
    "comprehension_risk_blind": "comprehension_risk_blind",
    "theme_coverage_pass": "theme_coverage_pass",
    "emphasis_coverage_pass": "emphasis_coverage_pass",
}


def schemas_root() -> Path:
    return repo_root() / "docs" / "cross-cutting" / "json-schemas"


def composed_cache_dir() -> Path:
    return schemas_root() / "composed"


@lru_cache(maxsize=64)
def load_schema_file(rel_path: str) -> dict[str, Any] | None:
    path = schemas_root() / rel_path
    if not path.is_file():
        alt = schemas_root() / "artifacts" / Path(rel_path).name
        if alt.is_file():
            path = alt
        else:
            return None
    return json.loads(path.read_text(encoding="utf-8"))


def structured_outputs_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "enabled": True,
        "strict": True,
        "fail_on_verify_error": True,
        "allow_json_object_fallback": False,
        "api_schema_tier": "full",
        "log_verification_to_gui": True,
    }
    so = analysis.get("structured_outputs") or {}
    return {**defaults, **so}


def structured_outputs_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(structured_outputs_cfg(cfg).get("enabled", True))


def _make_nullable(prop: dict[str, Any]) -> dict[str, Any]:
    prop = copy.deepcopy(prop)
    t = prop.get("type")
    if t is None:
        return {**prop, "type": ["object", "null"]}
    if isinstance(t, list):
        if "null" not in t:
            prop["type"] = [*t, "null"]
        return prop
    prop["type"] = [t, "null"]
    return prop


def strictify_schema(
    schema: dict[str, Any],
    *,
    source_required: set[str] | None = None,
    path: str = "",
) -> dict[str, Any]:
    """Make a JSON Schema OpenAI strict-mode compatible."""
    schema = copy.deepcopy(schema)
    schema.pop("$schema", None)
    schema.pop("title", None)

    if "$ref" in schema:
        return schema

    if "anyOf" in schema or "oneOf" in schema:
        key = "anyOf" if "anyOf" in schema else "oneOf"
        schema[key] = [
            strictify_schema(s, path=f"{path}.{key}[{idx}]") for idx, s in enumerate(schema[key])
        ]
        return schema

    t = schema.get("type")
    types = [t] if isinstance(t, str) else list(t or [])

    if "object" in types or (t is None and "properties" in schema):
        props = schema.get("properties") or {}
        req = set(schema.get("required") or [])
        if source_required is not None:
            req = source_required
        strict_props: dict[str, Any] = {}
        strict_required: list[str] = []
        for key, prop in props.items():
            if key not in req:
                prop = _make_nullable(prop)
            strict_props[key] = strictify_schema(
                prop,
                source_required=None,
                path=f"{path}.properties.{key}" if path else f"properties.{key}",
            )
            strict_required.append(key)
        schema["properties"] = strict_props
        schema["required"] = strict_required
        schema["type"] = "object"
        schema["additionalProperties"] = False
        return schema

    if "array" in types:
        if "items" not in schema:
            loc = path or "schema"
            raise ValueError(f"{loc}: array schema missing items")
        schema["items"] = strictify_schema(
            schema["items"],
            path=f"{path}.items" if path else "items",
        )
        return schema

    return schema


def _need_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["rerun_stage", "operator", "transcript_excerpt", "human_fact"],
            },
            "stage": {"type": ["string", "null"]},
            "reason": {"type": "string"},
            "blocking": {"type": ["boolean", "null"]},
            "params": {"type": ["object", "null"]},
        },
        "required": ["type", "reason", "stage", "blocking", "params"],
        "additionalProperties": False,
    }


def compose_envelope_schema(stage_key: str, *, strict: bool = True) -> dict[str, Any]:
    """Envelope root with stage artifact nested under artifacts."""
    artifact_file = STAGE_ARTIFACT_SCHEMAS.get(stage_key)
    if not artifact_file:
        raise KeyError(f"No artifact schema for stage_key={stage_key!r}")
    artifact = load_schema_file(f"artifacts/{artifact_file}")
    if not artifact:
        artifact = load_schema_file(artifact_file)
    if not artifact:
        raise FileNotFoundError(f"Missing artifact schema: {artifact_file}")

    artifact_body = strictify_schema(artifact) if strict else copy.deepcopy(artifact)
    envelope: dict[str, Any] = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["complete", "partial", "needs_input", "blocked"],
            },
            "artifacts": artifact_body,
            "memory_updates": {"type": "object"},
            "needs": {"type": "array", "items": _need_item_schema()},
            "follow_up_investigations": {"type": "array", "items": {"type": "object"}},
            "confidence": {"type": ["number", "null"]},
            "reasoning_summary": {"type": "string"},
        },
        "required": [
            "status",
            "artifacts",
            "memory_updates",
            "needs",
            "follow_up_investigations",
            "confidence",
            "reasoning_summary",
        ],
        "additionalProperties": False,
    }
    if strict:
        envelope = strictify_schema(envelope)
        assert_openai_strict_schema(envelope)
    return envelope


def compose_specialist_envelope_schema(specialist_key: str, *, strict: bool = True) -> dict[str, Any]:
    rel = SPECIALIST_SCHEMA_FILES.get(specialist_key)
    if not rel:
        raise KeyError(f"Unknown specialist_key={specialist_key!r}")
    artifact = load_schema_file(rel)
    if not artifact:
        raise FileNotFoundError(rel)
    return compose_envelope_schema_from_artifact(artifact, strict=strict)


def compose_envelope_schema_from_artifact(artifact: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
    artifact_body = strictify_schema(artifact) if strict else copy.deepcopy(artifact)
    envelope: dict[str, Any] = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["complete", "partial", "needs_input", "blocked"],
            },
            "artifacts": artifact_body,
            "memory_updates": {"type": "object"},
            "needs": {"type": "array", "items": _need_item_schema()},
            "follow_up_investigations": {"type": "array", "items": {"type": "object"}},
            "confidence": {"type": ["number", "null"]},
            "reasoning_summary": {"type": "string"},
        },
        "required": [
            "status",
            "artifacts",
            "memory_updates",
            "needs",
            "follow_up_investigations",
            "confidence",
            "reasoning_summary",
        ],
        "additionalProperties": False,
    }
    if strict:
        envelope = strictify_schema(envelope)
        assert_openai_strict_schema(envelope)
    return envelope


def compose_arbiter_schema(*, strict: bool = True) -> dict[str, Any]:
    schema = load_schema_file("arbiter_verdict.schema.json")
    if not schema:
        raise FileNotFoundError("arbiter_verdict.schema.json")
    schema = strictify_schema(schema) if strict else copy.deepcopy(schema)
    if strict:
        assert_openai_strict_schema(schema)
    return schema


def _schema_name(stage_key: str, task_kind: str) -> str:
    safe = stage_key.replace("__", "_").replace("-", "_")[:48]
    return f"{safe}_{task_kind}_response"


def resolve_parent_stage_key(stage_key: str) -> str:
    if "__" in stage_key:
        return stage_key.split("__", 1)[0]
    if stage_key == "_arbiter":
        return "_arbiter"
    return stage_key


def resolve_specialist_key(stage_key: str) -> str | None:
    if "__" not in stage_key:
        return None
    suffix = stage_key.split("__", 1)[1]
    if suffix in SPECIALIST_SCHEMA_FILES:
        return suffix
    return None


def resolve_response_format(
    stage_key: str,
    task_kind: str,
    *,
    cfg: dict[str, Any] | None = None,
    explicit: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return OpenAI response_format dict (strict json_schema or json_object fallback)."""
    if explicit is not None:
        return explicit
    if task_kind not in ("primary", "shard", "collate", "specialist", "arbiter"):
        return None

    so_cfg = structured_outputs_cfg(cfg)
    if not so_cfg.get("enabled", True):
        return {"type": "json_object"}

    strict = bool(so_cfg.get("strict", True))
    try:
        if task_kind == "arbiter":
            schema = compose_arbiter_schema(strict=strict)
            name = "arbiter_verdict"
        elif task_kind == "specialist":
            sk = resolve_specialist_key(stage_key)
            if sk:
                schema = compose_specialist_envelope_schema(sk, strict=strict)
                name = _schema_name(stage_key, "specialist")
            else:
                parent = resolve_parent_stage_key(stage_key)
                schema = compose_envelope_schema(parent, strict=strict)
                name = _schema_name(parent, "specialist")
        else:
            parent = resolve_parent_stage_key(stage_key)
            if parent not in STAGE_ARTIFACT_SCHEMAS:
                if so_cfg.get("allow_json_object_fallback"):
                    return {"type": "json_object"}
                return None
            schema = compose_envelope_schema(parent, strict=strict)
            name = _schema_name(parent, task_kind)

        if strict:
            assert_openai_strict_schema(schema)

        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": strict,
                "schema": schema,
            },
        }
    except (KeyError, FileNotFoundError, OSError, ValueError):
        if so_cfg.get("allow_json_object_fallback"):
            return {"type": "json_object"}
        raise


def schema_to_min_example(schema: dict[str, Any] | None) -> Any:
    """One array item, enums, null for optional — minimum sufficient prompt example."""
    if not schema:
        return {}
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            if branch.get("type") != "null":
                return schema_to_min_example(branch)
        return None
    if "oneOf" in schema:
        return schema_to_min_example(schema["oneOf"][0])

    t = schema.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        if not non_null:
            return None
        return schema_to_min_example({**schema, "type": non_null[0]})

    if t == "object":
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        example_keys = list(required)
        for key, prop in props.items():
            if key in required:
                continue
            raw_type = prop.get("type")
            if not raw_type:
                continue
            if isinstance(raw_type, list):
                ptypes = [x for x in raw_type if x != "null"]
            else:
                ptypes = [raw_type]
            if "array" in ptypes and prop.get("items"):
                example_keys.append(key)
            elif "object" in ptypes and prop.get("properties"):
                example_keys.append(key)
        out: dict[str, Any] = {}
        for key in example_keys:
            if key in props:
                out[key] = schema_to_min_example(props[key])
        return out

    if t == "array":
        items = schema.get("items") or {}
        return [schema_to_min_example(items)]

    if t == "string":
        return schema.get("enum", ["string"])[0] if "enum" in schema else "string"
    if t == "integer":
        return int(schema.get("minimum", 0) or 0)
    if t == "number":
        return float(schema.get("minimum", 0) or 0)
    if t == "boolean":
        return False
    return None


def min_example_for_stage(stage_key: str) -> dict[str, Any]:
    """Envelope min example with artifact skeleton from golden schema."""
    parent = resolve_parent_stage_key(stage_key)
    artifact_file = STAGE_ARTIFACT_SCHEMAS.get(parent)
    if artifact_file:
        artifact_schema = load_schema_file(f"artifacts/{artifact_file}") or load_schema_file(artifact_file)
        art = schema_to_min_example(artifact_schema) if artifact_schema else {}
    else:
        sk = resolve_specialist_key(stage_key)
        if sk:
            rel = SPECIALIST_SCHEMA_FILES[sk]
            artifact_schema = load_schema_file(rel)
            art = schema_to_min_example(artifact_schema) if artifact_schema else {}
        else:
            art = {}
    return {
        "status": "complete",
        "artifacts": art if isinstance(art, dict) else {},
        "memory_updates": {},
        "needs": [],
        "follow_up_investigations": [],
        "confidence": 0.0,
        "reasoning_summary": "2-5 sentences for the next stage",
    }


def min_example_for_arbiter() -> dict[str, Any]:
    schema = load_schema_file("arbiter_verdict.schema.json")
    return schema_to_min_example(schema) if schema else {
        "verdict": "accept",
        "confidence": 0.0,
        "gaps": [],
        "shard_plan": [],
        "suggested_investigation": None,
        "reasoning_summary": "",
    }
