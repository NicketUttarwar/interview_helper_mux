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
    stages = _build_stage_list(
        ctx,
        [],
        False,
        False,
        False,
        False,
    )
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
    stages = _build_stage_list(ctx, [], False, False, False, False)
    g15 = next(s for s in stages if s["id"] == "g1_5_preview_pickup")
    assert g15["status"] == "done"
    assert g15["stage_output_mode"] == "optional_skipped"
    assert g15["artifacts_status"].get("understanding/gap_report.json") == "complete"
    assert g15["artifacts_lifecycle"].get("understanding/gap_report.json") == "n_a"
    assert not validate_run_snapshot(stages=[g15])


def test_disfluency_review_disabled_optional_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "interview_mux.disfluency.config.disfluency_enabled",
        lambda cfg=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.web.server.disfluency_enabled",
        lambda cfg=None: False,
    )
    stages = _build_stage_list(ctx, [], False, False, False, False)
    review = next(s for s in stages if s["id"] == "disfluency_review")
    assert review["status"] == "done"
    assert review["stage_output_mode"] == "optional_skipped"
    assert review["status"] != "incomplete"
    assert not validate_run_snapshot(stages=[review])
