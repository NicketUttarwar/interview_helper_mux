"""JSON Schema nullability helpers — align artifact validation with OpenAI strict output."""

from __future__ import annotations

import copy
from typing import Any


def _add_null_to_type(prop: dict[str, Any]) -> dict[str, Any]:
    prop = copy.deepcopy(prop)
    t = prop.get("type")
    if t is None:
        if "enum" in prop:
            return prop
        return {**prop, "type": ["object", "null"]}
    if isinstance(t, list):
        if "null" not in t:
            prop["type"] = [*t, "null"]
    else:
        prop["type"] = [t, "null"]
    # enum is checked independently of type: a nullable enum must list null.
    enum = prop.get("enum")
    if isinstance(enum, list) and None not in enum:
        prop["enum"] = [*enum, None]
    return prop


def with_nullable_optional_leaves(
    schema: dict[str, Any],
    *,
    required: set[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of schema where non-required leaf properties accept null."""
    schema = copy.deepcopy(schema)
    req = set(schema.get("required") or [])
    if required is not None:
        req = required

    if "anyOf" in schema or "oneOf" in schema:
        key = "anyOf" if "anyOf" in schema else "oneOf"
        schema[key] = [
            with_nullable_optional_leaves(s, required=required) for s in schema[key]
        ]
        return schema

    t = schema.get("type")
    types = [t] if isinstance(t, str) else list(t or [])

    if "object" in types or (t is None and "properties" in schema):
        props = schema.get("properties") or {}
        new_props: dict[str, Any] = {}
        for key, prop in props.items():
            child_req = req if key in req else set()
            if key not in req:
                prop = _add_null_to_type(prop)
            new_props[key] = with_nullable_optional_leaves(prop, required=child_req or None)
        schema["properties"] = new_props
        return schema

    if "array" in types and "items" in schema:
        schema["items"] = with_nullable_optional_leaves(schema["items"])
        return schema

    return schema


def optional_property_names(schema: dict[str, Any]) -> set[str]:
    """Top-level optional property names for an object schema."""
    if not schema or schema.get("type") not in ("object", ["object"], None):
        if "properties" not in schema:
            return set()
    props = schema.get("properties") or {}
    req = set(schema.get("required") or [])
    return {k for k in props if k not in req}
