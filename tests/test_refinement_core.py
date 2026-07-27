"""Tests for refinement CFI, ledger, gate, and flow integrity."""

from __future__ import annotations

import pytest

from interview_mux.refinement_catalog import is_blacklisted, is_whitelisted
from interview_mux.refinement_flow_integrity import (
    FINAL_REL,
    ensure_gap_report_authoritative,
    g1_reachable,
    skip_copy_draft_to_final,
)
from interview_mux.refinement_gate import decide_pass
from interview_mux.refinement_identity import (
    assert_acyclic_refines,
    assert_unique_registry,
    cfi_for_pass,
    register_builtin_cfis,
)
from interview_mux.refinement_ledger import can_run_refinement, load_ledger, record_call
from interview_mux.run_context import RunContext
from interview_mux.refinement_accept import accept_gap_recompose
from interview_mux.refinement_champion import load_champion
from interview_mux.refinement_gate import freeze_inputs
from interview_mux.refinement_succession import is_unlocked, mutex_blocked
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    # Isolate each test under tmp_path — a plain env var does not affect
    # RunContext's executions_root resolution (it reads merged_config()).
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_refinement_test", create=True)
    return run


def test_cfi_registry_unique() -> None:
    register_builtin_cfis()
    assert_unique_registry()
    assert_acyclic_refines()
    assert cfi_for_pass("gap_framing_recompose") is not None


def test_blacklist_wins() -> None:
    assert is_blacklisted(stage_id="ingest")
    assert not is_whitelisted("ingest")
    assert is_whitelisted("gap_framing_recompose")


def test_ledger_refinement_cap(ctx: RunContext) -> None:
    cfi = cfi_for_pass("gap_framing_recompose")
    assert cfi is not None
    # Ensure clean ledger for this CFI
    from interview_mux.refinement_ledger import LEDGER_REL, save_ledger

    save_ledger(
        ctx,
        {
            "run_id": ctx.run_id,
            "schema_version": 1,
            "calls": [],
            "counts_by_cfi": {},
            "order_of_refinement_pass_ids": [],
        },
    )
    assert can_run_refinement(ctx, cfi.cfi_id)
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="ok",
    )
    assert not can_run_refinement(ctx, cfi.cfi_id)
    with pytest.raises(RuntimeError):
        record_call(
            ctx,
            cfi_id=cfi.cfi_id,
            human_key=cfi.human_key,
            stage_id="gap_framing_recompose",
            pass_id="gap_framing_recompose",
            pass_index=2,
            kind="refinement",
            outcome="ok",
        )
    doc = load_ledger(ctx)
    assert doc["counts_by_cfi"][cfi.cfi_id]["refinement"] == 1
    _ = LEDGER_REL


def test_skip_copy_and_g1_reachable(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.draft.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_1",
                    "text": "Hello",
                    "targets_segment_id": "seg_1",
                    "gap_type": "missing_question",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    skip_copy_draft_to_final(ctx, reason="simple_tape")
    assert ctx.artifact_exists(FINAL_REL)
    final = ctx.read_json(FINAL_REL)
    assert len(final.get("interviewer_lines") or []) == 1
    assert g1_reachable(ctx)
    ensure_gap_report_authoritative(ctx)


def test_decide_pass_blacklist_or_simple(ctx: RunContext) -> None:
    d = decide_pass(ctx, "ingest")
    assert d["status"] == "skip"


# ---------------------------------------------------------------------------
# Succession unlocks + mutex
# ---------------------------------------------------------------------------


def test_succession_locked_until_gap_recompose_done(ctx: RunContext) -> None:
    assert not is_unlocked(ctx, "transitions_refine")
    ctx.mark_done("gap_framing_recompose", force=True)
    assert is_unlocked(ctx, "transitions_refine")


def test_succession_unlocked_via_skip_copy(ctx: RunContext) -> None:
    assert not is_unlocked(ctx, "transitions_refine")
    ctx.write_json("understanding/refinement_skip_copy.json", {"reason": "pass2_skipped"})
    assert is_unlocked(ctx, "transitions_refine")


def test_succession_unlock_ranking_refine_needs_topic_holes(ctx: RunContext) -> None:
    assert not is_unlocked(ctx, "ranking_refine")
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.path("master", "coverage_audit.json").write_text(
        '{"uncovered_topics": ["topic_x"]}\n', encoding="utf-8"
    )
    assert is_unlocked(ctx, "ranking_refine")


def test_mutex_blocks_ranking_after_narrative_done(ctx: RunContext) -> None:
    assert not mutex_blocked(ctx, "ranking_refine")
    ctx.mark_done("narrative_arc_refine", force=True)
    assert mutex_blocked(ctx, "ranking_refine")
    # The pass that already ran is not blocked by itself.
    assert not mutex_blocked(ctx, "narrative_arc_refine")


# ---------------------------------------------------------------------------
# L1 gate — input-hash skip (no new evidence)
# ---------------------------------------------------------------------------


def test_gate_skips_on_unchanged_input_hash(ctx: RunContext) -> None:
    ctx.write_json("understanding/gap_report.draft.json", {"interviewer_lines": []})
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    req = ["understanding/gap_report.draft.json", "master/selection.json"]

    first = decide_pass(ctx, "gap_framing_recompose")
    assert first["status"] == "activate"

    # Simulate a completed refinement run: freeze inputs, write the final
    # gap_report, and mark the stage done — matching what
    # refinement_passes.run_gap_framing_recompose does on success.
    freeze_inputs(ctx, "gap_framing_recompose", req)
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []})
    ctx.mark_done("gap_framing_recompose", force=True)

    second = decide_pass(ctx, "gap_framing_recompose")
    assert second["status"] == "skip"
    assert second["reason_code"] == "no_new_evidence"
    assert second["gate"] == "input_hash"


# ---------------------------------------------------------------------------
# Champion accept — noop guard + promote
# ---------------------------------------------------------------------------


def _gap_line(line_id: str, text: str, **overrides: object) -> dict[str, object]:
    line: dict[str, object] = {
        "line_id": line_id,
        "text": text,
        "targets_segment_id": "seg_1",
        "gap_type": "missing_question",
        "placement": "before",
        "delivery": "synthesize",
    }
    line.update(overrides)
    return line


def test_accept_gap_recompose_noop_when_unchanged(ctx: RunContext) -> None:
    draft = {"interviewer_lines": [_gap_line("vo_1", "Hello")]}
    ctx.write_json("understanding/gap_report.draft.json", draft)

    result = accept_gap_recompose(ctx, dict(draft))
    assert result["accepted"] is False
    assert result["reason_code"] == "noop"
    assert ctx.read_json(FINAL_REL) == draft


def test_accept_gap_recompose_promotes_champion_on_improvement(ctx: RunContext) -> None:
    draft = {"interviewer_lines": [_gap_line("vo_1", "Hello")]}
    ctx.write_json("understanding/gap_report.draft.json", draft)
    assert load_champion(ctx, "gap_vo") is None

    candidate = {
        "interviewer_lines": [
            _gap_line("vo_1", "Hello"),
            _gap_line(
                "vo_2",
                "Welcome back to the show",
                line_category="episode_preface",
            ),
        ]
    }
    result = accept_gap_recompose(ctx, candidate)
    assert result["accepted"] is True
    assert result["reason_code"] == "accepted"
    assert ctx.read_json(FINAL_REL) == candidate

    champion = load_champion(ctx, "gap_vo")
    assert champion is not None
    assert champion["source"] == "gap_framing_recompose"
    assert champion["score_vector"] == result["candidate_scores"]
