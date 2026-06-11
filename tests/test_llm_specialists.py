from __future__ import annotations

from unittest.mock import patch

from interview_mux.llm_specialists import (
    _process_specialist_investigations,
    apply_segment_topic_patches,
    maybe_run_post_stage_specialists,
    maybe_run_pre_stage_specialists,
    specialists_enabled,
)
from run_fixtures import isolated_run_ctx

_VALID_SEGMENT = {
    "segment_id": "seg_1",
    "type": "interviewee_answer",
    "speaker_id": "spk_0",
    "speaker_role": "interviewee",
    "start_ms": 0,
    "end_ms": 1000,
    "topic_tags": [],
}


def _segment(seg_id: str, tags: list[str]) -> dict:
    return {
        "segment_id": seg_id,
        "type": "interviewee_answer",
        "speaker_id": "spk_0",
        "speaker_role": "interviewee",
        "start_ms": 0,
        "end_ms": 1000,
        "topic_tags": tags,
    }


_PILOT_CFG = {
    "analysis": {
        "specialists": {
            "enabled": True,
            "pilot_stages": ["full_master_ranking"],
        }
    }
}


def test_theme_coverage_specialist_applies_patches(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_theme_spec")
    ctx.write_json("segments/manifest.json", {"segments": [_VALID_SEGMENT]})
    count = _process_specialist_investigations(
        ctx,
        parent_stage="segment_classification",
        specialist_key="theme_coverage_pass",
        envelope={
            "artifacts": {
                "segment_topic_patches": [{"segment_id": "seg_1", "topic_tags": ["t1"]}],
            }
        },
    )
    assert count == 0
    manifest = ctx.read_json("segments/manifest.json")
    assert manifest["segments"][0]["topic_tags"] == ["t1"]


def test_apply_segment_topic_patches_merges_manifest(tmp_path, monkeypatch):
    from run_fixtures import patch_merged_config

    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "run_patch")
    ctx.write_json("segments/manifest.json", {"segments": [_segment("seg_2", ["old"])]})
    applied = apply_segment_topic_patches(
        ctx,
        [{"segment_id": "seg_2", "topic_tags": ["new_topic"]}],
    )
    assert applied == 1
    assert ctx.read_json("segments/manifest.json")["segments"][0]["topic_tags"] == ["new_topic"]


def test_pilot_stage_invokes_specialist_when_enabled(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_pilot_spec")
    with patch("interview_mux.llm_specialists.run_specialist") as mock_run:
        mock_run.return_value = {"artifacts": {}}
        outputs = maybe_run_post_stage_specialists(
            ctx,
            "full_master_ranking",
            {"segments": {}},
            cfg=_PILOT_CFG,
        )
        mock_run.assert_called_once_with(
            ctx,
            "comprehension_risk_blind",
            "full_master_ranking",
            {"segments": {}},
        )
        assert len(outputs) == 1


def test_non_pilot_stage_skips_when_pilot_configured(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_skip_spec")
    with patch("interview_mux.llm_specialists.run_specialist") as mock_run:
        outputs = maybe_run_post_stage_specialists(
            ctx,
            "missing_framing",
            {"segments": {}},
            cfg=_PILOT_CFG,
        )
        mock_run.assert_not_called()
        assert outputs == []


def test_specialists_enabled_globally_when_no_pilot():
    cfg = {"analysis": {"specialists": {"enabled": True}}}
    assert specialists_enabled(cfg=cfg)
    assert specialists_enabled(cfg=cfg, stage_key="missing_framing")
    assert specialists_enabled(cfg=cfg, stage_key="segment_classification")
    assert specialists_enabled(cfg=cfg, stage_key="topic_coverage_audit")
    assert specialists_enabled(cfg=cfg, stage_key="full_master_ranking")


def test_specialists_disabled_when_flag_off():
    cfg = {"analysis": {"specialists": {"enabled": False}}}
    assert not specialists_enabled(cfg=cfg, stage_key="full_master_ranking")


def test_pre_stage_specialist_runs_for_missing_framing(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_pre_spec")
    cfg = {
        "analysis": {
            "specialists": {
                "enabled": True,
                "pilot_stages": ["missing_framing"],
            }
        }
    }
    with patch("interview_mux.llm_specialists.run_specialist") as mock_run:
        mock_run.return_value = {"artifacts": {"comprehension_risks": []}}
        outputs = maybe_run_pre_stage_specialists(
            ctx,
            "missing_framing",
            {"segments": {}},
            cfg=cfg,
        )
        mock_run.assert_called_once()
        assert len(outputs) == 1


def test_run_specialist_injects_example_pack(tmp_path, monkeypatch):
    from interview_mux.llm_specialists import run_specialist

    ctx = isolated_run_ctx(tmp_path, "run_spec_examples")
    captured: dict[str, str] = {}

    def fake_run_prompt_envelope(*_a, **kwargs):
        captured["system"] = kwargs.get("system_override") or ""
        return {"status": "complete", "artifacts": {}}

    monkeypatch.setattr(
        "interview_mux.llm_specialists.run_prompt_envelope",
        fake_run_prompt_envelope,
    )
    monkeypatch.setattr(
        "interview_mux.llm_specialists.prepare_volley_for_llm",
        lambda *_a, **_k: ([{"role": "user", "content": "{}"}], None),
    )
    run_specialist(ctx, "comprehension_risk_blind", "missing_framing", {"segments": {}})
    assert "Compact examples" in captured.get("system", "") or "Examples" in captured.get("system", "")


def test_emphasis_coverage_specialist_enqueues(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_emph_spec")
    count = _process_specialist_investigations(
        ctx,
        parent_stage="topic_coverage_audit",
        specialist_key="emphasis_coverage_pass",
        envelope={"artifacts": {"emphasis_coverage": {"gaps": [{"segment_id": "seg_2"}]}}},
    )
    assert count == 1


def test_pre_stage_specialist_failure_enqueues_investigation(tmp_path, monkeypatch):
    from run_fixtures import patch_merged_config

    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True}, "specialists": {"enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "run_pre_fail")
    cfg = {
        "analysis": {
            "flow_hardening": {"enabled": True},
            "specialists": {"enabled": True, "pilot_stages": ["missing_framing"]},
        }
    }
    with patch("interview_mux.llm_specialists.run_specialist", side_effect=RuntimeError("boom")):
        outputs = maybe_run_pre_stage_specialists(ctx, "missing_framing", {"segments": {}}, cfg=cfg)
    assert outputs == []
    queue = ctx.read_json("understanding/investigation_queue.json")
    items = [i for i in (queue.get("items") or []) if i.get("status") == "open"]
    assert any(i.get("suggested_action", {}).get("specialist") == "comprehension_risk_blind" for i in items)


def test_apply_segment_topic_patches_invalidates_downstream_with_hardening(tmp_path, monkeypatch):
    from interview_mux.artifact_writes import write_validated_artifact
    from run_fixtures import minimal_manifest, patch_merged_config

    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "run_patch_hard")
    write_validated_artifact(
        ctx,
        "segments/manifest.json",
        minimal_manifest("seg_1"),
        merge_from_disk=False,
        stage_key="segment_classification",
    )
    ctx.mark_done("missing_framing")
    ctx.mark_done("optimal_questions")
    from run_fixtures import populated_analysis_state

    state = populated_analysis_state(ctx.run_id)
    state.setdefault("meta", {})["stage_summaries"] = {
        "missing_framing": {"status": "complete"},
        "optimal_questions": {"status": "complete"},
    }
    ctx.write_json("understanding/analysis_state.json", state)
    applied = apply_segment_topic_patches(
        ctx,
        [{"segment_id": "seg_1", "topic_tags": ["new_topic"]}],
    )
    assert applied == 1
    assert not ctx.is_done("missing_framing")
    assert not ctx.is_done("optimal_questions")
    summaries = (ctx.read_json("understanding/analysis_state.json").get("meta") or {}).get("stage_summaries") or {}
    assert "missing_framing" not in summaries
    assert "optimal_questions" not in summaries
