from __future__ import annotations

from interview_mux.required_response_format import (
    build_artifact_skeleton,
    build_envelope_skeleton,
    build_required_response_block,
    volley_format_footer,
)


def test_envelope_skeleton_has_required_keys():
    skel = build_envelope_skeleton()
    assert "status" in skel
    assert "artifacts" in skel
    assert "reasoning_summary" in skel


def test_content_context_artifact_skeleton():
    art = build_artifact_skeleton("content_context")
    assert "thesis" in art
    assert "topics" in art
    assert "jargon_glossary" in art
    assert "emotional_beats" in art
    assert art["jargon_glossary"][0]["term"]
    assert art["emotional_beats"][0]["label"]


def test_required_response_block_full_includes_null_rules():
    block = build_required_response_block("content_context", variant="full")
    assert "Required response format" in block
    assert "Critical" in block or "Nullable" in block
    assert "thesis" in block


def test_required_response_block_compact_for_volley():
    footer = volley_format_footer("speaker_roles", profile="full", task_kind="primary")
    assert "JSON envelope only" in footer
    assert "JSON null" in footer


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
