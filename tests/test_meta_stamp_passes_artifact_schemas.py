"""The pipeline's ``_meta`` stamp must not fail an artifact's own schema (ISSUES 32).

Every one-hour run logged ``fingerprint flush skipped for
understanding/sonic_context.json: ... ('_meta' was unexpected)`` (and the same
for delivery_brief and soundscape_policy): the fingerprinted copy never landed.
"""

from __future__ import annotations

from interview_mux.prompt_validation import _validate_dict

CLOSED = {
    "type": "object",
    "additionalProperties": False,
    "required": ["a"],
    "properties": {"a": {"type": "string"}},
}


def test_undeclared_meta_stamp_is_not_a_schema_error() -> None:
    assert _validate_dict({"a": "x", "_meta": {"content_hash": "h"}}, CLOSED) == []


def test_other_extra_keys_still_fail() -> None:
    errs = _validate_dict({"a": "x", "_meta": {}, "stray": 1}, CLOSED)
    assert errs and "stray" in errs[0]
    assert "_meta" not in errs[0]


def test_declared_meta_is_still_validated() -> None:
    schema = dict(CLOSED, properties={"a": {"type": "string"}, "_meta": {"type": "object"}})
    assert _validate_dict({"a": "x", "_meta": "not-an-object"}, schema)


def test_fingerprinted_copies_of_affected_artifacts_validate() -> None:
    from interview_mux.prompt_validation import validate_artifact_write

    for rel in (
        "understanding/sonic_context.json",
        "understanding/delivery_brief.json",
        "understanding/soundscape_policy.json",
    ):
        errs = validate_artifact_write(rel, {"_meta": {"producer_stage": "x", "content_hash": "h"}})
        assert not [e for e in errs if "_meta" in e], (rel, errs)
