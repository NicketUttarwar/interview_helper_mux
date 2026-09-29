"""EDL QC does not fail a locked volley the selection itself splits (ISSUES 50)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.edl_narrative_qc import _validate_speaker_volley_integrity
from interview_mux.run_context import RunContext

VOLLEY = {
    "speaker_volley_id": "sv_seg_001_seg_007",
    "segment_ids": ["seg_001", "seg_004", "seg_005", "seg_006", "seg_007"],
    "kind": "speaker_turn",
    "locked": True,
}


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sel_order: list[str]) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_volley_qc", create=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": sel_order})
    monkeypatch.setattr(
        "interview_mux.episode_structure.load_episode_structure",
        lambda c: {"speaker_volleys": [VOLLEY]},
    )
    return ctx


def test_violation_inherited_from_selection_is_a_warning(tmp_path, monkeypatch) -> None:
    # exec_049: ranking moved seg_006 ahead of seg_004; the EDL follows it.
    order = ["seg_001", "seg_006", "seg_004", "seg_005"]
    ctx = _ctx(tmp_path, monkeypatch, order)
    errors: list[str] = []
    _validate_speaker_volley_integrity(ctx, list(order), errors)
    assert errors == []


def test_violation_the_edl_introduced_still_fails(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, ["seg_001", "seg_004", "seg_005", "seg_006"])
    errors: list[str] = []
    _validate_speaker_volley_integrity(ctx, ["seg_001", "seg_006", "seg_004", "seg_005"], errors)
    assert errors == ["speaker_volley_integrity:speaker_volley_split:sv_seg_001_seg_007"]


def test_intact_volley_passes(tmp_path, monkeypatch) -> None:
    order = ["seg_001", "seg_004", "seg_005", "seg_006", "seg_007"]
    ctx = _ctx(tmp_path, monkeypatch, order)
    errors: list[str] = []
    _validate_speaker_volley_integrity(ctx, list(order), errors)
    assert errors == []
