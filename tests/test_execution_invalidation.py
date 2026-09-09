from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    check_write_approval_before_execute,
    enter_stage_staging,
    exit_stage_staging,
)
from run_fixtures import patch_write_approval_enabled, mark_done_raw


def _minimal_edl() -> dict:
    return {
        "version": 1,
        "ordered_segment_ids": ["seg_001"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_001",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "duration_ms": 1000,
                "timeline_start_ms": 0,
            }
        ],
        "timeline_duration_ms": 1000,
    }


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    (root / "ASSETS" / "executions").mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {
                "require_write_approval_per_stage": True,
                "first_try_mode": False,
                "defer_write_approval_until": "off",
            },
        },
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {
            "journey_ui": {
                "require_write_approval_per_stage": True,
                "first_try_mode": False,
                "defer_write_approval_until": "off",
            }
        },
    )
    monkeypatch.setattr("interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: False)
    monkeypatch.setattr("interview_mux.first_try.write_approval_deferred", lambda cfg=None: False)
    patch_write_approval_enabled(monkeypatch, enabled=True)
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_clear_from_archives_and_clears_pending_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    checksums = ctx.path("ingest/checksums.json")
    checksums.parent.mkdir(parents=True, exist_ok=True)
    checksums.write_text(
        json.dumps(
            {
                "source_path": "fixture.wav",
                "source_sha256": "a" * 64,
                "normalized_sha256": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    mark_done_raw(ctx, "ingest")
    # Sole-owned delivery-side path (coverage_audit) — boundaries.json is
    # shared with upstream ideal_cuts_materialize and is intentionally preserved.
    coverage = ctx.final_path("master/coverage_audit.json")
    coverage.parent.mkdir(parents=True, exist_ok=True)
    coverage.write_text(
        json.dumps(
            {
                "topics": [],
                "topic_mappings": [],
                "coverage_score": 1.0,
            }
        ),
        encoding="utf-8",
    )
    mark_done_raw(ctx, "topic_coverage_audit")
    enter_stage_staging("narrative_arc_plan")
    plan = ctx.path("master/narrative_plan.json")
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    assert check_write_approval_before_execute(ctx) is not None

    from interview_mux.pipeline import DELIVERY_ORDER

    ctx.clear_from("topic_coverage_audit", DELIVERY_ORDER)

    assert not ctx.final_path("master/coverage_audit.json").is_file()
    assert check_write_approval_before_execute(ctx) is None
    assert list(ctx.run_dir.glob(".archived/*"))


def test_discard_on_invalidate_unblocks_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/checksums.json")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    assert check_write_approval_before_execute(ctx) is not None
    ctx.clear_from("ingest", ANALYSIS_ORDER)
    assert check_write_approval_before_execute(ctx) is None


def test_clear_from_delivery_preserves_analysis_sound_design_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.pipeline import DELIVERY_ORDER

    ctx = _ctx(tmp_path, monkeypatch)
    sdp = ctx.final_path("understanding/sound_design_plan.json")
    sdp.parent.mkdir(parents=True, exist_ok=True)
    seeded = {
        "version": 1,
        "coherence": {"sonic_identity": "test identity", "primary_mood": "", "density": ""},
        "palettes": [{"palette_id": "p1", "name": "Warm"}],
        "assets": [],
        "flow_plans": {"podcast": {"profile": "podcast", "cues": []}},
        "generated": {},
        "_meta": {"producer_stage": "sound_design_palettes", "stale": False},
    }
    sdp.write_text(json.dumps(seeded), encoding="utf-8")
    # Analysis done marker — bypass hollow completeness for shared SDP path.
    done = ctx.final_path(".stage_done", "sound_design_palettes")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("done\n", encoding="utf-8")
    coverage = ctx.final_path("master/coverage_audit.json")
    coverage.parent.mkdir(parents=True, exist_ok=True)
    coverage.write_text(
        json.dumps({"topics": [], "topic_mappings": [], "coverage_score": 1.0}),
        encoding="utf-8",
    )
    mark_done_raw(ctx, "topic_coverage_audit")

    ctx.clear_from("topic_coverage_audit", DELIVERY_ORDER)

    # Analysis stage marker must survive; delivery co-owner may archive+reseed SDP.
    assert ctx.is_done("sound_design_palettes")
    archived = list(ctx.run_dir.glob(".archived/*/understanding/sound_design_plan.json"))
    if archived:
        doc = json.loads(archived[0].read_text(encoding="utf-8"))
        assert doc.get("palettes")
    elif sdp.is_file():
        doc = json.loads(sdp.read_text(encoding="utf-8"))
        assert doc.get("palettes") or (doc.get("_meta") or {}).get("producer_stage") == (
            "sound_design_palettes"
        )


def test_clear_from_mix_preserves_upstream_edl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """junction_snip_qa must not cause mix invalidation to archive master/edl.json."""
    from interview_mux.pipeline import DELIVERY_ORDER

    ctx = _ctx(tmp_path, monkeypatch)
    edl = ctx.final_path("master/edl.json")
    edl.parent.mkdir(parents=True, exist_ok=True)
    edl.write_text(json.dumps(_minimal_edl()), encoding="utf-8")
    mark_done_raw(ctx, "edl")
    assert ctx.is_done("edl"), "schema-valid EDL must accept mark_done_raw"
    assembly = ctx.final_path("master/assembly.wav")
    assembly.parent.mkdir(parents=True, exist_ok=True)
    assembly.write_bytes(b"RIFF" + b"\x00" * 64)
    mark_done_raw(ctx, "mix")
    snip = ctx.final_path("master/junction_snip_qa.json")
    snip.parent.mkdir(parents=True, exist_ok=True)
    snip.write_text("{}", encoding="utf-8")
    mark_done_raw(ctx, "junction_snip_qa")

    ctx.clear_from("mix", DELIVERY_ORDER)

    assert edl.is_file(), "EDL must survive clear_from(mix)"
    assert ctx.is_done("edl")
    assert not assembly.is_file()
    assert not snip.is_file()
    assert not ctx.is_done("mix")
    assert not ctx.is_done("junction_snip_qa")


def test_clear_from_stamps_stale_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.pipeline import DELIVERY_ORDER

    ctx = _ctx(tmp_path, monkeypatch)
    # Stamp applies to transitive downstream artifacts (not the from_stage itself).
    plan = ctx.final_path("master/narrative_plan.json")
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        json.dumps(
            {
                "acts": [],
                "_meta": {"stale": False, "content_hash": "abc", "producer_stage": "narrative_arc_plan"},
            }
        ),
        encoding="utf-8",
    )
    mark_done_raw(ctx, "narrative_arc_plan")
    ctx.clear_from("topic_coverage_audit", DELIVERY_ORDER)
    if plan.is_file():
        doc = json.loads(plan.read_text(encoding="utf-8"))
        assert (doc.get("_meta") or {}).get("stale") is True
    else:
        # Archived instead of stamped is also valid invalidation.
        assert list(ctx.run_dir.glob(".archived/*/master/narrative_plan.json"))


def test_clear_from_ideal_cuts_keeps_upstream_content_brief(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    ctx = _ctx(tmp_path, monkeypatch)
    brief = ctx.final_path("understanding/content_brief.json")
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(
        json.dumps(
            {
                "thesis": "Precision oncology from circulating tumour cells.",
                "topics": [{"name": "liquid biopsy", "summary": "blood draw diagnostics"}],
                "_meta": {"producer_stage": "content_context", "stale": False},
            }
        ),
        encoding="utf-8",
    )
    mark_done_raw(ctx, "content_context")
    ctx.final_path(".stage_done", "content_context").unlink()
    ctx.clear_from("ideal_cuts_propose", ANALYSIS_ORDER)
    assert brief.is_file()
    doc = json.loads(brief.read_text(encoding="utf-8"))
    assert not (doc.get("_meta") or {}).get("stale")
