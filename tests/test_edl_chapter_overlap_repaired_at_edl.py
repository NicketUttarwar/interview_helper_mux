"""EDL QC no longer blocks on a segment two chapters claim (ISSUES 175).

Client exec_018: "The challenge of finding rare circulating tumour cells"
[seg_016, seg_015] and "From cell counts to actionable single-cell analysis"
[seg_015, seg_022, seg_018] both claimed seg_015; EDL narrative QC asked for a
full_master_ranking redo, which cannot run under the hard freeze, and edl hit
the invoke cap.
"""

from __future__ import annotations

import inspect

from interview_mux.artifact_repairs import relabel_chapters_contiguous, repair_edl_narrative_selection
from interview_mux.edl_narrative_qc import _validate_chapter_continuity

ORDER = ["seg_013", "seg_016", "seg_015", "seg_022", "seg_018", "seg_024"]


def _selection() -> dict:
    return {
        "ordered_segment_ids": list(ORDER),
        "chapters": [
            {"chapter_id": "ch_00", "title": "Opening", "segment_ids": ["seg_013"]},
            {"chapter_id": "ch_01", "title": "The challenge of finding rare circulating tumour cells", "segment_ids": ["seg_016", "seg_015"]},
            {"chapter_id": "ch_02", "title": "From cell counts to actionable single-cell analysis", "segment_ids": ["seg_015", "seg_022", "seg_018"]},
            {"chapter_id": "ch_03", "title": "Close", "segment_ids": ["seg_024"]},
        ],
    }


def test_client_overlap_fails_qc_before_and_passes_after_relabel() -> None:
    sel = _selection()
    errors: list[str] = []
    _validate_chapter_continuity(sel, ORDER, errors)
    assert any("overlap" in e for e in errors)
    fixed, changed = relabel_chapters_contiguous(sel)
    assert changed
    members = [c["segment_ids"] for c in fixed["chapters"]]
    assert members == [["seg_013"], ["seg_016", "seg_015"], ["seg_022", "seg_018"], ["seg_024"]]
    errors = []
    _validate_chapter_continuity(fixed, ORDER, errors)
    assert errors == []


def test_edl_gate_repair_applies_the_relabel() -> None:
    src = inspect.getsource(repair_edl_narrative_selection)
    assert "relabel_chapters_contiguous(sel)" in src


# --- EDL dead-end sweep (ISSUES 175) ---

import json
from pathlib import Path

import pytest

from interview_mux import edl_narrative_qc as qc


def test_chapter_member_the_edl_omitted_as_unplayable_is_not_missing() -> None:
    sel = {"chapters": [{"title": "A", "segment_ids": ["seg_013", "seg_014"]}]}
    errors: list[str] = []
    qc._validate_chapter_continuity(sel, ["seg_013"], errors, {"omitted_unplayable_segment_ids": ["seg_014"]})
    assert errors == []
    errors = []
    qc._validate_chapter_continuity(sel, ["seg_013"], errors, {})
    assert any("missing from EDL speech clips" in e for e in errors)


def test_transition_on_an_intentionally_empty_layup_seam_is_not_required() -> None:
    edl = {"clips": [{"type": "speech", "segment_id": "seg_1"}, {"type": "speech", "segment_id": "seg_2"}],
           "warnings": {"missing_vo_files": ["vo_layup_seg_2"]}}
    transitions = {"transitions": [{"after_segment_id": "seg_1", "before_segment_id": "seg_2"}]}
    errors: list[str] = []
    qc._validate_transitions(transitions, edl, ["seg_1", "seg_2"], errors)
    assert errors == []
    edl["warnings"] = {}
    qc._validate_transitions(transitions, edl, ["seg_1", "seg_2"], errors)
    assert any("missing transition clip" in e for e in errors)


def _write(ctx, rel: str, doc: dict) -> None:
    path = ctx.run_dir.joinpath(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "exec_edl_frozen")
    for rel, doc in {
        "master/selection.json": {"ordered_segment_ids": ["seg_1", "seg_2"], "chapters": []},
        "master/coverage_audit.json": {},
        "master/narrative_plan.json": {},
    }.items():
        _write(c, rel, doc)
    return c


def _stub_validators(monkeypatch) -> None:
    for name in (
        "_validate_selection_parity", "_validate_coverage_survives_edl", "_validate_chapter_continuity",
        "_validate_transitions", "_validate_vo_after_legal_hinge", "_validate_gap_placements",
        "_validate_clone_voice_adjacency", "_validate_speaker_volley_integrity",
        "_validate_single_synthetic_between_natives", "_validate_episode_vo_identity", "_validate_audit_artifact",
    ):
        monkeypatch.setattr(qc, name, lambda *a, **k: None)
    monkeypatch.setattr(qc, "_validate_framing_before_impact", lambda c, e, s, errs: errs.append("impact lacks framing"))
    monkeypatch.setattr(qc, "_validate_framing_succinct_exclusions", lambda c, sel, s, errs: errs.append("framing-covered on air"))
    monkeypatch.setattr(qc, "_validate_ordering_constraints", lambda plan, s, errs: errs.append("constraint violated"))


EDL = {"clips": [{"type": "speech", "segment_id": "seg_1"}, {"type": "speech", "segment_id": "seg_2"}]}


def test_rerank_only_issues_are_warnings_when_the_order_is_frozen(ctx, monkeypatch) -> None:
    _stub_validators(monkeypatch)
    monkeypatch.setattr("interview_mux.artifact_repairs._order_frozen", lambda c: True)
    assert qc.validate_flow1_edl_narrative(ctx, dict(EDL)) == []


def test_rerank_only_issues_still_block_before_the_freeze(ctx, monkeypatch) -> None:
    _stub_validators(monkeypatch)
    monkeypatch.setattr("interview_mux.artifact_repairs._order_frozen", lambda c: False)
    assert len(qc.validate_flow1_edl_narrative(ctx, dict(EDL))) == 3


def test_builder_skipped_line_is_not_phantom_vo(ctx, monkeypatch) -> None:
    from interview_mux.publishability_boundary import _check_phantom_vo

    wav = ctx.run_dir / "vo_pickup" / "synthesized" / "vo_x.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF0000WAVE")
    monkeypatch.setattr("interview_mux.stages.assembly.resolve_vo_pickup_path", lambda c, line: wav)
    gap = {"interviewer_lines": [{"line_id": "vo_x", "delivery": "synthesize", "targets_segment_id": "seg_2"}]}
    edl = {"clips": [], "warnings": {"suppressed_clone_adjacency": ["vo_x"]}}
    assert _check_phantom_vo(ctx, edl, gap) == []
    assert _check_phantom_vo(ctx, {"clips": [], "warnings": {}}, gap)
