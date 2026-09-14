"""Wave 5 R-scan: producers cannot hollow-complete on a missing primary.

Disk path + incompleteness + heal refuse. FORCE_DONE_GUARDED stages refuse
raw mark_done. Ingest/transcribe stay on prepare unmark (no extra disk-path).
Do not start a run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import unmark_hollow_prepare_stages
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, STAGE_ARTIFACT_SCHEMAS
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from interview_mux.thrash_hardening import FORCE_DONE_GUARDED
from run_fixtures import isolated_run_ctx, mark_done_raw

_R_SCAN_STAGES = (
    "content_context",
    "talking_points_compose",
    "ideal_cuts_propose",
    "ideal_cuts_materialize",
    "boundary_detection",
    "segment_classification",
    "interview_spine_build",
    "audio_probe_build",
    "sound_design_palettes",
    "gap_framing_compose",
    "topic_coverage_audit",
    "narrative_arc_plan",
    "nugget_corpus_mine",
    "information_package_plan",
    "transitions",
    "sound_design_plan",
    "listen_delight_audit",
    "music_palette_compose",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "episode_meta_build",
    "episode_cover_prompt_craft",
    "podcast_encode_mp3",
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "wave5_hollow")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


@pytest.mark.parametrize("stage_id", _R_SCAN_STAGES)
def test_wave5_missing_primary_is_incomplete(ctx: RunContext, stage_id: str) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS[stage_id]
    assert not ctx.artifact_exists(rel)
    reason = stage_artifact_incompleteness(ctx, stage_id)
    assert reason is not None
    mark_done_raw(ctx, stage_id)
    out = heal_or_refuse_mark(ctx, stage_id)
    assert out.get("unmarked") is True or not ctx.is_done(stage_id)
    if stage_id in FORCE_DONE_GUARDED:
        ctx.mark_done(stage_id)
        assert not ctx.is_done(stage_id)


@pytest.mark.parametrize(
    "stage_id",
    [sid for sid in _R_SCAN_STAGES if sid in STAGE_ARTIFACT_SCHEMAS],
)
def test_wave5_empty_object_is_schema_hollow(ctx: RunContext, stage_id: str) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS[stage_id]
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{}", encoding="utf-8")
    reason = stage_artifact_incompleteness(ctx, stage_id)
    assert reason is not None
    mark_done_raw(ctx, stage_id)
    out = heal_or_refuse_mark(ctx, stage_id)
    assert out.get("unmarked") is True or not ctx.is_done(stage_id)


def test_wave5_ingest_transcribe_unmark_without_primary(ctx: RunContext) -> None:
    mark_done_raw(ctx, "ingest")
    mark_done_raw(ctx, "transcribe")
    cleared = unmark_hollow_prepare_stages(ctx)
    assert "ingest" in cleared
    assert "transcribe" in cleared
    assert not ctx.is_done("ingest")
    assert not ctx.is_done("transcribe")


def test_wave5_r_scan_disk_paths_registered() -> None:
    for sid in _R_SCAN_STAGES:
        assert sid in STAGE_ARTIFACT_DISK_PATHS, sid
    for sid in (
        "talking_points_compose",
        "interview_spine_build",
        "listen_delight_audit",
        "podcast_encode_mp3",
        "episode_meta_build",
    ):
        assert sid in FORCE_DONE_GUARDED
