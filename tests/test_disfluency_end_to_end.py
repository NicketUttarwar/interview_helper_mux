from __future__ import annotations

from pathlib import Path

from interview_mux.disfluency.extract import confirmed_events
from interview_mux.disfluency.restore import build_restore_plan
from interview_mux.prompt_validation import validate_edl_flow1
from interview_mux.stages.assembly_flow1 import build_flow1_edl
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_restore_plan_and_edl_schema_with_disfluency() -> None:
    segments = {"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 10_000}}
    disfluencies = {
        "events": [
            {
                "event_id": "fill_0001",
                "start_ms": 4000,
                "end_ms": 4300,
                "clip_path": "transcript/disfluency_clips/fill_0001.wav",
                "text": "um",
                "review_status": "confirmed",
                "include_in_restore": True,
            }
        ]
    }
    plan = build_restore_plan(
        ordered_segment_ids=["seg_a"],
        segments_by_id=segments,
        disfluencies=disfluencies,
    )
    assert plan["confirmed_event_count"] == 1
    assert "fill_0001" in plan["segment_pieces"][0]["event_ids"]

    events = confirmed_events(disfluencies)
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id=segments,
        disfluency_events=events,
        restore_enabled=True,
    )
    assert edl["disfluency_clip_count"] >= 1
    assert validate_edl_flow1(edl) == []


def test_end_to_end_artifacts_chain(tmp_path: Path) -> None:
    """Extract catalog → restore plan → EDL metadata without full ffmpeg mix."""
    ctx = isolated_run_ctx(tmp_path, "run_e2e")
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [
                {
                    "event_id": "fill_0001",
                    "start_ms": 2000,
                    "end_ms": 2300,
                    "clip_path": "transcript/disfluency_clips/fill_0001.wav",
                    "text": "uh",
                    "review_status": "confirmed",
                    "include_in_restore": True,
                }
            ],
            "stats": {"total": 1, "confirmed": 1, "pending": 0, "rejected": 0},
        },
    )
    ctx.write_json("flow_1_master/selection.json", {"ordered_segment_ids": ["seg_a"]})
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=8000)),
    )

    from interview_mux.disfluency.config import restore_settings
    from interview_mux.disfluency.extract import load_disfluencies

    doc = load_disfluencies(ctx)
    confirmed = confirmed_events(doc)
    plan = build_restore_plan(
        ordered_segment_ids=["seg_a"],
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 8000}},
        disfluencies=doc,
        settings=restore_settings(),
    )
    ctx.write_json("flow_1_master/disfluency_restore_plan.json", plan)

    edl = build_flow1_edl(
        selection=ctx.read_json("flow_1_master/selection.json"),
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 8000}},
        disfluency_events=confirmed,
        restore_enabled=True,
    )
    ctx.write_json("flow_1_master/edl.json", edl)

    assert any(c.get("type") == "disfluency" for c in edl.get("clips") or [])
    assert ctx.artifact_exists("flow_1_master/disfluency_restore_plan.json")
