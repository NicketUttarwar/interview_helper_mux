"""HS-1: island/fuse remainder drop, heal-mark after write, fuse-refresh cap.

After a successful island/fuse write, analysis remaining_stages drops those
stages even without .stage_done. Wrappers heal_or_refuse_mark (no raw stamp).
Full-auto refresh_connector_fuse_passes caps at 2 like layup.

Do not start a run. HS-3 skip-audit, HS-4 oscillation pin, HS-5 vernacular stay.
In-pass max_fuse_rounds stays finite — do not reopen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import remaining_stages, stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark
from interview_mux.stages.low_conf_fuse_stages import (
    _heal_island_stage,
    run_connector_fuse_pass as wrapper_fuse_pass,
)
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hs1_fuse")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hs1_analysis_remaining_keeps_island_without_outputs(ctx: RunContext) -> None:
    rem = remaining_stages(ctx, "analysis")
    assert "low_conf_island_scan" in rem
    assert "connector_fuse_pass" in rem
    assert not ctx.is_done("low_conf_island_scan")


def test_hs1_analysis_remaining_drops_island_when_outputs_present(ctx: RunContext) -> None:
    ctx.final_path("analysis", "low_conf_must_keep.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.final_path("analysis", "low_conf_must_keep.json").write_text(
        '{"must_keep_segment_ids":["seg_1"]}',
        encoding="utf-8",
    )
    assert stage_outputs_present(ctx, "low_conf_island_scan") is True
    assert not ctx.is_done("low_conf_island_scan")
    rem = remaining_stages(ctx, "analysis")
    assert "low_conf_island_scan" not in rem


def test_hs1_analysis_remaining_drops_fuse_when_audit_present(ctx: RunContext) -> None:
    ctx.final_path("analysis", "connector_fuse_audit.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.final_path("analysis", "connector_fuse_audit.json").write_text(
        '{"version":1,"passes":[],"applied_fuses":[],"stay_independent":[]}',
        encoding="utf-8",
    )
    assert not ctx.is_done("connector_fuse_pass")
    rem = remaining_stages(ctx, "analysis")
    assert "connector_fuse_pass" not in rem


def test_hs1_heal_marks_island_when_outputs_present(ctx: RunContext) -> None:
    ctx.final_path("analysis", "low_conf_islands.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.final_path("analysis", "low_conf_islands.json").write_text(
        '{"island_count":0,"islands":[]}',
        encoding="utf-8",
    )
    _heal_island_stage(ctx, "low_conf_island_scan")
    assert ctx.is_done("low_conf_island_scan")


def test_hs1_heal_does_not_raw_mark_without_outputs(ctx: RunContext) -> None:
    _heal_island_stage(ctx, "low_conf_island_scan")
    assert not ctx.is_done("low_conf_island_scan")
    heal_or_refuse_mark(ctx, "low_conf_island_scan", force=True)
    assert not ctx.is_done("low_conf_island_scan")


def test_hs1_wrapper_fuse_skip_heals_analysis_pass(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.segment_fuse.connector_fuse_cfg",
        lambda cfg=None: {"enabled": False, "max_fuses_per_pass": 24, "max_fuse_rounds": 8},
    )
    monkeypatch.setattr(
        "interview_mux.stages.low_conf_fuse_stages.connector_fuse_cfg",
        lambda cfg=None: {"enabled": False, "max_fuses_per_pass": 24, "max_fuse_rounds": 8},
    )
    wrapper_fuse_pass(ctx)
    assert ctx.artifact_exists("analysis/connector_fuse_audit.json")
    assert ctx.is_done("connector_fuse_pass")
    rem = remaining_stages(ctx, "analysis")
    assert "connector_fuse_pass" not in rem


def test_hs1_fuse_refresh_caps_at_two(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _tools = Path(__file__).resolve().parents[1] / "tools"
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))
    import full_auto_driver as driver  # noqa: E402

    monkeypatch.setattr(driver, "_FUSE_REFRESH_N", 0, raising=False)
    calls: list[dict] = []
    monkeypatch.setattr(driver, "execute", lambda spec: calls.append(dict(spec)))
    monkeypatch.setattr(driver, "log", lambda *a, **k: None)
    mark_done_raw(ctx, "connector_fuse_pass")

    assert driver.refresh_connector_fuse_passes(ctx, reason="first") is True
    assert driver.refresh_connector_fuse_passes(ctx, reason="second") is True
    assert driver.refresh_connector_fuse_passes(ctx, reason="third") is False
    assert len(calls) == 4
    assert not ctx.is_done("connector_fuse_pass")
