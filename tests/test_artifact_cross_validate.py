from __future__ import annotations

import pytest

from interview_mux.artifact_cross_validate import validate_cross_artifacts
from run_fixtures import (
    isolated_run_ctx,
    minimal_gap_line,
    minimal_gap_report,
    minimal_manifest,
    minimal_manifest_segment,
    seed_flow1_sound_spend_ready,
    sound_design_plan_with,
)


def test_pre_master_flow1_with_seeded_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_pre_master")
    seed_flow1_sound_spend_ready(ctx)
    from interview_mux.sdp_cross_validate import validate_pre_master

    assert validate_pre_master(ctx, "flow1") == []


def test_pre_master_flow1_flags_post_listen_fail(tmp_path, monkeypatch):
    from interview_mux.sdp_cross_validate import validate_pre_master
    from run_fixtures import patch_merged_config

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"sound_design": {"post_listen_gate_mode": "block_mix"}},
    )
    ctx = isolated_run_ctx(tmp_path, "cv_pre_master_listen")
    seed_flow1_sound_spend_ready(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["sfx_listen_results"] = [{"asset_id": "bed_01", "result": "fail"}]
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    errors = validate_pre_master(ctx, "flow1")
    assert any("post_listen failed" in e for e in errors)


def test_validate_cross_artifacts_pre_master_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_pre_master_x")
    seed_flow1_sound_spend_ready(ctx)
    errors = validate_cross_artifacts(ctx, "pre_master_flow1")
    assert errors == []


def test_post_segmentation_boundary_not_in_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_seg")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    boundaries_path = ctx.path("segments", "boundaries.json")
    boundaries_path.parent.mkdir(parents=True, exist_ok=True)
    boundaries_path.write_text(
        '{"boundaries": [{"segment_id": "seg_999", "start_ms": 0, "end_ms": 1000}]}',
        encoding="utf-8",
    )
    errors = validate_cross_artifacts(ctx, "post_segmentation")
    assert any("seg_999" in e for e in errors)


def test_post_gaps_evaluation_segment_not_in_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_gaps")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [{"segment_id": "seg_missing", "self_explanatory": False}]},
        skip_handoff=True,
    )
    errors = validate_cross_artifacts(ctx, "post_gaps")
    assert any("seg_missing" in e for e in errors)


def test_post_sound_palettes_missing_segment(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_palette")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            coherence={"sonic_identity": "warm", "primary_mood": "calm", "density": "sparse"},
            palettes=[
                {
                    "palette_id": "p1",
                    "segment_ids": ["seg_999"],
                    "theme_label": "x",
                    "keywords": ["test"],
                    "ambient_description": "sparse room tone",
                    "accent_description": "soft chime",
                    "avoid": ["harsh noise"],
                }
            ],
        ),
        skip_handoff=True,
    )
    errors = validate_cross_artifacts(ctx, "post_sound_palettes")
    assert any("seg_999" in e for e in errors)


def test_pre_sfx_generation_passes_with_seeded_sound_path(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_spend_ok")
    seed_flow1_sound_spend_ready(ctx)
    errors = validate_cross_artifacts(ctx, "pre_sfx_generation")
    assert errors == []


def test_pre_mix_flow1_passes_with_seeded_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_mix_ok")
    seed_flow1_sound_spend_ready(ctx)
    errors = validate_cross_artifacts(ctx, "pre_mix_flow1")
    assert errors == []


def test_pre_mix_flow1_full_sound_path(tmp_path, monkeypatch):
    from run_fixtures import seed_flow1_full_sound_path

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_mix_full")
    seed_flow1_full_sound_path(ctx)
    assert validate_cross_artifacts(ctx, "post_ranking") == []
    assert validate_cross_artifacts(ctx, "pre_mix_flow1") == []


def test_post_ranking_orphan_segment_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_rank_hard")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_999"]},
        skip_handoff=True,
    )
    errors = validate_cross_artifacts(ctx, "post_ranking")
    assert any("seg_999" in e for e in errors)


def test_post_transitions_invalid_id_hard_soft_split(tmp_path, monkeypatch):
    from interview_mux.artifact_cross_validate import _validate_post_transitions_split

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_tr_split")
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    vo_line = "this pickup line should not be duplicated in transition copy"
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(minimal_gap_line(text=vo_line)),
        skip_handoff=True,
    )
    ctx.write_json(
        "flow_1_master/transitions.json",
        {
            "transitions": [
                {
                    "transition_id": "t_bad",
                    "type": "bridge",
                    "before_segment_id": "seg_001",
                    "after_segment_id": "seg_bad",
                    "text": "Short bridge.",
                },
                {
                    "transition_id": "t_dup",
                    "type": "bridge",
                    "before_segment_id": "seg_001",
                    "after_segment_id": "seg_001",
                    "text": f"Bridge that repeats {vo_line} verbatim.",
                },
            ]
        },
        skip_handoff=True,
    )
    hard, soft = _validate_post_transitions_split(ctx)
    assert any("seg_bad" in e for e in hard)
    assert any("duplicates" in e for e in soft)


def test_maybe_cross_validate_transitions_soft_enqueues_investigation(tmp_path, monkeypatch):
    from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage
    from run_fixtures import patch_merged_config

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "cross_validate_enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "cv_tr_soft")
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    vo = "unique pickup line for overlap detection test case"
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(minimal_gap_line(text=vo)),
        skip_handoff=True,
    )
    ctx.write_json(
        "flow_1_master/transitions.json",
        {
            "transitions": [
                {
                    "transition_id": "t1",
                    "type": "bridge",
                    "before_segment_id": "seg_001",
                    "after_segment_id": "seg_001",
                    "text": f"Next we hear {vo} again.",
                }
            ]
        },
        skip_handoff=True,
    )
    maybe_cross_validate_after_stage(ctx, "transitions")
    queue = ctx.read_json("understanding/investigation_queue.json")
    items = queue.get("items") or queue.get("investigations") or []
    assert any(it.get("kind") == "cross_artifact_invalid" for it in items)


def test_maybe_cross_validate_ranking_raises_system_exit(tmp_path, monkeypatch):
    from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage
    from run_fixtures import patch_merged_config

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "cross_validate_enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "cv_rank_exit")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_999"]},
        skip_handoff=True,
    )
    with pytest.raises(SystemExit, match="post_ranking"):
        maybe_cross_validate_after_stage(ctx, "full_master_ranking")


def test_maybe_cross_validate_raises_on_failure(tmp_path, monkeypatch):
    from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage
    from run_fixtures import patch_merged_config

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "cross_validate_enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "cv_raise")
    manifest_path = ctx.path("segments", "manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('{"segments": []}', encoding="utf-8")
    with pytest.raises(SystemExit, match="Cross-artifact gate"):
        maybe_cross_validate_after_stage(ctx, "segment_classification")
