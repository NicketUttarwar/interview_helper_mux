"""HM-4: sonic_context_build cannot hollow-done.

Schema-complete understanding/sonic_context.json is required. Missing / {} /
partial stay incomplete. Skip and heal-forward refuse without a real write.
Empty tag_registry with sparse_mode is an honest sparse briefing, not hollow.

Do not start a run. HM-2 fingerprint pin and HG-2 gap-tail stay later.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import skip_stage, stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from interview_mux.stages.sonic_context_stages import run_sonic_context_build
from run_fixtures import (
    isolated_run_ctx,
    mark_done_raw,
    minimal_manifest_segment,
    minimal_narrative_plan,
    minimal_source_acoustic_profile,
)

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402

_STAGE = "sonic_context_build"
_REL = "understanding/sonic_context.json"


def _plant_json(ctx: RunContext, text: str) -> None:
    dest = ctx.final_path("understanding", "sonic_context.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def _sparse_valid_sonic() -> dict:
    return {
        "version": 1,
        "sparse_mode": True,
        "scenario": {
            "format_class": "one_on_one",
            "tone_class": "journalistic",
            "atlas_bucket": "one_on_one",
            "sound_posture": {
                "bed_density": "minimal",
                "stinger_cap_per_minute": 1,
            },
        },
        "sonic_identity_seed": {
            "primary_mood": "neutral",
            "density_hint": "minimal",
            "room_character": "unknown",
        },
        "tag_registry": [],
        "cue_opportunities": [],
        "mix_policy": {
            "underscore_policy": "sparse",
            "adaptive_max_assets_flow1": 2,
            "adaptive_max_assets_flow2": 1,
            "duration_bands_by_role": {},
        },
        "avoid_hard": [],
        "segment_flags": {},
    }


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hm4_sonic")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hm4_missing_file_is_incomplete(ctx: RunContext) -> None:
    mark_done_raw(ctx, _STAGE)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "pending" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)


def test_hm4_skip_without_file_refused(ctx: RunContext) -> None:
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _STAGE, reason="conductor whim")
    assert not ctx.is_done(_STAGE)


def test_hm4_empty_object_is_schema_hollow(ctx: RunContext) -> None:
    _plant_json(ctx, "{}")
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "schema-hollow" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _STAGE, reason="file exists")
    mark_done_raw(ctx, _STAGE)
    with pytest.raises(RuntimeError, match="hollow_done"):
        skip_stage(ctx, _STAGE, reason="hollow marker")
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)


def test_hm4_partial_missing_keys_is_schema_hollow(ctx: RunContext) -> None:
    _plant_json(ctx, '{"version": 1, "tag_registry": []}')
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "schema-hollow" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("refused") is True or not ctx.is_done(_STAGE)


def test_hm4_sparse_mode_empty_tags_completes(ctx: RunContext) -> None:
    ctx.write_json(_REL, _sparse_valid_sonic(), skip_handoff=True)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    assert stage_outputs_present(ctx, _STAGE) is True
    doc = skip_stage(ctx, _STAGE, reason="already briefed")
    assert _STAGE in doc["skipped"]
    assert not ctx.is_done(_STAGE)
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("marked") is True
    assert ctx.is_done(_STAGE)
    assert seed_stage_complete(ctx, _STAGE) is True


def test_hm4_heal_forward_refuses_without_write(ctx: RunContext) -> None:
    driver._heal_mark(ctx, _STAGE)
    assert not ctx.is_done(_STAGE)
    assert stage_artifact_incompleteness(ctx, _STAGE) is not None


def test_hm4_producer_write_marks(ctx: RunContext) -> None:
    from interview_mux.analysis_memory import default_analysis_state

    state = default_analysis_state(ctx.run_id)
    state["style"]["format_class"] = "one_on_one"
    state["style"]["tone_class"] = "journalistic"
    ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Interview on execution quality.",
            "topics": [
                {
                    "name": "Product strategy",
                    "summary": "Roadmap and delivery.",
                    "segment_ids": ["seg_001"],
                }
            ],
            "emotional_beats": [
                {"label": "measured confidence", "segment_ids": ["seg_001"]}
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        minimal_source_acoustic_profile(),
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest_segment(
                    "seg_001",
                    start_ms=0,
                    end_ms=6000,
                    speaker_id="host",
                    speaker_role="interviewer",
                )
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/narrative_plan.json",
        minimal_narrative_plan(),
        skip_handoff=True,
    )
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []}, skip_handoff=True)
    ctx.write_json("understanding/value_features.json", {"profiles": {}}, skip_handoff=True)

    run_sonic_context_build(ctx)
    assert ctx.is_done(_STAGE)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    assert seed_stage_complete(ctx, _STAGE) is True
