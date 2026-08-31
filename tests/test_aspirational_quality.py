"""Aspirational quality policy — candidate registry and pick-best."""

from __future__ import annotations

import json

from interview_mux.aspirational_quality import (
    apply_best_quality_candidate,
    register_quality_candidate,
    select_best_quality_candidate,
)
from run_fixtures import isolated_run_ctx


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_register_and_pick_best_candidate(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_aspirational_pick")
    master = ctx.path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)

    master.write_bytes(b"RIFF_low_score_master_bytes")
    _write_raw(
        ctx,
        "mastering/listen_delight_audit.json",
        {
            "overall": 0.72,
            "dimensions": {
                "cut_integrity": 0.88,
                "nugget_retention": 0.80,
                "conversation_fit": 0.70,
                "story_followability": 0.68,
            },
        },
    )
    low = register_quality_candidate(ctx, family="listen_delight", label="attempt_low")

    master.write_bytes(b"RIFF_high_score_master_bytes")
    _write_raw(
        ctx,
        "mastering/listen_delight_audit.json",
        {
            "overall": 0.81,
            "dimensions": {
                "cut_integrity": 0.90,
                "nugget_retention": 0.85,
                "conversation_fit": 0.78,
                "story_followability": 0.80,
            },
        },
    )
    high = register_quality_candidate(ctx, family="listen_delight", label="attempt_high")

    best = select_best_quality_candidate(ctx, family="listen_delight")
    assert best is not None
    assert best.get("attempt_id") == high.get("attempt_id")
    assert float(best.get("rank_score") or 0) > float(low.get("rank_score") or 0)

    master.write_bytes(b"RIFF_stale_current_master")
    applied = apply_best_quality_candidate(ctx, family="listen_delight")
    assert applied.get("ok")
    assert master.read_bytes().startswith(b"RIFF_high_score")
