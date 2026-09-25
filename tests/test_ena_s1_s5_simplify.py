"""ENA S1–S8: narrative audit simplify — ownership, demote-or-refuse, no prep thrash."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.audit_repair_loop import maybe_repair_after_narrative_audit
from interview_mux.edl_narrative_remutate import (
    _ACTION_STAGES,
    classify_edl_narrative_issue,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "ena_s1_s8")


def test_s3_action_stages_never_rewind_ranking_or_vo() -> None:
    for action, stages in _ACTION_STAGES.items():
        assert "full_master_ranking" not in stages
        assert "vo_synthesize" not in stages
        assert "vo_line_adjudicate" not in stages
        assert "nugget_layup_compose" not in stages
        assert "transitions" not in stages
        if stages:
            assert stages == ["edl_narrative_audit"], action


def test_s5_chapter_overflow_classifies_as_align_plan() -> None:
    assert (
        classify_edl_narrative_issue(
            "nine chapters exceeding the authoritative maximum of eight"
        )
        == "align_plan"
    )


def test_s1_repair_does_not_spoof_sanitize_stage_key(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        "interview_mux.artifact_writes.write_validated_artifact",
        lambda c, rel, doc, **kw: writes.append((str(rel), kw.get("stage_key"))),
    )
    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.apply_edl_narrative_metadata_align",
        lambda _c: {"notes": ["align_selection_chapters"], "cleared": [], "ok": True},
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.align_narrative_plan_to_selection",
        lambda _c: [],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.repair_edl_audit",
        lambda _c, arts: ({**dict(arts), "verdict": "warn", "blocking_issues": []}, []),
    )
    monkeypatch.setattr(ctx, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active", lambda _c: False
    )
    monkeypatch.setattr(
        ctx,
        "artifact_exists",
        lambda rel: rel
        in {"master/selection.json", "run_meta.json", "master/narrative_plan.json"},
    )
    monkeypatch.setattr(
        ctx,
        "read_json",
        lambda rel: {
            "master/selection.json": {"ordered_segment_ids": ["seg_001"]},
            "run_meta.json": {},
            "master/narrative_plan.json": {"chapters": []},
        }.get(rel, {}),
    )

    maybe_repair_after_narrative_audit(ctx, {"verdict": "fail", "blocking_issues": []})
    spoofed = [w for w in writes if w[0] == "master/selection.json"]
    assert not spoofed, f"selection must not write via write_validated: {spoofed}"
    assert not any(sk == "selection_order_sanitize" for _, sk in writes)


def test_s2_repair_edl_narrative_selection_never_blank_drops(ctx: RunContext) -> None:
    from interview_mux.artifact_repairs import repair_edl_narrative_selection

    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    # >8 words and >=8s so blank heuristic does not fire.
                    "text": (
                        "Substantial answer on the record about the buyer "
                        "reaction and the follow through."
                    ),
                    "start_ms": 0,
                    "end_ms": 12000,
                },
                {
                    "segment_id": "seg_blank",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Okay.",
                    "start_ms": 12000,
                    "end_ms": 12500,
                },
            ]
        },
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_blank"],
            "excluded_segment_ids": [],
            "chapters": [{"title": "A", "segment_ids": ["seg_001"]}],
        },
        stage_key="full_master_ranking",
    )
    notes = repair_edl_narrative_selection(ctx)
    assert not any(
        isinstance(n, dict) and n.get("action") == "uncover_orphan_mapping"
        for n in notes
    )
    sel = ctx.read_json("master/selection.json")
    ordered = list(sel.get("ordered_segment_ids") or [])
    assert ordered, "empty-order guard must keep air order non-empty"
    assert "seg_001" in ordered
    # Non-hard-keep micro blank may exclude; must never wipe the whole order.
    assert not any(
        isinstance(n, dict) and n.get("action") == "keep_blank_segments_refuse_empty_order"
        for n in notes
    ) or "seg_001" in ordered


def test_s7_repair_loop_never_remutates(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.apply_edl_narrative_metadata_align",
        lambda _c: {"notes": ["align_narrative_plan"], "cleared": [], "ok": True},
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.repair_edl_audit",
        lambda _c, arts: (
            {**dict(arts), "verdict": "fail", "blocking_issues": [{"issue": "still"}]},
            [{"action": "demote_noop"}],
        ),
    )
    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.plan_edl_narrative_remutate",
        lambda *_a, **_k: calls.append("plan") or {"exhausted": False},
    )
    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.apply_edl_narrative_remutate",
        lambda *_a, **_k: calls.append("apply") or {"ok": True},
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active", lambda _c: False
    )
    monkeypatch.setattr(ctx, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ctx,
        "artifact_exists",
        lambda rel: rel in {"master/selection.json", "run_meta.json"},
    )
    monkeypatch.setattr(
        ctx,
        "read_json",
        lambda rel: {
            "master/selection.json": {"ordered_segment_ids": ["seg_001"]},
            "run_meta.json": {},
        }.get(rel, {}),
    )

    out = maybe_repair_after_narrative_audit(
        ctx, {"verdict": "fail", "blocking_issues": [{"issue": "x"}]}
    )
    assert calls == []
    assert "remutate" not in out
    assert out.get("verdict") == "fail"


def test_s6_prepare_does_not_persist_transitions(ctx: RunContext) -> None:
    from interview_mux.stages.edl_narrative_audit import (
        prepare_edl_narrative_audit_inputs,
    )

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002"]},
        stage_key="full_master_ranking",
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "transition",
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "Bridge text.",
                }
            ]
        },
        stage_key="transitions",
        skip_handoff=True,
    )
    before = ctx.read_json("master/transitions.json")
    payload = prepare_edl_narrative_audit_inputs(ctx)
    assert payload["transitions"] == before
    assert ctx.read_json("master/transitions.json") == before
    assert not ctx.artifact_exists("master/seam_occupancy.json")


def test_s8_metadata_align_skips_coverage_write(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.edl_narrative_remutate import apply_edl_narrative_metadata_align

    writes: list[str] = []
    monkeypatch.setattr(
        "interview_mux.artifact_writes.write_validated_artifact",
        lambda _c, rel, _doc, **_k: writes.append(str(rel)),
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "chapters": [{"title": "A", "segment_ids": ["seg_001"]}],
            "excluded_segment_ids": [],
        },
        stage_key="full_master_ranking",
        skip_handoff=True,
    )
    ctx.write_json(
        "master/coverage_audit.json",
        {
            "coverage_score": 0.5,
            "topic_mappings": [],
            "claim_mappings": [],
            "missing_coverage": [],
        },
        stage_key="topic_coverage_audit",
        skip_handoff=True,
    )
    apply_edl_narrative_metadata_align(ctx)
    assert "master/coverage_audit.json" not in writes
