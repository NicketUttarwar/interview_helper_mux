"""Ranking must persist a usable order instead of looping on CTA vs must-keep."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from interview_mux.llm_simple import run_llm_stage_simple
from interview_mux.media_ip_cta import ranking_cta_omit_ids
from interview_mux.selection_order_repair import fill_chapter_list_membership_gaps
from interview_mux.stages.selection import (
    commit_persistable_ranking_from_last_envelope,
    ranking_artifacts_persistable,
)
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_fill_chapter_list_membership_gaps_assigns_to_previous_chapter() -> None:
    chapters = [
        {"title": "Open", "segment_ids": ["seg_001"]},
        {"title": "Finale", "segment_ids": ["seg_003"]},
    ]
    filled, ids = fill_chapter_list_membership_gaps(
        chapters, ["seg_001", "seg_002", "seg_003"]
    )
    assert ids == ["seg_002"]
    assert filled[0]["segment_ids"] == ["seg_001", "seg_002"]
    assert filled[1]["segment_ids"] == ["seg_003"]


def test_fill_chapter_list_membership_gaps_does_not_dump_onto_finale() -> None:
    chapters = [
        {"title": "A", "segment_ids": ["seg_001", "seg_002"]},
        {"title": "B", "segment_ids": ["seg_005"]},
    ]
    filled, ids = fill_chapter_list_membership_gaps(
        chapters, ["seg_001", "seg_002", "seg_003", "seg_004", "seg_005"]
    )
    assert set(ids) == {"seg_003", "seg_004"}
    assert "seg_003" in filled[0]["segment_ids"]
    assert "seg_005" in filled[1]["segment_ids"]
    assert filled[1]["segment_ids"][-1] == "seg_005"


def test_ranking_cta_omit_ids_strips_sponsor_text(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cta_omit")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_story", text="We studied the tumor biology."),
            minimal_manifest_segment(
                "seg_cta", text="Please subscribe to the show and hit like."
            ),
        ),
        skip_handoff=True,
    )
    omitted = ranking_cta_omit_ids(ctx)
    assert "seg_cta" in omitted
    assert "seg_story" not in omitted


def test_llm_simple_persists_ranking_partial_with_ordered_ids() -> None:
    ctx = MagicMock()
    ctx.mark_done = MagicMock()
    persisted: list[dict] = []
    envelope = {
        "status": "partial",
        "needs": [
            {
                "type": "operator",
                "stage": "",
                "reason": "must_keep vs CTA",
            }
        ],
        "artifacts": {"ordered_segment_ids": ["seg_001", "seg_002"]},
    }

    with patch("interview_mux.llm_simple.ensure_analysis_workspace"):
        with patch("interview_mux.llm_simple.run_prompt_envelope", return_value=envelope):
            out = run_llm_stage_simple(
                ctx,
                "full_master_ranking",
                "selection/full-master-ranking.system.txt",
                lambda _ctx: {"task": "rank"},
                lambda _ctx, arts: persisted.append(arts),
            )

    assert persisted == [{"ordered_segment_ids": ["seg_001", "seg_002"]}]
    ctx.mark_done.assert_called_once_with("full_master_ranking")
    assert out["status"] == "partial"


def test_commit_persistable_ranking_from_last_envelope(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "rank_heal")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_001",
                start_ms=0,
                end_ms=12000,
                text="We studied the tumor biology across several years of clinical work.",
            ),
            minimal_manifest_segment(
                "seg_002",
                start_ms=12000,
                end_ms=24000,
                text="The trial changed how we think about treating late-stage disease.",
            ),
        ),
        skip_handoff=True,
    )
    call_dir = (
        ctx.run_dir
        / ".pending_writes"
        / "full_master_ranking"
        / "understanding"
        / "llm_calls"
        / "full_master_ranking"
        / "attempt_001"
    )
    call_dir.mkdir(parents=True, exist_ok=True)
    (call_dir / "01_primary.json").write_text(
        json.dumps(
            {
                "response": {
                    "parsed_envelope": {
                        "status": "partial",
                        "artifacts": {
                            "ordered_segment_ids": ["seg_001", "seg_002"],
                            "excluded_segment_ids": [],
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert ranking_artifacts_persistable({"ordered_segment_ids": ["seg_001"]})
    assert commit_persistable_ranking_from_last_envelope(ctx)
    sel = ctx.read_json("master/selection.json")
    assert sel["ordered_segment_ids"] == ["seg_001", "seg_002"]
    assert ctx.is_done("full_master_ranking")


def test_llm_simple_persists_transitions_partial_instead_of_ranking_rerun() -> None:
    ctx = MagicMock()
    ctx.mark_done = MagicMock()
    persisted: list[dict] = []
    envelope = {
        "status": "partial",
        "needs": [
            {
                "type": "rerun_stage",
                "stage": "full_master_ranking",
                "reason": "The locked selection order conflicts with its exclusion evidence",
            }
        ],
        "artifacts": {
            "transitions": [
                {
                    "after_segment_id": "seg_005",
                    "before_segment_id": "seg_006",
                    "text": "On the trial design.",
                    "type": "topic_shift",
                }
            ]
        },
    }

    with patch("interview_mux.llm_simple.ensure_analysis_workspace"):
        with patch("interview_mux.llm_simple.run_prompt_envelope", return_value=envelope):
            out = run_llm_stage_simple(
                ctx,
                "transitions",
                "assembly/transitions.system.txt",
                lambda _ctx: {"task": "bridges"},
                lambda _ctx, arts: persisted.append(arts),
            )

    assert persisted and persisted[0]["transitions"]
    ctx.mark_done.assert_called_once_with("transitions")
    assert out["status"] == "partial"


def test_llm_simple_persists_empty_transitions_when_blocked_without_artifacts() -> None:
    ctx = MagicMock()
    ctx.mark_done = MagicMock()
    persisted: list[dict] = []
    envelope = {
        "status": "blocked",
        "needs": [
            {
                "type": "rerun_stage",
                "stage": "full_master_ranking",
                "reason": "Reconcile the locked order with the exclusion manifest",
            }
        ],
    }

    with patch("interview_mux.llm_simple.ensure_analysis_workspace"):
        with patch("interview_mux.llm_simple.run_prompt_envelope", return_value=envelope):
            out = run_llm_stage_simple(
                ctx,
                "transitions",
                "assembly/transitions.system.txt",
                lambda _ctx: {"task": "bridges"},
                lambda _ctx, arts: persisted.append(arts),
            )

    assert persisted == [{"transitions": []}]
    assert ctx.mark_done.call_count == 1
    assert out["artifacts"] == {"transitions": []}


def test_llm_simple_fail_open_edl_narrative_audit_as_warn() -> None:
    ctx = MagicMock()
    ctx.mark_done = MagicMock()
    persisted: list[dict] = []
    envelope = {
        "status": "partial",
        "needs": [{"type": "rerun_stage", "stage": "full_master_ranking"}],
        "artifacts": {"verdict": "fail", "blocking_issues": []},
    }

    with patch("interview_mux.llm_simple.ensure_analysis_workspace"):
        with patch("interview_mux.llm_simple.run_prompt_envelope", return_value=envelope):
            out = run_llm_stage_simple(
                ctx,
                "edl_narrative_audit",
                "selection/edl-narrative-audit.system.txt",
                lambda _ctx: {"task": "audit"},
                lambda _ctx, arts: persisted.append(arts),
            )

    assert persisted
    assert persisted[-1]["verdict"] == "warn"
    assert ctx.mark_done.call_count == 1
    assert out["artifacts"]["verdict"] == "warn"


def test_hard_keep_in_ordered_ids(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "ranking_hard_keep")
    monkeypatch.setattr(
        "interview_mux.hard_keep.hard_keep_segment_ids",
        lambda _ctx: {"seg_001"},
    )
    from interview_mux.hard_keep import enforce_hard_keeps

    healed = enforce_hard_keeps(
        ctx, {"ordered_segment_ids": ["seg_045"], "excluded_segment_ids": ["seg_001"]}
    )
    assert "seg_001" in [str(s) for s in (healed.get("ordered_segment_ids") or [])]
