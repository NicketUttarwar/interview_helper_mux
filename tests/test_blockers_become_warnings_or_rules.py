"""Quality judgements never block; structural guards keep a heal that works (ISSUES 185).

The maintainer asked to simplify: every hard blocker becomes a warning or a
simple deterministic rule. These tests pin the central switches so a later
change cannot quietly turn a judgement back into a stall.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "blockers_advisory")


def _put(ctx, rel: str, doc) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc), encoding="utf-8")


# --- lints ---------------------------------------------------------------


def test_only_structural_lints_block() -> None:
    from interview_mux.deterministic_lint import split_lint_errors

    blocking, advisory = split_lint_errors(
        [
            "ordered segment seg_041 not in manifest",
            "speakers list empty",
            "transition exceeds 30 words (41)",
            "high gap segment seg_012 has no interviewer line",
            "micro-segment explosion (>200 boundaries)",
            "lint internal error: hard_keep_segment_ids() got an unexpected keyword",
        ]
    )
    assert blocking == ["ordered segment seg_041 not in manifest", "speakers list empty"]
    assert len(advisory) == 4


def test_stage_acceptance_ignores_quality_and_crashing_lints(ctx, monkeypatch) -> None:
    from interview_mux import deterministic_lint
    from interview_mux.stage_acceptance import _lint_artifact_doc

    monkeypatch.setitem(
        deterministic_lint._LINTERS, "transitions", lambda _a, _c: ["transition exceeds 30 words (41)"]
    )
    assert _lint_artifact_doc("transitions", {}, ctx) == []

    def _boom(_a, _c):
        raise TypeError("lint bug")

    monkeypatch.setitem(deterministic_lint._LINTERS, "transitions", _boom)
    assert _lint_artifact_doc("transitions", {}, ctx) == []

    monkeypatch.setitem(
        deterministic_lint._LINTERS, "transitions", lambda _a, _c: ["ordered segment x not in manifest"]
    )
    assert _lint_artifact_doc("transitions", {}, ctx) == ["ordered segment x not in manifest"]


# --- transitions synthesis ----------------------------------------------


def test_a_transition_synthesis_refused_is_not_missing_audio(ctx) -> None:
    from interview_mux.spoken_copy_guard import script_hash
    from interview_mux.transition_vo import current_transition_pairs_missing

    text = "An ungrounded bridge the guard refused."
    _put(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_a", "seg_b"]})
    _put(
        ctx,
        "master/transitions.json",
        {"transitions": [{"after_segment_id": "seg_a", "before_segment_id": "seg_b", "text": text}]},
    )
    assert current_transition_pairs_missing(ctx) == ["seg_a->seg_b"]
    _put(ctx, "mastering/vo_synthesize.json", {"unspeakable_pairs": [f"seg_a->seg_b:{script_hash(text)}"]})
    assert current_transition_pairs_missing(ctx) == []
    # New text gets a fresh attempt.
    _put(
        ctx,
        "master/transitions.json",
        {"transitions": [{"after_segment_id": "seg_a", "before_segment_id": "seg_b", "text": text + " Again."}]},
    )
    assert current_transition_pairs_missing(ctx) == ["seg_a->seg_b"]


# --- publishability ------------------------------------------------------


def test_advisory_publishability_classes_never_raise(ctx) -> None:
    from interview_mux.publishability_boundary import (
        PublishabilityReport,
        PublishabilityViolation,
        commit_or_block,
    )

    report = PublishabilityReport(
        checkpoint="pre_mix",
        ok=False,
        violations=[
            PublishabilityViolation("incomplete_cut_unresolved", "critical_junction_residual", "x"),
            PublishabilityViolation("vo_audibility_drift", "phantom_vo", "y"),
        ],
    )
    commit_or_block(ctx, report, enforce=True)  # does not raise


def test_a_structural_publishability_class_still_raises(ctx) -> None:
    from interview_mux.publishability_boundary import (
        PublishabilityBlocked,
        PublishabilityReport,
        PublishabilityViolation,
        commit_or_block,
    )

    report = PublishabilityReport(
        checkpoint="pre_mix",
        ok=False,
        violations=[
            PublishabilityViolation("incomplete_cut_unresolved", "critical_junction_residual", "x"),
            PublishabilityViolation("omit_collateral_vo_strip", "unseated_required_vo", "vo_1"),
        ],
    )
    with pytest.raises(PublishabilityBlocked) as info:
        commit_or_block(ctx, report, enforce=True)
    assert info.value.error_class == "omit_collateral_vo_strip"


# --- post-master quality -------------------------------------------------


def test_pmq_structural_checks_are_master_integrity_only() -> None:
    from interview_mux.aspirational_quality import STRUCTURAL_PMQ_CHECKS

    assert STRUCTURAL_PMQ_CHECKS == {
        "master_exists_nonempty",
        "seam_commitment",
        "audible_script_hash_agreement",
    }


@pytest.mark.parametrize(
    ("check", "stage"),
    [
        ("audible_script_hash_agreement", "vo_synthesize"),
        ("seam_commitment", "junction_snip_qa"),
        ("master_exists_nonempty", "mix"),
    ],
)
def test_each_structural_pmq_failure_has_a_heal(ctx, check, stage) -> None:
    from interview_mux.heal_routing import classify_heal_error

    route = classify_heal_error(f"Post-master quality failed: {check}", ctx, stage="master_finalize")
    assert route is not None and route.from_stage == stage


# --- lay-up --------------------------------------------------------------


def test_a_layup_row_failing_qc_becomes_a_typed_skip(ctx) -> None:
    from interview_mux.nugget_layup import PLAN_REL, is_justified_skip_row, skip_rows_failing_layup_qc

    _put(
        ctx,
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_010", "seg_011"],
            "layups": [
                {"target_segment_id": "seg_010", "text": "Canned air.", "nugget_ids": ["n1"]},
                {"target_segment_id": "seg_011", "text": "Fine copy here.", "nugget_ids": ["n2"]},
            ],
        },
    )
    stamped = skip_rows_failing_layup_qc(
        ctx, {"ok": False, "errors": ["canned_air[seg_010]: generic hinge"]}
    )
    assert stamped == 1
    rows = {r["target_segment_id"]: r for r in ctx.read_json(PLAN_REL)["layups"]}
    assert rows["seg_010"]["skip"] is True
    assert is_justified_skip_row(rows["seg_010"])
    assert not rows["seg_011"].get("skip")


# --- LLM runner ----------------------------------------------------------


def test_second_attempt_accepts_valid_artifacts_whatever_the_need_label() -> None:
    import inspect

    from interview_mux import llm_simple

    src = inspect.getsource(llm_simple.run_llm_stage_simple)
    assert "accepting partial with valid artifacts" in src
    assert "and not soft_needs" not in src
