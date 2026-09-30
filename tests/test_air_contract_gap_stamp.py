"""The air-contract sanitizer lands its VO flags on the gap report under the owner's key (ISSUES 101)."""

from __future__ import annotations

import json

import pytest
from run_fixtures import isolated_run_ctx

from interview_mux.artifact_sanitize import air_script


def _seed_gap(ctx, *, layup_authority: bool) -> None:
    path = ctx.final_path("understanding", "gap_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"version": 1, "interviewer_lines": [{"line_id": "vo_preface_seg_021", "text": "So,"}]}
    if layup_authority:
        doc["nugget_layup_authority"] = True
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize(
    "layup_authority, expected_owner",
    [(True, "nugget_layup_compose"), (False, "gap_framing_compose")],
)
def test_flags_are_stamped_with_the_end_a_reason_and_owner_key(
    tmp_path, monkeypatch, layup_authority, expected_owner
) -> None:
    ctx = isolated_run_ctx(tmp_path, f"exec_air_gap_{expected_owner}")
    _seed_gap(ctx, layup_authority=layup_authority)
    calls: list[dict] = []

    def _persist(c, rel, doc, **kw):
        calls.append({"rel": rel, "doc": doc, **kw})
        return True

    monkeypatch.setattr("interview_mux.seat_authority.persist_frozen_seat_doc", _persist)
    gap = {
        "version": 1,
        "interviewer_lines": [
            {"line_id": "vo_preface_seg_021", "text": "So,", "skipped_optional": True, "air_script_omit": True}
        ],
    }
    air_script.persist_air_contract_gap(ctx, gap)
    assert len(calls) == 1
    assert calls[0]["rel"] == "understanding/gap_report.json"
    assert calls[0]["reason"] == "stamp_gap_omit_flags"
    assert calls[0]["stage_key"] == expected_owner
    assert calls[0]["doc"] is gap


def test_a_refused_stamp_is_an_error_not_a_silent_skip(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_air_gap_refused")
    _seed_gap(ctx, layup_authority=True)
    monkeypatch.setattr("interview_mux.seat_authority.persist_frozen_seat_doc", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="stamp_gap_omit_flags"):
        air_script.persist_air_contract_gap(ctx, {"version": 1, "interviewer_lines": []})
