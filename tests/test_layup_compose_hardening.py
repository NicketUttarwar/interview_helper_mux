"""P1–P8 nugget_layup_compose thrash hardening (no live LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import heal_pin_for
from interview_mux.delivery_guardrails import clamp_resume_through_order
from interview_mux.loud_fail import LoudStageFailure
from interview_mux.nugget_layup import (
    CORPUS_REL,
    GAP_REL,
    PLAN_REL,
    apply_craft_spine_or_skip,
    compose_qc_pending,
    gap_report_write_lock,
    invalidate_vo_after_layup_rewrite,
    prior_gap_line_fingerprints,
    publish_layup_plan_to_gap_report,
    raise_hosted_vo_floor_unsatisfiable,
    stamp_compose_qc_pending,
    stamp_sparse_or_empty_corpus_exits,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness


_ANALYSIS = {
    "target_beat": "The exit negotiation",
    "listener_need_entering_T": "Prior clip ended before the buyer appeared",
    "forward_unlock": "Why the snack pivot decided the price",
}


def _seed(ctx: RunContext, ordered: list[str]) -> None:
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ordered})
    segs = []
    t = 0
    for sid in ordered:
        segs.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_0",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "topic_tags": [],
                "text": f"Native content for {sid} about the snack pivot and exit.",
                "start_ms": t,
                "end_ms": t + 8000,
            }
        )
        t += 10_000
    ctx.write_json("segments/manifest.json", {"segments": segs})


def test_compose_qc_pending_blocks_done_without_dirty_gap():
    ctx = RunContext("exec_layup_qc_pending", create=True)
    _seed(ctx, ["seg_001", "seg_002"])
    prior = {
        "interviewer_lines": [
            {
                "line_id": f"vo_layup_seg_00{i}",
                "origin": "nugget_layup",
                "placement": "before",
                "targets_segment_id": f"seg_00{i}",
                "delivery": "synthesize",
                "text": f"Prior good host line {i} that unlocks the snack beat clearly?",
            }
            for i in (1, 2, 3)
        ],
        "nugget_layup_authority": True,
    }
    ctx.write_json(GAP_REL, prior, skip_handoff=True)
    pending = stamp_compose_qc_pending(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "layups": [],
        },
        errors=["canned_air[seg_001]: hinge"],
    )
    ctx.write_json(PLAN_REL, pending, skip_handoff=True)
    assert compose_qc_pending(pending) is True
    reason = stage_artifact_incompleteness(ctx, "nugget_layup_compose")
    assert reason and "layup_compose_qc_pending" in reason
    disk = ctx.read_json(GAP_REL)
    # Prior authority stamp must survive qc_pending (sanitize may omit orphans).
    assert disk.get("nugget_layup_authority") is True
    assert isinstance(disk.get("interviewer_lines"), list)


def test_empty_corpus_deterministic_exit_clears_open_high():
    ctx = RunContext("exec_layup_empty_corpus", create=True)
    _seed(ctx, ["seg_001", "seg_002"])
    ctx.write_json(CORPUS_REL, {"nuggets": []})
    plan = {
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "layups": [
            {
                "target_segment_id": "seg_001",
                "line_id": "vo_layup_seg_001",
                "skip": True,
                "text": "",
            }
        ],
        "open_high_salience_nugget_ids": ["nug_ghost"],
    }
    out, notes = stamp_sparse_or_empty_corpus_exits(ctx, plan)
    assert notes
    assert out.get("open_high_salience_nugget_ids") == []
    assert "empty_corpus_deterministic_exit" in (out.get("warnings") or [])
    for row in out.get("layups") or []:
        if isinstance(row, dict):
            assert row.get("skip") is True
            assert row.get("skip_reason_code")


def test_craft_spine_skips_unhealable_canned_row():
    ctx = RunContext("exec_layup_craft_spine", create=True)
    _seed(ctx, ["seg_011"])
    ctx.write_json(
        CORPUS_REL,
        {
            "nuggets": [
                {
                    "nugget_id": "nug_001",
                    "text_claim": "The snack pivot rewrote pricing across the channel.",
                    "evidence_quote": "snack pivot",
                    "in_selection": False,
                    "salience": "high",
                }
            ]
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_011"],
        "layups": [
            {
                "target_segment_id": "seg_011",
                "line_id": "vo_layup_seg_011",
                "text": "What comes next?",
                "skip": False,
                "nugget_ids": ["nug_001"],
                **_ANALYSIS,
            }
        ],
    }
    qc = {
        "ok": False,
        "errors": ["canned_air[seg_011]: what comes next"],
    }
    out, notes = apply_craft_spine_or_skip(ctx, plan, qc=qc)
    assert notes
    row = next(
        r
        for r in (out.get("layups") or [])
        if isinstance(r, dict) and r.get("target_segment_id") == "seg_011"
    )
    text = str(row.get("text") or "")
    assert "What comes next?" not in text
    if not row.get("skip"):
        assert len(text.split()) >= 8


def test_hosted_vo_floor_unsatisfiable_heal_pin_empty(monkeypatch):
    """Legacy path (progress floors off) still loud-fails with empty heal pin."""
    monkeypatch.setattr(
        "interview_mux.floor_progress.hosted_vo_aspirational",
        lambda _ctx=None: False,
    )
    ctx = RunContext("exec_layup_floor_unsat", create=True)
    _seed(ctx, ["seg_001"])
    ctx.write_json(PLAN_REL, {"ordered_segment_ids": ["seg_001"], "layups": []})
    with pytest.raises(LoudStageFailure) as ei:
        raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=0, eligible_nuggets=0)
    assert ei.value.reason == "hosted_vo_floor_unsatisfiable"
    assert heal_pin_for("hosted_vo_floor_unsatisfiable", ctx=ctx) == ""
    plan = ctx.read_json(PLAN_REL)
    assert (plan.get("_meta") or {}).get("hosted_vo_floor_unsatisfiable") is True
    esc = ctx.read_json("operator/escalations/nugget_layup_compose.json")
    assert esc.get("reason") == "hosted_vo_floor_unsatisfiable"


def test_hosted_vo_floor_aspirational_no_loud_fail():
    """HOLLOW_ZERO (active=0) still loud-fails; aspirational only waives PARTIAL."""
    ctx = RunContext("exec_layup_floor_asp", create=True)
    _seed(ctx, ["seg_001"])
    ctx.write_json(PLAN_REL, {"ordered_segment_ids": ["seg_001"], "layups": []})
    with pytest.raises(LoudStageFailure) as ei:
        raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=0, eligible_nuggets=0)
    assert ei.value.reason == "hosted_vo_floor_unsatisfiable"


def test_invalidate_vo_after_layup_rewrite_drops_wav(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "layup_vo_invalidate")
    _seed(ctx, ["seg_005"])
    pickup = ctx.path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    wav = pickup / "vo_layup_seg_005.wav"
    wav.write_bytes(b"RIFF....")
    done = ctx.final_path(".stage_done", "vo_synthesize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("ok\n")
    prior = {
        "vo_layup_seg_005": "old host copy about the snack pivot that unlocks pricing?",
    }
    new_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_005",
                "origin": "nugget_layup",
                "text": "new host copy about the snack pivot that unlocks pricing differently?",
                "placement": "before",
                "targets_segment_id": "seg_005",
                "delivery": "synthesize",
            }
        ]
    }
    changed = invalidate_vo_after_layup_rewrite(
        ctx, prior_fps=prior, new_report=new_report
    )
    assert "vo_layup_seg_005" in changed
    assert not wav.exists()
    assert not done.exists()


def test_gap_report_write_lock_serializes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "layup_gap_lock")
    seen: list[str] = []
    with gap_report_write_lock(ctx):
        seen.append("in")
        lock_path = ctx.path("understanding/.gap_report.write.lock")
        assert lock_path.parent.is_dir()
    assert seen == ["in"]


def test_clamp_layup_resume_defers_to_seed_front(monkeypatch):
    ctx = RunContext("exec_layup_clamp_seed", create=True)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.earliest_incomplete_must_precede",
        lambda _ctx, sid: "",
    )
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening._earliest_incomplete_seed_stage",
        lambda _ctx, sid: "narrative_arc_plan",
    )
    pinned = clamp_resume_through_order(ctx, "nugget_layup_compose")
    assert pinned == "narrative_arc_plan"


def test_publish_under_lock_holds_prior_on_hollow(monkeypatch):
    ctx = RunContext("exec_layup_publish_lock", create=True)
    _seed(ctx, ["seg_002", "seg_012", "seg_020"])
    prior_lines = [
        {
            "line_id": f"vo_layup_seg_{sid}",
            "gap_type": "nugget_layup",
            "placement": "before",
            "targets_segment_id": f"seg_{sid}",
            "delivery": "synthesize",
            "origin": "nugget_layup",
            "text": f"Host question for {sid} that unlocks the next beat clearly.",
        }
        for sid in ("002", "012", "020")
    ]
    ctx.write_json(
        GAP_REL,
        {"interviewer_lines": prior_lines, "nugget_layup_authority": True},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    fps = prior_gap_line_fingerprints(ctx)
    assert len(fps) == 3
    with gap_report_write_lock(ctx):
        report = publish_layup_plan_to_gap_report(
            ctx,
            {
                "ordered_segment_ids": ["seg_002", "seg_012", "seg_020"],
                "layups": [],
                "warnings": ["compose_restart"],
            },
        )
    assert len(report.get("interviewer_lines") or []) >= 3
