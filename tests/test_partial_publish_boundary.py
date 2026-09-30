"""Partial mode never packages before the operator's sign-off (ISSUES 98)."""

from __future__ import annotations

import pytest
from run_fixtures import isolated_run_ctx

from interview_mux.pipeline import stages_within_until
from interview_mux.stages.podcast_publish import (
    PARTIAL_SIGNOFF_PENDING,
    require_partial_signoff_before_publish,
)

ORDER = ["mix", "master_finalize", "episode_meta_build", "episode_cover_generate", "podcast_publish"]


def test_ship_walk_stops_at_the_boundary() -> None:
    left = ["episode_meta_build", "episode_cover_generate", "podcast_publish"]
    assert stages_within_until(left, ORDER, "episode_cover_generate") == [
        "episode_meta_build",
        "episode_cover_generate",
    ]
    assert stages_within_until(left, ORDER, None) == left
    assert stages_within_until(left, ORDER, "not_a_stage") == left


def test_partial_publish_halts_until_signed_off(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_partial_publish_guard")
    ctx.mutate_run_meta(lambda m: m.update({"run_mode": "partially-accelerated"}))
    with pytest.raises(SystemExit, match="G-Publish sign-off pending"):
        require_partial_signoff_before_publish(ctx)
    assert ctx.read_json("run_meta.json").get("g_publish_pending") is True
    ctx.mutate_run_meta(lambda m: m.__setitem__("g_publish_cleared", True))
    require_partial_signoff_before_publish(ctx)  # no raise


def test_full_auto_and_manual_are_untouched(tmp_path) -> None:
    for mode in ("full-auto", "manual"):
        ctx = isolated_run_ctx(tmp_path, f"exec_publish_guard_{mode}")
        ctx.mutate_run_meta(lambda m: m.update({"run_mode": mode}))
        require_partial_signoff_before_publish(ctx)
    assert "sign-off" in PARTIAL_SIGNOFF_PENDING
