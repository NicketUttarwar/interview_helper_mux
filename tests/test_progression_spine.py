from __future__ import annotations

from interview_mux.progression_spine import first_incomplete_p0_stage
from run_fixtures import init_run_meta_for_test, isolated_run_ctx, patch_merged_config


def test_first_incomplete_p0_stage_missing_boundaries(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "p0_spine_boundaries")
    init_run_meta_for_test(ctx)
    ctx.mark_done("speaker_roles", force=True)
    ctx.mark_done("content_context", force=True)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewer", "label": "Host", "confidence": 0.9}
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Main thesis",
            "topics": [{"name": "Tech", "summary": "Summary", "approx_time_range": "0:00-1:00"}],
        },
        skip_handoff=True,
    )
    assert first_incomplete_p0_stage(ctx) == "boundary_detection"


def test_p0_hole_detected_when_later_stages_marked_done(tmp_path, monkeypatch):
    from interview_mux.pipeline import ANALYSIS_ORDER

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {"flow_hardening": {"enabled": True}},
            "stage_execution_reuse": {"enabled": False},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "p0_spine_block")
    init_run_meta_for_test(ctx)
    for sid in ANALYSIS_ORDER:
        if sid == "segment_classification":
            break
        ctx.mark_done(sid, force=True)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewer", "label": "Host", "confidence": 0.9}
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Main thesis",
            "topics": [{"name": "Tech", "summary": "Summary", "approx_time_range": "0:00-1:00"}],
        },
        skip_handoff=True,
    )
    assert first_incomplete_p0_stage(ctx) == "boundary_detection"
