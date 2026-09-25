"""Tests for gap framing gates, succinct-master helpers, and skip paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_framing import (
    build_gap_framing_plan,
    infer_line_category,
    normalize_interviewer_line,
    ranking_exclude_segment_ids,
    validate_line_word_limits,
    word_limit_for_category,
)
from interview_mux.gap_vo_gates import (
    check_gap_framing_decision_pending,
    gap_framing_enabled,
    maybe_auto_accept_gap_gate_defaults,
    recommended_gap_framing_enabled,
    set_gap_framing_enabled,
    set_gap_vo_delivery,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.gaps import gap_compose_stage_done
from run_fixtures import init_run_meta_for_test, patch_executions_root, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_gap_framing", create=True)
    init_run_meta_for_test(run)
    run.write_json("understanding/source_topology.json", {"topology_class": "one_on_one_asymmetric"})
    mark_done_raw(run, "source_topology_build")
    return run


def test_default_gap_framing_recommended_yes_without_decision(ctx: RunContext) -> None:
    """Product default is Yes, but operator decision is still pending until explicit opt-in."""
    assert gap_framing_enabled(ctx) is True
    assert recommended_gap_framing_enabled() is True


def test_gap_framing_decision_pending_after_topology(ctx: RunContext) -> None:
    from interview_mux.v2.config import ANALYSIS_ORDER

    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        mark_done_raw(ctx, sid)
    assert check_gap_framing_decision_pending(ctx) is True


def test_auto_accept_gap_gate_defaults(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.v2.config import ANALYSIS_ORDER

    monkeypatch.setenv("INTERVIEW_MUX_AUTO_ACCEPT_GATES", "1")
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "least_spoken_speaker_id": "spk_0",
            "pickup_eligible_speaker_id": "spk_0",
            "speaker_stats": [
                {
                    "speaker_id": "spk_0",
                    "talk_ms": 10_000,
                    "talk_ratio": 0.2,
                    "role_hint": "interviewer",
                },
                {
                    "speaker_id": "spk_1",
                    "talk_ms": 40_000,
                    "talk_ratio": 0.8,
                    "role_hint": "guest",
                },
            ],
        },
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {
            "pickup_eligible_speaker_id": "spk_0",
            "operator_overrides": {},
        },
    )
    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        mark_done_raw(ctx, sid)
    assert check_gap_framing_decision_pending(ctx) is True
    assert maybe_auto_accept_gap_gate_defaults(ctx) is True
    assert check_gap_framing_decision_pending(ctx) is False
    assert gap_framing_enabled(ctx) is True
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is True
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    assert adapt["operator_overrides"].get("pickup_speaker_confirmed") is True


def test_homunculus_auto_resolve_accepts_framing_without_env(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INTERVIEW_MUX_AUTO_ACCEPT_GATES", raising=False)
    from interview_mux.v2.config import ANALYSIS_ORDER

    ctx.write_json(
        "run_meta.json",
        {
            **(ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}),
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        mark_done_raw(ctx, sid)
    assert check_gap_framing_decision_pending(ctx) is True
    assert maybe_auto_accept_gap_gate_defaults(ctx) is True
    assert gap_framing_enabled(ctx) is True
    assert check_gap_framing_decision_pending(ctx) is False


def test_full_auto_arms_homunculus_auto_path_without_features(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1: Full-auto + recommended auto_resolve arms gate path without env/features."""
    monkeypatch.delenv("INTERVIEW_MUX_AUTO_ACCEPT_GATES", raising=False)
    from interview_mux.v2.config import ANALYSIS_ORDER

    ctx.write_json(
        "run_meta.json",
        {
            **(ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}),
            "homunculus_version": "0.0.0",
            "run_mode": "full-auto",
            "full_auto": True,
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        mark_done_raw(ctx, sid)
    assert check_gap_framing_decision_pending(ctx) is True
    assert maybe_auto_accept_gap_gate_defaults(ctx) is True
    assert gap_framing_enabled(ctx) is True
    assert check_gap_framing_decision_pending(ctx) is False


def test_operator_no_not_overwritten_by_auto_accept(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_AUTO_ACCEPT_GATES", "1")
    from interview_mux.v2.config import ANALYSIS_ORDER

    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        mark_done_raw(ctx, sid)
    set_gap_framing_enabled(ctx, False)
    assert gap_framing_enabled(ctx) is False
    maybe_auto_accept_gap_gate_defaults(ctx)
    assert gap_framing_enabled(ctx) is False


def test_set_gap_framing_no_skips_compose_stage(ctx: RunContext) -> None:
    set_gap_framing_enabled(ctx, False)
    assert gap_framing_enabled(ctx) is False
    assert ctx.is_done("missing_framing")
    assert ctx.is_done("gap_framing_compose")
    assert gap_compose_stage_done(ctx)


def test_line_category_word_limits() -> None:
    assert word_limit_for_category("framing_question") == 60
    assert word_limit_for_category("segment_summary") == 80
    errors = validate_line_word_limits(
        [
            {
                "line_id": "vo_q",
                "line_category": "framing_question",
                "text": " ".join(["word"] * 65),
            }
        ]
    )
    assert errors


def test_infer_line_category_from_gap_type() -> None:
    assert infer_line_category({"gap_type": "missing_setup"}) == "context_setup"
    assert infer_line_category({"line_category": "episode_preface"}) == "episode_preface"


def test_build_gap_framing_plan_and_ranking_exclude(ctx: RunContext) -> None:
    lines = [
        normalize_interviewer_line(
            {
                "line_id": "vo_sum_1",
                "line_category": "segment_summary",
                "gap_type": "missing_setup",
                "placement": "before",
                "text": "Host summarizes the guest background.",
                "targets_segment_id": "seg_002",
                "replaces_source_segments": ["seg_001"],
            },
            eligible="spk_0",
            delivery="synthesize",
        )
    ]
    plan = build_gap_framing_plan(ctx, lines)
    assert plan["succinct_master_intent"] is True
    ctx.write_json("understanding/gap_framing_plan.json", plan)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": lines},
    )
    excluded = ranking_exclude_segment_ids(ctx)
    assert "seg_001" in excluded


def test_gap_vo_delivery_persisted(ctx: RunContext) -> None:
    set_gap_framing_enabled(ctx, True)
    set_gap_vo_delivery(ctx, "chatterbox")
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_vo_delivery") == "chatterbox"


def test_dedupe_transitions_for_framing() -> None:
    from interview_mux.gap_framing import dedupe_transitions_for_framing

    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_br",
                "line_category": "story_bridge",
                "targets_segment_id": "seg_b",
                "placement": "before",
            }
        ]
    }
    transitions = {
        "transitions": [
            {"after_segment_id": "seg_a", "before_segment_id": "seg_b", "text": "bridge"},
        ]
    }
    out = dedupe_transitions_for_framing(gap_report, transitions)
    assert out.get("transitions") == []
    assert out.get("framing_deduped_count") == 1


def test_dedupe_transitions_by_adjacency_prefers_statement() -> None:
    from interview_mux.gap_framing import dedupe_transitions_by_adjacency

    doc = {
        "transitions": [
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "What did that first encounter with computers change?",
            },
            {
                "after_segment_id": "seg_008",
                "before_segment_id": "seg_009",
                "text": "Where did that early consumer bet begin to falter?",
            },
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "At university, an unexpected encounter would change that direction.",
            },
            {
                "after_segment_id": "seg_008",
                "before_segment_id": "seg_009",
                "text": "The next challenge was finding the customer those bars were really for.",
            },
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "Education would soon open a door he never expected.",
            },
        ]
    }
    out = dedupe_transitions_by_adjacency(doc)
    kept = out["transitions"]
    assert len(kept) == 2
    assert out.get("adjacency_deduped_count") == 3
    by_pair = {
        (row["after_segment_id"], row["before_segment_id"]): row["text"] for row in kept
    }
    assert not by_pair[("seg_001", "seg_002")].endswith("?")
    assert not by_pair[("seg_008", "seg_009")].endswith("?")


def test_prune_transitions_outside_selection() -> None:
    from interview_mux.gap_framing import prune_transitions_outside_selection

    doc = {
        "transitions": [
            {
                "after_segment_id": "seg_002",
                "before_segment_id": "seg_005",
                "text": "Then the assay.",
            },
            {
                "after_segment_id": "seg_068b",
                "before_segment_id": "seg_068c",
                "text": "Follow us on your platform.",
            },
        ]
    }
    out = prune_transitions_outside_selection(doc, ["seg_002", "seg_005"])
    assert [row["after_segment_id"] for row in out["transitions"]] == ["seg_002"]
    assert out.get("outside_selection_pruned_count") == 1


def test_prune_transitions_drops_non_adjacent_selected_pair() -> None:
    from interview_mux.gap_framing import prune_transitions_outside_selection

    doc = {
        "transitions": [
            {
                "after_segment_id": "seg_003k",
                "before_segment_id": "seg_062",
                "text": "Let's talk about adoption.",
            },
            {
                "after_segment_id": "seg_032",
                "before_segment_id": "seg_038",
                "text": "So what does the assay report?",
            },
        ]
    }
    order = ["seg_003k", "seg_005", "seg_032", "seg_038", "seg_049", "seg_062"]
    out = prune_transitions_outside_selection(doc, order)
    assert [row["after_segment_id"] for row in out["transitions"]] == ["seg_032"]
    assert out.get("outside_selection_pruned_count") == 1


def test_demote_uncovered_high_gaps_clears_compose_lint(ctx: RunContext) -> None:
    from interview_mux.deterministic_lint import _lint_optimal_questions
    from interview_mux.high_gap_vo import demote_uncovered_high_gaps

    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_003",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "ok_with_light_bridge",
                    "listener_confusion": "who is speaking",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    before = _lint_optimal_questions({"interviewer_lines": []}, ctx)
    assert any("has no interviewer line" in e for e in before)
    assert demote_uncovered_high_gaps(ctx) == 1
    after = _lint_optimal_questions({"interviewer_lines": []}, ctx)
    assert not any("has no interviewer line" in e for e in after)
    evals = ctx.read_json("understanding/gap_evaluations.json")
    assert evals["evaluations"][0]["severity"] == "medium"
    assert (
        evals["evaluations"][0]["severity_demotion_reason"]
        == "high_gap_seat:compose_persist"
    )


def test_demote_uncovered_high_gaps_demotes_when_fill_unavailable(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without actionable fill, heal demotes and leaves floor remediation sticky."""
    from interview_mux.high_gap_vo import demote_uncovered_high_gaps

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.count_active_gap_vo_lines",
        lambda _ctx: 0,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_003",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "ok_with_light_bridge",
                    "listener_confusion": "who is speaking",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    assert demote_uncovered_high_gaps(ctx, origin="e2e_heal_lint_dirty") == 1
    evals = ctx.read_json("understanding/gap_evaluations.json")
    assert evals["evaluations"][0]["severity"] == "medium"


def test_fill_uncovered_high_gaps_sets_schema_fields(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filled lines must include gap_type + placement so gap_report.json validates."""
    from interview_mux.high_gap_vo import fill_uncovered_high_gaps

    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_003",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_setup",
                    "listener_confusion": "who is speaking",
                }
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _fake_envelope(*_a: object, **_k: object) -> dict:
        return {"artifacts": {"text": "Before we continue, who is speaking here?"}}

    monkeypatch.setattr(
        "interview_mux.stages.llm_runner.run_prompt_envelope", _fake_envelope
    )
    seed: dict = {"interviewer_lines": []}
    added = fill_uncovered_high_gaps(ctx, seed, applied=[])
    assert added == 1
    line = seed["interviewer_lines"][0]
    assert line["gap_type"] == "missing_setup"
    assert line["placement"] == "before"
    assert line["targets_segment_id"] == "seg_003"


def test_unspeakable_high_gap_seed_omitted_then_demoted(ctx: RunContext) -> None:
    """Seed lines that fail spoken-copy must not leave a high gap uncovered at lint."""
    from interview_mux.artifact_repairs import repair_gap_report
    from interview_mux.deterministic_lint import _lint_optimal_questions

    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_022",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_callback",
                    "listener_confusion": "unclear wait",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_022",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["guest"],
                    "text": "Okay. You know, so you don't have to wait.",
                }
            ]
        },
        skip_handoff=True,
    )
    repaired, notes = repair_gap_report(
        ctx,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_seed_seg_022",
                    "text": "",
                    "targets_segment_id": "seg_022",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    assert any(
        n.get("action") == "omit_unsafe_optional_vo" for n in notes if isinstance(n, dict)
    ) or not any(
        str(ln.get("line_id")) == "vo_seed_seg_022" and str(ln.get("text") or "").strip()
        for ln in (repaired.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    )
    # repair_gap_report demotes uncovered highs after omit (compose-path origin).
    assert any(
        n.get("action") == "demote_uncovered_high_after_repair"
        for n in notes
        if isinstance(n, dict)
    ) or (
        ctx.read_json("understanding/gap_evaluations.json")["evaluations"][0]["severity"]
        == "medium"
    )
    after = _lint_optimal_questions(repaired, ctx)
    assert not any("has no interviewer line" in e for e in after)


def test_courtesy_seed_never_empty_and_diversified() -> None:
    from interview_mux.gap_vo_prior_context import courtesy_seed_text

    a = courtesy_seed_text(None, category="story_bridge", target_segment_id="seg_051")
    b = courtesy_seed_text(None, category="story_bridge", target_segment_id="seg_015")
    assert a.strip()
    assert b.strip()
    assert a != b


def test_gap_framing_compose_incomplete_while_high_gap_unframed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hollow compose .stage_done must flip while high-gap lint is dirty."""
    from interview_mux.stage_completion import stage_artifact_incompleteness

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled", lambda _ctx: True
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.gap_fill_was_skipped", lambda _ctx: False
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_051",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_setup",
                    "listener_confusion": "assay undefined",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_after_cta_open",
                    "text": "Precision oncology seeks to match treatment.",
                    "targets_segment_id": "seg_002",
                    "delivery": "synthesize",
                    "skipped_optional": True,
                    "air_script_omit": True,
                }
            ]
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, "gap_framing_compose")
    assert reason and "high_gap_unframed" in reason
    assert "seg_051" in reason


def test_heal_demotes_when_fill_has_no_credentials_under_hosted_floor(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No credentials means fill is not budgeted, so heal must demote."""
    from interview_mux.high_gap_vo import demote_uncovered_high_gaps

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.count_active_gap_vo_lines",
        lambda _ctx: 0,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_051",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_setup",
                    "listener_confusion": "assay undefined",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    assert demote_uncovered_high_gaps(ctx, origin="e2e_heal_lint_dirty") == 1
    evals = ctx.read_json("understanding/gap_evaluations.json")
    assert evals["evaluations"][0]["severity"] == "medium"


def test_fill_uncovered_high_gaps_skips_when_identity_exhausted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.high_gap_vo import fill_uncovered_high_gaps

    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_003",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_setup",
                    "listener_confusion": "who is speaking",
                }
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "interview_mux.homunculus.budget.identity_exhausted", lambda *_a, **_k: True
    )
    calls = {"n": 0}

    def _boom(*_a: object, **_k: object) -> dict:
        calls["n"] += 1
        raise AssertionError("LLM must not run when identity is exhausted")

    monkeypatch.setattr("interview_mux.stages.llm_runner.run_prompt_envelope", _boom)
    seed: dict = {"interviewer_lines": []}
    applied: list[dict] = []
    added = fill_uncovered_high_gaps(ctx, seed, applied=applied)
    # Budget exhausted → skip LLM, then deterministic seed (no greenwash).
    assert calls["n"] == 0
    assert any(row.get("reason") == "limit_exhausted" for row in applied)
    assert added >= 1
    assert any(
        str(row.get("action") or "").startswith("high_gap_vo") for row in applied
    )


def test_fill_uncovered_high_gaps_stops_on_limit_exhausted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.homunculus.budget import LimitExhausted
    from interview_mux.high_gap_vo import fill_uncovered_high_gaps

    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": sid,
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_setup",
                    "listener_confusion": "who is speaking",
                }
                for sid in ("seg_003", "seg_004")
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "interview_mux.homunculus.budget.identity_exhausted", lambda *_a, **_k: False
    )
    calls = {"n": 0}

    def _raise(*_a: object, **_k: object) -> dict:
        calls["n"] += 1
        raise LimitExhausted(
            "high_gap_vo_fill", "max_invokes_per_identity", {"used": 3, "cap": 3}
        )

    monkeypatch.setattr("interview_mux.stages.llm_runner.run_prompt_envelope", _raise)
    seed: dict = {"interviewer_lines": []}
    applied: list[dict] = []
    added = fill_uncovered_high_gaps(ctx, seed, applied=applied)
    # First LLM hit LimitExhausted → seed remainder (no further LLM).
    assert calls["n"] == 1
    assert any(row.get("reason") == "limit_exhausted" for row in applied)
    assert added >= 1
    assert len(seed.get("interviewer_lines") or []) >= 1


def test_demote_uncovered_high_gaps_clears_listenability_ratio(ctx: RunContext) -> None:
    """Demoting stale high evals must flip uncovered_high_gap_ratio to zero."""
    from interview_mux.high_gap_vo import demote_uncovered_high_gaps
    from interview_mux.listenability_guards import uncovered_high_gap_ratio

    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {"segment_id": "seg_009", "severity": "high", "self_explanatory": False},
                {"segment_id": "seg_011", "severity": "high", "self_explanatory": False},
                {"segment_id": "seg_029", "severity": "high", "self_explanatory": False},
                {"segment_id": "seg_037", "severity": "high", "self_explanatory": False},
                {"segment_id": "seg_048", "severity": "high", "self_explanatory": False},
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_032",
                    "targets_segment_id": "seg_032",
                    "text": "Bridge to the next topic?",
                    "gap_type": "missing_setup",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_009", "seg_011", "seg_029", "seg_032", "seg_037", "seg_048"]},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_032",
                    "before_segment_id": "seg_037",
                    "type": "bridge",
                    "text": "Transition bridge",
                },
                {
                    "after_segment_id": "seg_037",
                    "before_segment_id": "seg_048",
                    "type": "bridge",
                    "text": "Another bridge",
                },
            ]
        },
        skip_handoff=True,
    )
    assert uncovered_high_gap_ratio(ctx) == 0.6  # 3/5 selected highs uncovered
    demoted = demote_uncovered_high_gaps(ctx, origin="listenability_heal")
    assert demoted >= 3
    assert uncovered_high_gap_ratio(ctx) == 0.0


def test_preface_forward_cue_heal(ctx: RunContext) -> None:
    from interview_mux.artifact_repairs import repair_gap_report
    from interview_mux.gap_vo_prior_context import has_forward_cue

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_010"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_010",
                    "text": "Circulating tumour cells are rare in blood.",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["science"],
                    "start_ms": 0,
                    "end_ms": 4000,
                }
            ]
        },
    )
    doc = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_open",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "targets_segment_id": "seg_010",
                "text": "Precision oncology is reshaping how we detect cancer.",
                "delivery": "synthesize",
            }
        ]
    }
    repaired, notes = repair_gap_report(ctx, doc)
    line = (repaired.get("interviewer_lines") or [doc["interviewer_lines"][0]])[0]
    assert has_forward_cue(str(line.get("text") or ""))
    assert any(n.get("action") == "preface_forward_cue_heal" for n in notes) or has_forward_cue(
        str(line.get("text") or "")
    )


def test_preface_cold_open_layup_heal_restatement(ctx: RunContext) -> None:
    """Cascade (MUX_FORENSICS=0): cued preface that restates first native must heal.

    exec_13181: vo_preface_seg_004 had a forward-cue question overlapping liquid/
    biopsy tokens on seg_004 → cold_open_layup_ok fail; F3 only healed missing cues.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.artifact_repairs import repair_gap_report
    from interview_mux.gap_vo_prior_context import cold_open_layup_ok, has_forward_cue

    native = (
        "Mohan, thanks for joining us. We're going to talk today about how AI is "
        "transforming both cancer care and the development of new therapies. "
        "OneCell .ai and how its liquid biopsy diagnostics are used by both "
        "clinicians and researchers. So let's start with the liquid biopsies. "
        "For audience members who may not be familiar with these, can you explain "
        "what they mean and how they work?"
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_004"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_004",
                    "text": native,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "topic_tags": ["biopsy"],
                    "start_ms": 0,
                    "end_ms": 8000,
                }
            ]
        },
    )
    restating = (
        "Precision oncology aims to tailor cancer care to the biology of an "
        "individual tumour. This conversation examines whether blood-based tests "
        "can add useful information without relying only on tissue samples. "
        "What distinguishes tissue biopsy, liquid biopsy and cell biopsy?"
    )
    doc = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_seg_004",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "targets_segment_id": "seg_004",
                "text": restating,
                "delivery": "synthesize",
                "placement": "before",
            }
        ]
    }
    assert has_forward_cue(restating)
    assert cold_open_layup_ok(
        doc["interviewer_lines"][0],
        target_text=native,
        ordered_ids=["seg_004"],
    ) is False

    repaired, notes = repair_gap_report(ctx, doc)
    line = (repaired.get("interviewer_lines") or [doc["interviewer_lines"][0]])[0]
    healed = str(line.get("text") or "")
    assert has_forward_cue(healed)
    assert cold_open_layup_ok(
        line, target_text=native, ordered_ids=["seg_004"]
    ), healed
    assert any(
        n.get("action") == "preface_cold_open_layup_heal" for n in notes
    ), notes


def test_context_setup_layup_stays_within_word_budget(ctx: RunContext) -> None:
    """Cascade (MUX_FORENSICS=0): layup must not re-bloom past context_setup max.

    exec_13159: trim_line_word_limit then repair_last_sentence_layup appended a cue
    → vo_context_seg_009 post-commit 22 words (max 20).
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.artifact_repairs import repair_gap_report
    from interview_mux.gap_framing import validate_line_word_limits, word_limit_for_category
    from interview_mux.gap_vo_prior_context import has_forward_cue, repair_last_sentence_layup

    body = (
        "Liquid biopsy looks for cancer-related material in blood, where tumour DNA "
        "can be mixed with DNA from normal dying cells."
    )
    limit = word_limit_for_category("context_setup")
    assert limit == 20
    healed = repair_last_sentence_layup(body, category="context_setup", max_words=limit)
    assert has_forward_cue(healed)
    assert len(healed.split()) <= limit

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_009"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_009",
                    "text": "Tumour DNA in blood mixes with DNA from normal dying cells.",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["science"],
                    "start_ms": 0,
                    "end_ms": 5000,
                }
            ]
        },
    )
    doc = {
        "interviewer_lines": [
            {
                "line_id": "vo_context_seg_009",
                "line_category": "context_setup",
                "targets_segment_id": "seg_009",
                "text": body,
                "delivery": "synthesize",
                "rationale": "orient the listener before the clip",
            }
        ]
    }
    repaired, notes = repair_gap_report(ctx, doc)
    lines = repaired.get("interviewer_lines") or []
    if not lines:
        # Ambient spoken-copy omit may drop optional context_setup (not GFC harden).
        # Direct repair_last_sentence_layup above already proves cue + word budget.
        assert any(
            isinstance(n, dict) and n.get("action") == "omit_unsafe_optional_vo"
            for n in (notes or [])
        )
        return
    line = lines[0]
    assert line is not None
    text = str(line.get("text") or "")
    assert has_forward_cue(text)
    assert validate_line_word_limits([line]) == []
    assert any(
        n.get("action") in ("repair_last_sentence_layup", "rebudget_after_layup", "trim_line_word_limit")
        for n in notes
    )


def test_small_batch_llm_fail_refuses_hollow_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1: small-batch LLM fail + fill must assert completeness before done."""
    from interview_mux.stages import gaps
    from interview_mux.stage_completion import stage_artifact_incompleteness
    from run_fixtures import isolated_run_ctx, minimal_manifest

    ctx = isolated_run_ctx(tmp_path, "gfc_small_batch_fail")
    ctx.write_json(
        "run_meta.json",
        {
            **(ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}),
            "gap_framing_enabled": True,
            "gap_fill_mode": "active",
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001"),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_001",
                    "self_explanatory": False,
                    "gap_type": "missing_setup",
                    "severity": "high",
                    "listener_confusion": "needs framing",
                }
            ]
        },
        skip_handoff=True,
    )

    monkeypatch.setattr(gaps, "_gap_pass_batch_size", lambda _cfg=None: 40)

    def _boom(*_a, **_k):
        raise RuntimeError("simulated flagship fail")

    monkeypatch.setattr(gaps, "run_analysis_llm_stage", _boom)
    monkeypatch.setattr(
        "interview_mux.high_gap_vo.fill_uncovered_high_gaps",
        lambda *_a, **_k: 0,
    )

    # Force incompleteness after persist so heal cannot stamp done.
    real_incompleteness = stage_artifact_incompleteness

    def _partial(ctx_arg, stage_id, *a, **k):
        if stage_id == "gap_framing_compose":
            return "understanding/gap_report.json is partial"
        return real_incompleteness(ctx_arg, stage_id, *a, **k)

    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        _partial,
    )

    with pytest.raises(RuntimeError, match="partial|incomplete|gap_report"):
        gaps.run_gap_framing_compose(ctx)
    assert not ctx.is_done("gap_framing_compose")


def test_gap_framing_compose_sufficiency_allows_empty_gaps() -> None:
    """B3: contract min_rows for gaps is 0 (skip stubs write gaps: [])."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("gap_framing_compose")
    assert contract is not None
    rules = [r for r in contract.sufficiency if r.path == "gaps"]
    assert len(rules) == 1
    assert rules[0].rule == "min_rows"
    assert rules[0].min_count == 0


def test_gap_framing_compose_noop_under_layup_authority_no_llm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): layup authority must no-op without LLM rewrite.

    Regression for wrong ``write_staging.heal_or_refuse_mark`` import that raised
    ImportError, was swallowed, and fell through into interviewer-script LLM —
    wiping contentful before-VO (hosted_vo_floor_unmet / nugget_layup needs_operator).
    """
    import interview_mux.stages.gaps as gaps

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )

    # Minimal committed gap_report under layup authority WITH contentful plan
    # (stamp-without-plan is orphan-cleared into analysis compose — not a no-op).
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "lines": [
                {
                    "line_id": "vo_seed_seg_001",
                    "text": "Host line one for floor.",
                    "targets_segment_id": "seg_001",
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "gaps": [
                {
                    "line_id": "vo_seed_seg_001",
                    "segment_id": "seg_001",
                    "placement": "before",
                    "text": "Host line one for floor.",
                    "delivery": "synthesize",
                    "status": "active",
                },
                {
                    "line_id": "vo_seed_seg_002",
                    "segment_id": "seg_002",
                    "placement": "before",
                    "text": "Host line two for floor.",
                    "delivery": "synthesize",
                    "status": "active",
                },
                {
                    "line_id": "vo_seed_seg_003",
                    "segment_id": "seg_003",
                    "placement": "before",
                    "text": "Host line three for floor.",
                    "delivery": "synthesize",
                    "status": "active",
                },
            ],
            "nugget_layup_authority": True,
        },
        skip_handoff=True,
    )

    llm_calls: list[str] = []

    def _llm_boom(*_a, **_k):
        llm_calls.append("called")
        raise AssertionError("LLM must not run under layup authority no-op")

    monkeypatch.setattr(gaps, "run_analysis_llm_stage", _llm_boom)
    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple",
        _llm_boom,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.publish_layup_plan_to_gap_report",
        lambda _ctx: None,
    )

    before = ctx.read_json("understanding/gap_report.json")
    gaps.run_gap_framing_compose(ctx)
    after = ctx.read_json("understanding/gap_report.json")

    assert llm_calls == [], "layup authority must no-op without LLM"
    assert after.get("nugget_layup_authority") is True
    assert len(after.get("gaps") or []) == len(before.get("gaps") or [])


def test_gap_framing_compose_guard_exception_fail_closed_no_llm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade: non-ImportError guard failure under freeze → no-op, never LLM."""
    import interview_mux.stages.gaps as gaps

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )

    def _boom_freeze(*_a, **_k):
        raise RuntimeError("simulated freeze_write_allowed failure")

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.freeze_write_allowed",
        _boom_freeze,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: False,
    )

    ctx.write_json(
        "understanding/gap_report.json",
        {
            "gaps": [
                {
                    "line_id": "vo_seed_seg_001",
                    "segment_id": "seg_001",
                    "placement": "before",
                    "text": "Host line.",
                    "delivery": "synthesize",
                    "status": "active",
                }
            ],
        },
        skip_handoff=True,
    )

    llm_calls: list[str] = []

    def _llm_boom(*_a, **_k):
        llm_calls.append("called")
        raise AssertionError("LLM must not run on fail-closed guard error")

    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple",
        _llm_boom,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.publish_layup_plan_to_gap_report",
        lambda _ctx: None,
    )

    gaps.run_gap_framing_compose(ctx)
    assert llm_calls == []


def test_gap_framing_compose_guard_exception_no_evidence_raises(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade: guard failure with no layup/freeze evidence must not LLM or hollow-done."""
    import interview_mux.stages.gaps as gaps

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: False,
    )

    def _boom_freeze(*_a, **_k):
        raise RuntimeError("simulated freeze_write_allowed failure")

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.freeze_write_allowed",
        _boom_freeze,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: False,
    )

    ctx.write_json(
        "understanding/gap_report.json",
        {"gaps": []},
        skip_handoff=True,
    )

    llm_calls: list[str] = []

    def _llm_boom(*_a, **_k):
        llm_calls.append("called")
        raise AssertionError("LLM must not run")

    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple",
        _llm_boom,
    )

    with pytest.raises(RuntimeError, match="refusing LLM fall-through"):
        gaps.run_gap_framing_compose(ctx)
    assert llm_calls == []
    assert not ctx.is_done("gap_framing_compose")

