"""A repaired role/tape conflict must not deadlock the walk after G0 (ISSUES 138, exec_005).

missing_framing's preflight repaired the manifest's mislabeled segment types,
then re-linted the copy it had read before the repair, stamped a blocking
conflict onto speakers.json, and the stamp was never cleared (the clearing
write was an unkeyed foreign write and was skipped). speakers.json then read
as partial, the hollow guard unmarked speaker_roles, and speaker_roles may not
rerun after G0: "seed order: complete speaker_roles before running
missing_framing" until the run halted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx

QUESTION = "So what does that mean for patients?"
SPEAKERS = [
    {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
    {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
]


def _put(ctx, rel: str, doc: dict) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc), encoding="utf-8")


def _segments(mislabeled: int) -> list[dict]:
    rows = []
    for i in range(20):
        rows.append(
            {
                "segment_id": f"seg_{i:03d}",
                "start_ms": i * 1000,
                "end_ms": (i + 1) * 1000,
                "speaker_id": "spk_1",
                "speaker_role": "interviewee",
                "topic_tags": [],
                "type": "interviewee_answer",
                "text": QUESTION if i < mislabeled else "It changes how we treat them.",
            }
        )
    return rows


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "exec_role_stamp")
    _put(c, "understanding/content_brief.json", {"thesis": "x"})
    _put(c, "mastering/mastering_plan.json", {"plan": {}})
    _put(c, "understanding/speakers.json", {"speakers": SPEAKERS})
    return c


def _stamp(ctx) -> dict:
    return (ctx.read_json("understanding/speakers.json") or {}).get("role_tape_conflict") or {}


def test_preflight_relints_the_repaired_manifest(ctx) -> None:
    from interview_mux.llm_preflight import _preflight_missing_framing
    from interview_mux.speaker_role_evidence import lint_role_tape_conflicts

    _put(ctx, "segments/manifest.json", {"segments": _segments(6)})
    assert lint_role_tape_conflicts(ctx.read_json("segments/manifest.json"))["blocking"]
    errs = _preflight_missing_framing(ctx)
    assert not [e for e in errs if "role_tape_conflict" in e]
    assert not _stamp(ctx).get("blocking")


def test_stale_blocking_stamp_is_cleared_when_the_manifest_is_clean(ctx) -> None:
    from interview_mux.artifact_completeness import _gaps_speakers
    from interview_mux.llm_preflight import _preflight_missing_framing

    _put(ctx, "segments/manifest.json", {"segments": _segments(0)})
    spk = ctx.read_json("understanding/speakers.json")
    spk["role_tape_conflict"] = {"blocking": True, "conflict_count": 8, "typed_qa_count": 52}
    _put(ctx, "understanding/speakers.json", spk)
    assert "role_tape_conflict" in _gaps_speakers(ctx.read_json("understanding/speakers.json"))
    _preflight_missing_framing(ctx)
    assert not _stamp(ctx).get("blocking")
    assert "role_tape_conflict" not in _gaps_speakers(ctx.read_json("understanding/speakers.json"))


def test_speaker_lint_ignores_a_stamp_the_live_manifest_does_not_support(ctx) -> None:
    from interview_mux.deterministic_lint import _lint_speaker_roles

    _put(ctx, "segments/manifest.json", {"segments": _segments(0)})
    doc = {
        "speakers": [{"speaker_id": "spk_0", "role": "interviewer"}, {"speaker_id": "spk_1", "role": "interviewee"}],
        "role_tape_conflict": {"blocking": True},
    }
    assert not [e for e in _lint_speaker_roles(doc, ctx) if "role_tape_conflict" in e]


def test_reconcile_does_not_interrupt_a_run_whose_driver_is_alive(ctx) -> None:
    from interview_mux.gui_job_reconcile import _reconcile_job_file

    _put(ctx, "gui_job.json", {"status": "running", "mode": "orchestrator", "stage": "speaker_roles"})
    _put(ctx, "operator/driver_claim.json", {"version": 1, "run_id": ctx.run_id, "pid": os.getpid()})
    assert _reconcile_job_file(ctx, lock_held=False) is False
    assert ctx.read_json("gui_job.json")["status"] == "running"
