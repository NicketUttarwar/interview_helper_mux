"""A required synthesize line with a WAV is seated, whatever its neighbours (ISSUES 184).

The run this guards (maintainer's exec_025, ~60 of 72): the gap report kept
vo_question_seg_027 as a required synthesize line, adjudication said air and the
WAV existed, but the EDL builder dropped it because the cloned host voice abutted
native seg_027 and the verifier said "same person". The line had no seat and no
active omit, so publishability refused the mix (omit_collateral_vo_strip /
unseated_required_vo) on every attempt until max_mix_cycles. Two paperwork bugs
made it stickier: the compensator read ``line_id`` from ledger rows keyed by
``subject_id``, and ``line_is_omitted`` was called with the line dict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.publishability_boundary import _check_unseated_required_vo
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import isolated_run_ctx

SEGMENTS = {
    "seg_026": {"segment_id": "seg_026", "speaker_id": "spk_host", "start_ms": 0, "end_ms": 4000},
    "seg_027": {"segment_id": "seg_027", "speaker_id": "spk_host", "start_ms": 4000, "end_ms": 9000},
    "seg_028": {"segment_id": "seg_028", "speaker_id": "spk_guest", "start_ms": 9000, "end_ms": 15000},
}
ORDER = ["seg_026", "seg_027", "seg_028"]
LINE_ID = "vo_question_seg_027"


def _line() -> dict:
    return {
        "line_id": LINE_ID,
        "text": "What made freelancing stop feeling like the right next step?",
        "targets_segment_id": "seg_027",
        "placement": "before",
        "delivery": "synthesize",
        "required": True,
        "voice_speaker_id": "spk_host",
    }


def _edl(tmp_path: Path, verdict: str | None) -> dict:
    wav = tmp_path / f"{LINE_ID}.wav"
    wav.write_bytes(b"x")
    return build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        gap_report={"interviewer_lines": [_line()]},
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 2500,
        verify_pair=lambda _a, _b: verdict,
    )


@pytest.mark.parametrize("verdict", ["YES", None])
def test_required_clone_adjacent_line_is_seated_and_recorded(tmp_path: Path, verdict) -> None:
    edl = _edl(tmp_path, verdict)
    seated = [c for c in edl["clips"] if c.get("type") == "vo_pickup"]
    assert [c.get("line_id") for c in seated] == [LINE_ID]
    assert seated[0]["targets_segment_id"] == "seg_027"
    assert edl["warnings"]["clone_adjacency_advisory"] == [LINE_ID]
    assert "suppressed_clone_adjacency" not in edl["warnings"]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "required_vo_seat")


def _put_ledger(ctx, entries: list[dict]) -> None:
    dest = ctx.final_path("understanding", "omit_ledger.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")


def test_the_seated_edl_passes_publishability(ctx, tmp_path: Path) -> None:
    edl = _edl(tmp_path, "YES")
    assert _check_unseated_required_vo(ctx, edl, {"interviewer_lines": [_line()]}) == []


def test_an_unseated_required_line_is_still_caught(ctx) -> None:
    edl = {"clips": [], "warnings": {}}
    out = _check_unseated_required_vo(ctx, edl, {"interviewer_lines": [_line()]})
    assert [v.code for v in out] == ["unseated_required_vo"]
    assert out[0].line_id == LINE_ID


def test_an_active_ledger_omit_keyed_by_subject_id_compensates(ctx) -> None:
    _put_ledger(
        ctx,
        [{"kind": "layup_skip", "subject_id": LINE_ID, "active": True, "decision": "omit"}],
    )
    edl = {"clips": [], "warnings": {}}
    assert _check_unseated_required_vo(ctx, edl, {"interviewer_lines": [_line()]}) == []


def test_an_inactive_ledger_omit_does_not_compensate(ctx) -> None:
    _put_ledger(
        ctx,
        [{"kind": "layup_skip", "subject_id": LINE_ID, "active": False, "decision": "omit"}],
    )
    edl = {"clips": [], "warnings": {}}
    out = _check_unseated_required_vo(ctx, edl, {"interviewer_lines": [_line()]})
    assert [v.code for v in out] == ["unseated_required_vo"]


def test_the_heal_route_re_speaks_instead_of_rebuilding_the_same_edl() -> None:
    from interview_mux.heal_routing import PLAYBOOK_REGISTRY

    spec = PLAYBOOK_REGISTRY["omit_collateral_vo_strip"]
    assert spec.resume_stage == "vo_synthesize"
    assert spec.action != "exempt_rebuild_edl"
