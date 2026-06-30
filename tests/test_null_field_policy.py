from __future__ import annotations

from interview_mux.null_field_policy import (
    acknowledge_null_fields,
    find_null_fields,
    null_acknowledged_paths,
    partition_nulls,
    strip_null_leaves_for_volley,
)


def test_find_null_fields_top_level():
    paths = find_null_fields("content_context", {"thesis": "ok", "audience": None})
    assert "audience" in paths


def test_partition_nullable_vs_critical():
    critical, ack = partition_nulls("content_context", ["thesis", "audience"])
    assert "thesis" in critical
    assert "audience" in ack


def test_acknowledge_null_fields_sets_meta():
    artifacts = {"thesis": "Main point", "topics": [{"name": "A", "summary": "s"}], "audience": None}
    out, critical, ack = acknowledge_null_fields(None, "content_context", artifacts)
    assert not critical
    assert "audience" in ack
    assert "audience" in null_acknowledged_paths(out)


def test_critical_null_thesis():
    artifacts = {"thesis": None, "topics": [{"name": "A", "summary": "s"}]}
    _out, critical, ack = acknowledge_null_fields(None, "content_context", artifacts)
    assert "thesis" in critical
    assert not ack


def test_jargon_glossary_first_segment_id_nullable():
    artifacts = {
        "thesis": "Main point",
        "topics": [{"name": "A", "summary": "s"}],
        "jargon_glossary": [
            {"term": "ESOP", "plain_definition": "Employee stock ownership plan", "first_segment_id": None},
        ],
    }
    _out, critical, ack = acknowledge_null_fields(None, "content_context", artifacts)
    assert not critical
    assert "jargon_glossary[].first_segment_id" in ack


def test_strip_null_leaves_for_volley():
    shaped = strip_null_leaves_for_volley({"audience": None, "thesis": "x"})
    assert shaped["audience"] == {"_unavailable": True}
    assert shaped["thesis"] == "x"
