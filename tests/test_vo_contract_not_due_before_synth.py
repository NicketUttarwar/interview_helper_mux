"""A seated line's missing WAV is not a contract violation before vo_synthesize,
and tier D never waives the last live host line (ISSUES 160).

exec_016: the invariant ladder ran around step 51, before vo_synthesize, saw
"seated synthesize vo_layup_seg_024 missing WAV", and tier D waived the run's
only host line. The hosted floor fell to 0 and layup looped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx, minimal_gap_report

GAP = "understanding/gap_report.json"


def _line(lid: str) -> dict:
    return {
        "line_id": lid,
        "text": "The question now is whether combined cell and omics data can support care.",
        "targets_segment_id": "seg_024",
        "placement": "before",
        "delivery": "synthesize",
    }


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_vo_due")


def test_missing_wav_not_reported_before_vo_synthesize(ctx, monkeypatch) -> None:
    from interview_mux import vo_contract

    ctx.write_json(GAP, {**minimal_gap_report(), "interviewer_lines": [_line("vo_layup_seg_024")]}, skip_handoff=True)
    monkeypatch.setattr(vo_contract, "_load_seated_omitted", lambda c: ({"vo_layup_seg_024"}, set()))
    monkeypatch.setattr(vo_contract, "seated_vo_missing_ids", lambda c: ["vo_layup_seg_024"])
    assert not any("missing WAV" in v for v in vo_contract.validate_vo_contract(ctx))
    monkeypatch.setattr(ctx, "is_done", lambda stage: stage == "vo_synthesize")
    assert "seated synthesize vo_layup_seg_024 missing WAV" in vo_contract.validate_vo_contract(ctx)


def test_tier_d_keeps_the_last_live_host_line(ctx, monkeypatch) -> None:
    from interview_mux import execution_contract as ec

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo", lambda c: True
    )
    one = {**minimal_gap_report(), "interviewer_lines": [_line("vo_a")]}
    assert ec._tier_d_would_hollow_hosted_floor(ctx, one, "vo_a")
    two = {**minimal_gap_report(), "interviewer_lines": [_line("vo_a"), _line("vo_b")]}
    assert not ec._tier_d_would_hollow_hosted_floor(ctx, two, "vo_a")


def test_tier_d_may_waive_when_hosted_vo_not_required(ctx, monkeypatch) -> None:
    from interview_mux import execution_contract as ec

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo", lambda c: False
    )
    one = {**minimal_gap_report(), "interviewer_lines": [_line("vo_a")]}
    assert not ec._tier_d_would_hollow_hosted_floor(ctx, one, "vo_a")
