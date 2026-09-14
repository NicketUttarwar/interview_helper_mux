"""HC-1: later-done must not preserve a hollow or stale earlier marker.

EDL-ready pre-EDL producers stay marked. Do not start a run.
HU-1 SAP hollow-done stays open.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import mark_done_raw, patch_executions_root

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("hc1_later_done", create=True)
    run.write_json("run_meta.json", {"homunculus_version": "0.1.0"}, skip_handoff=True)
    monkeypatch.setattr(driver, "RUN_ID", run.run_id)
    monkeypatch.setattr(driver, "log", lambda *_a, **_k: None)
    return run


def test_hc1_hollow_unmarks_even_when_later_done(ctx: RunContext) -> None:
    mark_done_raw(ctx, "music_palette_compose")
    mark_done_raw(ctx, "mix")
    assert stage_artifact_incompleteness(ctx, "music_palette_compose")
    label = driver.clear_hollow_and_stale_stage_done(ctx, "music_palette_compose")
    assert label is not None
    assert "music_palette_compose" in label
    assert not ctx.is_done("music_palette_compose")
    assert ctx.is_done("mix")


def test_hc1_stale_producer_unmarks_even_when_later_done(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json(
        "sound_design/music_palette_compose.json",
        {
            "status": "stale",
            "_meta": {
                "stale": True,
                "producer_stage": "music_palette_compose",
                "stale_reason": "hc1",
            },
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "music_palette_compose")
    mark_done_raw(ctx, "mix")
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: None,
    )
    label = driver.clear_hollow_and_stale_stage_done(ctx, "music_palette_compose")
    assert label is not None
    assert "stale-producer" in label
    assert not ctx.is_done("music_palette_compose")
    assert ctx.is_done("mix")


def test_hc1_edl_ready_keeps_pre_edl_hollow(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(driver, "_edl_ready_artifacts", lambda _ctx: True)
    mark_done_raw(ctx, "nugget_layup_compose")
    mark_done_raw(ctx, "mix")
    assert stage_artifact_incompleteness(ctx, "nugget_layup_compose")
    label = driver.clear_hollow_and_stale_stage_done(ctx, "nugget_layup_compose")
    assert label is None
    assert ctx.is_done("nugget_layup_compose")


def test_hc1_edl_ready_false_unmarks_pre_edl_hollow(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(driver, "_edl_ready_artifacts", lambda _ctx: False)
    mark_done_raw(ctx, "nugget_layup_compose")
    mark_done_raw(ctx, "mix")
    label = driver.clear_hollow_and_stale_stage_done(ctx, "nugget_layup_compose")
    assert label is not None
    assert not ctx.is_done("nugget_layup_compose")


def test_hc1_complete_stage_is_not_unmarked(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json(
        "sound_design/music_palette_compose.json",
        {"cues": [], "_meta": {"producer_stage": "music_palette_compose"}},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "music_palette_compose")
    mark_done_raw(ctx, "mix")
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: None,
    )
    label = driver.clear_hollow_and_stale_stage_done(ctx, "music_palette_compose")
    assert label is None
    assert ctx.is_done("music_palette_compose")
