"""Workstream B: nugget air coverage as aspirational goal + pick-best."""

from __future__ import annotations

import pytest

from interview_mux.nugget_layup import (
    CORPUS_REL,
    PLAN_REL,
    apply_best_layup_candidate,
    evaluate_layup_qc,
    evaluate_nugget_air_coverage,
    nugget_layup_cfg,
    park_open_high_salience_on_orientation,
    register_layup_candidate,
    select_best_layup_candidate,
    try_pick_best_layup_on_oscillation,
)
from interview_mux.run_context import RunContext

_ANALYSIS = {
    "target_beat": "Claim lands next.",
    "listener_need_entering_T": "Need the preview before the clip.",
    "forward_unlock": "Listen for the biomarker claim.",
}

_BASE_CFG = nugget_layup_cfg({})


def _cfg(**overrides):
    out = dict(_BASE_CFG)
    out.update(overrides)
    return out


def _soft_craft_cfg(**overrides):
    return _cfg(
        air_coverage_aspirational=True,
        min_layup_coverage=0.0,
        require_layup_per_native=False,
        require_analysis_fields=False,
        ban_canned_air=False,
        block_on_open_must_keep=False,
        block_on_open_high_salience=True,
        max_cross_layup_overlap=1.1,
        max_target_restate_overlap=1.1,
        **overrides,
    )


def _seed_order(ctx: RunContext, n: int = 12) -> list[str]:
    ids = [f"seg_{i:03d}" for i in range(1, n + 1)]
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ids, "selected_segment_ids": ids},
    )
    segments = []
    start = 0
    for i, sid in enumerate(ids, start=1):
        segments.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_0",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "topic_tags": [],
                "text": f"Native claim {i}.",
                "start_ms": start,
                "end_ms": start + 9000,
            }
        )
        start += 12_000
    ctx.write_json("segments/manifest.json", {"segments": segments})
    return ids


def _corpus(n: int = 12, *, salience: str = "high") -> dict:
    return {
        "nuggets": [
            {
                "nugget_id": f"nug_{i:03d}",
                "text_claim": f"Claim {i} about oncology biomarkers.",
                "evidence_quote": f"claim {i}",
                "in_selection": False,
                "salience": salience,
                "already_aired_in_selection": False,
            }
            for i in range(1, n + 1)
        ]
    }


def _aired_plan(ids: list[str], aired_n: int) -> dict:
    layups = []
    open_high: list[str] = []
    for i, sid in enumerate(ids, start=1):
        nid = f"nug_{i:03d}"
        if i <= aired_n:
            layups.append(
                {
                    "target_segment_id": sid,
                    "line_id": f"vo_layup_{sid}",
                    "nugget_ids": [nid],
                    "text": f"Brief preview of claim {i} about oncology biomarkers.",
                    "skip": False,
                    "forward_cue_ok": True,
                    **_ANALYSIS,
                }
            )
        else:
            open_high.append(nid)
            layups.append(
                {
                    "target_segment_id": sid,
                    "line_id": f"vo_layup_{sid}",
                    "nugget_ids": [nid],
                    "value_forgone": [nid],
                    "skip": True,
                    "skip_reason_code": "spoken_copy_unhealable",
                    **_ANALYSIS,
                }
            )
    return {
        "ordered_segment_ids": ids,
        "layups": layups,
        "open_high_salience_nugget_ids": open_high,
        "discharged_nugget_ids": [],
        "open_talking_point_ids": [],
        "discharged_talking_point_ids": [],
    }


def _mixed_corpus() -> dict:
    return {
        "nuggets": [
            {
                "nugget_id": f"nug_{i:03d}",
                "text_claim": f"Claim {i}.",
                "evidence_quote": f"claim {i}",
                "in_selection": False,
                "salience": "high" if i <= 10 else "medium",
                "already_aired_in_selection": False,
            }
            for i in range(1, 13)
        ]
    }


def _under_goal_plan(ids: list[str], aired: int) -> dict:
    layups = []
    for i, sid in enumerate(ids, start=1):
        if i <= aired:
            layups.append(
                {
                    "target_segment_id": sid,
                    "line_id": f"vo_layup_{sid}",
                    "nugget_ids": [f"nug_{i:03d}"],
                    "text": f"Brief preview of claim {i} about oncology biomarkers v{aired}.",
                    "skip": False,
                    "forward_cue_ok": True,
                    **_ANALYSIS,
                }
            )
        else:
            layups.append(
                {
                    "target_segment_id": sid,
                    "line_id": f"vo_layup_{sid}",
                    "nugget_ids": [],
                    "skip": True,
                    "skip_reason_code": "no_nugget_value",
                    **_ANALYSIS,
                }
            )
    return {
        "ordered_segment_ids": ids,
        "layups": layups,
        "open_high_salience_nugget_ids": [],
        "discharged_nugget_ids": [f"nug_{i:03d}" for i in range(1, min(aired, 10) + 1)],
        "open_talking_point_ids": [],
        "discharged_talking_point_ids": [],
    }


def test_orientation_park_still_credits_air_coverage(monkeypatch):
    """i2 regression: parks clear open_high and credit coverage math."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda cfg=None: _soft_craft_cfg(),
    )
    ctx = RunContext("exec_asp_orient_park", create=True)
    ids = _seed_order(ctx, 12)
    ctx.write_json(CORPUS_REL, _corpus(12))
    plan = _aired_plan(ids, 10)
    parked, notes = park_open_high_salience_on_orientation(ctx, plan)
    assert any(n.startswith("orientation_park:") for n in notes)
    qc = evaluate_layup_qc(ctx, parked)
    assert not qc.get("open_high_salience_nugget_ids")
    assert qc.get("nugget_air_coverage", 0) + 1e-9 >= 0.85
    assert not any("nugget_air_coverage" in e for e in (qc.get("errors") or []))
    assert qc.get("ok") is True


def test_accounted_under_goal_is_advisory_not_hard(monkeypatch):
    """~0.833 coverage with no open high → advisory accept under aspirational."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda cfg=None: _soft_craft_cfg(),
    )
    ctx = RunContext("exec_asp_under_goal", create=True)
    ids = _seed_order(ctx, 12)
    ctx.write_json(CORPUS_REL, _mixed_corpus())
    plan = _under_goal_plan(ids, 10)
    qc = evaluate_layup_qc(ctx, plan)
    assert qc["nugget_air_coverage"] == pytest.approx(10 / 12, rel=1e-3)
    assert not qc.get("open_high_salience_nugget_ids")
    assert qc.get("ok") is True
    assert qc.get("air_coverage_advisory") is True
    assert any("min_nugget_air_coverage" in w for w in (qc.get("warnings") or []))
    assert not any("min_nugget_air_coverage" in e for e in (qc.get("errors") or []))


def test_unaccounted_open_high_hard_refuse(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda cfg=None: _cfg(
            air_coverage_aspirational=False,
            min_layup_coverage=0.0,
            require_layup_per_native=False,
            require_analysis_fields=False,
            ban_canned_air=False,
            block_on_open_must_keep=False,
            block_on_open_high_salience=True,
            max_cross_layup_overlap=1.1,
            max_target_restate_overlap=1.1,
        ),
    )
    ctx = RunContext("exec_asp_open_high", create=True)
    ids = _seed_order(ctx, 12)
    ctx.write_json(CORPUS_REL, _corpus(12))
    plan = _aired_plan(ids, 10)
    qc = evaluate_layup_qc(ctx, plan)
    assert qc.get("ok") is False
    assert qc.get("open_high_salience_nugget_ids")
    blob = list(qc.get("errors") or []) + list(qc.get("warnings") or [])
    assert any("open_high_salience" in str(e) for e in blob)


def test_pick_best_selects_highest_coverage(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda cfg=None: _soft_craft_cfg(),
    )
    ctx = RunContext("exec_asp_pick_best", create=True)
    ids = _seed_order(ctx, 12)
    ctx.write_json(CORPUS_REL, _mixed_corpus())

    for aired in (8, 9, 10):
        plan = _under_goal_plan(ids, aired)
        qc = evaluate_layup_qc(ctx, plan)
        register_layup_candidate(ctx, plan=plan, qc=qc, label=f"aired_{aired}")

    best = select_best_layup_candidate(ctx)
    assert best is not None
    assert float(best.get("nugget_air_coverage") or 0) == pytest.approx(10 / 12, rel=1e-3)

    ctx.write_json(PLAN_REL, _under_goal_plan(ids, 8), stage_key="nugget_layup_compose")
    applied = apply_best_layup_candidate(ctx)
    assert applied.get("ok")
    live = ctx.read_json(PLAN_REL)
    live_qc = evaluate_layup_qc(ctx, live)
    assert live_qc.get("nugget_air_coverage") == pytest.approx(10 / 12, rel=1e-3)


def test_config_off_restores_hard_085(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda cfg=None: _cfg(
            air_coverage_aspirational=False,
            min_layup_coverage=0.0,
            require_layup_per_native=False,
            require_analysis_fields=False,
            ban_canned_air=False,
            block_on_open_must_keep=False,
            block_on_open_high_salience=False,
        ),
    )
    corpus = {
        "nuggets": [
            {
                "nugget_id": f"nug_{i}",
                "salience": "medium",
                "in_selection": False,
                "evidence_quote": f"q{i}",
                "text_claim": f"c{i}",
            }
            for i in range(1, 5)
        ]
    }
    body = {
        "layups": [
            {
                "target_segment_id": "seg_001",
                "text": "One fact.",
                "nugget_ids": ["nug_1"],
                "skip": False,
            }
        ]
    }
    hard = evaluate_nugget_air_coverage(body, [], None, corpus, hard=True)
    assert hard["ok"] is False
    assert any("min_nugget_air_coverage" in e for e in hard["errors"])


def test_oscillation_pick_best_disabled_s4(monkeypatch):
    """S4: oscillation thrash hook no longer restores from archive."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda cfg=None: _soft_craft_cfg(),
    )
    ctx = RunContext("exec_asp_osc", create=True)
    ids = _seed_order(ctx, 12)
    ctx.write_json(CORPUS_REL, _mixed_corpus())
    plan = _under_goal_plan(ids, 10)
    qc = evaluate_layup_qc(ctx, plan)
    assert qc.get("ok")
    register_layup_candidate(ctx, plan=plan, qc=qc, label="osc_a")
    ctx.write_json(PLAN_REL, plan, stage_key="nugget_layup_compose")
    picked = try_pick_best_layup_on_oscillation(ctx)
    assert picked.get("ok") is False
    assert picked.get("reason") == "oscillation_pick_disabled_s4"


def test_candidates_cap_at_two(monkeypatch):
    """S4: candidate ledger retains at most two attempts."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda cfg=None: _soft_craft_cfg(),
    )
    from interview_mux.nugget_layup import load_layup_candidates_doc

    ctx = RunContext("exec_asp_cap2", create=True)
    ids = _seed_order(ctx, 12)
    ctx.write_json(CORPUS_REL, _mixed_corpus())
    for aired in (8, 9, 10):
        plan = _under_goal_plan(ids, aired)
        qc = evaluate_layup_qc(ctx, plan)
        register_layup_candidate(ctx, plan=plan, qc=qc, label=f"aired_{aired}")
    doc = load_layup_candidates_doc(ctx)
    assert len(doc.get("candidates") or []) == 2
    assert int(doc.get("attempts") or 0) == 3
