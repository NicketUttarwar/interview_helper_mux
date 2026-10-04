"""Conform an artifact to its own on-disk schema before a refused write is final.

LLM envelopes allow ``null`` (ISSUES 137 made 46 enums nullable) and models
emit loose scalars ("true", 3.0, "Whole"). Some artifact validators relax
optional leaves to accept null and others do not, so the same reply was
admitted for one artifact and refused for another (exec on the client's
machine: ``master/selection.json`` refused ``media_ip_cta[1].mixed_with_story:
null`` and full_master_ranking stopped; ISSUES 169).

``conform_to_schema`` only repairs what the schema itself states:

* an optional property that is ``null`` where the schema does not allow null
  is dropped;
* a required ``null`` becomes ``False`` / ``[]`` / ``{}`` for boolean, array
  and object types; a required string or number is left alone so the write
  still fails loudly instead of inventing content;
* scalars are coerced to the declared type ("true"/1 -> True, "3"/3.0 -> 3,
  numbers -> str) and enum strings are matched case-insensitively; an optional
  value that cannot be coerced is dropped;
* ``null`` items are removed from arrays whose items cannot be null;
* unknown keys under ``additionalProperties: false`` are dropped.

Callers run it only after validation has failed and validate again, so a
document that is already valid is never changed.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_DROP = object()


def _resolve(schema: Any, root: dict[str, Any]) -> dict[str, Any]:
    seen = 0
    while isinstance(schema, dict) and isinstance(schema.get("$ref"), str) and seen < 8:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            return {}
        node: Any = root
        for part in ref[2:].split("/"):
            if not isinstance(node, dict):
                return {}
            node = node.get(part.replace("~1", "/").replace("~0", "~"))
        schema = node
        seen += 1
    return schema if isinstance(schema, dict) else {}


def _types(schema: dict[str, Any], root: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    t = schema.get("type")
    if isinstance(t, str):
        out.add(t)
    elif isinstance(t, list):
        out.update(str(x) for x in t)
    for key in ("anyOf", "oneOf"):
        for branch in schema.get(key) or []:
            out |= _types(_resolve(branch, root), root)
    enum = schema.get("enum")
    if isinstance(enum, list) and None in enum:
        out.add("null")
    if "const" in schema and schema.get("const") is None:
        out.add("null")
    return out


def _allows_null(schema: dict[str, Any], root: dict[str, Any]) -> bool:
    types = _types(schema, root)
    if not types:
        return True  # unknown shape: not ours to judge
    return "null" in types


def _required_default(schema: dict[str, Any], root: dict[str, Any]) -> Any:
    types = _types(schema, root) - {"null"}
    if types == {"boolean"}:
        return False
    if types == {"array"}:
        return []
    if types == {"object"}:
        return {}
    return _DROP


def _coerce_scalar(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> Any:
    types = _types(schema, root)
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        if value in enum:
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            for option in enum:
                if isinstance(option, str) and option.lower() == low:
                    return option
        return _DROP
    if not types:
        return value
    if isinstance(value, bool):
        if "boolean" in types:
            return value
        if "integer" in types or "number" in types:
            return int(value)
        if "string" in types:
            return "true" if value else "false"
        return _DROP
    if isinstance(value, int):
        if "integer" in types or "number" in types:
            return value
        if "boolean" in types and value in (0, 1):
            return bool(value)
        if "string" in types:
            return str(value)
        return _DROP
    if isinstance(value, float):
        if "number" in types:
            return value
        if "integer" in types and value.is_integer():
            return int(value)
        if "string" in types:
            return str(value)
        return _DROP
    if isinstance(value, str):
        if "string" in types:
            return value
        low = value.strip().lower()
        if "boolean" in types and low in {"true", "yes", "1", "false", "no", "0"}:
            return low in {"true", "yes", "1"}
        if ("integer" in types or "number" in types) and re.fullmatch(r"-?\d+(\.\d+)?", low):
            num = float(low)
            if "integer" in types and num.is_integer():
                return int(num)
            if "number" in types:
                return num
        return _DROP
    return value


def _conform(value: Any, schema: Any, root: dict[str, Any], path: str, notes: list[str]) -> Any:
    schema = _resolve(schema, root)
    if not schema or value is None:
        return value
    types = _types(schema, root)
    if isinstance(value, dict):
        if types and "object" not in types:
            return _DROP
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = set(schema.get("required") or [])
        extra = schema.get("additionalProperties")
        has_patterns = bool(schema.get("patternProperties"))
        for key in list(value.keys()):
            if key == "_meta":
                continue
            child_path = f"{path}.{key}" if path else key
            prop = props.get(key)
            if prop is None:
                if isinstance(extra, dict):
                    prop = extra
                elif extra is False and not has_patterns:
                    del value[key]
                    notes.append(f"{child_path}: dropped unknown key")
                    continue
                else:
                    continue
            prop_r = _resolve(prop, root)
            current = value[key]
            if current is None:
                if _allows_null(prop_r, root):
                    continue
                if key in required:
                    fallback = _required_default(prop_r, root)
                    if fallback is not _DROP:
                        value[key] = fallback
                        notes.append(f"{child_path}: required null -> {fallback!r}")
                    continue
                del value[key]
                notes.append(f"{child_path}: dropped null")
                continue
            fixed = _conform(current, prop_r, root, child_path, notes)
            if fixed is _DROP:
                if key in required:
                    continue  # leave it; validation reports it
                del value[key]
                notes.append(f"{child_path}: dropped {type(current).__name__} the schema cannot take")
                continue
            if fixed is not current and fixed != current:
                notes.append(f"{child_path}: {current!r} -> {fixed!r}")
            value[key] = fixed
        return value
    if isinstance(value, list):
        if types and "array" not in types:
            return _DROP
        items = _resolve(schema.get("items"), root) if isinstance(schema.get("items"), dict) else {}
        if not items:
            return value
        out: list[Any] = []
        for i, item in enumerate(value):
            child_path = f"{path}[{i}]"
            if item is None:
                if _allows_null(items, root):
                    out.append(item)
                else:
                    notes.append(f"{child_path}: dropped null item")
                continue
            fixed = _conform(item, items, root, child_path, notes)
            if fixed is _DROP:
                notes.append(f"{child_path}: dropped item the schema cannot take")
                continue
            if fixed is not item and fixed != item:
                notes.append(f"{child_path}: {item!r} -> {fixed!r}")
            out.append(fixed)
        return out
    return _coerce_scalar(value, schema, root)


def conform_to_schema(data: Any, schema: dict[str, Any] | None) -> tuple[Any, list[str]]:
    """Return (conformed copy, notes). ``data`` is never mutated."""
    if not isinstance(schema, dict) or not isinstance(data, dict):
        return data, []
    notes: list[str] = []
    doc = copy.deepcopy(data)
    fixed = _conform(doc, schema, schema, "", notes)
    if fixed is _DROP:
        return data, []
    return fixed, notes


_SCHEMA_CALL = re.compile(
    r"(_load_schema|_load_root_schema|_validate_by_artifact_schema)\(\s*[\"']([^\"']+\.json)[\"']"
)


def artifact_schema_for(rel_path: str) -> dict[str, Any] | None:
    """The schema the write validator for ``rel_path`` checks against, if one."""
    try:
        import inspect

        from interview_mux import prompt_validation as pv

        validator = pv.ARTIFACT_WRITE_VALIDATORS.get(rel_path)
        if validator is None:
            return None
        match = _SCHEMA_CALL.search(inspect.getsource(validator))
        if not match:
            return None
        loader, filename = match.group(1), match.group(2)
        if loader == "_load_root_schema":
            return pv._load_root_schema(filename)
        return pv._load_schema(filename)
    except Exception:
        return None
