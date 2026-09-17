"""The replay harness must not be able to manufacture a green promotion verdict.

``tools/solver_replay.py`` stands in for the live full-auto run the forensics campaign
forbids, so its failure mode is not "wrong number" — it is "reassuring number". Four
ways it could reassure wrongly, each pinned here:

1. **False green from emptiness.** ``solver.shadow_summary()["zero"]`` keys on
   ``disagree`` alone, and a solver with no justified opinion disagrees with nobody. So
   zero disagreements must not be sufficient — which under **D12** is bought by the
   second condition (no regression against the driver) rather than by a coverage
   percentage. The coverage numbers stay in the report and must stay *out* of the
   verdict; both halves of that are pinned.
2. **Merged divergence classes.** A dispatch the solver would have *skipped* is the
   thrash refusal this campaign exists to produce; a dispatch it would have *replaced*
   is a real disagreement. Summing them hides the second inside the first. A dispatch of
   an **already-complete** stage is neither, and folding it into `skip` (590 of 1,107)
   or into `blocked` is what made the headline unreadable.
3. **Drift from the live classifier.** The harness reuses
   ``solver.compare_walk_choice`` rather than reimplementing it, and its deferral
   buckets must stay exhaustive over the unknowns the solver actually emits.
4. **A laundered explanation.** ``KNOWN_DIVERGENCES`` is prose next to the numbers and
   must never be able to clear a gate.

Plus the safety property the corpus depends on: replaying a run must never write into
``ASSETS/executions``.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import solver_replay as replay  # noqa: E402

from interview_mux import solver  # noqa: E402


# ---------------------------------------------------------------------------
# 1. the verdict is D12's two conditions, and only those
# ---------------------------------------------------------------------------

def _summary(**patch) -> dict:
    base = {
        "choice_divergences": 0,
        "choice_unexplained": 0,
        "choice_reconstruction_limited": 0,
        "driver_regressions": 0,
        "authority_rate": 0.95,
        "structural_defer_rate": 0.0,
        "choice_resolution": {
            "mtime_only": 0,
            "content_postdates_point": 0,
            "genuine": 0,
        },
    }
    base.update(patch)
    return base


def test_the_gate_is_exactly_d12s_two_conditions() -> None:
    ids = [c["id"] for c in replay.promotion_verdict(_summary())["checks"]]
    assert ids == ["no_unexplained_disagreements", "no_regression_against_driver"]


def test_a_real_disagreement_vetoes_even_with_perfect_coverage() -> None:
    verdict = replay.promotion_verdict(
        _summary(choice_divergences=1, choice_unexplained=1)
    )
    assert verdict["promote"] is False
    assert "no_unexplained_disagreements" in verdict["vetoes"]


def test_a_regression_against_the_driver_vetoes_on_its_own() -> None:
    verdict = replay.promotion_verdict(_summary(driver_regressions=1))
    assert verdict["promote"] is False
    assert "no_regression_against_driver" in verdict["vetoes"]


def test_a_reconstruction_limited_divergence_is_reported_but_does_not_veto() -> None:
    """The evidence, not the solver, is what fails on these — and dropping them silently
    would be the same laundering this harness exists to prevent, so they stay visible."""
    verdict = replay.promotion_verdict(
        _summary(
            choice_divergences=14,
            choice_reconstruction_limited=14,
            choice_resolution={
                "mtime_only": 13,
                "content_postdates_point": 1,
                "genuine": 0,
            },
        )
    )
    assert verdict["promote"] is True
    detail = verdict["checks"][0]["detail"]
    assert "14 total" in detail
    assert "13 attributed to mtime-only" in detail
    assert "1 to content that post-dates" in detail


def test_evidence_is_read_off_the_ledger_not_guessed() -> None:
    assert replay.choice_evidence("mix", {"mix", "edl"}) == "ledger"
    assert replay.choice_evidence("content_brief_reanchor", {"mix"}) == "mtime_only"


# --- the two reconstruction witnesses, and the residue they leave ------------

def test_a_divergence_resolves_to_exactly_one_of_three_outcomes() -> None:
    assert _observation(replay.CHOICE, choice_evidence="mtime_only").resolution == "mtime_only"
    assert _observation(replay.CHOICE, choice_evidence="ledger").resolution == "genuine"
    assert (
        _observation(
            replay.CHOICE, choice_evidence="ledger", future_content="committed later"
        ).resolution
        == "content_postdates_point"
    )
    assert _observation(replay.SKIP).resolution == ""


def test_only_the_genuine_residue_counts_as_unexplained() -> None:
    """This is the gate's input, so the mapping is pinned rather than implied."""
    assert _observation(replay.CHOICE, choice_evidence="ledger").unexplained is True
    for excused in (
        _observation(replay.CHOICE, choice_evidence="mtime_only"),
        _observation(
            replay.CHOICE, choice_evidence="ledger", future_content="committed later"
        ),
    ):
        assert excused.unexplained is False


def test_future_content_is_proved_from_committed_at_not_assumed(tmp_path: Path) -> None:
    rel = "understanding/gap_evaluations.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    point = 1_000_000.0
    later = datetime.fromtimestamp(point + 41_580, timezone.utc).isoformat()
    path.write_text(
        json.dumps({"evaluations": [], "_meta": {"committed_at": later}}), encoding="utf-8"
    )
    proof = replay.content_postdates_point(tmp_path, (rel,), point)
    assert proof
    assert "committed_at" in proof and "11h33m" in proof


def test_an_artifact_committed_before_the_point_is_no_excuse(tmp_path: Path) -> None:
    rel = "understanding/gap_evaluations.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    point = 1_000_000.0
    earlier = datetime.fromtimestamp(point - 60, timezone.utc).isoformat()
    path.write_text(json.dumps({"_meta": {"committed_at": earlier}}), encoding="utf-8")
    assert replay.content_postdates_point(tmp_path, (rel,), point) == ""


@pytest.mark.parametrize(
    "doc",
    [
        {"evaluations": []},
        {"_meta": {}},
        {"_meta": {"committed_at": ""}},
        {"_meta": {"committed_at": "not-a-date"}},
        {"_meta": "not-a-dict"},
        [],
    ],
)
def test_a_missing_or_unreadable_stamp_leaves_the_divergence_vetoing(
    tmp_path: Path, doc
) -> None:
    """The witness must only ever excuse on positive evidence, never on absence."""
    rel = "a.json"
    (tmp_path / rel).write_text(json.dumps(doc), encoding="utf-8")
    assert replay.content_postdates_point(tmp_path, (rel,), 1_000_000.0) == ""


def test_an_absent_artifact_is_not_an_excuse(tmp_path: Path) -> None:
    assert replay.content_postdates_point(tmp_path, ("nope.json",), 1_000_000.0) == ""
    assert replay.content_postdates_point(tmp_path, (), 1_000_000.0) == ""


def test_the_summary_reports_the_resolution_split_over_every_divergence() -> None:
    run = replay.RunReplay(run_id="r", points=3, evaluated=3)
    run.observations.append(_observation(replay.CHOICE, choice_evidence="mtime_only"))
    run.observations.append(
        _observation(replay.CHOICE, choice_evidence="ledger", future_content="later")
    )
    run.observations.append(_observation(replay.CHOICE, choice_evidence="ledger"))
    summary = replay.summarise([run])
    assert summary["choice_resolution"] == {
        "mtime_only": 1,
        "content_postdates_point": 1,
        "genuine": 1,
    }
    assert sum(summary["choice_resolution"].values()) == summary["choice_divergences"]
    assert summary["choice_unexplained"] == 1
    assert summary["verdict"]["promote"] is False


def test_the_report_states_the_resolution_split_and_its_criteria() -> None:
    run = replay.RunReplay(run_id="r", points=2, evaluated=2)
    run.observations.append(_observation(replay.CHOICE, choice_evidence="mtime_only"))
    run.observations.append(
        _observation(
            replay.CHOICE,
            choice_evidence="ledger",
            future_content="`a.json` records `_meta.committed_at` later",
        )
    )
    markdown = replay.render_markdown(replay.summarise([run]))
    assert "How the choice divergences resolve" in markdown
    assert "2 reconstruction artifacts and 0 genuine" in markdown
    assert "_meta.committed_at" in markdown
    assert "Criterion" in markdown


def test_a_gate_cleared_by_attribution_carries_the_caveat_beside_the_verdict() -> None:
    """If a whole class is excused by a tool limitation, the reader must see it there."""
    run = replay.RunReplay(run_id="r", points=1, evaluated=1)
    run.observations.append(_observation(replay.CHOICE, choice_evidence="mtime_only"))
    markdown = replay.render_markdown(replay.summarise([run]))
    verdict_section = markdown.split("## Headline")[0]
    assert "D12 gate MET" in verdict_section
    assert "known limitations of the replay instrument" in verdict_section
    assert "Read this with the verdict" in verdict_section


def test_a_clean_pass_does_not_claim_a_caveat_it_does_not_have() -> None:
    markdown = replay.render_markdown(replay.summarise([]))
    assert "D12 gate MET" in markdown
    assert "Read this with the verdict" not in markdown


def test_the_adjacent_findings_are_recorded_without_becoming_gates() -> None:
    markdown = replay.render_markdown(replay.summarise([]))
    for note in replay.ADJACENT_FINDINGS:
        assert note in markdown
    assert "_MASTERING_SCHEMA_STAGES" in markdown
    verdict_ids = {
        c["id"] for c in replay.promotion_verdict(_summary())["checks"]
    }
    assert verdict_ids == {"no_unexplained_disagreements", "no_regression_against_driver"}


def test_promotion_needs_every_condition_at_once() -> None:
    assert replay.promotion_verdict(_summary())["promote"] is True
    assert (
        replay.promotion_verdict(_summary(choice_unexplained=1, driver_regressions=1))[
            "vetoes"
        ]
        == ["no_unexplained_disagreements", "no_regression_against_driver"]
    )


# --- D12 retired two bars. They must report and must never veto. -----------

def test_a_dismal_authority_rate_no_longer_vetoes() -> None:
    """D12: a deferring solver is safe, because deferral hands the pick to the walk.

    This is the exact inversion of the pre-D12 behaviour, so it is pinned as an
    assertion rather than left to the absence of a test.
    """
    verdict = replay.promotion_verdict(_summary(authority_rate=0.06))
    assert verdict["promote"] is True
    assert "solver_has_authority" not in verdict["vetoes"]


def test_unbounded_structural_deferral_no_longer_vetoes() -> None:
    verdict = replay.promotion_verdict(_summary(structural_defer_rate=0.4))
    assert verdict["promote"] is True
    assert "structural_deferral_bounded" not in verdict["vetoes"]


def test_a_missing_coverage_number_cannot_block_promotion() -> None:
    verdict = replay.promotion_verdict(
        _summary(authority_rate=None, structural_defer_rate=None)
    )
    assert verdict["promote"] is True


def test_the_retired_bars_are_still_reported_with_their_old_scale() -> None:
    """Retiring a gate must not delete the number — it is the D10/D11 progress signal."""
    verdict = replay.promotion_verdict(_summary(authority_rate=0.252))
    metrics = {m["id"]: m for m in verdict["metrics"]}
    assert set(metrics) == set(replay.RETIRED_GATE_IDS)
    assert metrics["solver_has_authority"]["value"] == 0.252
    assert metrics["solver_has_authority"]["retired_bar"] == replay.RETIRED_AUTHORITY_BAR
    assert "25.2%" in metrics["solver_has_authority"]["detail"]
    assert (
        metrics["structural_deferral_bounded"]["retired_bar"]
        == replay.RETIRED_STRUCTURAL_DEFER_BAR
    )


def test_no_retired_metric_is_wired_into_the_veto_list() -> None:
    """The structural guard: a future edit that re-gates coverage trips here."""
    worst = replay.promotion_verdict(
        _summary(authority_rate=0.0, structural_defer_rate=1.0)
    )
    assert worst["vetoes"] == []
    assert set(replay.RETIRED_GATE_IDS).isdisjoint(
        {c["id"] for c in worst["checks"]}
    )


def test_the_disagreement_bars_are_zero_because_being_wrong_is_the_thing() -> None:
    assert replay.MAX_CHOICE_DIVERGENCES == 0
    assert replay.MAX_DRIVER_REGRESSIONS == 0


def test_the_report_prints_the_retired_metrics_prominently() -> None:
    markdown = replay.render_markdown(replay.summarise([]))
    head = markdown.split("## Corpus")[0]
    assert "Retired" in head
    assert "solver_has_authority" in head
    assert "never as vetoes" in head


def test_a_traced_explanation_cannot_clear_a_gate() -> None:
    """KNOWN_DIVERGENCES is prose next to the numbers, never an input to them."""
    source = (REPO / "tools" / "solver_replay.py").read_text(encoding="utf-8")
    body = source.split("def promotion_verdict")[1].split("\ndef ")[0]
    assert "KNOWN_DIVERGENCES" not in body


# ---------------------------------------------------------------------------
# 1b. the driver-regression witness
# ---------------------------------------------------------------------------

def test_a_stage_the_driver_finished_and_never_reran_is_a_regression() -> None:
    proof = replay.regression_proof(
        "edl", 200.0, dones=[(100.0, "edl")], invalidations=[], starts={"edl": [90.0]}
    )
    assert proof
    assert "never started it again" in proof


def test_a_stage_the_driver_reran_later_proves_nothing() -> None:
    """The driver re-dispatching it is the opposite of proof, so this must not count."""
    assert (
        replay.regression_proof(
            "edl",
            200.0,
            dones=[(100.0, "edl")],
            invalidations=[],
            starts={"edl": [90.0, 300.0]},
        )
        == ""
    )


def test_an_invalidated_completion_is_not_proof() -> None:
    assert (
        replay.regression_proof(
            "edl",
            200.0,
            dones=[(100.0, "edl")],
            invalidations=[(150.0, frozenset({"edl"}))],
            starts={},
        )
        == ""
    )


def test_a_stage_with_no_completion_on_record_is_not_proof() -> None:
    assert replay.regression_proof("edl", 200.0, dones=[], invalidations=[], starts={}) == ""
    assert (
        replay.regression_proof(
            "edl", 50.0, dones=[(100.0, "edl")], invalidations=[], starts={}
        )
        == ""
    )


def test_only_choice_observations_can_regress() -> None:
    """A skip or already_done point proposes no stage, so it has nothing to regress on."""
    for klass in (replay.SKIP, replay.ALREADY_DONE, replay.AGREE, replay.DEFER):
        obs = _observation(klass, regression_proof="driver recorded `done`")
        assert obs.driver_regression is False
    assert (
        _observation(replay.CHOICE, regression_proof="driver recorded `done`").driver_regression
        is True
    )


def test_the_summary_counts_regressions_and_shows_the_proof() -> None:
    run = replay.RunReplay(run_id="r", points=1, evaluated=1)
    run.observations.append(
        _observation(
            replay.CHOICE,
            choice_evidence="ledger",
            regression_proof="driver recorded `done` at T and never started it again",
        )
    )
    summary = replay.summarise([run])
    assert summary["driver_regressions"] == 1
    assert summary["verdict"]["promote"] is False
    assert "no_regression_against_driver" in summary["verdict"]["vetoes"]
    assert summary["driver_regression_examples"][0]["regression_proof"]


# ---------------------------------------------------------------------------
# 2. the two divergence classes stay apart
# ---------------------------------------------------------------------------

class _Comparison:
    def __init__(
        self,
        verdict: str,
        chosen: str = "mix",
        choice: str | None = None,
        reason: str = "hard_input_missing:master/edl.json",
    ) -> None:
        self.verdict = verdict
        self.chosen = chosen
        self.solver_choice = choice
        self.reason = reason


def test_a_refused_dispatch_is_skip_and_a_replaced_one_is_choice() -> None:
    skip, _ = replay.classify(_Comparison(solver.DISAGREE), set())
    assert skip == replay.SKIP
    choice, ever = replay.classify(_Comparison(solver.DISAGREE, choice="edl"), {"edl"})
    assert choice == replay.CHOICE
    assert ever is True


def test_agree_and_defer_pass_through_unchanged() -> None:
    assert replay.classify(_Comparison(solver.AGREE), set())[0] == replay.AGREE
    assert replay.classify(_Comparison(solver.DEFER), set())[0] == replay.DEFER


def test_redispatching_a_finished_stage_is_its_own_class_not_a_skip() -> None:
    """590 of 1,107 'skip divergences' were this. A finished stage is not a blocker."""
    klass, _ = replay.classify(
        _Comparison(solver.DISAGREE, reason="already_done"), set()
    )
    assert klass == replay.ALREADY_DONE
    assert klass != replay.SKIP


def test_a_real_blocker_stays_a_skip() -> None:
    for reason in (
        "hard_input_missing:master/edl.json",
        "door_refused:max_invokes_per_identity",
        "lease_held_by_gui",
    ):
        klass, _ = replay.classify(_Comparison(solver.DISAGREE, reason=reason), set())
        assert klass == replay.SKIP, reason


def test_a_solver_preference_outranks_the_already_done_class() -> None:
    """A choice divergence must never be reclassified as bookkeeping."""
    klass, _ = replay.classify(
        _Comparison(solver.DISAGREE, choice="edl", reason="already_done"), {"edl"}
    )
    assert klass == replay.CHOICE


def _observation(klass: str, **patch) -> replay.Observation:
    row = dict(
        run_id="r",
        seq=1,
        at="",
        stage="mix",
        source="walk",
        verdict=solver.DISAGREE,
        klass=klass,
        solver_choice="edl" if klass == replay.CHOICE else None,
        reason="x",
        reasons=(),
        candidates=1,
        candidate_origin="walk_seed_agenda",
    )
    row.update(patch)
    return replay.Observation(**row)


def test_the_summary_never_folds_skip_into_choice() -> None:
    run = replay.RunReplay(run_id="r", points=2, evaluated=2)
    run.observations.append(_observation(replay.SKIP))
    run.observations.append(_observation(replay.CHOICE, choice_evidence="ledger"))
    summary = replay.summarise([run])
    assert summary["skip_divergences"] == 1
    assert summary["choice_divergences"] == 1
    assert "disagreements" not in summary


def test_the_summary_keeps_already_done_out_of_the_skip_count() -> None:
    run = replay.RunReplay(run_id="r", points=3, evaluated=3)
    run.observations.append(_observation(replay.SKIP))
    run.observations.append(_observation(replay.ALREADY_DONE, source="rerun"))
    run.observations.append(_observation(replay.ALREADY_DONE, source="conductor"))
    summary = replay.summarise([run])
    assert summary["skip_divergences"] == 1
    assert summary["already_done_dispatches"] == 2
    assert summary["already_done_sources"] == {"rerun": 1, "conductor": 1}


def test_already_done_stays_out_of_the_agreement_denominator() -> None:
    """Otherwise the agreement rate moves for a reason that is not about the solver."""
    run = replay.RunReplay(run_id="r", points=2, evaluated=2)
    run.observations.append(_observation(replay.AGREE))
    run.observations.append(_observation(replay.ALREADY_DONE))
    summary = replay.summarise([run])
    assert summary["agreement_denominator"] == 1
    assert summary["agreement_rate"] == 1.0


def test_the_summary_keeps_unexplained_and_reconstruction_limited_apart() -> None:
    run = replay.RunReplay(run_id="r", points=2, evaluated=2)
    run.observations.append(_observation(replay.CHOICE, choice_evidence="ledger"))
    run.observations.append(_observation(replay.CHOICE, choice_evidence="mtime_only"))
    summary = replay.summarise([run])
    assert summary["choice_divergences"] == 2
    assert summary["choice_unexplained"] == 1
    assert summary["choice_reconstruction_limited"] == 1
    assert summary["verdict"]["promote"] is False


# ---------------------------------------------------------------------------
# 3. no drift from the live classifier
# ---------------------------------------------------------------------------

def test_the_harness_reuses_the_solvers_classifier_rather_than_copying_it() -> None:
    source = (REPO / "tools" / "solver_replay.py").read_text(encoding="utf-8")
    assert "solver.compare_walk_choice(" in source
    assert "solver.admissible_set(" in source
    # A second implementation of the verdict rule is the drift this guards against.
    assert "def compare_walk_choice" not in source


def test_every_unknown_the_solver_emits_has_a_deferral_bucket() -> None:
    """Coverage vs structural is the split that decides whether promotion is possible."""
    text = (REPO / "src" / "interview_mux" / "solver.py").read_text(encoding="utf-8")
    emitted = set()
    for match in re.finditer(r"unknowns\.append\(\s*f?\"([a-z_]+)", text):
        emitted.add(match.group(1))
    assert emitted, "no unknown literals found — the scrape broke"
    known = set(replay.COVERAGE_UNKNOWNS) | set(replay.STRUCTURAL_UNKNOWNS)
    assert emitted <= known, sorted(emitted - known)


def test_the_buckets_do_not_overlap() -> None:
    assert not set(replay.COVERAGE_UNKNOWNS) & set(replay.STRUCTURAL_UNKNOWNS)
    assert replay.unknown_bucket("hard_inputs_undeclared") == "coverage"
    assert replay.unknown_bucket("gate_may_pause:g_publish") == "structural"
    assert replay.unknown_bucket("something_new") == "other"


# ---------------------------------------------------------------------------
# 4. comparison scope mirrors the walk's own candidate list
# ---------------------------------------------------------------------------

def _entries(*rows: dict) -> list[dict]:
    return [dict(row, seq=i + 1) for i, row in enumerate(rows)]


def test_candidates_come_from_the_walks_own_ledger_row() -> None:
    entries = _entries(
        {
            "kind": "fallback",
            "identity": "walk_seed_agenda",
            "stages": ["mix", "transitions", "edl"],
        },
        {
            "kind": "stage",
            "identity": "transitions",
            "status": "started",
            "at": "2026-01-01T00:00:01Z",
        },
    )
    points = replay.decision_points(entries)
    assert [p.stage for p in points] == ["transitions"]
    assert points[0].candidates == ("mix", "transitions", "edl")
    assert points[0].candidate_origin == "walk_seed_agenda"
    assert points[0].from_walk is True


def test_a_dispatch_outside_the_walk_list_narrows_scope_instead_of_widening_it() -> None:
    """Otherwise a heal pin gets scored against a list the driver was not choosing from."""
    entries = _entries(
        {"kind": "fallback", "identity": "walk_seed_agenda", "stages": ["mix", "edl"]},
        {
            "kind": "stage",
            "identity": "speaker_roles",
            "status": "started",
            "at": "2026-01-01T00:00:01Z",
        },
    )
    point = replay.decision_points(entries)[0]
    assert point.candidates == ("speaker_roles",)
    assert point.candidate_origin == "scope_narrowed"


def test_only_started_rows_are_decision_points() -> None:
    entries = _entries(
        {"kind": "stage", "identity": "mix", "status": "started", "at": "2026-01-01T00:00:01Z"},
        {"kind": "stage", "identity": "mix", "status": "done", "at": "2026-01-01T00:00:02Z"},
        {"kind": "stage", "identity": "mix", "status": "failed", "at": "2026-01-01T00:00:03Z"},
        {"kind": "admit", "identity": "admit:write:x", "at": "2026-01-01T00:00:04Z"},
    )
    assert len(replay.decision_points(entries)) == 1


# ---------------------------------------------------------------------------
# 5. state reconstruction
# ---------------------------------------------------------------------------

def test_done_state_unions_the_ledger_and_the_marker_mtime() -> None:
    dones = [(100.0, "transcribe")]
    markers = {"ingest": 50.0, "mix": 500.0}
    assert replay.done_at(120.0, dones, [], markers) == {"transcribe", "ingest"}
    assert replay.done_at(60.0, dones, [], markers) == {"ingest"}


def test_an_invalidation_reopens_a_stage_that_had_completed() -> None:
    dones = [(100.0, "edl")]
    invalidations = [(150.0, frozenset({"edl"}))]
    assert "edl" in replay.done_at(120.0, dones, invalidations, {})
    assert "edl" not in replay.done_at(200.0, dones, invalidations, {})


def test_a_completion_after_the_invalidation_still_counts() -> None:
    dones = [(100.0, "edl"), (200.0, "edl")]
    invalidations = [(150.0, frozenset({"edl"}))]
    assert "edl" in replay.done_at(250.0, dones, invalidations, {})


# ---------------------------------------------------------------------------
# 6. the corpus is read-only and bounded
# ---------------------------------------------------------------------------

def test_the_scan_budget_is_a_hard_cap(tmp_path: Path) -> None:
    root = tmp_path / "executions"
    for i in range(12):
        run = root / f"exec_{i:05d}_20260101T000000Z"
        (run / "mastering" / "homunculus").mkdir(parents=True)
        (run / "mastering" / "homunculus" / "ledger.json").write_text("{}", encoding="utf-8")
    assert len(replay.select_corpus(limit=5, root=root)) == 5
    assert len(replay.select_corpus(limit=100, root=root)) == 12


def test_the_pinned_run_sorts_to_the_front(tmp_path: Path) -> None:
    root = tmp_path / "executions"
    for name, size in (("exec_11871_x_20260101T000000Z", 10), ("exec_99999_20260101T000000Z", 9999)):
        run = root / name
        (run / "mastering" / "homunculus").mkdir(parents=True)
        (run / "mastering" / "homunculus" / "ledger.json").write_text(
            "x" * size, encoding="utf-8"
        )
    specs = replay.select_corpus(limit=10, root=root)
    assert specs[0].run_id.startswith("exec_11871")


def test_a_snapshot_is_a_copy_and_never_a_link_back_to_the_corpus(tmp_path: Path) -> None:
    """A write through a hardlink would edit the forensics tree itself."""
    source = tmp_path / "run"
    (source / "transcript").mkdir(parents=True)
    (source / "run_meta.json").write_text('{"homunculus_version": "0.2.0"}', encoding="utf-8")
    data = source / "transcript" / "full.json"
    data.write_text('{"segments": []}', encoding="utf-8")

    snapshot = replay.Snapshot.build(source, tmp_path / "snap")
    snapshot.advance_to(data.stat().st_mtime)
    copied = tmp_path / "snap" / "transcript" / "full.json"
    assert copied.is_file()
    assert copied.stat().st_ino != data.stat().st_ino
    copied.write_text("clobbered", encoding="utf-8")
    assert data.read_text(encoding="utf-8") == '{"segments": []}'


def test_large_media_becomes_a_same_size_placeholder_but_json_is_copied_whole(
    tmp_path: Path,
) -> None:
    """A placeholder for transcript/full.json reads as a corrupt artifact and
    fabricates hard_input_missing — the single worst replay artifact available."""
    source = tmp_path / "run"
    (source / "transcript").mkdir(parents=True)
    (source / "run_meta.json").write_text("{}", encoding="utf-8")
    big_json = source / "transcript" / "full.json"
    big_json.write_text(json.dumps({"segments": ["x" * 400_000]}), encoding="utf-8")
    wav = source / "master.wav"
    wav.write_bytes(b"\x00" * 400_000)

    snapshot = replay.Snapshot.build(source, tmp_path / "snap")
    snapshot.advance_to(max(big_json.stat().st_mtime, wav.stat().st_mtime))
    out_json = tmp_path / "snap" / "transcript" / "full.json"
    out_wav = tmp_path / "snap" / "master.wav"
    assert json.loads(out_json.read_text(encoding="utf-8"))["segments"]
    assert out_wav.stat().st_size == wav.stat().st_size


def test_the_matrix_version_seal_is_stripped_from_the_replayed_run_meta(
    tmp_path: Path,
) -> None:
    """Old runs were sealed against an old matrix; keeping the seal denies every write."""
    from interview_mux.artifact_ownership import MATRIX_VERSION_META_KEY

    source = tmp_path / "run"
    source.mkdir()
    (source / "run_meta.json").write_text(
        json.dumps({"run_mode": "full-auto", MATRIX_VERSION_META_KEY: "stale"}),
        encoding="utf-8",
    )
    replay.Snapshot.build(source, tmp_path / "snap")
    meta = json.loads((tmp_path / "snap" / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["run_mode"] == "full-auto"
    assert MATRIX_VERSION_META_KEY not in meta


def test_the_harness_never_writes_to_the_executions_tree() -> None:
    source = (REPO / "tools" / "solver_replay.py").read_text(encoding="utf-8")
    assert "os.link" not in source and "symlink_to" not in source
    assert "TemporaryDirectory" in source


# ---------------------------------------------------------------------------
# 7. the census is reported, not buried
# ---------------------------------------------------------------------------

class _Verdict:
    def __init__(
        self,
        stage: str,
        admissible: bool,
        unknowns: tuple[str, ...] = (),
        reasons: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.admissible = admissible
        self.unknowns = unknowns
        self.reasons = reasons or (() if admissible else ("hard_input_missing:x",))

    @property
    def confident(self) -> bool:
        return not self.unknowns


class _Decision:
    def __init__(self, verdicts, confident_pick) -> None:
        self.verdicts = verdicts
        self.would_choose_confident = confident_pick


def test_the_census_counts_confident_deferred_and_blocked_separately() -> None:
    decision = _Decision(
        [
            _Verdict("ingest", True),
            _Verdict("mix", True, ("hard_inputs_undeclared",)),
            _Verdict("edl", True, ("gate_may_pause:g_publish",)),
            _Verdict("transcribe", False),
        ],
        "ingest",
    )
    census = replay.census_for(decision)
    assert (census.confident, census.deferred, census.blocked) == (1, 2, 1)
    assert census.complete == 0
    assert census.has_authority is True
    assert census.defer_buckets == {"coverage": 1, "structural": 1}


def test_a_finished_stage_is_counted_complete_and_not_blocked() -> None:
    """`already_done` is a blocker for admissibility and a lie in a census: the blocked
    count would climb toward 72 precisely because the run was succeeding."""
    decision = _Decision(
        [
            _Verdict("ingest", False, reasons=("already_done",)),
            _Verdict("mix", False, reasons=("hard_input_missing:master/edl.json",)),
        ],
        None,
    )
    census = replay.census_for(decision)
    assert (census.complete, census.blocked) == (1, 1)


def test_already_done_must_be_the_sole_reason_to_count_as_complete() -> None:
    """Otherwise a genuinely blocked stage gets laundered into the complete bucket."""
    assert replay.verdict_is_complete(_Verdict("mix", False, reasons=("already_done",)))
    assert not replay.verdict_is_complete(
        _Verdict("mix", False, reasons=("already_done", "lease_held_by_gui"))
    )
    assert not replay.verdict_is_complete(_Verdict("mix", False, reasons=()))


def test_the_verdict_total_still_accounts_for_every_stage() -> None:
    """Splitting a bucket must not drop a verdict on the floor."""
    run = replay.RunReplay(run_id="r", points=1, evaluated=1)
    run.census = replay.Census(confident=2, deferred=5, blocked=3, complete=4)
    run.census_points = 1
    summary = replay.summarise([run])
    assert summary["stage_verdicts"] == 14
    assert (
        summary["confident_admissible"]
        + summary["deferred_stages"]
        + summary["blocked_stages"]
        + summary["complete_stages"]
        == summary["stage_verdicts"]
    )


def test_no_confident_pick_means_the_walk_still_decides() -> None:
    decision = _Decision([_Verdict("mix", True, ("hard_inputs_undeclared",))], None)
    assert replay.census_for(decision).has_authority is False


def test_the_report_headline_carries_coverage_and_agreement_together() -> None:
    run = replay.RunReplay(run_id="r", points=1, evaluated=1)
    run.census = replay.Census(confident=2, deferred=70, blocked=0)
    run.census_points = 1
    run.authority_points = 1
    markdown = replay.render_markdown(replay.summarise([run]))
    headline = markdown.split("## Corpus")[0]
    assert "authority" in headline.lower()
    assert "deferred" in headline.lower()
    assert "worthless as a gate" in headline


def test_the_report_states_plainly_whether_the_d12_bar_is_met() -> None:
    run = replay.RunReplay(run_id="r", points=1, evaluated=1)
    run.observations.append(_observation(replay.CHOICE, choice_evidence="ledger"))
    vetoed = replay.render_markdown(replay.summarise([run]))
    assert "D12 gate NOT MET" in vetoed
    assert "VETOED" in vetoed
    assert "D12 gate MET" in replay.render_markdown(replay.summarise([]))


def test_the_report_shows_the_already_complete_split_in_the_census() -> None:
    run = replay.RunReplay(run_id="r", points=1, evaluated=1)
    run.census = replay.Census(confident=1, deferred=1, blocked=1, complete=9)
    run.census_points = 1
    run.observations.append(_observation(replay.ALREADY_DONE, source="rerun"))
    markdown = replay.render_markdown(replay.summarise([run]))
    assert "already complete" in markdown
    assert "solver.py:602" in markdown


def test_the_verdict_section_precedes_every_number(tmp_path: Path) -> None:
    markdown = replay.render_markdown(replay.summarise([]))
    assert markdown.index("## Verdict") < markdown.index("## Corpus")
    assert "What this replay cannot prove" in markdown


def test_the_report_always_states_what_replay_cannot_prove() -> None:
    markdown = replay.render_markdown(replay.summarise([]))
    for note in replay.FIDELITY:
        assert note in markdown


# ---------------------------------------------------------------------------
# 8. end to end against a synthetic run
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("posture", ["full-auto", "manual"])
def test_a_synthetic_run_replays_without_touching_the_source(
    tmp_path: Path, posture: str
) -> None:
    root = tmp_path / "executions"
    run = root / "exec_00042_20260101T000000Z"
    (run / "mastering" / "homunculus").mkdir(parents=True)
    (run / ".stage_done").mkdir(parents=True)
    (run / "run_meta.json").write_text(
        json.dumps(
            {
                "homunculus_version": "0.2.0",
                "homunculus_control_plane": "deterministic",
                "run_mode": posture,
                "full_auto": posture == "full-auto",
            }
        ),
        encoding="utf-8",
    )
    (run / "mastering" / "homunculus" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": _entries(
                    {
                        "kind": "fallback",
                        "identity": "walk_seed_agenda",
                        "stages": ["ingest", "transcribe"],
                    },
                    {
                        "kind": "stage",
                        "identity": "ingest",
                        "status": "started",
                        "at": "2026-01-01T00:00:01Z",
                    },
                ),
            }
        ),
        encoding="utf-8",
    )
    before = {p: p.stat().st_mtime for p in run.rglob("*") if p.is_file()}

    spec = replay.select_corpus(limit=10, root=root)[0]
    result = replay.replay_run(spec, workdir=tmp_path / "work")

    assert result.error == ""
    assert result.points == 1
    assert len(result.observations) == 1
    assert result.observations[0].klass in {
        replay.AGREE,
        replay.DEFER,
        replay.SKIP,
        replay.CHOICE,
        replay.ALREADY_DONE,
    }
    assert result.census_points == 1
    assert {p: p.stat().st_mtime for p in run.rglob("*") if p.is_file()} == before
