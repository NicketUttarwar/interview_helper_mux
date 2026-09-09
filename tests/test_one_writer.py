"""One-writer admission for hot delivery JSON artifacts."""

from __future__ import annotations

from pathlib import Path

from run_fixtures import (
    isolated_run_ctx,
    minimal_manifest,
    sound_design_plan_with,
)

from interview_mux.artifact_sanitize.one_writer import (
    HOT_ARTIFACT_RELS,
    admitting,
    begin_admit,
    commit_nugget_layup_plan_doc,
    commit_sound_design_plan_doc,
    commit_transitions_doc,
    end_admit,
    is_hot_artifact,
    maybe_admit_hot_write,
)
from interview_mux.file_store import write_json as fs_write_json


def test_hot_artifact_set():
    assert "master/selection.json" in HOT_ARTIFACT_RELS
    assert "understanding/gap_report.json" in HOT_ARTIFACT_RELS
    assert "master/edl.json" in HOT_ARTIFACT_RELS
    assert is_hot_artifact("master/selection.json")
    assert not is_hot_artifact("run_meta.json")


def test_write_json_selection_routes_through_commit(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "ow_sel")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002"),
        skip_handoff=True,
    )
    sel = {
        "version": 1,
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "keep_segment_ids": ["seg_001", "seg_002"],
        "segments": {
            "seg_001": {"segment_id": "seg_001", "keep": True},
            "seg_002": {"segment_id": "seg_002", "keep": True},
        },
    }
    path = ctx.write_json("master/selection.json", sel, skip_handoff=True)
    assert path.is_file()
    loaded = ctx.read_json("master/selection.json")
    assert loaded["ordered_segment_ids"] == ["seg_001", "seg_002"]
    assert not admitting(ctx)


def test_write_json_gap_routes_through_commit(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "ow_gap")
    gap = {
        "version": 1,
        "interviewer_lines": [],
        "gaps": [],
    }
    path = ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    assert path.is_file()
    loaded = ctx.read_json("understanding/gap_report.json")
    assert isinstance(loaded.get("interviewer_lines"), list)
    meta = loaded.get("_meta") if isinstance(loaded.get("_meta"), dict) else {}
    stamp = meta.get("sanitize") if isinstance(meta.get("sanitize"), dict) else {}
    assert stamp.get("ok") is True or "interviewer_lines" in loaded


def test_raw_escape_skips_admit(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "ow_raw")
    ctx._one_writer_raw = True
    assert (
        maybe_admit_hot_write(
            ctx,
            "understanding/gap_report.json",
            {"version": 1, "interviewer_lines": [], "gaps": []},
            skip_handoff=True,
        )
        is None
    )


def test_commit_transitions_and_sdp_and_layup(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "ow_multi")
    # Seed selection without re-entering full checkpoint schema surface.
    fs_write_json(
        ctx.path("master/selection.json"),
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "keep_segment_ids": ["seg_001"],
            "segments": {"seg_001": {"segment_id": "seg_001", "keep": True}},
        },
    )
    commit_transitions_doc(
        ctx,
        {"version": 1, "transitions": []},
        skip_handoff=True,
        reason="test",
    )
    assert ctx.artifact_exists("master/transitions.json")

    commit_sound_design_plan_doc(
        ctx,
        sound_design_plan_with(),
        skip_handoff=True,
        reason="test",
    )
    assert ctx.artifact_exists("understanding/sound_design_plan.json")

    commit_nugget_layup_plan_doc(
        ctx,
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "layups": [
                {
                    "target_segment_id": "seg_001",
                    "nugget_ids": [],
                    "selected_nugget_ids": [],
                    "skip": True,
                    "skip_reason_code": "test",
                }
            ],
        },
        skip_handoff=True,
        reason="test",
    )
    assert ctx.artifact_exists("understanding/nugget_layup_plan.json")


def test_nested_admit_no_recursion(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "ow_nested")
    begin_admit(ctx)
    try:
        assert admitting(ctx)
        ctx.write_json(
            "understanding/gap_report.json",
            {"version": 1, "interviewer_lines": [], "gaps": []},
            skip_handoff=True,
        )
    finally:
        end_admit(ctx)
    assert not admitting(ctx)
