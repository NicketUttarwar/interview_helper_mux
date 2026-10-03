"""A required line the spoken-copy guard refuses is cured or released, never a stage failure (ISSUES 128).

The run this guards (one-hour source, exec_102): four compose shards returned
their lines, one context line repeated a sentence another shard had already
voiced, the guard had no grounded fallback for it, and the repair raised
"required gap VO blocked by spoken_copy_guard", failing the whole stage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.spoken_copy_guard import (
    guard_spoken_copy,
    spoken_copy_violations,
    strip_repeated_sentences,
)
from run_fixtures import isolated_run_ctx

FIRST = "Cancer care depends on timely signals. What does the blood show first?"
REPEAT = (
    "Cancer care depends on timely signals. The lab now pairs tumour DNA with intact cells. "
    "Listen for how that changes monitoring."
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "release")


def test_the_repeated_sentence_is_stripped_and_the_rest_kept() -> None:
    assert "spoken_repeated_sentence" in spoken_copy_violations(REPEAT, seen_texts=[FIRST])
    stripped = strip_repeated_sentences(REPEAT, [FIRST])
    assert stripped == "The lab now pairs tumour DNA with intact cells. Listen for how that changes monitoring."
    decision = guard_spoken_copy(REPEAT, evidence={}, required=True, purpose="gap_repair[x]", seen_texts=[FIRST])
    assert decision["action"] == "fallback"
    assert decision["text"] == stripped


def test_an_in_line_repeat_is_stripped_too() -> None:
    text = "The assay reads both signals. The assay reads both signals. Listen for what that buys."
    assert strip_repeated_sentences(text) == "The assay reads both signals. Listen for what that buys."


def test_a_line_that_is_only_the_repeat_still_blocks_at_the_guard() -> None:
    decision = guard_spoken_copy(
        "Cancer care depends on timely signals.",
        evidence={},
        required=True,
        purpose="gap_repair[x]",
        seen_texts=[FIRST],
    )
    assert decision["action"] == "block"


def _report() -> dict:
    return {
        "gaps": [],
        "interviewer_lines": [
            {
                "line_id": "vo_context_seg_001",
                "line_category": "context_setup",
                "text": FIRST,
                "targets_segment_id": "seg_001",
                "placement": "before",
                "delivery": "synthesize",
            },
            {
                "line_id": "vo_context_seg_062",
                "line_category": "context_setup",
                "text": "Cancer care depends on timely signals.",
                "targets_segment_id": "seg_062",
                "placement": "before",
                "delivery": "synthesize",
                "required": True,
            },
        ],
    }


def test_the_repair_releases_the_line_instead_of_failing_the_stage(ctx, monkeypatch) -> None:
    import interview_mux.artifact_repairs as ar

    released: list[dict] = []
    real = ar._release_unspeakable_required_line

    def _spy(c, row, decision, applied, out):
        real(c, row, decision, applied, out)
        released.append(dict(row))

    monkeypatch.setattr(ar, "_release_unspeakable_required_line", _spy)
    import interview_mux.spoken_copy_guard as scg

    real_guard = scg.guard_spoken_copy

    def _guard(text, **kw):
        # The guard's verdict for the line in the incident: required, repeated, no fallback.
        if "seg_062" in str(kw.get("purpose") or ""):
            return {
                "action": "block",
                "text": "",
                "violations": ["spoken_repeated_sentence", "no_grounded_fallback"],
                "script_hash": scg.script_hash(""),
                "context_hash": scg.context_hash({}),
                "purpose": kw.get("purpose"),
            }
        return real_guard(text, **kw)

    monkeypatch.setattr(scg, "guard_spoken_copy", _guard)
    if hasattr(ar, "guard_spoken_copy"):
        monkeypatch.setattr(ar, "guard_spoken_copy", _guard)
    # No LoudStageFailure: the stage keeps the other shards' work.
    repaired, notes = ar.repair_gap_report(ctx, _report(), resolve_high_gap_seats=False)
    assert [r["line_id"] for r in released] == ["vo_context_seg_062"]
    ids = [str(r.get("line_id") or "") for r in repaired.get("interviewer_lines") or []]
    assert "vo_context_seg_062" not in ids
    assert "vo_context_seg_001" in ids


def test_neither_loud_failure_remains_in_the_guard_loop() -> None:
    import interview_mux.artifact_repairs as ar

    src = Path(ar.__file__).read_text(encoding="utf-8")
    assert "required gap VO blocked by spoken_copy_guard" not in src
    assert "required high-gap VO omitted after rewrite" not in src
    assert src.count("_release_unspeakable_required_line(ctx, row, decision, applied, out)") == 2


def test_a_short_remnant_is_not_kept_as_the_line() -> None:
    decision = guard_spoken_copy(
        "Cancer care depends on timely signals. What broke next?",
        evidence={},
        required=True,
        purpose="gap_repair[x]",
        seen_texts=[FIRST],
    )
    assert decision["action"] == "block"
