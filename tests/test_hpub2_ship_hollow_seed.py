"""HPUB-2: cover generate and podcast_publish cannot hollow-complete.

episode_cover_generate needs publish/cover.jpg. podcast_publish remaining
needs package_ready with ready:true, not chapters.json. Hollow done unmarks
and pins cover generate. HPUB-3 transcript stays later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import (
    ship_after_master_remaining,
    stage_outputs_present,
    unmark_hollow_delivery_producers,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw


def _jpg(ctx: RunContext) -> None:
    dest = ctx.final_path("publish", "cover.jpg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\xff\xd8\xff")


def _package_ready(ctx: RunContext, *, ready: bool) -> None:
    ctx.write_json(
        "publish/package_ready.json",
        {"ready": ready},
        skip_handoff=True,
    )


def _chapters(ctx: RunContext) -> None:
    ctx.write_json("publish/chapters.json", {"chapters": []}, skip_handoff=True)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hpub2_ship")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hpub2_cover_missing_is_not_present(ctx: RunContext) -> None:
    mark_done_raw(ctx, "episode_cover_generate")
    assert stage_outputs_present(ctx, "episode_cover_generate") is False
    reason = stage_artifact_incompleteness(ctx, "episode_cover_generate")
    assert reason is not None
    assert "cover_missing" in reason
    assert seed_stage_complete(ctx, "episode_cover_generate") is False


def test_hpub2_cover_jpg_is_present(ctx: RunContext) -> None:
    _jpg(ctx)
    assert stage_outputs_present(ctx, "episode_cover_generate") is True
    assert stage_artifact_incompleteness(ctx, "episode_cover_generate") is None


def test_hpub2_chapters_alone_is_not_publish_complete(ctx: RunContext) -> None:
    _chapters(ctx)
    mark_done_raw(ctx, "podcast_publish")
    assert stage_outputs_present(ctx, "podcast_publish") is False
    reason = stage_artifact_incompleteness(ctx, "podcast_publish")
    assert reason is not None
    assert "package_ready" in reason
    assert seed_stage_complete(ctx, "podcast_publish") is False


def test_hpub2_package_ready_false_is_not_complete(ctx: RunContext) -> None:
    _package_ready(ctx, ready=False)
    assert stage_outputs_present(ctx, "podcast_publish") is False
    reason = stage_artifact_incompleteness(ctx, "podcast_publish")
    assert reason is not None
    assert "ready is not true" in reason


def test_hpub2_package_ready_true_is_complete(ctx: RunContext) -> None:
    _package_ready(ctx, ready=True)
    assert stage_outputs_present(ctx, "podcast_publish") is True
    assert stage_artifact_incompleteness(ctx, "podcast_publish") is None


def test_hpub2_ship_remaining_includes_cover_and_publish_without_outputs(
    ctx: RunContext,
) -> None:
    remaining = ship_after_master_remaining(ctx)
    assert "episode_cover_generate" in remaining
    assert "podcast_publish" in remaining


def test_hpub2_ship_remaining_drops_cover_and_publish_when_outputs_present(
    ctx: RunContext,
) -> None:
    _jpg(ctx)
    _package_ready(ctx, ready=True)
    remaining = ship_after_master_remaining(ctx)
    assert "episode_cover_generate" not in remaining
    assert "podcast_publish" not in remaining


def test_hpub2_hollow_cover_unmarks_and_pins(ctx: RunContext) -> None:
    mark_done_raw(ctx, "episode_cover_generate")
    cleared = unmark_hollow_delivery_producers(ctx, {"episode_cover_generate"})
    assert "episode_cover_generate" in cleared
    assert ctx.is_done("episode_cover_generate") is False
    reason = stage_artifact_incompleteness(ctx, "episode_cover_generate")
    assert reason is not None
    assert producer_pin_for_token(reason) == "episode_cover_generate"
    heal = heal_or_refuse_mark(ctx, "episode_cover_generate")
    assert heal.get("refused") is True


def test_hpub2_hollow_publish_unmarks_chapters_only(ctx: RunContext) -> None:
    _chapters(ctx)
    mark_done_raw(ctx, "podcast_publish")
    cleared = unmark_hollow_delivery_producers(ctx, {"podcast_publish"})
    assert "podcast_publish" in cleared
    assert ctx.is_done("podcast_publish") is False
    heal = heal_or_refuse_mark(ctx, "podcast_publish")
    assert heal.get("refused") is True
    assert producer_pin_for_token("package_ready") == "podcast_publish"
