"""Narrative excellence: prefer/forbid, plan loader FT, research rollup, two-pass shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.listen_delight import run_listen_delight_audit
from interview_mux.mastering_plan_loader import (
    forced_sparse_plan,
    validate_or_degrade,
    write_plan,
)
from interview_mux.mastering_research import WAVE_FIELDS, run_research_rollup
from interview_mux.mastering_shape_runtime import (
    run_mastering_plan_confirm,
    run_mastering_plan_synthesize,
    run_mastering_shape_agenda,
    run_mastering_shape_candidates,
)
from interview_mux.narrative_mode import (
    NARRATIVE_MODES,
    hybrid_acceptance,
    load_prefer_forbid,
    mode_consistency_report,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


def test_prefer_forbid_covers_all_modes():
    doc = load_prefer_forbid()
    modes = doc["modes"]
    for m in NARRATIVE_MODES:
        assert m in modes
        assert "sonic_density" in modes[m]


def test_mode_consistency_advisory_forbid():
    report = mode_consistency_report(
        mode="sparse_source",
        interviewer_lines=[
            {"line_id": "a", "line_category": "episode_preface"},
            {"line_id": "b", "line_category": "story_bridge"},
        ],
    )
    assert report["advisory"] is True
    assert report["blocking"] is False
    assert report["ok"] is False
    assert any(v["reason"] == "forbidden_for_mode" for v in report["violations"])


def test_hybrid_acceptance_requires_matrix():
    ok, why = hybrid_acceptance({"narrative_mode": "hybrid_bespoke", "hybrid_label": "x"})
    assert ok is False
    assert "evidence" in why or "matrix" in why or "anti" in why


def test_validate_or_degrade_corrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_ne_corrupt", create=True)
    ctx.path("mastering").mkdir(parents=True, exist_ok=True)
    ctx.path("mastering/mastering_plan.json").write_text("{not-json", encoding="utf-8")
    plan = validate_or_degrade(ctx)
    assert plan["plan_status"] == "forced_sparse"


def test_forced_sparse_and_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_ne_sparse", create=True)
    plan = forced_sparse_plan(reason="no_survivors")
    write_plan(ctx, plan)
    assert ctx.artifact_exists("mastering/mastering_plan.json")
    loaded = validate_or_degrade(ctx)
    assert loaded["narrative_mode"] == "sparse_source"


def test_research_rollup_fail_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_ne_research", create=True)
    dossier = run_research_rollup(ctx)
    assert "fields" in dossier
    assert len(WAVE_FIELDS) == 8
    assert len(dossier["fields"]) == sum(len(v) for v in WAVE_FIELDS.values())


def test_two_pass_shape_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_ne_shape", create=True)
    ctx.write_json("understanding/content_brief.json", {"thesis": "t", "topics": []})
    # Bypass schema: evidence probe only needs file presence for research/shape
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/gap_evaluations.json").write_text(
        json.dumps(
            {
                "evaluations": [
                    {
                        "segment_id": f"seg_{i}",
                        "self_explanatory": False,
                        "gap_type": "missing_setup",
                        "recommended_framing": "setup",
                    }
                    for i in range(3)
                ]
            }
        ),
        encoding="utf-8",
    )
    run_research_rollup(ctx)
    run_mastering_shape_agenda(ctx)
    run_mastering_shape_candidates(ctx)
    run_mastering_plan_synthesize(ctx)
    assert ctx.artifact_exists("mastering/mastering_plan.json")
    provisional = ctx.read_json("mastering/mastering_plan.json")
    assert provisional.get("pass") == "provisional"
    run_mastering_plan_confirm(ctx)
    confirmed = ctx.read_json("mastering/mastering_plan.json")
    assert confirmed.get("pass") == "confirmed"
    assert confirmed.get("plan_status") in ("complete", "degraded", "forced_sparse")
    run_listen_delight_audit(ctx)
    audit = ctx.read_json("mastering/listen_delight_audit.json")
    assert audit["advisory"] is True
    assert audit["blocking"] is False


def test_no_shape_timeout_keys_in_defaults():
    cfg = json.loads(Path("config/app.defaults.json").read_text(encoding="utf-8"))
    soft = cfg["mastering"]["shape"]["soft_gate"]
    forbidden = {"timeout", "max_spend", "max_remint", "max_attempts", "timeout_sec", "timeout_ms"}
    assert forbidden.isdisjoint(soft.keys())
