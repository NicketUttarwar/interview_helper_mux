"""A refused side-effect write costs the write, not the stage (ISSUES 127).

The run this guards: ``gap_framing_compose`` finished its real work, a shared
helper then tried to persist ``mastering/mastering_plan.json`` under the
compose stage's key, the ownership table refused it, the refusal was counted
toward a no-heal halt against compose, and the dispatch door then refused to
re-run compose ("no_delta") while the seed order kept demanding it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import artifact_ownership as ao
from interview_mux import fallback_backstop as fb
from interview_mux import write_staging as ws
from interview_mux.dispatch_delta import record_attempt
from interview_mux.dispatch_door import demand_seed_prereq, evaluate_dispatch, seed_prereq_demanded
from interview_mux.identical_failures import read_identical_failures
from run_fixtures import isolated_run_ctx

PLAN = "mastering/mastering_plan.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "foreign")
    c.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    dest = c.final_path(*PLAN.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"narrative_mode": "sparse_source", "marker": "owner"}), encoding="utf-8")
    yield c
    ws.exit_stage_staging()


def _plan_on_disk(c) -> dict:
    return json.loads(c.final_path(*PLAN.split("/")).read_text(encoding="utf-8"))


def test_compose_has_no_row_for_the_mastering_plan(ctx) -> None:
    ok, reason = ao.write_permitted(ctx, PLAN, "gap_framing_compose", role="producer", verb="persist")
    assert not ok
    assert ao.is_foreign_refusal(reason)


def test_an_unkeyed_write_from_a_stage_with_no_row_is_skipped_not_raised(ctx) -> None:
    ws.enter_stage_staging("gap_framing_compose")
    ctx.write_json(PLAN, {"narrative_mode": "sparse_source", "marker": "compose"})
    ws.exit_stage_staging()
    # The owner's document is untouched and nothing was staged for it.
    assert _plan_on_disk(ctx)["marker"] == "owner"
    assert not (Path(ctx.run_dir) / ".pending_writes" / "gap_framing_compose" / "mastering").exists()
    rows = [
        json.loads(line)
        for line in (Path(ctx.run_dir) / ao.FOREIGN_WRITE_LEDGER_REL).read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["path"] == PLAN and rows[-1]["stage"] == "gap_framing_compose"
    # The ledger names the code that made the write (frames inside the package only).
    assert isinstance(rows[-1]["callers"], list)


def test_the_committed_write_point_follows_the_same_rule(ctx) -> None:
    ws.enter_stage_staging("gap_framing_compose")
    ws.write_committed_json(ctx, PLAN, {"narrative_mode": "sparse_source", "marker": "compose"})
    ws.exit_stage_staging()
    assert _plan_on_disk(ctx)["marker"] == "owner"


def test_a_named_writer_still_gets_the_exception(ctx) -> None:
    """A caller that names a key is making a claim; its fallbacks depend on the raise."""
    with pytest.raises(ao.AuthorityDenied) as info:
        ctx.write_json(PLAN, {"narrative_mode": "sparse_source"}, stage_key="gap_framing_compose")
    assert info.value.foreign is True
    assert _plan_on_disk(ctx)["marker"] == "owner"


def test_a_denial_is_not_counted_toward_a_halt_when_it_is_raised(ctx) -> None:
    for _ in range(3):
        with pytest.raises(ao.AuthorityDenied):
            ao.assert_write(ctx, PLAN, "gap_framing_compose")
    rows = (read_identical_failures(ctx).get("signatures") or {}).values()
    assert not [r for r in rows if isinstance(r, dict) and r.get("halt")]
    meta = ctx.read_json("run_meta.json")
    assert "authority_denied_halted" not in meta and "authority_denied_no_heal" not in meta


def test_a_foreign_denial_logs_a_warning_and_a_rule_denial_an_error(ctx, monkeypatch) -> None:
    levels: list[str] = []
    monkeypatch.setattr(type(ctx), "log", lambda self, msg, level="info", **kw: levels.append(level))
    ao._log_authority_denied(
        ctx, ao.AuthorityDenied("x", path=PLAN, stage_key="gap_framing_compose", reason="not_allow:owner=air_contract_sanitize")
    )
    ao._log_authority_denied(
        ctx, ao.AuthorityDenied("x", path=PLAN, stage_key="air_script_compose", reason="freeze_blocks:air_script_compose:x:hard_freeze")
    )
    assert levels == ["warning", "error"]


def test_the_owner_still_writes_its_own_document(ctx) -> None:
    ws.enter_stage_staging("air_contract_sanitize")
    assert not ao.skip_foreign_side_effect(ctx, PLAN, stage_key=None, role=None)
    ws.exit_stage_staging()


def _arm_no_delta(ctx, monkeypatch, stage: str) -> None:
    from interview_mux import dispatch_delta as dd
    from interview_mux.homunculus import agenda

    monkeypatch.setattr(dd, "hard_input_paths", lambda c, s: ("understanding/gap_evaluations.json",))
    monkeypatch.setattr(agenda, "stage_outputs_present", lambda c, s: True)
    dest = ctx.final_path("understanding", "gap_evaluations.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{}", encoding="utf-8")
    record_attempt(ctx, stage, outcome="done")


def test_the_door_refuses_an_unchanged_stage_but_not_a_demanded_prerequisite(ctx, monkeypatch) -> None:
    _arm_no_delta(ctx, monkeypatch, "gap_framing_compose")
    verdict = evaluate_dispatch(ctx, "gap_framing_compose", source="walk")
    assert verdict.refused and verdict.reason == "no_delta"
    with demand_seed_prereq(ctx, "gap_framing_compose"):
        assert seed_prereq_demanded(ctx) == "gap_framing_compose"
        assert evaluate_dispatch(ctx, "gap_framing_compose", source="walk").allowed
        # Only the demanded stage is exempt.
        _arm_no_delta(ctx, monkeypatch, "missing_framing")
        assert evaluate_dispatch(ctx, "missing_framing", source="walk").refused
    assert seed_prereq_demanded(ctx) == ""
    assert evaluate_dispatch(ctx, "gap_framing_compose", source="walk").refused


def test_the_walk_runs_a_prerequisite_under_the_demand(ctx, monkeypatch) -> None:
    from interview_mux.homunculus import agenda

    seen: list[tuple[str, str]] = []

    def _run(c, stage):
        seen.append((stage, seed_prereq_demanded(c)))

    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: True)
    agenda._run_demanded_prereq(ctx, "gap_framing_compose", "delivery_brief_build", _run)
    assert seen == [("gap_framing_compose", "gap_framing_compose")]
    assert seed_prereq_demanded(ctx) == ""


def test_a_prerequisite_left_incomplete_is_explained_in_its_own_words(ctx, monkeypatch) -> None:
    from interview_mux.homunculus import agenda

    lines: list[str] = []
    monkeypatch.setattr(type(ctx), "log", lambda self, msg, level="info", **kw: lines.append(str(msg)))
    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: False)
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        lambda c, s, force=False: {"refused": True, "reason": "high_gap_unframed:seg_013"},
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda c, s: "high_gap_unframed:seg_013",
    )
    agenda._run_demanded_prereq(ctx, "gap_framing_compose", "delivery_brief_build", lambda c, s: None)
    assert any("still incomplete" in ln and "high_gap_unframed:seg_013" in ln for ln in lines)


def test_the_fallback_at_the_cap_goes_to_the_incomplete_prerequisite(ctx, monkeypatch) -> None:
    asked: list[str] = []

    def _prior(c, stage):
        asked.append(stage)
        return "understanding/gap_report.json" if stage == "gap_framing_compose" else None

    monkeypatch.setattr(fb, "prior_committed_artifact", _prior)
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        lambda c, s, force=False: {"marked": True},
    )
    reason = "RuntimeError:seed order: complete gap_framing_compose before running delivery_brief_build"
    decision = fb.apply_declared_fallback(ctx, "delivery_brief_build", reason)
    assert decision and decision["stage"] == "gap_framing_compose"
    assert decision["unblocks"] == "delivery_brief_build"
    assert decision["fallback"] == "keep_prior_committed_artifact"
    # The blocked consumer is never skipped through its stub on a prerequisite failure.
    assert asked == ["gap_framing_compose"]


def test_no_fallback_for_the_prerequisite_means_the_halt_stands(ctx, monkeypatch) -> None:
    monkeypatch.setattr(fb, "prior_committed_artifact", lambda c, s: None)
    reason = "RuntimeError:seed order: complete full_master_ranking before running air_script_compose"
    assert fb.apply_declared_fallback(ctx, "air_script_compose", reason) is None


def test_the_cta_remap_asks_the_table_instead_of_probing_by_denial() -> None:
    import interview_mux.media_ip_cta as m

    src = Path(m.__file__).read_text(encoding="utf-8")
    body = src[src.find("def _publish_story_children_sources") :]
    body = body[: body.find("\ndef _admit_story_ids")]
    assert "write_permitted(ctx, rel, key" in body
    assert "ctx.write_json(rel, doc, skip_handoff=True)\n" not in body


# --- guardrails around the same chain --------------------------------------


def test_a_refusal_stands_for_a_complete_stage(ctx, monkeypatch) -> None:
    from interview_mux.homunculus import agenda

    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: True)
    rerun: set[str] = set()
    assert agenda._refusal_strands_stage(ctx, "gap_framing_compose", "no_delta", rerun) is False
    assert rerun == set()


def test_a_refused_stage_complete_on_disk_gets_its_marker_back(ctx, monkeypatch) -> None:
    from interview_mux.homunculus import agenda

    state = {"complete": False}
    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: state["complete"])
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        lambda c, s, force=False: state.update(complete=True) or {"marked": True},
    )
    rerun: set[str] = set()
    assert agenda._refusal_strands_stage(ctx, "gap_framing_compose", "no_delta", rerun) is False
    assert state["complete"] is True and rerun == set()


def test_a_refused_incomplete_stage_is_run_once_per_walk(ctx, monkeypatch) -> None:
    from interview_mux.homunculus import agenda

    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: False)
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        lambda c, s, force=False: {"refused": True},
    )
    rerun: set[str] = set()
    assert agenda._refusal_strands_stage(ctx, "gap_framing_compose", "no_delta", rerun) is True
    assert agenda._refusal_strands_stage(ctx, "gap_framing_compose", "no_delta", rerun) is False
    assert agenda._refusal_strands_stage(ctx, "delivery_brief_build", "no_delta", rerun) is True
    # The attempt memo ("already failed at this state") and a cap refusal are
    # left alone, and the audio ping-pong stages keep the guard.
    assert agenda._refusal_strands_stage(ctx, "content_context", "attempt_memo", rerun) is False
    assert agenda._refusal_strands_stage(ctx, "missing_framing", "max_invokes", rerun) is False
    assert agenda._refusal_strands_stage(ctx, "mix", "no_delta", rerun) is False


def test_the_walk_runs_a_stranded_stage_under_the_demand() -> None:
    import interview_mux.homunculus.agenda as agenda

    src = Path(agenda.__file__).read_text(encoding="utf-8")
    body = src[src.find("def walk_seed_agenda") :]
    assert body.find("_refusal_strands_stage(ctx, stage, verdict.reason, refusal_void_rerun)") < body.find(
        "refuse_dispatch(ctx, stage, verdict, source=reason)"
    )
    assert "with demand_seed_prereq(ctx, stage):" in body


def test_an_incomplete_prerequisite_gets_its_recovery_playbook(ctx, monkeypatch) -> None:
    from interview_mux.homunculus import agenda

    state = {"complete": False}
    seen: list[tuple[str, str]] = []

    class _Result:
        status = "recovered"

    def _handle(c, stage, exc):
        seen.append((stage, str(exc)))
        state["complete"] = True
        return _Result()

    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: state["complete"])
    monkeypatch.setattr("interview_mux.recovery_controller.handle_stage_failure", _handle)
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark", lambda c, s, force=False: {"refused": True}
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda c, s: "high_gap_unframed:seg_013",
    )
    lines: list[str] = []
    monkeypatch.setattr(type(ctx), "log", lambda self, msg, level="info", **kw: lines.append(str(msg)))
    agenda._run_demanded_prereq(ctx, "gap_framing_compose", "delivery_brief_build", lambda c, s: None)
    assert seen == [("gap_framing_compose", "high_gap_unframed:seg_013")]
    assert any("completed by its recovery playbook" in ln for ln in lines)
    assert not any("still incomplete" in ln for ln in lines)


def test_the_second_wind_forgets_memo_rows_of_incomplete_stages(ctx, monkeypatch) -> None:
    from interview_mux.dispatch_delta import forget_incomplete_stage_rows, memo_row

    record_attempt(ctx, "gap_framing_compose", outcome="done")
    record_attempt(ctx, "missing_framing", outcome="done")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: s == "missing_framing"
    )
    assert forget_incomplete_stage_rows(ctx) == 1
    assert memo_row(ctx, "gap_framing_compose") == {}
    assert memo_row(ctx, "missing_framing")["outcome"] == "done"


def test_the_second_wind_resets_the_memo_and_falls_back_on_the_prerequisite() -> None:
    import interview_mux.orchestrator as orch

    src = Path(orch.__file__).read_text(encoding="utf-8")
    body = src[src.find("def _second_wind") : src.find("    # ----- main")]
    assert "forget_incomplete_stage_rows(self.ctx)" in body
    assert 'apply_declared_fallback(self.ctx, "", err)' in body


def test_the_fallback_reads_a_prerequisite_from_the_engine_error(ctx, monkeypatch) -> None:
    monkeypatch.setattr(
        fb, "prior_committed_artifact", lambda c, s: "understanding/gap_report.json" if s == "gap_framing_compose" else None
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark", lambda c, s, force=False: {"marked": True}
    )
    err = "analysis: seed order: complete gap_framing_compose before running delivery_brief_build"
    decision = fb.apply_declared_fallback(ctx, "", err)
    assert decision and decision["stage"] == "gap_framing_compose"


def test_the_verdict_reports_fallbacks_and_skipped_foreign_writes(ctx) -> None:
    from interview_mux.orchestrator import run_verdict

    fb.record_fallback_decision(
        ctx, {"stage": "gap_framing_compose", "fallback": "keep_prior_committed_artifact", "unblocks": "delivery_brief_build"}
    )
    ws.enter_stage_staging("gap_framing_compose")
    ctx.write_json(PLAN, {"narrative_mode": "sparse_source"})
    ws.exit_stage_staging()
    verdict = run_verdict(ctx, complete=False, error="x")
    assert verdict["fallback_decisions"][0]["stage"] == "gap_framing_compose"
    assert verdict["foreign_writes_skipped"] == [f"gap_framing_compose:{PLAN}"]


def test_commit_path_documents_keep_the_exception(ctx) -> None:
    """Their writers catch the refusal and retry as the owner; a skip would bypass that."""
    assert "master/edl.json" in ao.FOREIGN_SKIP_EXEMPT
    ws.enter_stage_staging("gap_framing_compose")
    for rel in sorted(ao.FOREIGN_SKIP_EXEMPT):
        ok, reason = ao.write_permitted(ctx, rel, "gap_framing_compose", role="producer", verb="persist")
        if ok or not ao.is_foreign_refusal(reason):
            continue
        assert ao.skip_foreign_side_effect(ctx, rel, stage_key=None, role=None) is False
    ws.exit_stage_staging()


def test_no_unkeyed_plan_write_relies_on_a_refusal_to_reach_its_owner_keyed_retry() -> None:
    """Static sweep: a try body with an unkeyed plan write and a handler that writes as the owner."""
    import ast

    import interview_mux

    root = Path(interview_mux.__file__).parent
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            unkeyed = False
            for stmt in node.body:
                for n in ast.walk(stmt):
                    if not isinstance(n, ast.Call):
                        continue
                    name = getattr(n.func, "attr", "") or getattr(n.func, "id", "")
                    kws = {k.arg for k in n.keywords}
                    if name == "write_plan" and "stage_key" not in kws and None not in kws:
                        unkeyed = True
            if not unkeyed:
                continue
            for handler in node.handlers:
                for n in ast.walk(handler):
                    if isinstance(n, ast.Call):
                        name = getattr(n.func, "attr", "") or getattr(n.func, "id", "")
                        if name == "persist_frozen_seat_doc":
                            offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


# ISSUES 140: a write keyed as the owner passed the ownership check but was
# staged under the active stage, whose flush discarded it without a log.


def test_owner_keyed_write_under_another_stage_lands_committed(ctx) -> None:
    ws.enter_stage_staging("gap_framing_compose")
    try:
        ctx.write_json(
            PLAN,
            {"narrative_mode": "sparse_source", "marker": "seat_owner"},
            stage_key="air_contract_sanitize",
        )
        assert not (Path(ctx.run_dir) / ".pending_writes" / "gap_framing_compose" / "mastering").exists()
        ws.flush_stage_writes(ctx, "gap_framing_compose")
    finally:
        ws.exit_stage_staging()
    assert _plan_on_disk(ctx)["marker"] == "seat_owner"


def test_the_active_stage_still_stages_its_own_outputs(ctx) -> None:
    ws.enter_stage_staging("air_contract_sanitize")
    try:
        assert not ws.keyed_write_lost_at_flush(ctx, PLAN, "air_contract_sanitize")
        ctx.write_json(PLAN, {"narrative_mode": "sparse_source", "marker": "staged"}, stage_key="air_contract_sanitize")
        assert _plan_on_disk(ctx)["marker"] == "owner"
        assert (Path(ctx.run_dir) / ".pending_writes" / "air_contract_sanitize" / PLAN).is_file()
    finally:
        ws.exit_stage_staging()


def test_no_active_stage_is_unchanged(ctx) -> None:
    assert not ws.keyed_write_lost_at_flush(ctx, PLAN, "air_contract_sanitize")
