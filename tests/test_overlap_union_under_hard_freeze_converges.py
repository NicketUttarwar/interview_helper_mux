"""exec_009 in miniature: an overlap union under hard freeze leaves nothing stale (ISSUES 113).

Two neighbouring segments overlap in source; the repair absorbs one into the
other and retires it from the selection. The lay-up plan and the sound design
plan both referenced the retired id. Afterwards the EDL loader's freshness
check must pass, the cue must sit on a live segment, and the run log must
carry no ownership denial and no frozen-seat skip for these documents.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.nugget_layup import PLAN_REL, assert_layup_fresh_vs_selection, layup_freshness_errors
from run_fixtures import (
    isolated_run_ctx,
    minimal_gap_report,
    minimal_manifest,
    minimal_manifest_segment,
    plant_seed_complete_through,
    write_fixture_json,
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "overlap_hard_freeze")


def _seed_overlap(ctx) -> None:
    plant_seed_complete_through(ctx, "vo_synthesize")
    write_fixture_json(
        ctx,
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_003c", start_ms=62_900, end_ms=74_760, speaker_id="spk_0"),
            minimal_manifest_segment("seg_003d", start_ms=71_000, end_ms=74_810, speaker_id="spk_0"),
            minimal_manifest_segment("seg_004", start_ms=80_000, end_ms=90_000, speaker_id="spk_1"),
        ),
    )
    write_fixture_json(ctx, "understanding/gap_report.json", minimal_gap_report())
    write_fixture_json(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_003c", "seg_003d", "seg_004"], "order_lock": {"revision": 2}},
    )
    sel = ctx.read_json("master/selection.json")
    write_fixture_json(
        ctx,
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_003c", "seg_003d", "seg_004"],
            "layups": [
                {"target_segment_id": sid, "line_id": f"vo_layup_{sid}"}
                for sid in ("seg_003c", "seg_003d", "seg_004")
            ],
            "order_lock": dict(sel.get("order_lock") or {}),
            "_meta": {"producer_stage": "nugget_layup_compose"},
        },
    )
    write_fixture_json(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_003c", "seg_003d", "seg_004"],
            "timeline_duration_ms": 25_670,
            "clips": [
                {"type": "speech", "segment_id": "seg_003c", "source_start_ms": 62_900, "source_end_ms": 74_760, "timeline_start_ms": 0, "duration_ms": 11_860},
                {"type": "speech", "segment_id": "seg_003d", "source_start_ms": 71_000, "source_end_ms": 74_810, "timeline_start_ms": 11_860, "duration_ms": 3_810},
                {"type": "speech", "segment_id": "seg_004", "source_start_ms": 80_000, "source_end_ms": 90_000, "timeline_start_ms": 15_670, "duration_ms": 10_000},
            ],
        },
    )
    write_fixture_json(
        ctx,
        "segments/nle_edits.json",
        {"segment_overrides": {}, "sequence_order": ["seg_003c", "seg_003d", "seg_004"]},
    )


def _log_lines(ctx) -> list[str]:
    log = ctx.final_path("gui_log.jsonl")
    if not log.is_file():
        return []
    return log.read_text(encoding="utf-8", errors="replace").splitlines()


def test_overlap_union_under_hard_freeze_leaves_no_stale_dependent(ctx, monkeypatch) -> None:
    from interview_mux import selection_dependents as deps
    from interview_mux.edl_overlap_repair import repair_overlapping_source_ranges

    _seed_overlap(ctx)
    monkeypatch.setattr("interview_mux.seat_authority.hard_freeze_active", lambda c: True)
    monkeypatch.setattr("interview_mux.seat_authority.soft_freeze_active", lambda c: False)
    # The sound design plan is validated on write; stand in for its persist and
    # keep the reconciled document so the anchor rule is checked end to end.
    sdp_writes: list[dict] = []
    monkeypatch.setattr(
        "interview_mux.seat_authority.persist_frozen_seat_doc",
        lambda c, rel, doc, *, reason="", **kw: sdp_writes.append({"rel": rel, "doc": doc, "reason": reason, "kw": kw}) or True,
    )
    sdp = ctx.final_path("understanding", "sound_design_plan.json")
    sdp.parent.mkdir(parents=True, exist_ok=True)
    sdp.write_text(
        json.dumps(
            {
                "_meta": {"producer_stage": "music_palette_compose"},
                "flow_plans": {"podcast": {"cues": [{"cue_id": "c1", "before_segment_id": "seg_003d"}]}},
            }
        ),
        encoding="utf-8",
    )

    result = repair_overlapping_source_ranges(ctx)
    assert result.get("repaired"), result

    sel = ctx.read_json("master/selection.json")
    assert sel["ordered_segment_ids"] == ["seg_003c", "seg_004"]
    # The lay-up plan followed the selection: ids and lock, no retired id.
    assert layup_freshness_errors(ctx) == []
    assert_layup_fresh_vs_selection(ctx, stage="edl")
    plan = ctx.read_json(PLAN_REL)
    assert "seg_003d" not in plan["ordered_segment_ids"]
    # The cue moved off the retired id onto the live neighbour, under the owner.
    assert sdp_writes and sdp_writes[-1]["reason"] == deps.END_A_REASON
    cue = sdp_writes[-1]["doc"]["flow_plans"]["podcast"]["cues"][0]
    assert cue["before_segment_id"] == "seg_004"
    assert sdp_writes[-1]["kw"]["stage_key"] == "music_palette_compose"
    # Nothing was refused on the way.
    lines = _log_lines(ctx)
    assert not [l for l in lines if "authority_denied" in l], [l[:200] for l in lines if "authority_denied" in l]
    assert not [l for l in lines if "seat_freeze: skip write" in l], [l[:200] for l in lines if "skip write" in l]
