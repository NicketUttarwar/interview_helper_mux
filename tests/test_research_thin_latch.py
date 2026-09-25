"""A-01 latch: a completed Shape/gap consumer must not read incomplete forever.

Reproduces the `exec_5188` seq-207 divergence. `mastering_research_rollup` ran
once, probed a run whose shape-core evidence had not landed yet, wrote a thin
dossier and marked itself done. Every consumer refusal names that rollup as the
resume target, but a completed rollup never re-probes, so the refusal could not
be cleared for the rest of the phase.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.mastering_research import DOSSIER_REL, WAVE_FIELDS
from interview_mux.run_context import RunContext
from run_fixtures import (
    minimal_content_brief,
    minimal_gap_evaluations,
    minimal_speakers,
    patch_executions_root,
)

GAP_CONSUMERS = ("missing_framing", "gap_framing_compose")
DOSSIER_READERS = ("mastering_shape_agenda", "mastering_plan_synthesize")


def _thin_dossier() -> dict:
    """What the rollup wrote: every field probed absent."""
    fields = {
        fid: {
            "version": 1,
            "field_id": fid,
            "wave": wave,
            "status": "skipped_or_thin",
            "evidence_refs": [],
        }
        for wave, fids in WAVE_FIELDS.items()
        for fid in fids
    }
    return {
        "version": 1,
        "fields": fields,
        "complete_fields": [],
        "thin_fields": sorted(fields),
        "field_reports": [],
        "salience_map": {},
        "generated_at": "2026-09-03T04:30:27+00:00",
    }


def _seq207_ctx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, evidence_landed: bool
) -> RunContext:
    """exec_5188 @ seq 207: thin dossier on disk, rollup and missing_framing both done."""
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_5188_latch", create=True)
    doc = _thin_dossier()
    ctx.write_json(DOSSIER_REL, doc, skip_handoff=True)
    ctx.write_json("mastering/research/rollup.json", doc, skip_handoff=True)
    ctx.write_json(
        "understanding/gap_evaluations.json", minimal_gap_evaluations(), skip_handoff=True
    )
    if evidence_landed:
        # Shape-core probes the dossier recorded as absent, now on disk.
        ctx.write_json(
            "understanding/content_brief.json", minimal_content_brief(), skip_handoff=True
        )
        ctx.write_json("understanding/speakers.json", minimal_speakers(), skip_handoff=True)
        from run_fixtures import confirm_test_pickup_speaker

        ctx.write_json(
            "understanding/source_topology.json",
            {"topology_class": "one_on_one_asymmetric", "speaker_stats": []},
            skip_handoff=True,
        )
        confirm_test_pickup_speaker(ctx)
        ctx.write_json(
            "transcript/full.json",
            {"segments": [{"start": 0.0, "end": 1.0, "text": "hello"}]},
            skip_handoff=True,
        )
        spine = ctx.path("understanding/interview_spine.json")
        spine.parent.mkdir(parents=True, exist_ok=True)
        spine.write_text('{"schema_version":1,"windows":[{"window_id":"w1"}]}', encoding="utf-8")
    markers = ctx.final_path(".stage_done")
    markers.mkdir(parents=True, exist_ok=True)
    for sid in ("mastering_research_rollup", "missing_framing"):
        (markers / sid).touch()
    return ctx


def test_completed_gap_consumer_is_not_pinned_to_a_stale_dossier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The latch: missing_framing finished, its evidence is on disk, and the only
    thing calling it incomplete is a record the rollup took before that evidence
    existed."""
    from interview_mux.mastering_research import (
        research_dossier_shape_core_stale,
        research_shape_core_thin,
    )
    from interview_mux.stage_completion import (
        _research_thin_late_refuse,
        stage_artifact_incompleteness,
    )

    ctx = _seq207_ctx(tmp_path, monkeypatch, evidence_landed=True)
    assert research_shape_core_thin(ctx) is True
    assert research_dossier_shape_core_stale(ctx) is True

    with monkeypatch.context() as no_staleness:
        # The latch as it stood: a finished stage refused by a record nothing
        # re-reads, pinned to a producer that reports itself complete.
        no_staleness.setattr(
            "interview_mux.mastering_research.research_dossier_shape_core_stale",
            lambda _ctx: False,
        )
        latched = stage_artifact_incompleteness(ctx, "missing_framing")
        assert latched is None or "mastering_research_rollup" in latched or "vo_path_not_ready" in latched
        assert stage_artifact_incompleteness(ctx, "mastering_research_rollup") is None

    leftover = stage_artifact_incompleteness(ctx, "missing_framing")
    assert leftover is None or "vo_path_not_ready" in leftover
    for sid in GAP_CONSUMERS:
        assert _research_thin_late_refuse(ctx, sid) is None


def test_stale_dossier_makes_its_own_rollup_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stages that read the dossier keep waiting, so the record it holds must be
    refreshable: the rollup reports incomplete while its output is stale."""
    from interview_mux.stage_completion import (
        _research_thin_late_refuse,
        stage_artifact_incompleteness,
    )

    ctx = _seq207_ctx(tmp_path, monkeypatch, evidence_landed=True)
    rollup = stage_artifact_incompleteness(ctx, "mastering_research_rollup")
    assert rollup is not None and "mastering_research_rollup" in rollup
    for sid in DOSSIER_READERS:
        assert _research_thin_late_refuse(ctx, sid) is not None


def test_refreshed_dossier_clears_the_refusal_for_every_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the rollup is a real clearing path: one re-probe ends the refusal
    and does not leave the stage incomplete a second time."""
    from interview_mux.mastering_research import (
        research_dossier_shape_core_stale,
        research_shape_core_thin,
        run_research_rollup,
    )
    from interview_mux.stage_completion import (
        _research_thin_late_refuse,
        stage_artifact_incompleteness,
    )

    ctx = _seq207_ctx(tmp_path, monkeypatch, evidence_landed=True)
    run_research_rollup(ctx)
    assert research_shape_core_thin(ctx) is False
    assert research_dossier_shape_core_stale(ctx) is False
    assert stage_artifact_incompleteness(ctx, "mastering_research_rollup") is None
    for sid in GAP_CONSUMERS + DOSSIER_READERS:
        assert _research_thin_late_refuse(ctx, sid) is None


def test_consumers_still_refused_when_research_is_genuinely_thin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protection intact: with no shape-core evidence anywhere, every consumer is
    still refused — unlatching must not mean always allowing."""
    from interview_mux.mastering_research import research_dossier_shape_core_stale
    from interview_mux.stage_completion import (
        _research_thin_late_refuse,
        stage_artifact_incompleteness,
    )

    ctx = _seq207_ctx(tmp_path, monkeypatch, evidence_landed=False)
    assert research_dossier_shape_core_stale(ctx) is False
    for sid in GAP_CONSUMERS + DOSSIER_READERS:
        assert _research_thin_late_refuse(ctx, sid) is not None
    assert stage_artifact_incompleteness(ctx, "missing_framing") is not None
    # Nothing to refresh, so the rollup is not accused of being stale either.
    assert stage_artifact_incompleteness(ctx, "mastering_research_rollup") is None
