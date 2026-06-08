from __future__ import annotations

from interview_mux.analysis_memory import (
    _derive_one_line_summary,
    default_analysis_state,
    enqueue_style_conflicts,
    ensure_analysis_workspace,
    load_analysis_state,
    load_queue,
    merge_memory_updates,
    save_analysis_state,
    sync_content_brief_to_state,
)
from run_fixtures import isolated_run_ctx


def test_merge_memory_updates_applies_style_patch():
    state = default_analysis_state("run_style")
    merged, conflicts = merge_memory_updates(
        state,
        {
            "style_patch": {
                "tone": "Warm investigative",
                "tone_class": "journalistic",
                "format_class": "one_on_one",
            },
            "interview_identity_patch": {"one_line_summary": "A founder on scaling teams."},
        },
    )
    assert merged["style"]["tone"] == "Warm investigative"
    assert merged["style"]["tone_class"] == "journalistic"
    assert merged["interview_identity"]["one_line_summary"] == "A founder on scaling teams."
    assert conflicts == []


def test_merge_memory_updates_skips_locked_style_field():
    state = default_analysis_state("run_locked")
    state["style"]["tone"] = "Operator tone"
    state["meta"]["operator_locked_fields"] = ["style.tone"]
    merged, conflicts = merge_memory_updates(
        state,
        {"style_patch": {"tone": "AI suggested tone", "tone_class": "investor"}},
    )
    assert merged["style"]["tone"] == "Operator tone"
    assert merged["style"]["tone_class"] == "investor"
    assert len(conflicts) == 1
    assert conflicts[0]["field"] == "style.tone"


def test_enqueue_style_conflicts_adds_investigation(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_style_conflict")
    ensure_analysis_workspace(ctx)
    enqueue_style_conflicts(
        ctx,
        "content_context",
        [{"field": "style.tone_class", "locked": "journalistic", "suggested": "investor"}],
    )
    queue = load_queue(ctx)
    assert len(queue["items"]) == 1
    assert queue["items"][0]["kind"] == "style_conflict"


def test_sync_content_brief_derives_one_line_summary(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_summary_fallback")
    ensure_analysis_workspace(ctx)
    sync_content_brief_to_state(
        ctx,
        {"thesis": "The guest explains how early hiring shaped product velocity."},
    )
    state = load_analysis_state(ctx)
    assert "early hiring" in state["interview_identity"]["one_line_summary"]


def test_save_analysis_state_tracks_operator_edits(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_gui_lock")
    ensure_analysis_workspace(ctx)
    base = default_analysis_state(ctx.run_id)
    save_analysis_state(ctx, base, stage="analysis_profile")
    edited = default_analysis_state(ctx.run_id)
    edited["style"]["tone"] = "Edited by operator"
    save_analysis_state(ctx, edited, stage="operator_gui")
    state = load_analysis_state(ctx)
    assert "style.tone" in (state.get("meta") or {}).get("operator_locked_fields", [])


def test_derive_one_line_summary_caps_length():
    long_thesis = "A" * 200 + ". Second sentence."
    summary = _derive_one_line_summary({"thesis": long_thesis})
    assert len(summary) <= 120


def test_analysis_state_gaps_include_style_fields():
    from interview_mux.artifact_completeness import compute_gaps

    gaps = compute_gaps("understanding/analysis_state.json", default_analysis_state("run_gaps"))
    paths = {g.path for g in gaps}
    assert "style.tone" in paths
    assert "style.tone_class" in paths
    assert "style.format_class" in paths
