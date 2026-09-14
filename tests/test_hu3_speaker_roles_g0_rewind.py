"""HU-3: after G0, speaker_roles with speakers.json on disk must not rewind.

Do not start a run. HU-4 topology hollow-done and HP-4 G0 pin stay open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import PROTECTED_CORE_STAGES, rerun_stage
from interview_mux.homunculus.runtime import dispatch_stage
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_speakers
from test_homunculus import _mark_analysis_prefix


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hu3_roles")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _close_g0(ctx: RunContext) -> None:
    ctx.write_json(
        "transcript/full.json",
        {"text": "Hello from the reviewed tape."},
        skip_handoff=True,
    )
    ctx.write_json("transcript/review_queue.json", {"chunks": []}, skip_handoff=True)
    mark_done_raw(ctx, "transcript_review")


def test_hu3_protected_core_lists_speakers_json() -> None:
    assert PROTECTED_CORE_STAGES["speaker_roles"] == ("understanding/speakers.json",)


def test_hu3_g0_refuses_speaker_roles_rewind_when_speakers_exist(ctx: RunContext) -> None:
    _close_g0(ctx)
    ctx.write_json("understanding/speakers.json", minimal_speakers(), skip_handoff=True)
    ran: list[str] = []
    with pytest.raises(RuntimeError, match="timeline artifacts exist"):
        dispatch_stage(ctx, "speaker_roles", lambda: ran.append("ran"), source="conductor")
    assert ran == []


def test_hu3_g0_allows_speaker_roles_when_speakers_missing(ctx: RunContext) -> None:
    _mark_analysis_prefix(ctx, "speaker_roles")
    _close_g0(ctx)
    assert not ctx.artifact_exists("understanding/speakers.json")
    ran: list[str] = []

    def _write_roles() -> None:
        ran.append("ran")
        ctx.write_json("understanding/speakers.json", minimal_speakers(), skip_handoff=True)

    dispatch_stage(ctx, "speaker_roles", _write_roles, source="conductor")
    assert ran == ["ran"]
    assert ctx.artifact_exists("understanding/speakers.json")


def test_hu3_open_g0_still_allows_speaker_roles_with_file(ctx: RunContext) -> None:
    _mark_analysis_prefix(ctx, "speaker_roles")
    ctx.write_json("transcript/review_queue.json", {"chunks": []}, skip_handoff=True)
    ctx.write_json("understanding/speakers.json", minimal_speakers(), skip_handoff=True)
    ran: list[str] = []
    dispatch_stage(ctx, "speaker_roles", lambda: ran.append("ran"), source="test")
    assert ran == ["ran"]


def test_hu3_rerun_refused_after_g0_when_speakers_exist(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _close_g0(ctx)
    ctx.write_json("understanding/speakers.json", minimal_speakers(), skip_handoff=True)
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _c, stage: ran.append(stage),
    )
    with pytest.raises(RuntimeError, match="timeline artifacts exist"):
        rerun_stage(ctx, "speaker_roles")
    assert ran == []
