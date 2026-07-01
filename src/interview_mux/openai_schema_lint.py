"""Lint JSON schemas for OpenAI strict structured-output compatibility."""

from __future__ import annotations

from typing import Any


def lint_openai_strict_schema(schema: dict[str, Any], *, path: str = "") -> list[str]:
    """Return human-readable violations of OpenAI strict json_schema rules."""
    errors: list[str] = []
    _lint_node(schema, path or "schema", errors)
    return errors


def assert_openai_strict_schema(schema: dict[str, Any], *, path: str = "") -> None:
    errors = lint_openai_strict_schema(schema, path=path)
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(f"OpenAI strict schema lint failed:\n{joined}")


def _lint_node(schema: dict[str, Any], path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        errors.append(f"{path}: $ref is not supported in OpenAI strict schemas")
        return

    if "anyOf" in schema or "oneOf" in schema:
        key = "anyOf" if "anyOf" in schema else "oneOf"
        errors.append(f"{path}: {key} is not supported in OpenAI strict schemas")
        for idx, branch in enumerate(schema[key]):
            if isinstance(branch, dict):
                _lint_node(branch, f"{path}.{key}[{idx}]", errors)
        return

    t = schema.get("type")
    types = [t] if isinstance(t, str) else list(t or [])

    if "object" in types or (t is None and "properties" in schema):
        if schema.get("additionalProperties") is not False:
            errors.append(f"{path}: object must set additionalProperties: false")
        for key, prop in (schema.get("properties") or {}).items():
            if isinstance(prop, dict):
                _lint_node(prop, f"{path}.properties.{key}", errors)
        return

    if "array" in types:
        if "items" not in schema:
            errors.append(f"{path}: array schema missing items")
            return
        items = schema.get("items")
        if isinstance(items, dict):
            _lint_node(items, f"{path}.items", errors)
        return

    if len(types) > 1:
        for branch_type in types:
            if branch_type == "null":
                continue
            branch = {k: v for k, v in schema.items() if k != "type"}
            branch["type"] = branch_type
            _lint_node(branch, f"{path}.type[{branch_type}]", errors)


__all__ = ["assert_openai_strict_schema", "lint_openai_strict_schema"]
