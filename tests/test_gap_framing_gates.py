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
    assert evals["evaluations"][0]["severity_demotion_reason"] == "uncovered_after_fill"


def test_demote_uncovered_high_gaps_refuses_below_hosted_floor(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under G-Framing Yes, demote must not clear high pressure while active VO < floor."""
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
    assert demote_uncovered_high_gaps(ctx, origin="e2e_heal_lint_dirty") == 0
    evals = ctx.read_json("understanding/gap_evaluations.json")
    assert evals["evaluations"][0]["severity"] == "high"


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
    from interview_mux.high_gap_vo import demote_uncovered_high_gaps

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
    assert demote_uncovered_high_gaps(ctx, gap_report=repaired) == 1
    after = _lint_optimal_questions(repaired, ctx)
    assert not any("has no interviewer line" in e for e in after)


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
    assert added == 0
    assert calls["n"] == 0
    assert any(row.get("reason") == "limit_exhausted" for row in applied)
    evals = ctx.read_json("understanding/gap_evaluations.json")
    assert evals["evaluations"][0]["severity"] == "medium"


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
    assert added == 0
    assert calls["n"] == 1
    assert any(row.get("reason") == "limit_exhausted" for row in applied)
    evals = ctx.read_json("understanding/gap_evaluations.json")
    assert all(row["severity"] == "medium" for row in evals["evaluations"])


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

