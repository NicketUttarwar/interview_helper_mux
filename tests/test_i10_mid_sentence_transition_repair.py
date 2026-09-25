"""MUX_FORENSICS=0 cascade: mid-sentence transition fallback / freeze repair (exec_13167)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.edl_narrative_remutate import _repair_mid_sentence_transition_openers
from interview_mux.spoken_copy_guard import guard_spoken_copy
import interview_mux.spoken_copy_guard as scg
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i10_mid_sentence")


def test_guard_rejects_mid_sentence_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        scg,
        "_grounded_fallback",
        lambda _ev: "alone does not settle whether a diagnostic reaches routine care.",
    )
    out = guard_spoken_copy(
        "mentions /tmp/artifact.json",
        evidence={},
        required=True,
        purpose="transition",
    )
    # Production still uses grounded fallback for required mid-sentence traps.
    assert out.get("action") in {"fallback", "ok", "refuse"}


def test_repair_mid_sentence_transition_openers(ctx) -> None:
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_060",
                    "before_segment_id": "seg_064",
                    "text": "alone does not settle whether a diagnostic reaches routine care.",
                    "type": "chapter",
                }
            ]
        },
        skip_handoff=True,
    )
    notes = _repair_mid_sentence_transition_openers(ctx)
    assert "repair_mid_sentence_transition_openers" in notes
    tr = ctx.read_json("master/transitions.json")
    assert str((tr.get("transitions") or [{}])[0].get("text") or "").startswith(
        "That alone"
    )
