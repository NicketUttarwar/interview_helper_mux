"""Runtime read/write recorder + conformance ratchet (plan §4.1, todo `p1-conformance`).

The recorder measures what stage bodies really touch; this test compares that
against `docs/cross-cutting/stage-contracts/*.yaml`. Enforcement is per group:

* a group in `contract_conformance.STRICT_GROUPS` **fails** on an undeclared
  read or write;
* every other group is **report-only** — findings are collected and printed but
  never fail, which is what lets the 45 hollow contracts be populated one group
  at a time without the suite going red in between (plan §3, the ratchet).

`STRICT_GROUPS` only ever grows. `MUX_CONTRACT_STRICT_GROUPS` overrides it per
plan §8.10 so one bad group can be reverted without reverting the campaign.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import contract_conformance as cc
from interview_mux.artifact_dependency_graph import build_graph
from interview_mux.stage_contract import PIPELINE_TIERS, all_contract_stage_ids, load_contract
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

from run_fixtures import isolated_run_ctx

# A path the ownership catalog has no row for, so `write_permitted` answers
# `unknown_path` rather than naming another owner. That is the shape of a stage
# minting an unmodelled artifact — a genuine undeclared write, not a `ctx.path()`
# probe of somebody else's file.
_UNMODELLED_WRITE = "ingest/not_in_the_ownership_catalog.json"


@pytest.fixture(autouse=True)
def _clean_recorder():
    """`build_graph()` is lru_cached over contract YAML; the flag read is cached too."""
    build_graph.cache_clear()
    cc.clear_in_process()
    cc.reset_flag_cache()
    yield
    build_graph.cache_clear()
    cc.clear_in_process()
    cc.reset_flag_cache()
    exit_stage_staging()


def _ctx(tmp_path: Path):
    return isolated_run_ctx(tmp_path, "exec_conformance_20260101T000000Z")


# ---------------------------------------------------------------------------
# Recorder: off by default, cheap, and never a writer without authority
# ---------------------------------------------------------------------------

def test_recorder_is_off_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv(cc._ENV_RECORD, raising=False)
    cc.reset_flag_cache()
    assert cc.recording_enabled() is False

    ctx = _ctx(tmp_path)
    enter_stage_staging("transcribe")
    ctx.path("transcript", "full.json")
    ctx.read_path("ingest", "normalized.wav")
    exit_stage_staging()
    assert cc.observed_in_process(ctx) == {}
    assert cc.flush_observed(ctx) is None
    assert not (ctx.run_dir / cc.CONTRACT_OBSERVED_REL).exists()


@pytest.mark.parametrize("raw", ["0", "false", "off", "no", ""])
def test_recorder_flag_only_accepts_truthy(monkeypatch: pytest.MonkeyPatch, raw: str):
    monkeypatch.setenv(cc._ENV_RECORD, raw)
    cc.reset_flag_cache()
    assert cc.recording_enabled() is False


def test_recorder_captures_reads_and_writes_through_ctx_seams(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv(cc._ENV_RECORD, "1")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)

    enter_stage_staging("transcribe")
    try:
        ctx.path("transcript", "full.json")          # resolve_write_path
        ctx.read_path("ingest", "normalized.wav")     # resolve_read_path
        ctx.artifact_path("transcript/speakers.json")  # read_path alias
    finally:
        exit_stage_staging()

    observed = cc.observed_in_process(ctx)
    assert observed["transcribe"]["writes"] == ["transcript/full.json"]
    assert observed["transcribe"]["reads"] == [
        "ingest/normalized.wav",
        "transcript/speakers.json",
    ]


def test_recorder_ignores_infrastructure_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """No contract declares run_meta / done markers / operator telemetry."""
    monkeypatch.setenv(cc._ENV_RECORD, "1")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)

    enter_stage_staging("ingest")
    try:
        ctx.path("run_meta.json")
        ctx.path(".stage_done", "ingest")
        ctx.path("operator", "execution_status.json")
        ctx.path("ingest", "checksums.json")
    finally:
        exit_stage_staging()

    assert cc.observed_in_process(ctx)["ingest"]["writes"] == ["ingest/checksums.json"]


def test_recorder_records_nothing_outside_a_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv(cc._ENV_RECORD, "1")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)
    ctx.path("transcript", "full.json")
    assert cc.observed_in_process(ctx) == {}


def test_observed_map_is_persisted_and_merged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv(cc._ENV_RECORD, "1")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)

    enter_stage_staging("ingest")
    try:
        ctx.path("ingest", "checksums.json")
    finally:
        exit_stage_staging()
    dest = cc.flush_observed(ctx)
    assert dest is not None and dest.is_file()

    # A second process contributes a different path; the record must union.
    cc.clear_in_process(ctx)
    enter_stage_staging("ingest")
    try:
        ctx.path("ingest", "loudness.json")
    finally:
        exit_stage_staging()
    cc.flush_observed(ctx)
    assert cc.read_observed(ctx)["ingest"]["writes"] == [
        "ingest/checksums.json",
        "ingest/loudness.json",
    ]


def test_recorder_refuses_to_write_without_an_ownership_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The observer must not be the reason a run gains an unauthorised write."""
    monkeypatch.setenv(cc._ENV_RECORD, "1")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "deny:test"),
    )
    assert cc.flush_observed(ctx) is None
    assert not (ctx.run_dir / cc.CONTRACT_OBSERVED_REL).exists()


def test_observed_path_has_an_ownership_allow_row():
    from interview_mux import artifact_ownership as ownership

    ok, reason = ownership.write_permitted(
        None, cc.CONTRACT_OBSERVED_REL, None, role="ops", verb="persist"
    )
    assert ok, f"{cc.CONTRACT_OBSERVED_REL} needs an ownership row: {reason}"
    # A row of its own, not the generic `operator/` fallback.
    assert reason == "operational"
    assert ownership.owners_of(cc.CONTRACT_OBSERVED_REL) == ("ops",)


def test_recorder_never_raises_from_the_seam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv(cc._ENV_RECORD, "1")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(cc, "note_write", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    enter_stage_staging("ingest")
    try:
        assert ctx.path("ingest", "checksums.json")  # resolves despite the recorder
    finally:
        exit_stage_staging()


def test_wrapped_stage_records_and_flushes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The hook is wired into `run_wrapped_stage`, not just callable in theory."""
    from interview_mux import write_staging

    monkeypatch.setenv(cc._ENV_RECORD, "1")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(write_staging, "require_stage_inputs", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.require_stage_inputs", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.maybe_require_upstream_llm_progress",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(write_staging, "preflight_stage_enter", lambda *a, **k: None)
    monkeypatch.setattr(write_staging, "after_stage_write_check", lambda *a, **k: None)

    def body():
        ctx.path("ingest", "checksums.json")
        ctx.read_path("preclean", "isolated.wav")

    write_staging.run_wrapped_stage(ctx, "ingest", body)

    observed = cc.read_observed(ctx)["ingest"]
    assert observed["writes"] == ["ingest/checksums.json"]
    assert observed["reads"] == ["preclean/isolated.wav"]
    assert (ctx.run_dir / cc.CONTRACT_OBSERVED_REL).is_file()


def test_wrapped_stage_records_nothing_when_the_flag_is_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from interview_mux import write_staging

    monkeypatch.delenv(cc._ENV_RECORD, raising=False)
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.require_stage_inputs", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.maybe_require_upstream_llm_progress",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(write_staging, "preflight_stage_enter", lambda *a, **k: None)
    monkeypatch.setattr(write_staging, "after_stage_write_check", lambda *a, **k: None)

    write_staging.run_wrapped_stage(ctx, "ingest", lambda: ctx.path("ingest", "checksums.json"))
    assert not (ctx.run_dir / cc.CONTRACT_OBSERVED_REL).exists()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def test_evaluate_flags_undeclared_reads_and_writes():
    report = cc.evaluate(
        {
            "ingest": {
                "reads": ["understanding/speakers.json"],
                "writes": [_UNMODELLED_WRITE],
            }
        }
    )
    kinds = {(f.kind, f.path) for f in report.findings}
    assert (cc.UNDECLARED_READ, "understanding/speakers.json") in kinds
    assert (cc.UNDECLARED_WRITE, _UNMODELLED_WRITE) in kinds


def test_a_write_ownership_refuses_is_reclassified_as_a_path_probe():
    """`ctx.path()` on another stage's artifact is a resolution, not a write.

    A real write there raises `authority_denied` at commit, so recording it as an
    undeclared write would fail a flipped group for something that cannot happen.
    """
    report = cc.evaluate({"ingest": {"reads": [], "writes": ["master/edl.json"]}})
    probes = [f for f in report.findings if f.path == "master/edl.json"]
    assert [f.kind for f in probes] == [cc.PROBE_WRITE]
    assert not probes[0].blocking


def test_evaluate_accepts_declared_paths_and_output_readback():
    report = cc.evaluate(
        {"ingest": {"reads": ["ingest/normalized.wav"], "writes": ["ingest/normalized.wav"]}}
    )
    assert [f for f in report.findings if f.blocking] == []


def test_declared_but_untouched_is_never_blocking():
    report = cc.evaluate({"ingest": {"reads": [], "writes": []}})
    assert report.findings, "declared outputs that were never written should be reported"
    assert all(not f.blocking for f in report.findings)


def test_glob_output_specs_match_concrete_paths():
    assert cc._matches("transcript/review_clips/a.wav", "glob:transcript/review_clips/*.wav")
    assert not cc._matches("transcript/full.json", "glob:transcript/review_clips/*.wav")


def test_findings_carry_their_group():
    report = cc.evaluate({"ingest": {"reads": ["master/edl.json"], "writes": []}})
    assert {f.group for f in report.findings} == {"prepare"}


# ---------------------------------------------------------------------------
# The ratchet
# ---------------------------------------------------------------------------

def test_strict_groups_are_a_subset_of_the_real_phases():
    from interview_mux.v2.phases import PHASES

    known = {str(p.get("id")) for p in PHASES}
    assert set(cc.STRICT_GROUPS) <= known


def test_strict_group_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(cc._ENV_STRICT_GROUPS, "prepare, build")
    assert cc.strict_groups() == {"prepare", "build"}
    monkeypatch.setenv(cc._ENV_STRICT_GROUPS, "")
    assert cc.strict_groups() == frozenset()


def test_the_flipped_groups_are_pinned():
    """Pinned so a flip is a deliberate, reviewed change — and only ever adds."""
    assert cc.STRICT_GROUPS == ("prepare", "understand-c", "sound")


# Why each remaining group is still report-only. Every entry is a claim about
# code or about the ownership catalog, not about a contract — none of them can be
# closed by declaring another input, which is why the D11 ratchet stopped here.
REPORT_ONLY_REASONS: dict[str, str] = {
    "understand-a": (
        "flipping it makes content_context / talking_points_compose / "
        "ideal_cuts_propose precision_droppable, which is the state "
        "tests/test_precision_invalidation.py::test_an_ungreen_consumer_is_never_"
        "dropped pins against"
    ),
    "understand-b": (
        "flipping it drops boundary_topic_resplit from framing_posture_decide's "
        "fan-out, and boundary_topic_resplit still reads protected_zones / "
        "run_golden_facts / interview_spine through helpers no contract declares"
    ),
    "fill_gaps": (
        "missing_framing and gap_framing_compose write "
        "understanding/interviewer_script.txt with Path.write_text, bypassing the "
        "commit path; the artifact has no ownership catalog row, so it can be "
        "neither declared as an output nor honestly ignored"
    ),
    "plan_rank": (
        "flipping it drops gap_report_sanitize from nugget_layup_compose's "
        "fan-out even though nugget_layup_compose is a permitted writer of "
        "understanding/gap_report.json — _input_producers collapses that "
        "five-writer artifact to one canonical producer"
    ),
    "build": (
        "5 of 11 stages have no row in tools/contract_dependency_data.py, so "
        "their inputs are whatever the generator could derive; edl_narrative_audit "
        "declares one input and reads five"
    ),
    "ship": (
        "3 of 7 stages have no dependency-data row; master_transcript_build reads "
        "six undeclared artifacts and podcast_publish writes publish/cover.png "
        "and publish/cover_meta.json undeclared"
    ),
}


def test_the_report_only_groups_are_pinned():
    """The six groups the ratchet stopped short of, each with its reason.

    Pinned in the same shape as the flipped set so closing one of these gaps is a
    reviewed change too, and so the list can only shrink.
    """
    from interview_mux.v2.phases import PHASES, phase_stage_ids

    dispatchable = {str(p.get("id")) for p in PHASES if phase_stage_ids(str(p.get("id")))}
    assert dispatchable - set(cc.STRICT_GROUPS) == set(REPORT_ONLY_REASONS)


def test_a_flip_leaves_precision_invalidation_inert():
    """A flipped group must not start dropping stages from invalidation sets.

    `precision_eligible` reads `STRICT_GROUPS`, so flipping a group is also a
    claim that its stages may be left out of an upstream redo's fan-out. Under-
    invalidation ships a master built from stale parts, so a flip is only allowed
    while `transitive_invalidate` still equals `_blanket_invalidate` everywhere.
    """
    from interview_mux import artifact_dependency_graph as adg
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    dropped = {
        sid: [s for s in adg._blanket_invalidate(sid) if s not in adg.transitive_invalidate(sid)]
        for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    }
    assert {k: v for k, v in dropped.items() if v} == {}


def test_fail_mode_actually_fails_for_a_flipped_group(tmp_path: Path):
    """The ratchet has teeth: a recorded undeclared write in `prepare` blocks."""
    report = cc.evaluate({"ingest": {"reads": [], "writes": [_UNMODELLED_WRITE]}})
    blocking = report.blocking(groups={"prepare"})
    assert [f.kind for f in blocking] == [cc.UNDECLARED_WRITE]
    # ... and the same finding in a group still in report-only does not.
    later = cc.evaluate({"mix": {"reads": [], "writes": ["publish/audio.mp3"]}})
    assert later.blocking(groups={"prepare"}) == []


def test_recorded_run_conformance_for_flipped_groups(tmp_path: Path):
    """Read `operator/contract_observed.json` if a real run left one behind.

    This is the assertion the DoD §3.5 item 2 turns on. In a unit environment
    there is no recorded map, so it is a no-op; against a run directory produced
    with `MUX_CONTRACT_RECORD=1` it fails on any undeclared read or write by a
    flipped group's stages.
    """
    ctx = _ctx(tmp_path)
    observed = cc.read_observed(ctx)
    if not observed:
        pytest.skip("no recorded contract_observed.json — run with MUX_CONTRACT_RECORD=1")
    blocking = cc.evaluate(observed).blocking()
    assert blocking == [], "\n".join(str(f) for f in blocking)


def test_non_strict_groups_are_report_only():
    """A mismatch in a group not yet flipped must not be blocking."""
    report = cc.evaluate({"podcast_publish": {"reads": ["master/edl.json"], "writes": []}})
    assert report.findings
    assert report.blocking(groups=frozenset()) == []


def test_runtime_hook_is_report_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Even a strict group only *warns* at runtime — a wrong contract cannot halt a run."""
    monkeypatch.setenv(cc._ENV_RECORD, "1")
    monkeypatch.setenv(cc._ENV_STRICT_GROUPS, "prepare")
    cc.reset_flag_cache()
    ctx = _ctx(tmp_path)

    enter_stage_staging("ingest")
    try:
        ctx.path(*_UNMODELLED_WRITE.split("/"))  # undeclared write by a strict-group stage
    finally:
        exit_stage_staging()

    findings = cc.warn_on_mismatch(ctx, "ingest")
    assert any(f.kind == cc.UNDECLARED_WRITE for f in findings)


# ---------------------------------------------------------------------------
# Contract shape invariants the recorder depends on
# ---------------------------------------------------------------------------

def test_every_pipeline_stage_maps_to_exactly_one_group():
    unmapped = [
        sid
        for sid in all_contract_stage_ids()
        if (c := load_contract(sid))
        and c.tier in PIPELINE_TIERS
        and not cc.group_for_stage(sid)
    ]
    assert unmapped == [], f"pipeline stages with no conformance group: {unmapped}"


def test_declared_input_producers_name_real_contracts():
    """A `producer` that is not a contract id would mint a phantom `requires` edge."""
    known = set(all_contract_stage_ids())
    unknown: dict[str, set[str]] = {}
    for sid in known:
        contract = load_contract(sid)
        if not contract:
            continue
        for dep in contract.inputs:
            if dep.producer and dep.producer not in known:
                unknown.setdefault(sid, set()).add(dep.producer)
    # `junction_thought_complete` cites `transcription` (typo for `transcribe`);
    # it predates this campaign and is a `meta` contract, so it is pinned rather
    # than silently fixed.
    assert unknown == {"junction_thought_complete": {"transcription"}}


def test_strict_groups_have_no_blocking_findings_from_the_declared_shape():
    """The ratchet itself: a flipped group must be clean against recorded reality.

    With no recording available in a unit test there is nothing observed, so this
    asserts the weaker static property that every strict-group stage declares at
    least one output — the precondition for the runtime check to mean anything.
    """
    thin: list[str] = []
    for group in cc.strict_groups():
        from interview_mux.v2.phases import phase_stage_ids

        for sid in phase_stage_ids(group):
            contract = load_contract(sid)
            if not contract or not contract.outputs:
                thin.append(sid)
    assert thin == [], f"strict group stages with no declared outputs: {thin}"
