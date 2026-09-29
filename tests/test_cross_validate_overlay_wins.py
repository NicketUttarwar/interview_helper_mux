"""During write approval, the stage's pending write must be what gets validated.

_committed_json checked the committed file first and only fell back to the pending
overlay when it was missing. For a stage replacing an existing artifact, the stale
committed copy was therefore validated instead of the replacement. On a keyless
traversal that judged a first-pass narrative plan against a manifest a re-split
had since shrunk, refused the flush, and the clean plan sitting in staging could
never land: "narrative segment seg_004 not in manifest", with the fix already
written.
"""

from __future__ import annotations

import json

from interview_mux import artifact_cross_validate as acv


def test_pending_overlay_shadows_committed_copy(tmp_path, monkeypatch) -> None:
    committed = tmp_path / "narrative_plan.json"
    committed.write_text(json.dumps({"chapters": [{"segment_ids": ["seg_004"]}]}), encoding="utf-8")
    staged = tmp_path / "staged_narrative_plan.json"
    staged.write_text(json.dumps({"chapters": [{"segment_ids": ["seg_001"]}]}), encoding="utf-8")

    class Ctx:
        def final_path(self, *parts):
            return committed

    monkeypatch.setattr(acv, "_overlay_pending_path", lambda ctx, rel: staged)
    doc = acv._committed_json(Ctx(), "master/narrative_plan.json")
    assert doc["chapters"][0]["segment_ids"] == ["seg_001"], (
        "the write being approved must be validated, not the copy it replaces"
    )


def test_without_overlay_the_committed_copy_is_read(tmp_path, monkeypatch) -> None:
    committed = tmp_path / "narrative_plan.json"
    committed.write_text(json.dumps({"chapters": []}), encoding="utf-8")

    class Ctx:
        def final_path(self, *parts):
            return committed

    monkeypatch.setattr(acv, "_overlay_pending_path", lambda ctx, rel: None)
    assert acv._committed_json(Ctx(), "master/narrative_plan.json") == {"chapters": []}
