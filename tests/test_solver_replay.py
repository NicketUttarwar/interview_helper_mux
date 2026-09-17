"""The replay harness must not be able to manufacture a green promotion verdict.

``tools/solver_replay.py`` stands in for the live full-auto run the forensics campaign
forbids, so its failure mode is not "wrong number" — it is "reassuring number". Three
ways it could reassure wrongly, each pinned here:

1. **False green from emptiness.** ``solver.shadow_summary()["zero"]`` keys on
   ``disagree`` alone, and a solver with no justified opinion disagrees with nobody. So
   zero disagreements must NOT be sufficient: the verdict has to veto on coverage too.
2. **Merged divergence classes.** A dispatch the solver would have *skipped* is the
   thrash refusal this campaign exists to produce; a dispatch it would have *replaced*
   is a real disagreement. Summing them hides the second inside the first.
3. **Drift from the live classifier.** The harness reuses
   ``solver.compare_walk_choice`` rather than reimplementing it, and its deferral
   buckets must stay exhaustive over the unknowns the solver actually emits.

Plus the safety property the corpus depends on: replaying a run must never write into
``ASSETS/executions``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import solver_replay as replay  # noqa: E402

from interview_mux import solver  # noqa: E402


# ---------------------------------------------------------------------------
# 1. the verdict cannot go green on emptiness
# ---------------------------------------------------------------------------

def _summary(**patch) -> dict:
    base = {
        "choice_divergences": 0,
        "choice_unexplained": 0,
        "choice_reconstruction_limited": 0,
        "authority_rate": 0.95,
        "structural_defer_rate": 0.0,
    }
    base.update(patch)
    return base


def test_zero_disagreements_alone_does_not_promote() -> None:
    """The exact false green: no disagreements because there are no opinions."""
    verdict = replay.promotion_verdict(_summary(authority_rate=0.06))
    assert verdict["promote"] is False
    assert "solver_has_authority" in verdict["vetoes"]


def test_a_real_disagreement_vetoes_even_with_perfect_coverage() -> None:
    verdict = replay.promotion_verdict(
        _summary(choice_divergences=1, choice_unexplained=1)
    )
    assert verdict["promote"] is False
    assert "no_unexplained_disagreements" in verdict["vetoes"]


def test_a_reconstruction_limited_divergence_is_reported_but_does_not_veto() -> None:
    """The evidence, not the solver, is what fails on these — and dropping them silently
    would be the same laundering this harness exists to prevent, so they stay visible."""
    verdict = replay.promotion_verdict(
        _summary(choice_divergences=13, choice_reconstruction_limited=13)
    )
    assert verdict["promote"] is True
    detail = verdict["checks"][0]["detail"]
    assert "13" in detail and "mtime-only" in detail


def test_evidence_is_read_off_the_ledger_not_guessed() -> None:
    assert replay.choice_evidence("mix", {"mix", "edl"}) == "ledger"
    assert replay.choice_evidence("content_brief_reanchor", {"mix"}) == "mtime_only"


def test_structural_deferral_vetoes_because_population_will_never_fix_it() -> None:
    verdict = replay.promotion_verdict(_summary(structural_defer_rate=0.4))
    assert verdict["promote"] is False
    assert "structural_deferral_bounded" in verdict["vetoes"]


def test_promotion_needs_every_condition_at_once() -> None:
    assert replay.promotion_verdict(_summary())["promote"] is True
    assert replay.promotion_verdict(_summary(authority_rate=None))["promote"] is False


def test_the_authority_bar_is_a_majority_not_a_token() -> None:
    """A bar low enough to pass on a handful of opinions is the bug, not the gate."""
    assert replay.MIN_AUTHORITY_RATE >= 0.5
    assert replay.MAX_CHOICE_DIVERGENCES == 0


# ---------------------------------------------------------------------------
# 2. the two divergence classes stay apart
# ---------------------------------------------------------------------------

class _Comparison:
    def __init__(self, verdict: str, chosen: str = "mix", choice: str | None = None) -> None:
        self.verdict = verdict
        self.chosen = chosen
        self.solver_choice = choice


def test_a_refused_dispatch_is_skip_and_a_replaced_one_is_choice() -> None:
    skip, _ = replay.classify(_Comparison(solver.DISAGREE), set())
    assert skip == replay.SKIP
    choice, ever = replay.classify(_Comparison(solver.DISAGREE, choice="edl"), {"edl"})
    assert choice == replay.CHOICE
    assert ever is True


def test_agree_and_defer_pass_through_unchanged() -> None:
    assert replay.classify(_Comparison(solver.AGREE), set())[0] == replay.AGREE
    assert replay.classify(_Comparison(solver.DEFER), set())[0] == replay.DEFER


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
    def __init__(self, stage: str, admissible: bool, unknowns: tuple[str, ...] = ()) -> None:
        self.stage = stage
        self.admissible = admissible
        self.unknowns = unknowns

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
    assert census.has_authority is True
    assert census.defer_buckets == {"coverage": 1, "structural": 1}


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
    assert "worthless on its own" in headline


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
    }
    assert result.census_points == 1
    assert {p: p.stat().st_mtime for p in run.rglob("*") if p.is_file()} == before
