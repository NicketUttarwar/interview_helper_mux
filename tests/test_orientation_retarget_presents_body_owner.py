"""The orientation retarget writes gap_report as its body owner (ISSUES 153).

exec_014: vo_line_adjudicate's retarget passed write_permitted, then the
gap-body sole-writer rule refused it (owner nugget_layup_compose under the soft
freeze) as an error-level authority denial; the orientation stayed unretargeted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def test_retarget_is_written_under_the_body_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux import opening_orientation as oo

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_orient_owner")
    for rel, doc in (
        ("understanding/gap_report.json", {"nugget_layup_authority": True, "interviewer_lines": []}),
        ("master/selection.json", {"ordered_segment_ids": ["seg_005", "seg_006"]}),
    ):
        dest = ctx.final_path(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(oo, "ensure_episode_orientation", lambda c, g, o: (dict(g, opening_orientation={"target_segment_id": "seg_005"}), []))
    monkeypatch.setattr("interview_mux.artifact_ownership.gap_report_body_owner", lambda doc: "nugget_layup_compose")
    seen: list[dict] = []
    monkeypatch.setattr(ctx, "write_json", lambda rel, doc, **kw: seen.append({"rel": rel, **kw}))
    oo.retarget_orientation_to_open(ctx, stage_key="vo_line_adjudicate")
    gap_writes = [w for w in seen if w["rel"] == "understanding/gap_report.json"]
    assert gap_writes and gap_writes[0]["stage_key"] == "nugget_layup_compose"
    assert gap_writes[0]["mutation_class"] == "segment_id_remap"


def test_a_refused_retarget_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux import opening_orientation as oo

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_orient_refused")
    for rel, doc in (
        ("understanding/gap_report.json", {"interviewer_lines": []}),
        ("master/selection.json", {"ordered_segment_ids": ["seg_005"]}),
    ):
        dest = ctx.final_path(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(oo, "ensure_episode_orientation", lambda c, g, o: (g, []))

    def _deny(rel, doc, **kw):
        raise RuntimeError("authority_denied:persist:understanding/gap_report.json")

    monkeypatch.setattr(ctx, "write_json", _deny)
    assert oo.retarget_orientation_to_open(ctx, stage_key="vo_line_adjudicate") == []
