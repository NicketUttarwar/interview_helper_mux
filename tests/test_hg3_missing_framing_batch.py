"""HG-3: batched missing_framing cannot raw-stamp done.

Heal-mark after persist. Default batch_fill rows refuse done (LLM must score).
severity+gap_type still counts as scored. Research-thin and skip-stub-while-Yes
still refuse via existing incompleteness.

Do not start a run. HG-2 gap-tail and HM-2 rollup pin stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import remaining_stages, skip_stage, stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_STAGE = "missing_framing"
_REL = "understanding/gap_evaluations.json"
_FILL_BY = "missing_framing_batch_coverage"


def _llm_row(sid: str) -> dict:
    return {
        "segment_id": sid,
        "self_explanatory": True,
        "gap_type": "ok_with_light_bridge",
        "severity": "low",
        "listener_confusion": "",
    }


def _filled_row(sid: str) -> dict:
    row = _llm_row(sid)
    row["_meta"] = {
        "filled_by": _FILL_BY,
        "reason": "llm_sparse_shard_output",
    }
    return row


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.mastering_research.research_shape_core_thin",
        lambda _ctx: False,
    )
    run = isolated_run_ctx(tmp_path, "hg3_batch")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hg3_missing_file_is_incomplete(ctx: RunContext) -> None:
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "gap_evaluations.json" in reason or "pending" in reason or "missing" in reason.lower()
    assert seed_stage_complete(ctx, _STAGE) is False


def test_hg3_empty_object_is_incomplete(ctx: RunContext) -> None:
    dest = ctx.final_path(*_REL.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{}", encoding="utf-8")
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("refused") is True or not ctx.is_done(_STAGE)


def test_hg3_batch_fill_refuses_done(ctx: RunContext) -> None:
    ctx.write_json(
        _REL,
        {"evaluations": [_llm_row("seg_001"), _filled_row("seg_002")]},
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "batch_fill" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    mark_done_raw(ctx, _STAGE)
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)
    assert seed_stage_complete(ctx, _STAGE) is False


def test_hg3_batch_fill_still_counts_as_scored(ctx: RunContext) -> None:
    from interview_mux.listenability_guards import gap_eval_scored_ratio

    ctx.write_json(
        _REL,
        {"evaluations": [_filled_row("seg_001"), _filled_row("seg_002")]},
        skip_handoff=True,
    )
    assert gap_eval_scored_ratio(ctx) + 0.001 >= 1.0
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "batch_fill" in reason


def test_hg3_llm_scored_rows_heal_mark(ctx: RunContext) -> None:
    ctx.write_json(
        _REL,
        {"evaluations": [_llm_row("seg_001"), _llm_row("seg_002")]},
        skip_handoff=True,
    )
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("marked") is True
    assert ctx.is_done(_STAGE)
    assert seed_stage_complete(ctx, _STAGE) is True


def test_hg3_repair_default_value_with_scores_is_keep_eligible(ctx: RunContext) -> None:
    """exec_11630: schema-patched LLM rows must not poison coverage leftovers."""
    from interview_mux.stages.gaps import _split_keep_and_leftover

    row = _llm_row("seg_001")
    row["_meta"] = {"filled_by": "repair_gap_evaluations", "reason": "default_value"}
    keep, leftover = _split_keep_and_leftover(["seg_001"], [row])
    assert leftover == []
    assert [r["segment_id"] for r in keep] == ["seg_001"]
    ctx.write_json(_REL, {"evaluations": [row]}, skip_handoff=True)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("marked") is True


def test_hg3_skip_stub_while_yes_still_refuses(ctx: RunContext) -> None:
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "gap_framing_enabled": True,
            "gap_fill_mode": "active",
        },
        skip_handoff=True,
    )
    ctx.write_json(_REL, {"evaluations": [_llm_row("seg_001")]}, skip_handoff=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "gaps": [],
            "_meta": {"producer": "gap_fill_skip", "producer_stage": "optimal_questions"},
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "skip stub" in reason
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("refused") is True or not ctx.is_done(_STAGE)


def test_hg3_research_thin_pins_rollup_not_batch(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.mastering_research.research_shape_core_thin",
        lambda _ctx: True,
    )
    ctx.write_json(_REL, {"evaluations": [_llm_row("seg_001")]}, skip_handoff=True)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "shape-core thin" in reason
    assert parse_resume_stage_from_reason(reason) == "mastering_research_rollup"
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("refused") is True or not ctx.is_done(_STAGE)


def test_hg3_thin_wins_over_batch_fill(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.mastering_research.research_shape_core_thin",
        lambda _ctx: True,
    )
    ctx.write_json(_REL, {"evaluations": [_filled_row("seg_001")]}, skip_handoff=True)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "shape-core thin" in reason
    assert "batch_fill" not in reason
    assert parse_resume_stage_from_reason(reason) == "mastering_research_rollup"


def test_hg3_operator_skip_rows_are_not_batch_fill(ctx: RunContext) -> None:
    ctx.write_json(
        _REL,
        {
            "evaluations": [_llm_row("seg_001")],
            "_meta": {"producer": "gap_fill_skip", "producer_stage": "missing_framing"},
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is None or "batch_fill" not in reason


def test_hg3_analysis_remaining_keeps_batch_fill(ctx: RunContext) -> None:
    ctx.write_json(
        _REL,
        {"evaluations": [_filled_row("seg_001")]},
        skip_handoff=True,
    )
    rem = remaining_stages(ctx, "analysis")
    assert _STAGE in rem


def test_hg3_skip_refused_while_batch_fill(ctx: RunContext) -> None:
    ctx.write_json(
        _REL,
        {"evaluations": [_filled_row("seg_001")]},
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _STAGE, reason="filled file exists")
    assert not ctx.is_done(_STAGE)


def test_hg3_repair_tag_refuses_done(ctx: RunContext) -> None:
    ctx.write_json(
        _REL,
        {
            "evaluations": [
                {
                    "segment_id": "seg_001",
                    "self_explanatory": True,
                    "gap_type": "ok_with_light_bridge",
                    "severity": "low",
                    "listener_confusion": "",
                    "_meta": {
                        "filled_by": "repair_gap_evaluations",
                        "reason": "fabricate_evaluation",
                    },
                }
            ]
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "batch_fill" in reason
    out = heal_or_refuse_mark(ctx, _STAGE, force=True)
    assert out.get("refused") is True or not ctx.is_done(_STAGE)


def test_hg3_leftover_split_keeps_llm_rows() -> None:
    from interview_mux.stages.gaps import _split_keep_and_leftover

    keep, leftover = _split_keep_and_leftover(
        ["seg_001", "seg_002", "seg_003"],
        [_llm_row("seg_001"), _filled_row("seg_002")],
    )
    assert [r["segment_id"] for r in keep] == ["seg_001"]
    assert leftover == ["seg_002", "seg_003"]


def test_hg3_coverage_cap_seals_without_llm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import run_missing_framing

    monkeypatch.setattr(
        "interview_mux.boundary_enrich.restamp_run_span_speakers",
        lambda _c: None,
    )

    def _boom(*_a, **_k):
        raise AssertionError("LLM must not run after coverage cap")

    monkeypatch.setattr("interview_mux.llm_simple.run_llm_stage_simple", _boom)
    monkeypatch.setattr(
        "interview_mux.stages.analysis_stage.run_analysis_llm_stage",
        _boom,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "speaker_id": "spk_001",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "text": "Sample.",
                    "topic_tags": ["origin_story"],
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        _REL,
        {
            "evaluations": [_filled_row("seg_001")],
            "_meta": {"coverage_passes": 2},
        },
        skip_handoff=True,
    )
    run_missing_framing(ctx)
    assert ctx.is_done(_STAGE)
    doc = ctx.read_json(_REL)
    row = (doc.get("evaluations") or [])[0]
    assert (row.get("_meta") or {}).get("filled_by") == "coverage_exhausted_accept"
    assert stage_artifact_incompleteness(ctx, _STAGE) is None


def test_hg3_same_invoke_cap_seals_leftovers(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same invoke: leftover volleys hit CAP → seal (not batch_fill thrash)."""
    from interview_mux.stages.gaps import (
        MISSING_FRAMING_COVERAGE_CAP,
        run_missing_framing,
    )

    monkeypatch.setattr(
        "interview_mux.boundary_enrich.restamp_run_span_speakers",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.gaps.maybe_run_pre_stage_specialists",
        lambda *_a, **_k: None,
    )

    def _empty_llm(*_a, **_k):
        return {"artifacts": {"evaluations": []}}

    monkeypatch.setattr("interview_mux.llm_simple.run_llm_stage_simple", _empty_llm)
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Same-invoke coverage cap seal fixture.",
            "topics": [
                {
                    "name": "Origin",
                    "summary": "Opening beat",
                    "segment_ids": ["seg_001"],
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "speaker_id": "spk_001",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "text": "Kept.",
                    "topic_tags": ["origin_story"],
                },
                {
                    "segment_id": "seg_002",
                    "start_ms": 5000,
                    "end_ms": 10000,
                    "speaker_id": "spk_002",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "text": "Leftover.",
                    "topic_tags": ["origin_story"],
                },
            ]
        },
        skip_handoff=True,
    )
    # One LLM keep + one batch_fill leftover at passes=CAP-1 → same-invoke seal.
    assert MISSING_FRAMING_COVERAGE_CAP >= 2
    ctx.write_json(
        _REL,
        {
            "evaluations": [_llm_row("seg_001"), _filled_row("seg_002")],
            "_meta": {"coverage_passes": MISSING_FRAMING_COVERAGE_CAP - 1},
        },
        skip_handoff=True,
    )
    run_missing_framing(ctx)
    assert ctx.is_done(_STAGE)
    doc = ctx.read_json(_REL)
    by_id = {
        str(r.get("segment_id")): r
        for r in (doc.get("evaluations") or [])
        if isinstance(r, dict)
    }
    leftover = by_id["seg_002"]
    assert (leftover.get("_meta") or {}).get("filled_by") == "coverage_exhausted_accept"
    assert (leftover.get("_meta") or {}).get("reason") == "coverage_cap_seal"
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    assert "batch_fill" not in str(stage_artifact_incompleteness(ctx, _STAGE) or "")


def test_repair_seals_fabricate_after_coverage_cap(tmp_path, monkeypatch):
    """Cascade (MUX_FORENSICS=0): coverage_passes>=CAP must not leave fabricate thrash.

    exec_13159: seg_061–064 stayed fabricate_evaluation after coverage_passes=2.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.artifact_repairs import repair_gap_evaluations
    from interview_mux.stages.gaps import _gap_eval_is_unscored_fill
    from interview_mux.stage_completion import _missing_framing_batch_fill_incompleteness
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "cap_seal_fabricate")
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["science"],
                },
                {
                    "segment_id": "seg_002",
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["science"],
                },
            ]
        },
        skip_handoff=True,
    )
    doc = {
        "_meta": {"coverage_passes": 2},
        "evaluations": [
            {
                "segment_id": "seg_001",
                "self_explanatory": True,
                "gap_type": "ok_with_light_bridge",
                "severity": "low",
                "listener_confusion": "",
                "_meta": {
                    "filled_by": "repair_gap_evaluations",
                    "reason": "fabricate_evaluation",
                },
            }
        ],
    }
    repaired, notes = repair_gap_evaluations(ctx, doc)
    assert any(n.get("action") == "coverage_cap_seal_existing" for n in notes)
    assert any(n.get("action") == "coverage_cap_seal_fabricate" for n in notes)
    for row in repaired["evaluations"]:
        assert not _gap_eval_is_unscored_fill(row), row
    ctx.write_json("understanding/gap_evaluations.json", repaired, skip_handoff=True)
    assert _missing_framing_batch_fill_incompleteness(ctx) is None
