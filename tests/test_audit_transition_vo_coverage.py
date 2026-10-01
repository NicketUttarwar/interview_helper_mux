"""The narrative audit sees heard-WAV evidence for spoken transitions (ISSUES 120)."""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    c = isolated_run_ctx(tmp_path, "audit_tr_cov")
    c.write_json("master/selection.json", {"ordered_segment_ids": ["seg_007", "seg_005", "seg_004", "seg_008"]}, skip_handoff=True)
    tr = c.final_path("master", "transitions.json")
    tr.parent.mkdir(parents=True, exist_ok=True)
    tr.write_text(
        json.dumps(
            {
                "transitions": [
                    {"after_segment_id": "seg_007", "before_segment_id": "seg_005", "spoken_text": "And then."},
                    {"after_segment_id": "seg_004", "before_segment_id": "seg_008", "spoken_text": "Next."},
                ]
            }
        ),
        encoding="utf-8",
    )
    gp = c.final_path("understanding", "gap_report.json")
    gp.parent.mkdir(parents=True, exist_ok=True)
    gp.write_text(json.dumps({"interviewer_lines": []}), encoding="utf-8")
    return c


def _wav(path: Path, seconds: float = 0.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<" + "h" * int(16000 * seconds), *([0] * int(16000 * seconds))))


def test_coverage_rows_name_each_transition_and_its_heard_status(ctx) -> None:
    from interview_mux.stages.edl_narrative_audit import compact_vo_coverage

    _wav(ctx.final_path("master", "transitions", "tr_seg_007_seg_005.wav"))
    rows = compact_vo_coverage(ctx)
    by_id = {r["line_id"]: r for r in rows}
    assert by_id["tr_seg_007_seg_005"]["coverage"] == "rendered"
    assert by_id["tr_seg_004_seg_008"]["coverage"] == "missing"
    assert all(r.get("kind") == "transition" for r in rows)


def test_cited_pairs_with_playable_wavs_demote_the_placement_issue(ctx) -> None:
    from interview_mux.artifact_repairs import _edl_issue_premature_vo_nle_placement

    _wav(ctx.final_path("master", "transitions", "tr_seg_007_seg_005.wav"))
    _wav(ctx.final_path("master", "transitions", "tr_seg_004_seg_008.wav"))
    row = {
        "code": "pre_edl_vo_placement_missing",
        "issue": (
            "Heard-WAV audit cannot verify either occupied spoken transition because "
            "vo_coverage is empty despite seam_occupancy assigning transition occupants "
            "at seg_007 → seg_005 and seg_004 → seg_008."
        ),
    }
    assert _edl_issue_premature_vo_nle_placement(ctx, row) is True


def test_a_cited_pair_without_a_wav_is_not_demoted(ctx) -> None:
    from interview_mux.artifact_repairs import _edl_issue_premature_vo_nle_placement

    _wav(ctx.final_path("master", "transitions", "tr_seg_007_seg_005.wav"))
    row = {
        "code": "pre_edl_vo_placement_missing",
        "issue": "no evidence at seg_007 → seg_005 and seg_004 → seg_008.",
    }
    assert _edl_issue_premature_vo_nle_placement(ctx, row) is False
