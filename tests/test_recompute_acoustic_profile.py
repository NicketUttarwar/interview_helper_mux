"""GC-Q4 — recompute acoustic profile invalidates downstream sound design on pace change."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from interview_mux.session_log import read_log
from interview_mux.web.server import create_app
from run_fixtures import (
    init_run_meta_for_test,
    isolated_run_ctx,
    log_detail_matches,
    mark_done_raw,
    minimal_source_acoustic_profile,
    parse_log_detail,
    patch_server_ctx,
)

def _write_profile(ctx, *, pace_class: str) -> None:
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        minimal_source_acoustic_profile(
            pacing={
                "pace_class": pace_class,
                "global_wpm": 120,
                "wpm_by_quartile": [110, 115, 120, 125],
            },
            mix_contract={"underscore_policy": "normal"},
        ),
    )

def _mock_recompute_to_pace(monkeypatch, new_pace: str) -> None:
    from interview_mux.stages import understanding

    def _run(ctx) -> None:
        profile = minimal_source_acoustic_profile(
            pacing={
                "pace_class": new_pace,
                "global_wpm": 120,
                "wpm_by_quartile": [110, 115, 120, 125],
            },
        )
        ctx.write_json("understanding/source_acoustic_profile.json", profile)
        ctx.mark_done("source_acoustic_profile")

    monkeypatch.setattr(understanding, "run_source_acoustic_profile", _run)

def test_recompute_invalidates_sound_design_on_pace_change(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_recompute_pace")
    init_run_meta_for_test(ctx)
    _write_profile(ctx, pace_class="calm")
    mark_done_raw(ctx, "sound_design_palettes")
    mark_done_raw(ctx, "missing_framing")
    mark_done_raw(ctx, "sound_design_plan")
    mark_done_raw(ctx, "sfx_prompt_craft")

    _mock_recompute_to_pace(monkeypatch, "dense")
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    res = client.post(f"/api/runs/{ctx.run_id}/recompute-acoustic-profile")
    assert res.status_code == 200
    body = res.json()
    assert body["prior_pace"] == "calm"
    assert body["new_pace"] == "dense"
    assert body["invalidated_from"] == "sound_design_palettes"

    assert not ctx.is_done("sound_design_palettes")
    assert not ctx.is_done("missing_framing")
    assert not ctx.is_done("sound_design_plan")
    assert not ctx.is_done("sfx_prompt_craft")

    invalidation_logs = [
        e
        for e in read_log(ctx.run_dir)
        if log_detail_matches(e, "acoustic_profile_invalidation:")
    ]
    assert len(invalidation_logs) == 1
    envelope = parse_log_detail(invalidation_logs[0])
    text = str(envelope.get("detail", ""))
    cleared = json.loads(text.split("acoustic_profile_invalidation:", 1)[1].strip())
    assert "sound_design_palettes" in cleared
    assert "missing_framing" in cleared
    assert "sound_design_plan" in cleared
    assert "sfx_prompt_craft" in cleared

def test_recompute_skips_invalidation_when_pace_unchanged(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_recompute_same")
    init_run_meta_for_test(ctx)
    _write_profile(ctx, pace_class="conversational")
    mark_done_raw(ctx, "sound_design_palettes")

    _mock_recompute_to_pace(monkeypatch, "conversational")
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    res = client.post(f"/api/runs/{ctx.run_id}/recompute-acoustic-profile")
    assert res.status_code == 200
    body = res.json()
    assert body["prior_pace"] == "conversational"
    assert body["new_pace"] == "conversational"
    assert "invalidated_from" not in body
    assert ctx.is_done("sound_design_palettes")

    assert not any(
        log_detail_matches(e, "acoustic_profile_invalidation:")
        for e in read_log(ctx.run_dir)
    )
