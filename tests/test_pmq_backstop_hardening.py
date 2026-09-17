"""PMQ is the last backstop before a wrong master ships. These are its own tests.

Three holes are covered here.

1. **Fail-open count.** An exception while counting ship-bar defects used to yield
   ``{"open_ship_bar": 0}``, so the final safety check passed precisely when it was
   broken. It must refuse, with an operator-visible reason.
2. **Severity keyed on the stage.** ``degrades_ship_bar`` was a static stage
   allowlist, so whether a defect blocked depended on which stage recorded it. It is
   now a property of the defect, with the stage list kept as a floor that can only
   widen.
3. **The silent class.** ``record_defect`` only ever fired when a stage could not be
   *dispatched*. A stage that dispatches successfully and commits a semantically
   wrong artifact recorded nothing, which is the class the guard layer exists to
   catch. The sweep records it, report-only until enforced.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from interview_mux.defect_ledger import (
    DEFECT_LEDGER_REL,
    ORPHAN_ARTIFACT_STAGE,
    SEMANTIC_OUTPUT_BLOCKER,
    SEMANTIC_OUTPUT_MISSING_BLOCKER,
    SEMANTIC_SWEEP_SOURCE,
    SHIP_BAR_CRITICAL_STAGES,
    DefectLedgerUnreadable,
    defect_severity,
    defect_summary,
    defects,
    degrades_ship_bar,
    open_ship_bar_defects,
    orphan_rule_artifacts,
    read_defect_ledger,
    record_defect,
    record_semantic_output_defects,
    semantic_output_findings,
    semantic_rule_coverage,
    semantic_sweep_blocks,
    semantic_sweep_enforced,
)
from interview_mux.run_context import RunContext
from run_fixtures import mark_done_raw

_ENV_BLOCKING = "MUX_DEFECT_SEMANTIC_BLOCKING"
_ENV_BLOCKING_STAGES = "MUX_DEFECT_SEMANTIC_BLOCKING_STAGES"


def _ctx(tmp_path: Path, name: str) -> RunContext:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


def _raw_write(ctx: RunContext, rel: str, doc: Any) -> Path:
    """Commit an artifact straight to the run dir, bypassing write validation.

    The point of these tests is what the *checker* makes of a bad artifact, so the
    writer's own guards must not stand in the way of producing one.
    """
    dest = Path(ctx.run_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc), encoding="utf-8")
    return dest


def _corrupt_ledger(ctx: RunContext) -> Path:
    dest = Path(ctx.run_dir) / DEFECT_LEDGER_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{ this is not json", encoding="utf-8")
    return dest


def _check(quality: dict[str, Any], check_id: str) -> dict[str, Any]:
    for row in quality.get("checks") or []:
        if row.get("check_id") == check_id:
            return row
    raise AssertionError(f"{check_id} missing from PMQ checks")


@pytest.fixture(autouse=True)
def _report_only_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise ambient enforcement so each test states its own mode."""
    monkeypatch.delenv(_ENV_BLOCKING, raising=False)
    monkeypatch.delenv(_ENV_BLOCKING_STAGES, raising=False)


# ---------------------------------------------------------------------------
# 1 — the count fails CLOSED
# ---------------------------------------------------------------------------

def test_unreadable_ledger_raises_instead_of_counting_zero(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "pmq_unreadable_raises")
    _corrupt_ledger(ctx)
    with pytest.raises(DefectLedgerUnreadable):
        defect_summary(ctx)


def test_absent_ledger_is_zero_not_an_error(tmp_path: Path) -> None:
    """A run that never recorded a defect must not be refused."""
    ctx = _ctx(tmp_path, "pmq_absent_ledger")
    assert not (Path(ctx.run_dir) / DEFECT_LEDGER_REL).exists()
    assert defect_summary(ctx)["open_ship_bar"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        "{ this is not json",
        json.dumps([1, 2, 3]),
        json.dumps({"defects": ["not", "an", "object"]}),
        json.dumps({"defects": {}, "order": "not-a-list"}),
    ],
)
def test_pmq_refuses_publish_when_defects_cannot_be_counted(
    tmp_path: Path, payload: str
) -> None:
    """The fail-open regression: any counting error used to read as "no defects"."""
    from interview_mux import post_master_quality as pmq

    ctx = _ctx(tmp_path, f"pmq_failclosed_{abs(hash(payload))}")
    dest = Path(ctx.run_dir) / DEFECT_LEDGER_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(payload, encoding="utf-8")

    quality = pmq.evaluate_post_master_quality(ctx)
    row = _check(quality, "no_open_ship_bar_defects")
    assert row["passed"] is False
    assert "no_open_ship_bar_defects" in quality["structural_failed_checks"]
    assert quality["publish_allowed"] is False
    # Never a silent zero, and never a mysterious refusal.
    detail = row["detail"]
    assert detail["open_ship_bar"] is None
    assert detail["unresolved"] is True
    assert detail["error"]
    assert "operator/defect_ledger.json" in detail["operator_reason"]


def test_pmq_refuses_when_the_ledger_module_itself_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import defect_ledger, post_master_quality as pmq

    ctx = _ctx(tmp_path, "pmq_failclosed_raise")

    def boom(_ctx: RunContext) -> dict[str, Any]:
        raise RuntimeError("ledger backend exploded")

    monkeypatch.setattr(defect_ledger, "defect_summary", boom)
    quality = pmq.evaluate_post_master_quality(ctx)
    row = _check(quality, "no_open_ship_bar_defects")
    assert row["passed"] is False
    assert quality["publish_allowed"] is False
    assert "ledger backend exploded" in row["detail"]["error"]


def test_pmq_refuses_when_the_summary_is_the_wrong_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-dict summary must not slip through `.get` duck-typing."""
    from interview_mux import defect_ledger, post_master_quality as pmq

    ctx = _ctx(tmp_path, "pmq_failclosed_shape")
    monkeypatch.setattr(defect_ledger, "defect_summary", lambda _c: ["nonsense"])
    quality = pmq.evaluate_post_master_quality(ctx)
    assert _check(quality, "no_open_ship_bar_defects")["passed"] is False
    assert quality["publish_allowed"] is False


def test_recording_still_works_while_the_ledger_is_corrupt(tmp_path: Path) -> None:
    """Strictness belongs on the decision path, not on the advance-past path.

    `refuse_dispatch` must keep recording while the walk advances; only the count
    that gates publication refuses.
    """
    ctx = _ctx(tmp_path, "pmq_corrupt_write_path")
    _corrupt_ledger(ctx)
    row = record_defect(ctx, stage="mix", blocker="max_mix_cycles")
    assert row["degrades_ship_bar"] is True
    assert defect_summary(ctx)["open_ship_bar"] == 1
    assert "_unreadable" not in read_defect_ledger(ctx)


# ---------------------------------------------------------------------------
# 2 — severity is a property of the defect
# ---------------------------------------------------------------------------

_SAMPLE_BLOCKERS = (
    "",
    "no_delta",
    "attempt_memo",
    "max_mix_cycles",
    "max_invokes_per_identity",
    "missing_hard_input",
    SEMANTIC_OUTPUT_BLOCKER,
    SEMANTIC_OUTPUT_MISSING_BLOCKER,
    "some_future_blocker",
)

_SAMPLE_STAGES = tuple(sorted(SHIP_BAR_CRITICAL_STAGES)) + (
    "mmaudio_sfx",
    "sfx_prompt_craft",
    "music_palette_compose",
    "episode_cover_generate",
    "a_stage_nobody_has_written_yet",
)


def test_stage_floor_is_preserved_for_every_critical_stage() -> None:
    for stage in sorted(SHIP_BAR_CRITICAL_STAGES):
        severity = defect_severity(stage, "anything_at_all")
        assert severity.degrades_ship_bar is True, stage
        assert severity.reason == f"critical_stage:{stage}"


def test_severity_only_ever_widens_what_blocks() -> None:
    """Old rule: `stage in SHIP_BAR_CRITICAL_STAGES`. New rule must imply it."""
    for stage, blocker in product(_SAMPLE_STAGES, _SAMPLE_BLOCKERS):
        blocked_before = stage in SHIP_BAR_CRITICAL_STAGES
        blocked_now = degrades_ship_bar(stage, blocker)
        assert blocked_now or not blocked_before, (stage, blocker)


def test_serious_defect_outside_the_stage_list_now_blocks(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "pmq_severity_widen")
    assert "mmaudio_sfx" not in SHIP_BAR_CRITICAL_STAGES
    row = record_defect(ctx, stage="mmaudio_sfx", blocker="missing_hard_input")
    assert row["degrades_ship_bar"] is True
    assert row["ship_bar_reason"] == "critical_blocker:missing_hard_input"
    assert [r["stage"] for r in open_ship_bar_defects(ctx)] == ["mmaudio_sfx"]
    assert defect_summary(ctx)["open_ship_bar"] == 1


def test_declared_detail_severity_blocks_from_any_stage(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "pmq_severity_detail")
    row = record_defect(
        ctx,
        stage="music_palette_compose",
        blocker="something_bespoke",
        detail={"severity": "critical"},
    )
    assert row["degrades_ship_bar"] is True
    assert row["ship_bar_reason"] == "detail_severity:critical"


def test_budget_refusal_off_the_critical_path_still_does_not_block() -> None:
    """Widening must stay keyed on the artifact, not on spent budget.

    A spent cap says nothing about the output, and production already allows an
    omitted bed — treating it as severe everywhere would flood the ledger.
    """
    assert degrades_ship_bar("mmaudio_sfx", "max_invokes_per_identity") is False
    assert degrades_ship_bar("mmaudio_sfx", "attempt_memo") is False


def test_no_delta_override_behaviour_is_unchanged(tmp_path: Path) -> None:
    """`refuse_dispatch` suppresses `no_delta`; the classifier is recorded beside it."""
    from interview_mux.dispatch_door import DispatchVerdict, refuse_dispatch

    ctx = _ctx(tmp_path, "pmq_severity_nodelta")
    refuse_dispatch(
        ctx,
        "transitions",
        DispatchVerdict(False, "no_delta", {"input_digest": "abc"}),
        source="delivery_walk_to_master",
    )
    assert open_ship_bar_defects(ctx) == []
    row = defects(ctx)[0]
    assert row["degrades_ship_bar"] is False
    assert "caller:False" in row["ship_bar_reason"]
    assert "critical_stage:transitions" in row["ship_bar_reason"]


def test_legacy_single_argument_call_still_works() -> None:
    assert degrades_ship_bar("edl") is True
    assert degrades_ship_bar("mmaudio_sfx") is False


# ---------------------------------------------------------------------------
# 3 — a stage that SUCCEEDS and produces a wrong artifact
# ---------------------------------------------------------------------------

def _stage_done_with_bad_output(ctx: RunContext) -> None:
    """`edl` claims done; `master/edl.json` is absent. Dispatch recorded nothing."""
    mark_done_raw(ctx, "edl")


def test_successful_stage_with_missing_output_is_recorded(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "sweep_missing_output")
    _stage_done_with_bad_output(ctx)
    findings, report = semantic_output_findings(ctx)
    assert [f.stage for f in findings] == ["edl"]
    assert findings[0].status == "pending"
    assert findings[0].artifact == "master/edl.json"
    assert report["examined_stages"] == 1

    record_semantic_output_defects(ctx)
    row = defects(ctx)[0]
    assert row["stage"] == "edl"
    assert row["blocker"] == SEMANTIC_OUTPUT_MISSING_BLOCKER
    assert row["detail"]["source"] == SEMANTIC_SWEEP_SOURCE


def test_successful_stage_with_semantically_incomplete_output_is_recorded(
    tmp_path: Path,
) -> None:
    """The artifact is present and parseable; a `_gaps_*` rule is what refuses it."""
    ctx = _ctx(tmp_path, "sweep_incomplete_output")
    mark_done_raw(ctx, "full_master_ranking")
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": []})

    findings, _ = semantic_output_findings(ctx)
    assert len(findings) == 1
    assert findings[0].status == "partial"
    assert findings[0].coverage == "gap_rule"
    assert "ordered_segment_ids" in findings[0].gaps

    record_semantic_output_defects(ctx)
    assert defects(ctx)[0]["blocker"] == SEMANTIC_OUTPUT_BLOCKER


def test_complete_output_records_nothing(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "sweep_clean")
    mark_done_raw(ctx, "full_master_ranking")
    _raw_write(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "chapters": []},
    )
    findings, report = semantic_output_findings(ctx)
    assert findings == []
    assert report["findings"] == 0
    assert record_semantic_output_defects(ctx)["recorded_defect_ids"] == []


def test_detection_survives_a_passing_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-hollow proof: with json-schema forced to pass, the rules still refuse.

    If the sweep degraded to "file exists and validates", this test would find
    nothing — which is the failure mode that would license deleting the guards it
    claims to replace.
    """
    from interview_mux import artifact_completeness

    monkeypatch.setattr(artifact_completeness, "validate_artifact_write", lambda *_a: [])

    ctx = _ctx(tmp_path, "sweep_no_schema_help")
    mark_done_raw(ctx, "segment_classification", "speaker_roles")
    _raw_write(ctx, "segments/manifest.json", {"segments": []})
    _raw_write(ctx, "understanding/speakers.json", {"speakers": []})

    findings, _ = semantic_output_findings(ctx)
    by_stage = {f.stage: f for f in findings}
    assert set(by_stage) == {"segment_classification", "speaker_roles"}
    assert by_stage["segment_classification"].coverage == "gap_rule"
    assert "segments" in by_stage["segment_classification"].gaps
    assert "speakers" in by_stage["speaker_roles"].gaps


def test_the_whole_gaps_rule_table_is_exercised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every reachable `_gaps_*` rule must actually run during a sweep.

    A hollow version of this check is worse than none, so the rule table is spied
    on directly rather than inferred from a status string. `optimal_questions` is
    the one unreachable entry: it is a no-op allowlist (``lambda d: []``) and the
    stage declares no primary output, so it can only ever loosen a verdict.
    """
    from interview_mux import artifact_completeness as ac
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    called: set[str] = set()

    def spy(key: str, fn: Any) -> Any:
        def wrapped(data: Any) -> list[str]:
            called.add(key)
            return fn(data)

        return wrapped

    monkeypatch.setattr(
        ac,
        "ARTIFACT_COMPLETENESS_RULES",
        {k: spy(k, v) for k, v in ac.ARTIFACT_COMPLETENESS_RULES.items()},
    )
    monkeypatch.setattr(
        ac,
        "STAGE_GAP_RULES",
        {k: spy(f"stage:{k}", v) for k, v in ac.STAGE_GAP_RULES.items()},
    )

    ctx = _ctx(tmp_path, "sweep_rule_table")
    # Every artifact the rule table governs, present but empty, with its producing
    # stage stamped done so the sweep reaches it.
    for rel in ac.ARTIFACT_COMPLETENESS_RULES:
        _raw_write(ctx, rel, {})
        for stage, declared in STAGE_ARTIFACT_DISK_PATHS.items():
            if declared == rel:
                mark_done_raw(ctx, stage)
    for stage in ac.STAGE_GAP_RULES:
        if stage in STAGE_ARTIFACT_DISK_PATHS:
            mark_done_raw(ctx, stage)

    semantic_output_findings(ctx)

    expected = set(ac.ARTIFACT_COMPLETENESS_RULES) | {
        f"stage:{s}" for s in ac.STAGE_GAP_RULES if s in STAGE_ARTIFACT_DISK_PATHS
    }
    assert expected <= called, f"rules never invoked: {sorted(expected - called)}"
    # Guard the size of the table so a future shrink is a failing test, not a
    # silently weaker backstop.
    assert len(ac.ARTIFACT_COMPLETENESS_RULES) >= 20
    assert len(called) >= 21


def test_orphan_rule_artifacts_are_reachable(tmp_path: Path) -> None:
    """Rules for artifacts no stage declares must still run — else a third of the
    table is dead weight and the sweep is closer to an existence check."""
    ctx = _ctx(tmp_path, "sweep_orphans")
    mark_done_raw(ctx, "full_master_ranking")
    _raw_write(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "chapters": []},
    )
    orphans = orphan_rule_artifacts()
    assert "understanding/analysis_state.json" in orphans
    for rel in orphans:
        _raw_write(ctx, rel, {})

    findings, report = semantic_output_findings(ctx)
    assert report["examined_orphan_artifacts"] == len(orphans)
    orphan_findings = {f.artifact for f in findings if f.stage == ORPHAN_ARTIFACT_STAGE}
    assert orphan_findings == set(orphans)


def test_orphan_pass_is_skipped_when_nothing_completed(tmp_path: Path) -> None:
    """"Succeeded on bad data" presupposes a success; an abandoned run is not one."""
    ctx = _ctx(tmp_path, "sweep_orphans_idle")
    for rel in orphan_rule_artifacts():
        _raw_write(ctx, rel, {})
    findings, report = semantic_output_findings(ctx)
    assert findings == []
    assert report["examined_orphan_artifacts"] == 0


def test_coverage_is_reported_honestly(tmp_path: Path) -> None:
    """A size check must never be presented as a semantic one."""
    assert semantic_rule_coverage("master/selection.json", "full_master_ranking") == "gap_rule"
    assert semantic_rule_coverage("master/master.wav", "master_finalize") == "bytes_only"
    assert semantic_rule_coverage("publish/cover.jpg", "episode_cover_generate") == "bytes_only"
    assert (
        semantic_rule_coverage("understanding/interview_spine.json", "interview_spine_build")
        == "schema_only"
    )

    ctx = _ctx(tmp_path, "sweep_coverage")
    mark_done_raw(ctx, "master_finalize")
    findings, report = semantic_output_findings(ctx)
    assert [f.coverage for f in findings] == ["bytes_only"]
    assert report["coverage"] == {"bytes_only": 1}


def test_coverage_agrees_with_the_completeness_module(tmp_path: Path) -> None:
    """Anti-drift: our coverage verdict must match `_gap_rule_for` everywhere."""
    from interview_mux import artifact_completeness as ac
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        if semantic_rule_coverage(rel, stage) == "bytes_only":
            continue
        has_rule = ac._gap_rule_for(rel, stage) is not None
        expected = "gap_rule" if has_rule else "schema_only"
        assert semantic_rule_coverage(rel, stage) == expected, (stage, rel)


# ---------------------------------------------------------------------------
# 3b — rollout: report-only by default, blocking behind a flag
# ---------------------------------------------------------------------------

def test_report_only_is_the_default(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "sweep_report_only")
    assert semantic_sweep_enforced() is False
    assert semantic_sweep_blocks("edl") is False
    _stage_done_with_bad_output(ctx)

    report = record_semantic_output_defects(ctx)
    assert report["findings"] == 1
    assert report["blocking_findings"] == 0
    assert report["enforced"] is False
    # Recorded — so the rate is observable — but not a ship-bar blocker.
    row = defects(ctx)[0]
    assert row["degrades_ship_bar"] is False
    assert row["detail"]["report_only"] is True
    assert open_ship_bar_defects(ctx) == []
    # The classifier's own verdict is still on the row for when the flag flips.
    assert "critical_stage:edl" in row["ship_bar_reason"]


def test_report_only_does_not_refuse_publish(tmp_path: Path) -> None:
    from interview_mux import post_master_quality as pmq

    ctx = _ctx(tmp_path, "sweep_report_only_pmq")
    _stage_done_with_bad_output(ctx)
    quality = pmq.evaluate_post_master_quality(ctx)
    row = _check(quality, "stage_output_semantics")
    assert row["passed"] is True
    assert row["detail"]["findings"] == 1
    assert row["detail"]["enforced"] is False
    assert "stage_output_semantics" not in quality["structural_failed_checks"]
    assert _check(quality, "no_open_ship_bar_defects")["passed"] is True


def test_global_flag_makes_the_sweep_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import post_master_quality as pmq

    monkeypatch.setenv(_ENV_BLOCKING, "1")
    ctx = _ctx(tmp_path, "sweep_blocking")
    _stage_done_with_bad_output(ctx)

    assert semantic_sweep_enforced() is True
    quality = pmq.evaluate_post_master_quality(ctx)
    assert _check(quality, "stage_output_semantics")["passed"] is False
    assert "stage_output_semantics" in quality["structural_failed_checks"]
    assert quality["publish_allowed"] is False
    # And the defect itself now degrades the ship bar, so the ledger check agrees.
    assert _check(quality, "no_open_ship_bar_defects")["passed"] is False
    assert [r["stage"] for r in open_ship_bar_defects(ctx)] == ["edl"]


def test_per_stage_ratchet_scopes_enforcement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors `MUX_CONTRACT_STRICT_GROUPS`: one stage can be enforced or reverted."""
    monkeypatch.setenv(_ENV_BLOCKING_STAGES, "edl")
    assert semantic_sweep_blocks("edl") is True
    assert semantic_sweep_blocks("mix") is False

    ctx = _ctx(tmp_path, "sweep_ratchet")
    mark_done_raw(ctx, "edl", "mix")
    report = record_semantic_output_defects(ctx)
    assert report["findings"] == 2
    assert report["blocking_findings"] == 1
    blocking = {r["stage"] for r in open_ship_bar_defects(ctx)}
    assert blocking == {"edl"}


def test_a_repaired_artifact_stops_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enforcement must be reversible without a stage re-dispatch.

    `resolve_stage_defects` only fires when a stage walks to done again, and the
    orphan pass has no stage to walk at all, so the sweep closes its own rows.
    """
    monkeypatch.setenv(_ENV_BLOCKING, "1")
    ctx = _ctx(tmp_path, "sweep_self_heal")
    mark_done_raw(ctx, "full_master_ranking")
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": []})
    record_semantic_output_defects(ctx)
    assert len(open_ship_bar_defects(ctx)) == 1

    _raw_write(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "chapters": []},
    )
    report = record_semantic_output_defects(ctx)
    assert report["findings"] == 0
    assert len(report["resolved_defect_ids"]) == 1
    assert open_ship_bar_defects(ctx) == []


def test_a_broken_sweep_is_unknown_not_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import defect_ledger, post_master_quality as pmq

    def boom(_ctx: RunContext) -> dict[str, Any]:
        raise RuntimeError("sweep exploded")

    monkeypatch.setattr(defect_ledger, "record_semantic_output_defects", boom)

    ctx = _ctx(tmp_path, "sweep_broken_reportonly")
    row = _check(pmq.evaluate_post_master_quality(ctx), "stage_output_semantics")
    assert row["passed"] is True  # report-only: visible, advisory
    assert row["detail"]["unresolved"] is True
    assert "sweep exploded" in row["detail"]["error"]

    monkeypatch.setenv(_ENV_BLOCKING, "1")
    ctx2 = _ctx(tmp_path, "sweep_broken_enforced")
    quality = pmq.evaluate_post_master_quality(ctx2)
    row2 = _check(quality, "stage_output_semantics")
    assert row2["passed"] is False  # enforced: a broken detector refuses
    assert quality["publish_allowed"] is False
    assert row2["detail"]["operator_reason"]


def test_sweep_errors_are_surfaced_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-stage failure must appear in the report rather than vanish."""
    from interview_mux import artifact_completeness as ac

    def boom(*_a: Any, **_k: Any) -> str:
        raise RuntimeError("status backend down")

    monkeypatch.setattr(ac, "artifact_status_for_stage", boom)
    ctx = _ctx(tmp_path, "sweep_stage_error")
    mark_done_raw(ctx, "edl")
    _findings, report = semantic_output_findings(ctx)
    assert report["sweep_errors"]
    assert "status backend down" in report["sweep_errors"][0]


def test_new_check_is_structural_so_it_cannot_be_softened() -> None:
    from interview_mux.aspirational_quality import is_rubric_pmq_check

    assert is_rubric_pmq_check("stage_output_semantics") is False
