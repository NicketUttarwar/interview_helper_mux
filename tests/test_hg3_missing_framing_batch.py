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
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            # Framing off → sealed_ratio rescue skipped; this test asserts pure CAP seal.
            "gap_framing_enabled": False,
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
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "gap_framing_enabled": False,
        },
        skip_handoff=True,
    )
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


def _sealed_row(sid: str) -> dict:
    row = _llm_row(sid)
    row["_meta"] = {
        "filled_by": "coverage_exhausted_accept",
        "producer": "coverage_exhausted_accept",
        "reason": "coverage_cap_seal",
    }
    return row


def _manifest_segments(ids: list[str]) -> dict:
    return {
        "segments": [
            {
                "segment_id": sid,
                "start_ms": i * 1000,
                "end_ms": i * 1000 + 900,
                "speaker_id": "spk_001",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "text": f"Text {sid}",
                "topic_tags": ["origin_story"],
            }
            for i, sid in enumerate(ids)
        ]
    }


def test_hg3_empty_shard_envelope_detection() -> None:
    from interview_mux.stages.gaps import _shard_envelope_has_evaluations

    assert _shard_envelope_has_evaluations({}) is False
    assert _shard_envelope_has_evaluations({"evaluations": []}) is False
    assert _shard_envelope_has_evaluations({"evaluations": [{"severity": "low"}]}) is False
    assert (
        _shard_envelope_has_evaluations(
            {"evaluations": [{"segment_id": "seg_001", "severity": "low"}]}
        )
        is True
    )


def test_hg3_sealed_ratio_incompleteness_without_rescue(ctx: RunContext) -> None:
    """ASSETS shape: ~40% sealed without rescue_done refuses done."""
    from interview_mux.stage_completion import (
        _missing_framing_sealed_ratio_incompleteness,
    )

    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "gap_framing_enabled": True,
        },
        skip_handoff=True,
    )
    ids = [f"seg_{i:03d}" for i in range(1, 6)]
    ctx.write_json("segments/manifest.json", _manifest_segments(ids), skip_handoff=True)
    evals = [_llm_row(sid) for sid in ids[:3]] + [_sealed_row(sid) for sid in ids[3:]]
    ctx.write_json(
        _REL,
        {"evaluations": evals, "_meta": {"coverage_passes": 2}},
        skip_handoff=True,
    )
    reason = _missing_framing_sealed_ratio_incompleteness(ctx)
    assert reason is not None
    assert "sealed_ratio" in reason
    assert "sealed_ratio" in (stage_artifact_incompleteness(ctx, _STAGE) or "")


def test_hg3_sealed_ratio_rescue_done_allows_complete(ctx: RunContext) -> None:
    from interview_mux.stage_completion import (
        _missing_framing_sealed_ratio_incompleteness,
    )

    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "gap_framing_enabled": True,
        },
        skip_handoff=True,
    )
    ids = [f"seg_{i:03d}" for i in range(1, 6)]
    ctx.write_json("segments/manifest.json", _manifest_segments(ids), skip_handoff=True)
    # 1/5 sealed = 20% — under hard_max 0.35 after rescue → complete
    evals = [_llm_row(sid) for sid in ids[:4]] + [_sealed_row(sid) for sid in ids[4:]]
    ctx.write_json(
        _REL,
        {
            "evaluations": evals,
            "_meta": {"coverage_passes": 2, "sealed_ratio_rescue_done": True},
        },
        skip_handoff=True,
    )
    assert _missing_framing_sealed_ratio_incompleteness(ctx) is None
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is None or "sealed_ratio" not in reason


def test_hg3_sealed_ratio_hard_after_rescue(ctx: RunContext) -> None:
    """After rescue, seal fraction above hard_max is operator-STOP (not auto-accept)."""
    from interview_mux.stage_completion import (
        _missing_framing_sealed_ratio_incompleteness,
    )

    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "gap_framing_enabled": True,
        },
        skip_handoff=True,
    )
    ids = [f"seg_{i:03d}" for i in range(1, 6)]
    ctx.write_json("segments/manifest.json", _manifest_segments(ids), skip_handoff=True)
    # 2/5 = 40% > hard_max 0.35
    evals = [_llm_row(sid) for sid in ids[:3]] + [_sealed_row(sid) for sid in ids[3:]]
    ctx.write_json(
        _REL,
        {
            "evaluations": evals,
            "_meta": {"coverage_passes": 2, "sealed_ratio_rescue_done": True},
        },
        skip_handoff=True,
    )
    reason = _missing_framing_sealed_ratio_incompleteness(ctx)
    assert reason is not None
    assert "sealed_ratio_hard" in reason


def test_hg3_coverage_report_writer(ctx: RunContext) -> None:
    from interview_mux.stages.gaps import (
        MISSING_FRAMING_COVERAGE_REPORT_REL,
        write_missing_framing_coverage_report,
    )

    ids = ["seg_001", "seg_002", "seg_003", "seg_004"]
    ctx.write_json("segments/manifest.json", _manifest_segments(ids), skip_handoff=True)
    doc = {
        "evaluations": [
            _llm_row("seg_001"),
            _llm_row("seg_002"),
            _sealed_row("seg_003"),
            _filled_row("seg_004"),
        ],
        "_meta": {"coverage_passes": 2},
    }
    report = write_missing_framing_coverage_report(
        ctx,
        doc,
        required_ids=ids,
        shard_empty_count=1,
        shard_empty_retries=1,
    )
    assert report["required_count"] == 4
    assert report["sealed_count"] == 1
    assert report["batch_fill_count"] == 1
    assert report["shard_empty_count"] == 1
    assert ctx.artifact_exists(MISSING_FRAMING_COVERAGE_REPORT_REL)
    disk = ctx.read_json(MISSING_FRAMING_COVERAGE_REPORT_REL)
    assert disk["producer_stage"] == "missing_framing"


def test_hg3_skip_report_stamps_missing_framing_producer(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        lambda *_a, **_k: {"marked": True},
    )
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "gap_framing_enabled": False,
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_segments(["seg_001"]),
        skip_handoff=True,
    )
    ensure_gap_fill_skipped(
        ctx,
        reason="gap_framing_disabled_by_operator",
        signals={"skip_signal": "gap_framing_no"},
    )
    report = ctx.read_json("understanding/gap_report.json")
    meta = report.get("_meta") or {}
    assert meta.get("producer") == "gap_fill_skip"
    assert meta.get("producer_stage") == "missing_framing"


def test_hg3_proactive_empty_shard_raises(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proactive (non-coverage) empty shards fail closed after one retry."""
    from interview_mux.stages.gaps import run_missing_framing

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
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "gap_framing_enabled": False,
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Empty proactive shard fixture.",
            "topics": [
                {
                    "name": "Origin",
                    "summary": "Opening",
                    "segment_ids": ["seg_001"],
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_segments(["seg_001"]),
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="empty shard after retry"):
        run_missing_framing(ctx)


def test_hg3_seal_row_has_full_keep_eligible_fields() -> None:
    from interview_mux.stages.gaps import _coverage_exhausted_accept_row

    row = _coverage_exhausted_accept_row("seg_001")
    assert row["recommended_framing"] == "none"
    assert row["candidate_for_summary"] is False
    assert row["supports_ranking_exclude"] is False
    assert row.get("duplicate_claim_cluster") == ""
    assert "secondary_gap_type" in row


def test_hg3_merge_prefers_scored_over_thinner() -> None:
    from interview_mux.stages.gaps import _merge_gap_evaluations

    scored = {
        "segment_id": "seg_001",
        "self_explanatory": True,
        "gap_type": "missing_context",
        "severity": "high",
        "listener_confusion": "why",
        "recommended_framing": "question",
    }
    thin = {
        "segment_id": "seg_001",
        "self_explanatory": True,
        "_meta": {
            "filled_by": "missing_framing_batch_coverage",
            "reason": "llm_sparse_shard_output",
        },
    }
    merged = _merge_gap_evaluations(
        [{"evaluations": [scored]}, {"evaluations": [thin]}],
        ["seg_001"],
    )
    row = merged["evaluations"][0]
    assert row["severity"] == "high"
    assert row["gap_type"] == "missing_context"


def test_hg3_blocking_rerun_need_parsed() -> None:
    from interview_mux.stages.gaps import _blocking_rerun_stage_from_needs

    assert (
        _blocking_rerun_stage_from_needs(
            [{"type": "rerun_stage", "stage": "speaker_roles"}]
        )
        == "speaker_roles"
    )
    assert (
        _blocking_rerun_stage_from_needs(
            [{"type": "rerun_stage", "stage": "speaker_roles", "blocking": False}]
        )
        is None
    )


def test_hg3_needs_rerun_blocks_cap_seal(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import run_missing_framing

    monkeypatch.setattr(
        "interview_mux.boundary_enrich.restamp_run_span_speakers",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.gaps.maybe_run_pre_stage_specialists",
        lambda *_a, **_k: None,
    )

    def _partial(*_a, **_k):
        # Sparse scores + blocking need → hard-stop (coverage < 50%)
        return {
            "status": "partial",
            "needs": [{"type": "rerun_stage", "stage": "speaker_roles"}],
            "artifacts": {"evaluations": []},
        }

    monkeypatch.setattr("interview_mux.llm_simple.run_llm_stage_simple", _partial)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "gap_framing_enabled": False},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "needs rerun fixture",
            "topics": [{"name": "A", "summary": "s", "segment_ids": ["seg_001"]}],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_segments(["seg_001", "seg_002"]),
        skip_handoff=True,
    )
    # One scored keep + one leftover at CAP-1 → coverage pass returns need → refuse seal
    from interview_mux.stages.gaps import MISSING_FRAMING_COVERAGE_CAP

    ctx.write_json(
        _REL,
        {
            "evaluations": [_llm_row("seg_001"), _filled_row("seg_002")],
            "_meta": {"coverage_passes": MISSING_FRAMING_COVERAGE_CAP - 1},
        },
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="needs.rerun_stage"):
        run_missing_framing(ctx)


def test_hg3_needs_rerun_soft_when_shard_scores(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chatty needs + usable scores must not hard-stop CAP seal."""
    from interview_mux.stages.gaps import run_missing_framing

    monkeypatch.setattr(
        "interview_mux.boundary_enrich.restamp_run_span_speakers",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.gaps.maybe_run_pre_stage_specialists",
        lambda *_a, **_k: None,
    )

    def _partial(*_a, **_k):
        return {
            "status": "partial",
            "needs": [{"type": "rerun_stage", "stage": "speaker_roles"}],
            "artifacts": {"evaluations": [_llm_row("seg_002")]},
        }

    monkeypatch.setattr("interview_mux.llm_simple.run_llm_stage_simple", _partial)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "gap_framing_enabled": False},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "needs soft fixture",
            "topics": [{"name": "A", "summary": "s", "segment_ids": ["seg_001"]}],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_segments(["seg_001", "seg_002"]),
        skip_handoff=True,
    )
    from interview_mux.stages.gaps import MISSING_FRAMING_COVERAGE_CAP

    ctx.write_json(
        _REL,
        {
            "evaluations": [_llm_row("seg_001"), _filled_row("seg_002")],
            "_meta": {"coverage_passes": MISSING_FRAMING_COVERAGE_CAP - 1},
        },
        skip_handoff=True,
    )
    run_missing_framing(ctx)  # must not raise
    doc = ctx.read_json(_REL)
    assert any(
        str(r.get("segment_id")) == "seg_002" and r.get("severity")
        for r in (doc.get("evaluations") or [])
        if isinstance(r, dict)
    )


def test_hg3_merge_prefers_higher_severity() -> None:
    from interview_mux.stages.gaps import _merge_gap_evaluations

    low = {
        "segment_id": "seg_001",
        "self_explanatory": True,
        "gap_type": "missing_setup",
        "severity": "low",
        "listener_confusion": "early",
        "recommended_framing": "none",
    }
    high = {
        "segment_id": "seg_001",
        "self_explanatory": False,
        "gap_type": "missing_question",
        "severity": "high",
        "listener_confusion": "later better",
        "recommended_framing": "question",
    }
    # Later low must not clobber earlier high
    merged = _merge_gap_evaluations(
        [{"evaluations": [high]}, {"evaluations": [low]}],
        ["seg_001"],
    )
    assert merged["evaluations"][0]["severity"] == "high"
    # Later high must upgrade earlier low
    merged2 = _merge_gap_evaluations(
        [{"evaluations": [low]}, {"evaluations": [high]}],
        ["seg_001"],
    )
    assert merged2["evaluations"][0]["severity"] == "high"


def test_hg3_sealed_vs_risk_incompleteness(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.stage_completion import (
        _missing_framing_sealed_ratio_incompleteness,
    )

    monkeypatch.setattr(
        "interview_mux.stages.gaps.resolve_framing_risk_segment_ids",
        lambda _ctx, **_k: {
            "ids": {"seg_004"},
            "ordered_ids": ["seg_004"],
            "sources": {"seg_004": "specialist"},
            "specialist_count": 1,
            "proxy_count": 0,
            "mode": "specialist",
        },
    )
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "gap_framing_enabled": True,
        },
        skip_handoff=True,
    )
    ids = [f"seg_{i:03d}" for i in range(1, 6)]
    ctx.write_json("segments/manifest.json", _manifest_segments(ids), skip_handoff=True)
    evals = [_llm_row(sid) for sid in ids[:3]] + [_sealed_row(sid) for sid in ids[3:]]
    ctx.write_json(
        _REL,
        {"evaluations": evals, "_meta": {"coverage_passes": 2}},
        skip_handoff=True,
    )
    reason = _missing_framing_sealed_ratio_incompleteness(ctx)
    assert reason is not None
    assert "sealed_vs_risk" in reason


def test_i5_sealed_vs_risk_prefers_scored_duplicate(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13181: seal + scored row for same risk id must not thrash sealed_vs_risk."""
    from interview_mux.stage_completion import (
        _missing_framing_sealed_ratio_incompleteness,
    )
    from interview_mux.stages.gaps import _sealed_vs_risk_ids

    monkeypatch.setattr(
        "interview_mux.stages.gaps.resolve_framing_risk_segment_ids",
        lambda _ctx, **_k: {
            "ids": {"seg_004"},
            "ordered_ids": ["seg_004"],
            "sources": {"seg_004": "specialist"},
            "specialist_count": 1,
            "proxy_count": 0,
            "mode": "specialist",
        },
    )
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "gap_framing_enabled": True},
        skip_handoff=True,
    )
    ids = [f"seg_{i:03d}" for i in range(1, 6)]
    ctx.write_json("segments/manifest.json", _manifest_segments(ids), skip_handoff=True)
    scored = dict(_llm_row("seg_004"))
    scored["severity"] = "medium"
    scored["gap_type"] = "missing_followup"
    scored["self_explanatory"] = False
    evals = [_llm_row(sid) for sid in ids[:3]] + [_sealed_row("seg_004"), scored, _llm_row("seg_005")]
    doc = {"evaluations": evals, "_meta": {"coverage_passes": 2}}
    ctx.write_json(_REL, doc, skip_handoff=True)
    assert _sealed_vs_risk_ids(ctx, doc) == []
    assert _missing_framing_sealed_ratio_incompleteness(ctx) is None


def test_i5_spine_freeze_keeps_open_missing_framing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13181: do not bump missing_framing → gap_framing_compose while incomplete."""
    from interview_mux.pipeline import run_analysis
    from interview_mux.stage_completion import stage_artifact_incompleteness

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "gap_framing_enabled": True},
        skip_handoff=True,
    )
    ids = [f"seg_{i:03d}" for i in range(1, 6)]
    ctx.write_json("segments/manifest.json", _manifest_segments(ids), skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.stages.gaps.resolve_framing_risk_segment_ids",
        lambda _ctx, **_k: {
            "ids": {"seg_004"},
            "ordered_ids": ["seg_004"],
            "sources": {"seg_004": "specialist"},
            "specialist_count": 1,
            "proxy_count": 0,
            "mode": "specialist",
        },
    )
    evals = [_llm_row(sid) for sid in ids[:3]] + [_sealed_row("seg_004"), _llm_row("seg_005")]
    ctx.write_json(
        _REL,
        {"evaluations": evals, "_meta": {"coverage_passes": 2}},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"gaps": [], "_meta": {"producer": "gap_framing_compose"}},
        skip_handoff=True,
    )
    assert stage_artifact_incompleteness(ctx, "missing_framing")

    seen: list[str] = []

    def _mf(_ctx: RunContext) -> None:
        raise RuntimeError("stop_after:missing_framing")

    def _gfc(_ctx: RunContext) -> None:
        raise RuntimeError("stop_after:gap_framing_compose")

    monkeypatch.setattr(
        "interview_mux.pipeline.effective_analysis_order",
        lambda: ["missing_framing", "gap_framing_compose"],
    )
    monkeypatch.setattr(
        "interview_mux.pipeline._analysis_stage_fns",
        lambda _ctx: {"missing_framing": _mf, "gap_framing_compose": _gfc},
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime.has_dispatch_ledger",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.done_authority.may_skip_as_complete",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.pipeline.resolve_before_stage_run",
        lambda *_a, **_k: "run",
    )

    def _wrapped(_ctx: RunContext, name: str, fn) -> None:
        seen.append(name)
        fn(_ctx)

    monkeypatch.setattr("interview_mux.write_staging.run_wrapped_stage", _wrapped)
    with pytest.raises(RuntimeError, match="stop_after:missing_framing"):
        run_analysis(ctx, from_stage="missing_framing", invalidate=False)
    assert seen == ["missing_framing"]


def test_hg3_stale_ids_incompleteness(ctx: RunContext) -> None:
    from interview_mux.stage_completion import (
        _missing_framing_stale_ids_incompleteness,
    )

    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "gap_framing_enabled": True},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_segments(["seg_001"]),
        skip_handoff=True,
    )
    ctx.write_json(
        _REL,
        {"evaluations": [_llm_row("seg_001"), _llm_row("seg_gone")]},
        skip_handoff=True,
    )
    reason = _missing_framing_stale_ids_incompleteness(ctx)
    assert reason is not None
    assert "stale_segment_ids" in reason


def test_hg3_hard_plan_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.loud_fail import LoudStageFailure
    from interview_mux.pipeline import _run_missing_framing_stage
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "hard_plan")
    ctx.write_json(
        "run_meta.json",
        {"gap_framing_enabled": True, "homunculus_version": "0.1.0"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.maybe_auto_accept_gap_gate_defaults",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.require_gap_framing_decision_clear",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.require_gap_path_clear",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.pipeline._gap_path_skipped",
        lambda _c: False,
    )
    with pytest.raises(LoudStageFailure, match="mastering_plan"):
        _run_missing_framing_stage(ctx)

def test_hg3_stageinfo_declares_llm_calls_and_stage_runs() -> None:
    from interview_mux.write_staging import operator_visible_staging_path

    assert operator_visible_staging_path(
        "missing_framing",
        "understanding/llm_calls/missing_framing/volley_001.json",
    )
    assert operator_visible_staging_path(
        "missing_framing",
        "understanding/stage_runs/missing_framing/coverage_report.json",
    )


def test_hg3_proxy_risk_ids_when_specialists_empty(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import resolve_framing_risk_segment_ids

    monkeypatch.setattr(
        "interview_mux.llm_specialists.load_comprehension_risks",
        lambda *_a, **_k: [],
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_segments(["seg_010", "seg_020", "seg_030"]),
        skip_handoff=True,
    )
    path = ctx.final_path("understanding", "talking_points.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"talking_points": [{"segment_id": "seg_010", "importance": 0.9},'
        ' {"segment_id": "seg_020", "importance": 0.8},'
        ' {"segment_id": "seg_999", "importance": 1.0}]}\n'
    )
    risk = resolve_framing_risk_segment_ids(ctx)
    assert risk["mode"] == "proxy"
    assert "seg_010" in risk["ids"]
    assert "seg_020" in risk["ids"]
    assert "seg_999" not in risk["ids"]  # orphan filtered by live gap ids
    assert risk["sources"]["seg_010"] == "proxy_talking_point"


def test_hg3_framing_risk_unions_specialist_and_proxy(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import resolve_framing_risk_segment_ids

    monkeypatch.setattr(
        "interview_mux.llm_specialists.load_comprehension_risks",
        lambda *_a, **_k: [{"segment_id": "seg_001", "risk_score": 0.9}],
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_segments(["seg_001", "seg_010"]),
        skip_handoff=True,
    )
    path = ctx.final_path("understanding", "talking_points.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"talking_points": [{"segment_id": "seg_010", "importance": 0.95}]}\n'
    )
    risk = resolve_framing_risk_segment_ids(ctx)
    assert risk["mode"] == "specialist+proxy"
    assert risk["sources"]["seg_001"] == "specialist"
    assert risk["sources"]["seg_010"].startswith("proxy_")


def test_hitch_confirm_pickup_writes_as_hitch_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hitch auto-confirm must own the write — not spoof missing_framing."""
    from interview_mux.artifact_ownership import assert_write
    from interview_mux.chapter_close_hitch import _ensure_inner_walk_gates
    from interview_mux.source_topology import pickup_speaker_confirmed

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"gap_framing_enabled": True, "homunculus_version": "0.1.0"},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "pickup_eligible_speaker_id": "spk_host",
            "speaker_stats": [
                {"speaker_id": "spk_host", "role": "host", "total_ms": 1000},
                {"speaker_id": "spk_guest", "role": "guest", "total_ms": 5000},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {
            "pickup_eligible_speaker_id": "spk_host",
            "operator_overrides": {},
        },
        skip_handoff=True,
    )
    # Ownership constitution: hitch is an ALLOW co-owner.
    assert_write(ctx, "understanding/flow_adaptation.json", "chapter_close_hitch")
    assert not pickup_speaker_confirmed(ctx)
    _ensure_inner_walk_gates(ctx)
    assert pickup_speaker_confirmed(ctx)
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    meta = adapt.get("_meta") or {}
    assert meta.get("writer") == "chapter_close_hitch"
    assert meta.get("hitch_auto_confirm") is True
    assert meta.get("confirm_reason") == "inner_walk_gate_auto_confirm"
