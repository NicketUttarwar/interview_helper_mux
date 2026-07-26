from __future__ import annotations

import json
from pathlib import Path

from interview_mux.artifact_lifecycle import build_outputs_view
from run_fixtures import isolated_run_ctx

BRIEF_PATH = "understanding/content_brief.json"
STAGE = "content_context"


def test_build_outputs_view_marks_blocking_sufficiency(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("interview_mux.sufficiency_engine.sufficiency_enabled", lambda: True)
    monkeypatch.setattr(
        "interview_mux.sufficiency_engine.evaluate",
        lambda stage_id, doc, ctx: [
            type("F", (), {"blocking": True, "path": "style.tone"})()
        ]
        if stage_id == STAGE and isinstance(doc, dict) and not str(doc.get("thesis") or "").strip()
        else [],
    )
    ctx = isolated_run_ctx(tmp_path, "suff_view")
    fixture = Path(__file__).resolve().parent / "fixtures" / "sufficiency" / "content_context" / "fail_empty_thesis.json"
    doc = json.loads(fixture.read_text(encoding="utf-8"))
    brief_path = ctx.path(*BRIEF_PATH.split("/"))
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(json.dumps(doc), encoding="utf-8")
    ctx.mark_done(STAGE)

    rows = build_outputs_view(ctx, STAGE)
    row = next(r for r in rows if r["path"] == BRIEF_PATH)
    assert row["sufficiency_status"] == "blocking"


def test_build_outputs_view_ok_when_sufficient(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "suff_ok")
    fixture = Path(__file__).resolve().parent / "fixtures" / "sufficiency" / "content_context" / "pass.json"
    doc = json.loads(fixture.read_text(encoding="utf-8"))
    ctx.write_json(BRIEF_PATH, doc, stage_key=STAGE)

    rows = build_outputs_view(ctx, STAGE)
    row = next(r for r in rows if r["path"] == BRIEF_PATH)
    assert row["sufficiency_status"] == "ok"
