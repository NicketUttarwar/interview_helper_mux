from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages.audio_preclean import ensure_preclean_skipped
from interview_mux.ui_truth import validate_run_snapshot
from interview_mux.web.server import _build_stage_list


from run_fixtures import patch_merged_config


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": False},
        },
    )
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_preclean_skip_outputs_not_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ensure_preclean_skipped(ctx, checkpoint="before_ingest", scope="ingest", reason="test")
    stages = _build_stage_list(ctx, [], False, False, False)
    preclean = next(s for s in stages if s["id"] == "audio_preclean")
    assert preclean["status"] in ("done", "incomplete")
    assert ctx.artifact_exists("preclean/skip.json")


def test_g1_5_na_not_incomplete_without_gap_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-TBIY / inapplicable G1.5 must not T1-downgrade to FAILED via pending gap_report."""
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "interview_mux.gates_tbiy.g1_5_preview_pickup_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.production_profile.is_tbiy",
        lambda _ctx: False,
    )
    stages = _build_stage_list(ctx, [], False, False, False)
    g15 = next(s for s in stages if s["id"] == "g1_5_preview_pickup")
    assert g15["status"] == "done"
    assert g15["stage_output_mode"] == "optional_skipped"
    assert g15["artifacts_status"].get("understanding/gap_report.json") == "complete"
    assert g15["artifacts_lifecycle"].get("understanding/gap_report.json") == "n_a"
    assert not validate_run_snapshot(stages=[g15])


def test_content_context_stays_done_when_brief_only_missing_reanchor_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GUI stage list must not downgrade content_context when re-anchor fields are absent."""
    import json

    from interview_mux.artifact_writes import write_validated_artifact

    ctx = _ctx(tmp_path, monkeypatch)
    fixture = (
        Path(__file__).resolve().parent / "fixtures/sufficiency/content_context/pass.json"
    )
    brief = json.loads(fixture.read_text())
    write_validated_artifact(
        ctx,
        "understanding/content_brief.json",
        brief,
        merge_from_disk=False,
        stage_key="content_context",
    )
    ctx.mark_done("content_context", force=True)
    ctx.mark_done("content_brief_reanchor", force=True)
    ctx.mark_done("boundary_detection", force=True)
    ctx.mark_done("segment_classification", force=True)

    stages = _build_stage_list(ctx, [], False, False, False)
    content = next(s for s in stages if s["id"] == "content_context")
    reanchor = next(s for s in stages if s["id"] == "content_brief_reanchor")
    assert content["status"] == "done"
    assert content["artifacts_status"]["understanding/content_brief.json"] == "complete"
    assert reanchor["status"] in ("incomplete", "pending")
    assert not ctx.is_done("content_brief_reanchor")
    assert not validate_run_snapshot(stages=[content])


def test_disfluency_review_absent_from_stage_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v2 removes disfluency gates from the operator stage list."""
    ctx = _ctx(tmp_path, monkeypatch)
    stages = _build_stage_list(ctx, [], False, False, False)
    assert "disfluency_review" not in {s["id"] for s in stages}


def test_gap_fill_stages_stay_visible_when_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap-fill GUI stages remain visible even when the gap-fill decision is skipped.

    The hide-when-skipped path was intentionally retired so that gap_vo-class stages
    (missing_framing, gap_framing_compose, optimal_questions, g1_vo_pickup) stay
    reachable and eligible for the Refinement Pass agenda rather than disappearing
    from the operator stage list.
    """
    from interview_mux.gap_fill_eligibility import GAP_FILL_GUI_STAGE_IDS
    from interview_mux.v2.config import v2_enabled

    ctx = _ctx(tmp_path, monkeypatch)
    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    ensure_gap_fill_skipped(ctx, reason="peer topology", signals={"topology_class": "test"})
    stages = _build_stage_list(ctx, [], False, False, False)
    hidden_ids = {s["id"] for s in stages if s.get("stage_visibility") == "hidden"}
    stage_ids = {s["id"] for s in stages}
    assert not (hidden_ids & GAP_FILL_GUI_STAGE_IDS)
    if v2_enabled():
        assert "gap_framing_compose" in stage_ids
    for stage_id in ("missing_framing", "g1_vo_pickup"):
        if stage_id in stage_ids:
            assert stage_id not in hidden_ids
