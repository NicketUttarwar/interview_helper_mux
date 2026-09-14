"""HG-2: delivery brief / soundscape / episode structure cannot hollow-done.

Schema-complete producer JSON is required. Missing / {} / partial stay incomplete.
Disabled flags write a schema-valid skip stub then heal-mark. Skip and heal-forward
refuse without a real write.

Do not start a run. HG-3 missing_framing batch and HM-3 bind stay later.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.delivery_brief import run_delivery_brief_build
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.episode_structure import run_episode_structure_compose
from interview_mux.homunculus.agenda import skip_stage, stage_outputs_present
from interview_mux.prompt_validation import (
    validate_delivery_brief,
    validate_episode_structure,
    validate_soundscape_policy,
)
from interview_mux.run_context import RunContext
from interview_mux.soundscape_policy import run_soundscape_policy_build
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402

_BRIEF = "delivery_brief_build"
_SOUND = "soundscape_policy_build"
_STRUCT = "episode_structure_compose"
_BRIEF_REL = "understanding/delivery_brief.json"
_SOUND_REL = "understanding/soundscape_policy.json"
_STRUCT_REL = "understanding/episode_structure.json"


def _plant(ctx: RunContext, rel: str, text: str) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def _valid_brief() -> dict:
    return {
        "version": 1,
        "source_duration_ms": 600000,
        "target_duration_sec": {"min": 300, "ideal": 420, "max": 540},
        "question_budget": {"min": 0, "ideal": 2, "max": 4},
        "chapter_budget": {"min": 2, "ideal": 3, "max": 4},
        "selection_mode": "coverage_first",
        "sfx_density": {},
        "ranking_weights": {},
        "rationale": [],
        "operator_overrides": {},
        "generated": {},
    }


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hg2_gap_tail")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


@pytest.mark.parametrize(
    "stage,rel",
    [
        (_BRIEF, _BRIEF_REL),
        (_SOUND, _SOUND_REL),
        (_STRUCT, _STRUCT_REL),
    ],
)
def test_hg2_missing_file_is_incomplete(ctx: RunContext, stage: str, rel: str) -> None:
    mark_done_raw(ctx, stage)
    reason = stage_artifact_incompleteness(ctx, stage)
    assert reason is not None
    assert "pending" in reason
    assert parse_resume_stage_from_reason(reason) == stage
    assert stage_outputs_present(ctx, stage) is False
    assert seed_stage_complete(ctx, stage) is False
    out = heal_or_refuse_mark(ctx, stage)
    assert out.get("unmarked") is True or not ctx.is_done(stage)


@pytest.mark.parametrize("stage", [_BRIEF, _SOUND, _STRUCT])
def test_hg2_skip_without_file_refused(ctx: RunContext, stage: str) -> None:
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, stage, reason="conductor whim")
    assert not ctx.is_done(stage)


@pytest.mark.parametrize(
    "stage,rel",
    [
        (_BRIEF, _BRIEF_REL),
        (_SOUND, _SOUND_REL),
        (_STRUCT, _STRUCT_REL),
    ],
)
def test_hg2_empty_object_is_schema_hollow(ctx: RunContext, stage: str, rel: str) -> None:
    _plant(ctx, rel, "{}")
    reason = stage_artifact_incompleteness(ctx, stage)
    assert reason is not None
    assert "schema-hollow" in reason
    assert parse_resume_stage_from_reason(reason) == stage
    out = heal_or_refuse_mark(ctx, stage, force=True)
    assert out.get("refused") is True or not ctx.is_done(stage)


def test_hg2_zeroed_disabled_brief_is_schema_complete(ctx: RunContext) -> None:
    ctx.write_json(_BRIEF_REL, _valid_brief() | {
        "target_duration_sec": {"min": 0, "ideal": 0, "max": 0},
        "rationale": ["disabled"],
    }, skip_handoff=True)
    assert validate_delivery_brief(ctx.read_json(_BRIEF_REL)) == []
    assert stage_artifact_incompleteness(ctx, _BRIEF) is None
    out = heal_or_refuse_mark(ctx, _BRIEF)
    assert out.get("marked") is True
    assert seed_stage_complete(ctx, _BRIEF) is True


def test_hg2_disabled_brief_writes_stub_and_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_brief.delivery_brief_enabled",
        lambda _cfg=None: False,
    )
    run_delivery_brief_build(ctx)
    doc = ctx.read_json(_BRIEF_REL)
    assert "disabled" in (doc.get("rationale") or [])
    assert validate_delivery_brief(doc) == []
    assert ctx.is_done(_BRIEF)
    assert stage_artifact_incompleteness(ctx, _BRIEF) is None


def test_hg2_disabled_soundscape_writes_stub_and_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.soundscape_policy.soundscape_enabled",
        lambda _cfg=None: False,
    )
    run_soundscape_policy_build(ctx)
    doc = ctx.read_json(_SOUND_REL)
    assert "disabled" in (doc.get("rationale") or [])
    assert validate_soundscape_policy(doc) == []
    assert ctx.is_done(_SOUND)
    assert stage_artifact_incompleteness(ctx, _SOUND) is None


def test_hg2_disabled_structure_writes_stub_and_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.episode_structure.structure_enabled",
        lambda _cfg=None: False,
    )
    run_episode_structure_compose(ctx)
    doc = ctx.read_json(_STRUCT_REL)
    assert doc.get("skipped") == "feature_disabled"
    assert validate_episode_structure(doc) == []
    assert ctx.is_done(_STRUCT)
    assert stage_artifact_incompleteness(ctx, _STRUCT) is None


def test_hg2_heal_forward_refuses_without_write(ctx: RunContext) -> None:
    driver._heal_mark(ctx, _SOUND)
    assert not ctx.is_done(_SOUND)
    assert stage_artifact_incompleteness(ctx, _SOUND) is not None
