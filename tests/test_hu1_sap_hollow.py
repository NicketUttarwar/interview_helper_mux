"""HU-1: source_acoustic_profile cannot hollow-done or skip without a schema-valid SAP.

Missing file and {} stay incomplete. Skip is refused. Spine does not consume
a hollow profile. Do not start a run. HU-4 topology stays later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import skip_stage, stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from interview_mux.stages.interview_spine_stage import run_interview_spine_build
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_source_acoustic_profile

_SAP = "understanding/source_acoustic_profile.json"
_STAGE = "source_acoustic_profile"


def _plant_hollow_sap(ctx: RunContext) -> None:
    dest = ctx.final_path("understanding", "source_acoustic_profile.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{}", encoding="utf-8")


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hu1_sap")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hu1_missing_file_is_incomplete(ctx: RunContext) -> None:
    mark_done_raw(ctx, _STAGE)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "pending" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)


def test_hu1_skip_without_file_refused(ctx: RunContext) -> None:
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _STAGE, reason="conductor whim")
    assert not ctx.is_done(_STAGE)


def test_hu1_empty_object_is_incomplete_and_skip_refused(ctx: RunContext) -> None:
    _plant_hollow_sap(ctx)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "schema-hollow" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _STAGE, reason="file exists")
    mark_done_raw(ctx, _STAGE)
    with pytest.raises(RuntimeError, match="hollow_done"):
        skip_stage(ctx, _STAGE, reason="hollow marker")
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)


def test_hu1_valid_sap_completes_and_skip_does_not_mark(ctx: RunContext) -> None:
    ctx.write_json(_SAP, minimal_source_acoustic_profile(), skip_handoff=True)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    assert stage_outputs_present(ctx, _STAGE) is True
    doc = skip_stage(ctx, _STAGE, reason="already profiled")
    assert _STAGE in doc["skipped"]
    assert not ctx.is_done(_STAGE)
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("marked") is True
    assert ctx.is_done(_STAGE)
    assert seed_stage_complete(ctx, _STAGE) is True


def test_hu1_spine_refuses_hollow_sap(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda cfg=None: True,
    )
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello", "words": [], "segments": []},
        skip_handoff=True,
    )
    _plant_hollow_sap(ctx)
    with pytest.raises(RuntimeError, match="schema-hollow|resume source_acoustic_profile"):
        run_interview_spine_build(ctx)
    assert not ctx.is_done("interview_spine_build")


def test_hu1_spine_missing_sap_is_file_not_found(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda cfg=None: True,
    )
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello", "words": [], "segments": []},
        skip_handoff=True,
    )
    with pytest.raises(FileNotFoundError, match="source_acoustic_profile"):
        run_interview_spine_build(ctx)
