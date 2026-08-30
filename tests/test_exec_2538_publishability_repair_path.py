"""exec_2538 publishability repair path — fixture-backed integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.media_ip_cta import (
    ARTIFACT_REL,
    clamp_edl_speech_away_from_never_touch,
    heal_nle_unplayable_keep_overrides,
)
from interview_mux.omit_ledger import (
    empty_omit_ledger,
    mint_entry,
    reconcile_edl_with_omit_ledger,
    write_omit_ledger,
)
from interview_mux.publishability_boundary import (
    PublishabilityBlocked,
    commit_or_block,
    validate_publishability,
    violation_playbook,
    write_publishability_repair_plan,
)
from run_fixtures import isolated_run_ctx, write_fixture_vo_wav

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "exec_2538"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _seed_exec_2538_geometry(ctx) -> None:
    ctx.write_json("run_meta.json", {"homunculus_version": "0.1.0"})
    ctx.write_json("master/selection.json", _load("selection.json"), skip_handoff=True)
    ctx.write_json("segments/manifest.json", _load("manifest.json"), skip_handoff=True)
    ctx.write_json("segments/nle_edits.json", _load("nle_edits.json"), skip_handoff=True)
    ctx.write_json(ARTIFACT_REL, _load("media_ip_cta.json"), skip_handoff=True)


def _seed_exec_2538_vo(ctx) -> None:
    orientation = _load("gap_report_orientation_line.json")
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [orientation]},
        skip_handoff=True,
    )
    ctx.write_json("master/edl.json", _load("edl.json"), skip_handoff=True)
    write_fixture_vo_wav(
        ctx.final_path(
            "vo_pickup",
            "synthesized",
            "vo_preface_episode_orientation.wav",
        )
    )
    write_fixture_vo_wav(
        ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_003a.wav")
    )


def test_non_cta_keep_gets_punch_path_not_zero_ms(tmp_path: Path) -> None:
    from interview_mux.media_ip_cta import never_touch_source_intervals

    ctx = isolated_run_ctx(tmp_path, "exec_2538_punch")
    _seed_exec_2538_geometry(ctx)

    restored = heal_nle_unplayable_keep_overrides(ctx)
    assert "seg_003a" in restored

    intervals = never_touch_source_intervals(ctx)
    assert any(b == 83020 for a, b, _ in intervals)
    assert any(a == 87160 for a, b, _ in intervals)
    assert all(not (a < 83020 and b > 87160) for a, b, _ in intervals)

    edl = {
        "ordered_segment_ids": ["seg_003a", "seg_004"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_003a",
                "source_start_ms": 83020,
                "source_end_ms": 87160,
                "timeline_start_ms": 0,
                "duration_ms": 87160 - 83020,
            },
            {
                "type": "speech",
                "segment_id": "seg_004",
                "source_start_ms": 121660,
                "source_end_ms": 130000,
                "timeline_start_ms": 87160 - 83020,
                "duration_ms": 130000 - 121660,
            },
        ],
    }
    fixed, rows = clamp_edl_speech_away_from_never_touch(ctx, edl)
    clip_a = next(c for c in fixed["clips"] if c.get("segment_id") == "seg_003a")
    assert int(clip_a["source_start_ms"]) == 83020
    assert int(clip_a["source_end_ms"]) == 87160
    assert int(clip_a["duration_ms"]) == 87160 - 83020
    assert int(clip_a["duration_ms"]) >= 400
    assert "seg_003a" in [c.get("segment_id") for c in fixed["clips"]]
    assert not any("never_touch_unplayable" in (r.get("notes") or []) for r in rows)


def test_orientation_vo_not_stripped_by_omit_layup(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_2538_orientation")
    _seed_exec_2538_vo(ctx)
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_003a",
            target_segment_id="seg_003a",
            decision="omit",
            reason_code="spoken_copy_unhealable",
            owner_stage="nugget_layup_compose",
            compensating_path="omit_unsafe_spoken_copy",
            seq=1,
        )
    ]
    ledger["summary"] = {
        "active_count": 1,
        "by_kind": {"layup_skip": 1},
        "compensated_count": 1,
        "unresolved_high_salience": 0,
    }
    write_omit_ledger(ctx, ledger)

    report = reconcile_edl_with_omit_ledger(ctx)
    assert report["updated"] is True
    assert "vo_layup_seg_003a" in report["removed"]
    assert "vo_preface_episode_orientation" not in report["removed"]

    edl = ctx.read_json("master/edl.json")
    vo_ids = [c.get("line_id") for c in edl["clips"] if c.get("type") == "vo_pickup"]
    assert vo_ids == ["vo_preface_episode_orientation"]
    placements = [p.get("line_id") for p in edl.get("gap_placements") or []]
    assert placements == ["vo_preface_episode_orientation"]


def test_publishability_boundary_catches_violations_post_edl(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_2538_boundary")
    _seed_exec_2538_geometry(ctx)
    _seed_exec_2538_vo(ctx)

    report = validate_publishability(ctx, checkpoint="post_edl")
    assert not report.ok
    classes = {v.error_class for v in report.violations}
    assert "never_touch_zeroed_keep" in classes
    assert "opening_orientation_inaudible" in classes

    playbook = violation_playbook(report.violations[0])
    assert playbook.resume_stage == "edl"
    write_publishability_repair_plan(ctx, report, playbook=playbook)
    assert ctx.artifact_exists("operator/publishability_repair_plan.json")
    plan = ctx.read_json("operator/publishability_repair_plan.json")
    assert plan.get("from_stage") == "edl"
    assert "mix" in (plan.get("invalidate_set") or [])

    with pytest.raises(PublishabilityBlocked) as excinfo:
        commit_or_block(ctx, report, enforce=True)
    assert excinfo.value.error_class == "never_touch_zeroed_keep"
