"""Tests for envelope min-examples and required response format blocks."""

from __future__ import annotations

from interview_mux.envelope_min_example import (
    build_envelope_min_example,
    MEMORY_UPDATES_MIN_EXAMPLE,
    NEEDS_MIN_EXAMPLE,
)
from interview_mux.required_response_format import (
    build_artifact_skeleton,
    build_envelope_skeleton,
    build_required_response_block,
    volley_format_footer,
)


def test_envelope_skeleton_has_typed_samples_in_every_field():
    skel = build_envelope_skeleton()
    assert skel["status"] == "complete"
    assert isinstance(skel["artifacts"], dict) and skel["artifacts"]
    assert isinstance(skel["memory_updates"], dict) and skel["memory_updates"]
    assert isinstance(skel["needs"], list) and skel["needs"]
    assert isinstance(skel["follow_up_investigations"], list) and skel["follow_up_investigations"]
    assert isinstance(skel["confidence"], (int, float)) and skel["confidence"] > 0
    assert isinstance(skel["reasoning_summary"], str) and skel["reasoning_summary"].strip()
    assert skel["memory_updates"]["themes_append"][0]["id"]
    assert skel["needs"][0]["type"]


def test_memory_updates_min_example_has_list_and_object_shapes():
    assert isinstance(MEMORY_UPDATES_MIN_EXAMPLE["themes_append"], list)
    assert isinstance(MEMORY_UPDATES_MIN_EXAMPLE["style_patch"], dict)
    assert isinstance(NEEDS_MIN_EXAMPLE[0]["params"], dict)


def test_content_context_artifact_skeleton():
    art = build_artifact_skeleton("content_context")
    assert "thesis" in art
    assert "topics" in art
    assert "jargon_glossary" in art
    assert "emotional_beats" in art
    assert art["jargon_glossary"][0]["term"]
    assert art["emotional_beats"][0]["label"]


def test_min_example_for_stage_includes_typed_envelope_fields():
    from interview_mux.openai_structured_output import min_example_for_stage

    env = min_example_for_stage("content_context")
    assert env["memory_updates"]["themes_append"]
    assert env["needs"]
    assert env["follow_up_investigations"]


def test_required_response_block_full_includes_null_rules():
    block = build_required_response_block("content_context", variant="full")
    assert "Required response format" in block
    assert "Critical" in block or "Nullable" in block
    assert "thesis" in block
    assert "themes_append" in block


def test_required_response_block_compact_for_volley():
    footer = volley_format_footer("speaker_roles", profile="full", task_kind="primary")
    assert "JSON envelope only" in footer
    assert "JSON null" in footer
    assert "memory_updates" in footer


def test_gap_fill_patch_mode():
    gfc = {"gaps": ["thesis"], "skip_fields": ["topics"]}
    block = build_required_response_block(
        "content_context",
        variant="compact",
        gap_fill_context=gfc,
    )
    assert "Patch-only" in block
    assert "thesis" in block


def test_arbiter_block():
    block = build_required_response_block("_arbiter", task_kind="arbiter")
    assert "verdict" in block


def test_build_envelope_min_example_empty_needs_option():
    env = build_envelope_min_example(include_optional_arrays=False)
    assert env["needs"] == []
    assert env["follow_up_investigations"] == []
