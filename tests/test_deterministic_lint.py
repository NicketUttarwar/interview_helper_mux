from __future__ import annotations

from interview_mux.deterministic_lint import deterministic_lint
from run_fixtures import isolated_run_ctx, minimal_gap_evaluations, minimal_manifest


def test_lint_rejects_generic_thesis_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_cc")
    envelope = {"artifacts": {"thesis": "", "topics": []}}
    errors = deterministic_lint("content_context", envelope, ctx)
    assert any("thesis" in e.lower() for e in errors)


def test_lint_plan_flow1_asset_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_plan")
    ctx.write_json("flow_1_master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    assets = [{"asset_id": f"a{i}", "role": "chapter_stinger"} for i in range(8)]
    envelope = {
        "artifacts": {
            "assets": assets,
            "flow_plans": {"flow1": {"cues": []}},
        }
    }
    errors = deterministic_lint("sound_design_plan_flow1", envelope, ctx)
    assert any("cap" in e.lower() or "exceeds" in e.lower() for e in errors)


def test_lint_optimal_questions_high_gap_without_line(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_oq")
    ctx.write_json(
        "understanding/gap_evaluations.json",
        minimal_gap_evaluations(
            {"segment_id": "seg_001", "severity": "high", "self_explanatory": False, "gap_type": "missing_context"}
        ),
    )
    errors = deterministic_lint("optimal_questions", {"artifacts": {"interviewer_lines": []}}, ctx)
    assert any("interviewer line" in e for e in errors)


def test_lint_topic_coverage_missing_score(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_tca")
    errors = deterministic_lint("topic_coverage_audit", {"artifacts": {"missing_coverage": []}}, ctx)
    assert any("coverage_score" in e for e in errors)


def test_lint_narrative_arc_empty_chapter(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_nap")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"))
    errors = deterministic_lint(
        "narrative_arc_plan",
        {"artifacts": {"chapters": [{"chapter_id": "ch1", "segment_ids": []}]}},
        ctx,
    )
    assert any("segment_ids" in e for e in errors)


def test_lint_edl_audit_invalid_verdict(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_edl")
    errors = deterministic_lint("edl_narrative_audit", {"artifacts": {"verdict": "maybe"}}, ctx)
    assert any("verdict" in e for e in errors)


def test_lint_show_description_word_count(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_show")
    errors = deterministic_lint(
        "podcast_show_description",
        {"artifacts": {"word_count": 10, "description_markdown": "short"}},
        ctx,
    )
    assert any("word_count" in e for e in errors)


def test_lint_legacy_sfx_brief_when_sdp_exists(tmp_path, monkeypatch):
    from run_fixtures import seed_flow1_sound_spend_ready

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_legacy")
    seed_flow1_sound_spend_ready(ctx)
    errors = deterministic_lint("podcast_sfx_brief", {"artifacts": {"cues": []}}, ctx)
    assert any("SDP" in e or "legacy" in e.lower() or "sound_design_plan" in e for e in errors)


def test_lint_craft_rejects_short_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_craft")
    envelope = {
        "artifacts": {
            "prompts": [
                {
                    "asset_id": "bed_01",
                    "elevenlabs_prompt": "short",
                    "duration_seconds": 6,
                    "negative_prompt": "no vocals",
                }
            ]
        }
    }
    errors = deterministic_lint("elevenlabs_prompt_craft", envelope, ctx)
    assert any("40 words" in e or "under" in e for e in errors)
