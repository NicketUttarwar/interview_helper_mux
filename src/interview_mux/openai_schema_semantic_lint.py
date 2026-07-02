"""Semantic lint for OpenAI strict json_schema — catches enum/type mismatches structural lint misses."""

from __future__ import annotations

from typing import Any


def lint_openai_semantic_schema(schema: dict[str, Any], *, path: str = "") -> list[str]:
    """Return human-readable semantic violations."""
    errors: list[str] = []
    _lint_node(schema, path or "schema", errors)
    return errors


def assert_openai_semantic_schema(schema: dict[str, Any], *, path: str = "") -> None:
    errors = lint_openai_semantic_schema(schema, path=path)
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(f"OpenAI semantic schema lint failed:\n{joined}")


def resolve_effective_type(node: dict[str, Any]) -> str | None:
    """Best-effort primary non-null JSON Schema type for a node."""
    t = node.get("type")
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        if len(non_null) == 1:
            return str(non_null[0])
        if non_null:
            return str(non_null[0])
    if "enum" in node:
        vals = node.get("enum") or []
        if vals and all(isinstance(v, str) for v in vals):
            return "string"
        if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            return "number"
    if "properties" in node:
        return "object"
    if "items" in node:
        return "array"
    return None


def _enum_values_compatible(node: dict[str, Any], effective_type: str | None) -> bool:
    enum_vals = node.get("enum")
    if not enum_vals:
        return True
    if effective_type == "string":
        return all(isinstance(v, str) for v in enum_vals)
    if effective_type == "number":
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in enum_vals)
    if effective_type == "integer":
        return all(isinstance(v, int) and not isinstance(v, bool) for v in enum_vals)
    if effective_type == "boolean":
        return all(isinstance(v, bool) for v in enum_vals)
    if effective_type == "object":
        return all(isinstance(v, dict) for v in enum_vals)
    return True


def _lint_node(schema: dict[str, Any], path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        return

    if "anyOf" in schema or "oneOf" in schema:
        key = "anyOf" if "anyOf" in schema else "oneOf"
        for idx, branch in enumerate(schema[key]):
            if isinstance(branch, dict):
                _lint_node(branch, f"{path}.{key}[{idx}]", errors)
        return

    effective = resolve_effective_type(schema)
    if "enum" in schema and not _enum_values_compatible(schema, effective):
        errors.append(
            f"{path}: enum values incompatible with effective type {effective!r}"
        )

    if effective == "object" and "enum" in schema:
        props = schema.get("properties") or {}
        if not props:
            errors.append(
                f"{path}: enum on type object without properties "
                f"(values={schema.get('enum')[:3]!r}...)"
            )

    if "minLength" in schema and effective not in (None, "string"):
        errors.append(f"{path}: minLength requires string type, got {effective!r}")

    if "maxLength" in schema and effective not in (None, "string"):
        errors.append(f"{path}: maxLength requires string type, got {effective!r}")

    if effective == "object":
        for key, prop in (schema.get("properties") or {}).items():
            if isinstance(prop, dict):
                _lint_node(prop, f"{path}.properties.{key}", errors)

    if effective == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            _lint_node(items, f"{path}.items", errors)


__all__ = [
    "assert_openai_semantic_schema",
    "lint_openai_semantic_schema",
    "resolve_effective_type",
]
