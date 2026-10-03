"""A nullable enum must list null (ISSUES 137).

JSON Schema checks ``enum`` independently of ``type``, so
``{"type": ["string", "null"], "enum": ["a", "b"]}`` rejects null. In exec_004
every ``stay_independent`` seam verdict carried ``fuse_direction: null``,
failed verification, retried to the invoke cap, and all fifteen LLM seam
verdicts were discarded. 46 such nodes sat in 21 schemas.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent


def _gaps(node, path="$"):
    if isinstance(node, dict):
        t = node.get("type")
        e = node.get("enum")
        if isinstance(t, list) and "null" in t and isinstance(e, list) and None not in e:
            yield path
        for k, v in node.items():
            yield from _gaps(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _gaps(v, f"{path}[{i}]")


def test_no_committed_schema_has_a_nullable_enum_without_null() -> None:
    bad = []
    for base in ("docs", "src", "config"):
        for f in (ROOT / base).rglob("*.json"):
            if "node_modules" in f.parts:
                continue
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            bad.extend(f"{f.relative_to(ROOT)}:{p}" for p in _gaps(doc))
    assert not bad, "nullable enum missing null:\n" + "\n".join(bad[:20])


def test_make_nullable_adds_null_to_enum() -> None:
    from interview_mux.openai_structured_output import _make_nullable

    out = _make_nullable({"type": "string", "enum": ["into_earlier", "into_later"]})
    assert out["type"] == ["string", "null"]
    assert None in out["enum"]
    jsonschema.validate(None, out)


def test_add_null_to_type_adds_null_to_enum() -> None:
    from interview_mux.schema_nullability import _add_null_to_type

    out = _add_null_to_type({"type": "string", "enum": ["left", "right"]})
    assert None in out["enum"]
    jsonschema.validate(None, out)


def test_seam_verdict_with_null_direction_validates() -> None:
    schema = json.loads(
        (ROOT / "docs/cross-cutting/json-schemas/artifacts/connector_seam_adjudicate.schema.json").read_text()
    )
    jsonschema.validate(
        {"verdicts": [{"pair_id": "p1", "decision": "stay_independent", "fuse_direction": None}]},
        schema,
    )
