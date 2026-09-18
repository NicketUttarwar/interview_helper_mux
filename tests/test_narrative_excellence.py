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


def test_research_waves_writes_waves_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from interview_mux.mastering_research import run_mastering_research_waves

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_ne_waves", create=True)
    run_mastering_research_waves(ctx)
    assert ctx.artifact_exists("mastering/research/waves.json")
    doc = ctx.read_json("mastering/research/waves.json")
    assert len(doc.get("waves") or []) == 8


def test_research_rollup_fail_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A-01: early rollup thin is advisory; Shape consumers refuse shape-core thin under defaults."""
    from interview_mux.mastering_plan_loader import research_llm_enabled
    from interview_mux.mastering_research import research_shape_core_thin
    from interview_mux.stage_completion import (
        _research_is_thin,
        _research_thin_late_refuse,
        stage_artifact_incompleteness,
    )

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_ne_research", create=True)
    dossier = run_research_rollup(ctx)
    assert "fields" in dossier
    assert len(WAVE_FIELDS) == 8
    assert len(dossier["fields"]) == sum(len(v) for v in WAVE_FIELDS.values())
    # Defaults: research.llm stays off; shape.llm may be on (Q6B) — refuse must not depend on them.
    assert research_llm_enabled() is False
    # Early: thin rollup does not late-refuse the rollup stage itself.
    assert _research_thin_late_refuse(ctx, "mastering_research_rollup") is None
    assert _research_is_thin(ctx) is True
    assert research_shape_core_thin(ctx) is True
    # Late: Shape consumers refuse shape-core thin without LLM/consumers_bind flags.
    late = _research_thin_late_refuse(ctx, "mastering_plan_synthesize")
    assert late is not None
    assert "thin" in late.lower() or "shape-core" in late.lower()
    # seed_stage path also surfaces the refuse once the plan path exists.
    ctx.write_json(
        "mastering/mastering_plan.json",
        {"plan_status": "degraded", "narrative_mode": "sparse_source"},
        skip_handoff=True,
    )
    # With Shape about-to-bind, rollup itself becomes late.
    rollup_late = _research_thin_late_refuse(ctx, "mastering_research_rollup")
    assert rollup_late is not None
    inc = stage_artifact_incompleteness(ctx, "mastering_plan_synthesize")
    assert inc is not None and ("thin" in inc.lower() or "shape-core" in inc.lower())


def test_a01_shape_core_complete_allows_shape_despite_late_waves_thin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """W1–3 complete + W5–8 thin still allows Shape consumers under defaults."""
    from interview_mux.mastering_plan_loader import research_llm_enabled
    from interview_mux.mastering_research import (
        DOSSIER_REL,
        SHAPE_CORE_REQUIRED_FIELDS,
        WAVE_FIELDS,
        research_shape_core_thin,
        shape_core_field_ids,
    )
    from interview_mux.stage_completion import _research_thin_late_refuse

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_a01_core_ok", create=True)
    assert research_llm_enabled() is False

    fields: dict = {}
    for wave, fids in WAVE_FIELDS.items():
        for fid in fids:
            if wave <= 3:
                status = "complete"
            else:
                status = "skipped_or_thin"
            fields[fid] = {
                "version": 1,
                "field_id": fid,
                "wave": wave,
                "status": status,
                "evidence_refs": [],
            }
    # Ensure hard-required are complete (already via W1–3).
    for fid in SHAPE_CORE_REQUIRED_FIELDS:
        assert fid in shape_core_field_ids()
        fields[fid]["status"] = "complete"
    dossier = {
        "version": 1,
        "fields": fields,
        "complete_fields": [k for k, v in fields.items() if v["status"] == "complete"],
        "thin_fields": [k for k, v in fields.items() if v["status"] != "complete"],
        "field_reports": [
            {
                "field_id": fid,
                "wave": int(fields[fid]["wave"]),
                "status": fields[fid]["status"],
                "path": f"mastering/research/{fid}.json",
            }
            for fid in fields
        ],
        "salience_map": {},
        "generated_at": "2026-01-01T00:00:00+00:00",
    }
    ctx.write_json(DOSSIER_REL, dossier, skip_handoff=True)
    ctx.write_json("mastering/research/rollup.json", dossier, skip_handoff=True)
    assert research_shape_core_thin(ctx) is False
    assert _research_thin_late_refuse(ctx, "mastering_plan_synthesize") is None
    assert _research_thin_late_refuse(ctx, "mastering_shape_agenda") is None
    assert _research_thin_late_refuse(ctx, "missing_framing") is None


def test_field_probes_use_canon_g0_and_speaker_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollup must not mark shape-core thin when review_queue + speakers.json exist."""
    from interview_mux.mastering_research import (
        research_shape_core_thin,
        run_research_rollup,
    )
    from interview_mux.stage_completion import _research_thin_late_refuse
    from run_fixtures import minimal_content_brief, minimal_speakers

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_probe_canon", create=True)
    ctx.write_json(
        "transcript/review_queue.json",
        {"version": 1, "chunks": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/full.json",
        {"segments": [{"start": 0.0, "end": 1.0, "text": "hello"}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        minimal_speakers(),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_asymmetric", "speaker_stats": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(),
        skip_handoff=True,
    )
    # Probe only checks existence — write raw to avoid full spine schema in unit test.
    spine_path = ctx.path("understanding/interview_spine.json")
    spine_path.parent.mkdir(parents=True, exist_ok=True)
    spine_path.write_text(
        '{"schema_version":1,"windows":[{"window_id":"w1"}],'
        '"derived_from":{},"encoders":{},"window_policy":{},'
        '"boundary_events":[],"retrieval":{},"speaker_stats":[]}',
        encoding="utf-8",
    )
    dossier = run_research_rollup(ctx)
    fields = dossier.get("fields") or {}
    assert fields.get("g0_transcript_fidelity", {}).get("status") == "complete"
    assert fields.get("speaker_roles", {}).get("status") == "complete"
    assert fields.get("interview_spine_windows", {}).get("status") == "complete"
    assert research_shape_core_thin(ctx) is False
    # Orphan shape agenda must not late-refuse rollup once core probes hit.
    agenda_path = ctx.path("mastering/shape/agenda.json")
    agenda_path.parent.mkdir(parents=True, exist_ok=True)
    agenda_path.write_text('{"version": 1, "items": []}', encoding="utf-8")
    assert _research_thin_late_refuse(ctx, "mastering_research_rollup") is None



def test_a03_soft_gate_cannot_claim_complete_when_llm_flags_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A-03 / SYN-SHAPE-01: soft_gate must not set plan_status=complete when shape.llm on."""
    from interview_mux.mastering_plan_loader import soft_gate_may_claim_complete
    from interview_mux.mastering_shape_runtime import (
        run_mastering_plan_synthesize,
        run_mastering_shape_agenda,
        run_mastering_shape_candidates,
    )

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_a03_shape", create=True)
    # Heuristic stage bodies; claim_plan_complete still sees shape.llm on via loader.
    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.shape_llm_enabled",
        lambda _cfg=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    assert soft_gate_may_claim_complete() is False
    ctx.write_json("understanding/content_brief.json", {"thesis": "t", "topics": [{"name": "a", "summary": "b"}]})
    run_research_rollup(ctx)
    run_mastering_shape_agenda(ctx)
    run_mastering_shape_candidates(ctx)
    run_mastering_plan_synthesize(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("plan_status") != "complete"
    assert "soft_gate_not_authoritative" in list(plan.get("degradation_reasons") or [])
    assert plan.get("source") == "soft_gate"

def test_two_pass_shape_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_ne_shape", create=True)
    # Exercise heuristic two-pass Shape (not live OpenAI).
    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.shape_llm_enabled",
        lambda _cfg=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: False,
    )
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
    # Plan 6: listener_outcome carries Essence mutation-space hints (native keep/order,
    # synthetic+music/SFX/air) alongside the finishability/recommendability delight pair.
    outcome = provisional.get("listener_outcome") or {}
    assert outcome.get("nugget_density") == "optimize"
    assert outcome.get("sonic_weave") == "optimize"
    run_mastering_plan_confirm(ctx)
    confirmed = ctx.read_json("mastering/mastering_plan.json")
    assert confirmed.get("pass") == "confirmed"
    assert confirmed.get("plan_status") in ("complete", "degraded", "forced_sparse")
    # This test exercises the two-pass Shape mechanism, not delight scoring — force
    # advisory mode so a sparse fixture run doesn't hit the authoritative ship gate
    # (see tests/test_listen_delight.py for authoritative pass/fail coverage).
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "advisory"},
    )
    run_listen_delight_audit(ctx)
    audit = ctx.read_json("mastering/listen_delight_audit.json")
    assert audit["mode"] == "advisory"
    assert audit["advisory"] is True
    assert audit["blocking"] is False


def test_no_shape_timeout_keys_in_defaults():
    cfg = json.loads(Path("config/app.defaults.json").read_text(encoding="utf-8"))
    soft = cfg["mastering"]["shape"]["soft_gate"]
    forbidden = {"timeout", "max_spend", "max_remint", "max_attempts", "timeout_sec", "timeout_ms"}
    assert forbidden.isdisjoint(soft.keys())
