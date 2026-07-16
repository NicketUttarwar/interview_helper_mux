from __future__ import annotations

from interview_mux.deterministic_lint import deterministic_lint
from run_fixtures import isolated_run_ctx, minimal_gap_evaluations, minimal_manifest, patch_merged_config

def test_lint_rejects_generic_thesis_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_cc")
    envelope = {"artifacts": {"thesis": "", "topics": []}}
    errors = deterministic_lint("content_context", envelope, ctx)
    assert any("thesis" in e.lower() for e in errors)

def test_lint_plan_flow1_asset_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_plan")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    assets = [{"asset_id": f"a{i}", "role": "chapter_stinger"} for i in range(8)]
    envelope = {
        "artifacts": {
            "assets": assets,
            "flow_plans": {"podcast": {"cues": []}},
        }
    }
    errors = deterministic_lint("sound_design_plan", envelope, ctx)
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
                    "sfx_prompt": "short",
                    "duration_seconds": 6,
                    "negative_prompt": "no vocals",
                }
            ]
        }
    }
    errors = deterministic_lint("sfx_prompt_craft", envelope, ctx)
    assert any("40 words" in e or "under" in e for e in errors)

def test_lint_content_context_claim_field_uses_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_claim")
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "thesis": "Main point",
            "topics": [{"name": "Product", "summary": "x", "segment_ids": ["seg_001"]}],
            "key_claims": [{"id": "c1", "claim": "We launched in 2020.", "claim_type": "fact"}],
        },
    }
    errors = deterministic_lint("content_context", envelope, ctx)
    assert any("key_claim without evidence" in e for e in errors)

def test_lint_content_context_claim_passes_with_segment_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_claim_ok")
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "thesis": "Main point",
            "topics": [{"name": "Product", "summary": "x", "segment_ids": ["seg_001"]}],
            "key_claims": [
                {
                    "id": "c1",
                    "claim": "We launched in 2020.",
                    "claim_type": "fact",
                    "segment_ids": ["seg_001"],
                }
            ],
        },
    }
    errors = [
        e
        for e in deterministic_lint("content_context", envelope, ctx)
        if "key_claim" in e or "thesis empty" in e
    ]
    assert not errors


def test_lint_content_context_claim_passes_with_approx_time_range(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_claim_time")
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "thesis": "Main point from the guest.",
            "topics": [
                {
                    "name": "Product",
                    "summary": "Launch story",
                    "approx_time_range": "00:30-02:00",
                    "segment_ids": None,
                }
            ],
            "key_claims": [
                {
                    "id": "c1",
                    "claim": "We launched in 2020.",
                    "claim_type": "fact",
                    "approx_time_range": "01:10-01:45",
                    "segment_ids": None,
                    "evidence_segment_ids": None,
                }
            ],
        },
    }
    errors = [
        e
        for e in deterministic_lint("content_context", envelope, ctx)
        if "key_claim" in e or "topic without evidence" in e or "thesis empty" in e
    ]
    assert not errors


def test_lint_speaker_roles_multi_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_spk")
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "speakers": [
                {"speaker_id": "a", "role": "unknown"},
                {"speaker_id": "b", "role": "unknown"},
            ]
        },
    }
    errors = deterministic_lint("speaker_roles", envelope, ctx)
    assert any("unknown" in e.lower() for e in errors)


def test_lint_speaker_roles_panel_requires_two_content(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_panel")
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "speakers": [
                {"speaker_id": "a", "role": "moderator", "confidence": 0.9},
                {"speaker_id": "b", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {"format_class_candidate": "panel", "format_confidence": 0.8},
        },
    }
    errors = deterministic_lint("speaker_roles", envelope, ctx)
    assert any("panel format requires" in e for e in errors)

def test_producer_artifact_complete_passes_envelope_before_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_prod")
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "thesis": "A clear thesis from the interview.",
            "topics": [{"name": "Product", "summary": "Details", "segment_ids": ["seg_001"]}],
            "key_claims": [],
        },
    }
    errors = [
        e for e in deterministic_lint("content_context", envelope, ctx) if "producer_artifact_complete" in e
    ]
    assert not errors
