"""The walk resolves the seed-order chain before dispatch (ISSUES 106)."""

from __future__ import annotations

import pytest

from run_fixtures import isolated_run_ctx, mark_done_raw

from interview_mux.homunculus import agenda


def test_the_chain_runs_ahead_in_order_and_once(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_prereqs_ahead")
    chain = iter(["chapter_close_hitch", "full_master_ranking", None])
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block", lambda c, s: next(chain, None)
    )
    monkeypatch.setattr(agenda, "_seed_prereq_needs_run", lambda c, p: True)
    ran: list[str] = []
    retried: set[str] = set()

    out = agenda._run_seed_prerequisites_first(
        ctx, "refinement_agenda", retried, lambda c, s: ran.append(s)
    )

    assert out == ["chapter_close_hitch", "full_master_ranking"]
    assert ran == out
    assert retried == {"chapter_close_hitch", "full_master_ranking"}


def test_a_prerequisite_already_tried_is_not_run_again(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_prereqs_once")
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block", lambda c, s: "chapter_close_hitch"
    )
    monkeypatch.setattr(agenda, "_seed_prereq_needs_run", lambda c, p: True)
    ran: list[str] = []
    assert agenda._run_seed_prerequisites_first(
        ctx, "refinement_agenda", {"chapter_close_hitch"}, lambda c, s: ran.append(s)
    ) == []
    assert ran == []


def test_a_complete_prerequisite_stops_the_loop(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_prereqs_complete")
    mark_done_raw(ctx, "chapter_close_hitch")
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block", lambda c, s: "chapter_close_hitch"
    )
    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: True)
    ran: list[str] = []
    assert agenda._run_seed_prerequisites_first(ctx, "refinement_agenda", set(), lambda c, s: ran.append(s)) == []
    assert ran == []


def test_a_failing_prerequisite_falls_through_to_dispatch(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_prereqs_fail")
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block", lambda c, s: "chapter_close_hitch"
    )
    monkeypatch.setattr(agenda, "_seed_prereq_needs_run", lambda c, p: True)

    def _boom(c, s):
        raise RuntimeError("model refused")

    retried: set[str] = set()
    # ISSUES 119: the failure is raised before dispatch, in the words the
    # walk's prerequisite parser reads, so the consumer never runs into it.
    with pytest.raises(agenda.SeedPrerequisiteFailed, match="Prerequisite stage chapter_close_hitch"):
        agenda._run_seed_prerequisites_first(ctx, "refinement_agenda", retried, _boom)
    assert retried == {"chapter_close_hitch"}
