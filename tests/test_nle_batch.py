from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run_id = "exec_nle_batch"
    c = RunContext(run_id, create=True)
    init_run_meta_for_test(c)
    c.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "text": "hello",
                    "topic_tags": [],
                }
            ]
        },
    )
    c.write_json("segments/nle_edits.json", {"playhead_ms": 0})
    return c


def test_nle_batch_merges_overrides(ctx: RunContext) -> None:
    from interview_mux.nle_state import load_nle, save_nle

    nle = load_nle(ctx)
    overrides = nle.setdefault("segment_overrides", {})
    overrides["seg_a"] = {**overrides.get("seg_a", {}), "excluded": True}
    overrides["seg_b"] = {"excluded": True, "mark_redo": True}
    save_nle(ctx, nle)
    saved = load_nle(ctx)
    assert saved["segment_overrides"]["seg_a"]["excluded"] is True
    assert saved["segment_overrides"]["seg_b"]["mark_redo"] is True
