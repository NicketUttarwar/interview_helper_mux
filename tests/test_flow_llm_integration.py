from __future__ import annotations

import pytest

from interview_mux.analysis_memory import ensure_analysis_workspace
from interview_mux.stages import analysis_stage
from interview_mux.deterministic_lint import deterministic_lint
from interview_mux.llm_preflight import run_preflight
from interview_mux.stages import analysis_stage  # noqa: F401 — patched via module ref
from run_fixtures import isolated_run_ctx, minimal_manifest, patch_merged_config, seed_analysis_ready_artifacts


@pytest.mark.parametrize(
    "stage_key,prompt_rel",
    [
        ("full_master_ranking", "flow-1/full-master-ranking.system.txt"),
        ("transitions", "flow-1/transitions.system.txt"),
        ("sound_design_plan_flow1", "sound-design/plan-flow1.system.txt"),
    ],
)
def test_flow_stage_preflight_lint_hooks(tmp_path, monkeypatch, stage_key, prompt_rel):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, f"flow_int_{stage_key}")
    ensure_analysis_workspace(ctx)
    seed_analysis_ready_artifacts(ctx, verified=True)
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "preflight_enabled": True}}},
    )
    stage_input = {"segments": {"segments": [{"segment_id": "seg_001"}]}}
    preflight_errors = run_preflight(stage_key, ctx)
    assert isinstance(preflight_errors, list)

    bad_envelope = {"status": "complete", "artifacts": {"ordered_segment_ids": ["seg_missing"]}}
    lint_errors = deterministic_lint(stage_key, bad_envelope, ctx)
    if stage_key == "full_master_ranking":
        assert lint_errors

    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    monkeypatch.setattr(
        analysis_stage,
        "run_llm_stage_with_routing",
        lambda *_a, **_k: (
            {"status": "complete", "artifacts": {"ordered_segment_ids": ["seg_001"]}, "_routing_meta": {}},
            [],
            {"verdict": "accept"},
            [],
            0,
            "primary",
        ),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_cross_validate.maybe_cross_validate_after_stage",
        lambda *_a, **_k: None,
    )
    analysis_stage.run_flow_llm_stage(
        ctx,
        stage_key,
        prompt_rel,
        lambda _c: stage_input,
        lambda _c, _a: None,
        max_iterations=1,
        auto_complete=False,
    )
    assert ctx.artifact_exists(f"understanding/stage_runs/{stage_key}/attempt_001.json")
