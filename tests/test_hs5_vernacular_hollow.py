"""HS-5: vernacular_segment_sanitize cannot hollow-done.

Skip stub or this producer's restamped manifest completes. Missing/corrupt
manifest writes a skip stub. Heal-forward refuses a marker with no write.

Do not start a run. HS-1 remainder/refresh, HS-2 resplit, HS-3 fuse skip-audit stay.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import skip_stage, stage_outputs_present, unmark_stage_only
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from interview_mux.stages.audio_probes import run_vernacular_segment_sanitize
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_manifest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402

_STAGE = "vernacular_segment_sanitize"
_REPORT = "vernacular/resplit_report.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hs5_vernacular")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_hollow_report(ctx: RunContext) -> None:
    dest = ctx.final_path("vernacular", "resplit_report.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{}", encoding="utf-8")


def _plant_zones(ctx: RunContext, *, empty: bool = False) -> None:
    ctx.write_json(
        "transcript/protected_zones.json",
        {
            "zones": []
            if empty
            else [
                {
                    "zone_id": "pz_001",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "retention": "must_keep",
                }
            ]
        },
        skip_handoff=True,
    )


def test_hs5_missing_file_is_incomplete(ctx: RunContext) -> None:
    mark_done_raw(ctx, _STAGE)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "pending" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)


def test_hs5_empty_object_is_incomplete(ctx: RunContext) -> None:
    _plant_hollow_report(ctx)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "schema-hollow" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    mark_done_raw(ctx, _STAGE)
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)


def test_hs5_skip_without_report_refused(ctx: RunContext) -> None:
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _STAGE, reason="conductor whim")
    assert not ctx.is_done(_STAGE)


def test_hs5_missing_manifest_writes_skip_stub_and_marks(ctx: RunContext) -> None:
    _plant_zones(ctx)
    run_vernacular_segment_sanitize(ctx)
    report = ctx.read_json(_REPORT)
    assert report.get("skipped") == "no_manifest"
    assert isinstance(report.get("rows"), list)
    assert ctx.is_done(_STAGE)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    assert seed_stage_complete(ctx, _STAGE) is True


def test_hs5_corrupt_manifest_writes_skip_stub_and_marks(ctx: RunContext) -> None:
    _plant_zones(ctx)
    dest = ctx.final_path("segments", "manifest.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{not-json", encoding="utf-8")
    run_vernacular_segment_sanitize(ctx)
    report = ctx.read_json(_REPORT)
    assert report.get("skipped") == "corrupt_manifest"
    assert ctx.is_done(_STAGE)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None


def test_hs5_no_zones_writes_skip_stub_and_marks(ctx: RunContext) -> None:
    run_vernacular_segment_sanitize(ctx)
    report = ctx.read_json(_REPORT)
    assert report.get("skipped") == "no_zones"
    assert ctx.is_done(_STAGE)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None


def test_hs5_restamped_manifest_completes_without_report(ctx: RunContext) -> None:
    doc = minimal_manifest()
    doc["_meta"] = {"producer_stage": _STAGE}
    ctx.write_json("segments/manifest.json", doc, skip_handoff=True)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert ctx.is_done(_STAGE)
    assert seed_stage_complete(ctx, _STAGE) is True


def test_hs5_classification_manifest_is_not_enough(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(),
        stage_key="segment_classification",
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "pending" in reason
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("refused") is True or not ctx.is_done(_STAGE)


def test_hs5_heal_forward_refuses_without_write(ctx: RunContext) -> None:
    driver._heal_mark(ctx, _STAGE)
    assert not ctx.is_done(_STAGE)
    assert stage_artifact_incompleteness(ctx, _STAGE) is not None


def test_hs5_heal_forward_marks_after_skip_stub(ctx: RunContext) -> None:
    _plant_zones(ctx)
    run_vernacular_segment_sanitize(ctx)
    unmark_stage_only(ctx, _STAGE)
    assert not ctx.is_done(_STAGE)
    driver._heal_mark(ctx, _STAGE)
    assert ctx.is_done(_STAGE)
