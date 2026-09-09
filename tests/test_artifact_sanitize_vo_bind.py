"""Tests for artifact_sanitize VO bind / synthesis_report (W5)."""

from __future__ import annotations

import json

from interview_mux.artifact_sanitize.vo_synthesize import sanitize_synthesis_report
from interview_mux.run_context import RunContext


def test_synthesis_report_drops_stale_missing_wav() -> None:
    ctx = RunContext(create=True)
    ctx.path("vo_pickup").mkdir(parents=True, exist_ok=True)
    doc = {
        "entries": [
            {
                "line_id": "vo_ok",
                "out_wav": "vo_pickup/vo_ok.wav",
                "wav_sha256": "abc123",
            },
            {
                "line_id": "vo_ghost",
                "out_wav": "vo_pickup/missing_ghost.wav",
                "wav_sha256": "deadbeef",
            },
            {
                "line_id": "vo_nosha",
                "out_wav": "vo_pickup/nosha.wav",
            },
        ]
    }
    # Create only vo_ok wav so ghost path is missing
    (ctx.path("vo_pickup") / "vo_ok.wav").write_bytes(b"RIFF....WAVEfmt ")
    result = sanitize_synthesis_report(ctx, doc)
    lids = [r.get("line_id") for r in result.doc.get("entries") or []]
    assert "vo_ok" in lids
    assert "vo_ghost" not in lids
    assert "vo_nosha" not in lids
    assert any(a.get("action") == "drop_missing_wav" for a in result.actions)
    assert any(a.get("action") == "drop_missing_wav_sha" for a in result.actions)


def test_sanitize_refuses_forge_seated_stale(monkeypatch) -> None:
    ctx = RunContext(create=True)
    ctx.path("mastering").mkdir(parents=True, exist_ok=True)
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    # Bypass schema validation for minimal fixture
    plan_path = ctx.path("mastering", "mastering_plan.json")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(
            {
                "air_script": {
                    "vo_seats": {
                        "seated_line_ids": ["vo_seated"],
                        "omitted_line_ids": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    gap_path = ctx.path("understanding", "gap_report.json")
    gap_path.parent.mkdir(parents=True, exist_ok=True)
    gap_path.write_text(
        json.dumps(
            {
                "interviewer_lines": [
                    {
                        "line_id": "vo_seated",
                        "text": "spoken",
                        "targets_segment_id": "seg_001",
                        "gap_type": "clarify",
                        "placement": "before",
                        "delivery": "synthesize",
                        "required": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "interview_mux.stage_input_checks.compact_vo_coverage_stale_or_missing",
        lambda _ctx: ["vo_seated"],
    )
    result = sanitize_synthesis_report(ctx, {"entries": []})
    assert not result.ok
    assert any("seated_bind_stale:vo_seated" in e for e in result.errors)
    # Must not invent a forged bind entry
    assert not (result.doc.get("entries") or [])
