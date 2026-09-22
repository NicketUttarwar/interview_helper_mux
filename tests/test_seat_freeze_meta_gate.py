"""Tests for Pillar B seat freeze + Pillar C meta-gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def run_ctx(tmp_path: Path):
    from interview_mux.run_context import RunContext

    run = tmp_path / "exec_test_seat_001"
    run.mkdir()
    (run / "run_meta.json").write_text(
        '{"version":1,"delivery_epoch":{}}\n', encoding="utf-8"
    )
    (run / ".stage_done").mkdir()
    (run / "understanding").mkdir()
    (run / "understanding" / "gap_report.json").write_text(
        json.dumps(
            {
                "interviewer_lines": [
                    {
                        "line_id": "vo_layup_seg_001",
                        "delivery": "synthesize",
                        "text": "Hello there friend.",
                        "required": True,
                    },
                    {
                        "line_id": "vo_layup_seg_002",
                        "delivery": "synthesize",
                        "text": "Next thought.",
                        "required": True,
                        "skipped_optional": True,
                        "air_script_omit": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return RunContext(str(run), create=False)


def test_soft_hard_freeze_and_fingerprint(run_ctx, monkeypatch):
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: ["vo_layup_seg_002"],
    )
    soft = sa.stamp_soft_seat_freeze(run_ctx, reason="test")
    assert soft.get("soft") is True
    assert soft.get("fingerprint")
    hard = sa.stamp_hard_seat_freeze(run_ctx, reason="vo_synthesize")
    assert hard.get("hard") is True
    assert sa.soft_freeze_active(run_ctx)
    assert sa.hard_freeze_active(run_ctx)


def test_seat_mutation_blocked_after_soft_freeze(run_ctx, monkeypatch):
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: [],
    )
    sa.stamp_soft_seat_freeze(run_ctx)
    allowed, why = sa.seat_mutation_allowed(
        run_ctx, reason="compose_pass_b", require_meta_gate=True
    )
    assert allowed is False
    assert "meta_gate" in why or "frozen" in why


def test_holistic_seat_review_reports_intersection(run_ctx, monkeypatch):
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_002"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: ["vo_layup_seg_002"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.gap_line_air_eligible",
        lambda ln: not ln.get("skipped_optional"),
    )
    report = sa.holistic_seat_review(run_ctx)
    assert report["ok"] is False
    assert any("seated_and_omitted" in f for f in report["failures"])
    assert report["resume_pin"] == "air_contract_sanitize"


def test_frozen_omitted_ids(run_ctx, monkeypatch):
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: ["vo_layup_seg_002"],
    )
    sa.stamp_soft_seat_freeze(run_ctx)
    ids = sa.frozen_omitted_line_ids(run_ctx)
    assert "vo_layup_seg_002" in ids


def test_timeline_reopen_refuses_cosmetic_edge(run_ctx):
    from interview_mux.timeline_reopen_meta_gate import (
        INTENT_EDL_EDGE,
        decide_timeline_reopen,
    )

    row = decide_timeline_reopen(
        run_ctx,
        intent=INTENT_EDL_EDGE,
        detail={"cosmetic_mid_word": True},
    )
    assert row["allow"] is False


def test_timeline_reopen_allows_critical_incomplete(run_ctx):
    from interview_mux.timeline_reopen_meta_gate import (
        INTENT_JUNCTION,
        decide_timeline_reopen,
    )

    row = decide_timeline_reopen(
        run_ctx,
        intent=INTENT_JUNCTION,
        detail={"incomplete_kinds": ["incomplete_clause"]},
    )
    assert row["allow"] is True


def test_delight_remutate_refused_low_gain(run_ctx, monkeypatch):
    from interview_mux import listen_delight_remutate as ldr

    plan = {
        "failed_dimensions": ["conversation_fit"],
        "from_stages": ["transitions", "edl", "mix"],
        "from_stage": "transitions",
        "overall": 0.88,
        "dims_fingerprint": "abc",
        "exhausted": False,
    }
    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        lambda *a, **k: {
            "allow": False,
            "refuse_reason": "low",
            "expected_gain": 0.05,
            "decision_id": "x",
        },
    )
    run_ctx.write_json(ldr.REMUTATE_REL, plan)
    out = ldr.apply_listen_delight_remutate(run_ctx, plan)
    assert out.get("reason") == "refused_low_gain"


def test_seat_rewrite_catastrophe_allows(run_ctx):
    from interview_mux.timeline_reopen_meta_gate import decide_seat_rewrite

    row = decide_seat_rewrite(
        run_ctx,
        proposed_delta={"ops": [{"action": "omit", "line_id": "x"}]},
        reason="g1_red",
    )
    assert row["allow"] is True


def test_seat_rewrite_generation_cap(run_ctx, monkeypatch):
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: [],
    )
    sa.stamp_soft_seat_freeze(run_ctx)
    for _ in range(2):
        sa.bump_seat_rewrite_generation(run_ctx)
    ok, why = sa.seat_rewrite_budget_ok(run_ctx)
    assert ok is False
    assert "soft_rewrite_cap" in why
    # DP-A2 A: named CTA End-A proceeds even under soft rewrite cap (no substring).
    allowed, why2 = sa.seat_mutation_allowed(
        run_ctx, reason="media_ip_cta_editorial_omits", require_meta_gate=True
    )
    assert allowed is True
    assert why2 == "end_a_allowlist"
    assert sa.gate_seat_mutation(
        run_ctx,
        reason="media_ip_cta_editorial_omits",
        symptoms=["media_ip_cta"],
    )
    # Non-exact packaging substring must not auto-allow past the cap.
    sub_ok, sub_why = sa.seat_mutation_allowed(
        run_ctx, reason="repair:media_ip_cta_residue", require_meta_gate=True
    )
    assert sub_ok is False
    assert "soft_rewrite_cap" in sub_why or sub_why.startswith("end_a_near_miss:")


def test_story_remutate_dual_gate_under_hard_freeze(run_ctx, monkeypatch):
    from interview_mux import listen_delight_remutate as ldr
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: [],
    )
    sa.stamp_soft_seat_freeze(run_ctx)
    sa.stamp_hard_seat_freeze(run_ctx)
    plan = {
        "failed_dimensions": ["story_followability"],
        "from_stages": ["air_script_seams"],
        "from_stage": "air_script_seams",
        "overall": 0.75,
        "dims_fingerprint": "story",
        "exhausted": False,
        "delight_axis": "story",
    }
    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        lambda *a, **k: {
            "allow": True,
            "expected_gain": 0.5,
            "decision_id": "gain_ok",
            "axes_allowed": ["story"],
        },
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *a, **k: {"allow": False, "refuse_reason": "low_opportunity"},
    )
    run_ctx.write_json(ldr.REMUTATE_REL, plan)
    master = run_ctx.final_path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "assembly.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    out = ldr.apply_listen_delight_remutate(run_ctx, plan)
    assert out.get("ok") is False
    assert out.get("reason") == "refused_seat_freeze"


def test_seat_rewrite_uses_llm_runner_path(run_ctx, monkeypatch):
    """Contested seat rewrite must call llm_runner (not dead prompt_envelope import)."""
    from interview_mux import timeline_reopen_meta_gate as trg

    calls: list[dict] = []

    def _fake_envelope(stage_key, prompt_rel, user_content=None, **kwargs):
        calls.append({"stage_key": stage_key, "prompt_rel": prompt_rel, **kwargs})
        return {
            "artifacts": {
                "allow": True,
                "opportunity_score": 0.9,
                "expected_listener_gain": 0.85,
                "rewrite_ops": [{"action": "omit", "line_id": "vo_x"}],
                "refuse_reason": "",
            }
        }

    monkeypatch.setattr(trg, "_invoke_prompt_envelope", _fake_envelope)
    row = trg.decide_seat_rewrite(
        run_ctx,
        proposed_delta={"ops": [{"action": "omit", "line_id": "vo_x"}]},
        reason="vo_wall_adjacent",
        symptoms=["vo_wall"],
    )
    assert calls, "llm_runner.run_prompt_envelope was never invoked"
    assert calls[0]["stage_key"] == "seat_rewrite_meta_gate"
    assert calls[0].get("task_kind") == "advisory"
    assert row["path"] == "llm"
    assert row["allow"] is True
    assert row["opportunity_score"] == 0.9


def test_timeline_reopen_uses_llm_runner_path(run_ctx, monkeypatch):
    from interview_mux import timeline_reopen_meta_gate as trg

    calls: list[str] = []

    def _fake_envelope(stage_key, prompt_rel, user_content=None, **kwargs):
        calls.append(stage_key)
        return {
            "artifacts": {
                "allow": True,
                "intent": trg.INTENT_DELIGHT,
                "expected_gain": 0.55,
                "axes_allowed": ["sonic"],
                "refuse_reason": "",
            }
        }

    monkeypatch.setattr(trg, "_invoke_prompt_envelope", _fake_envelope)
    monkeypatch.setattr(
        trg,
        "_deterministic_prefilter",
        lambda *a, **k: None,
    )
    row = trg.decide_timeline_reopen(
        run_ctx,
        intent=trg.INTENT_DELIGHT,
        failed_dims=["sonic_weave"],
        detail={"overall": 0.88, "dim_scores": {"sonic_weave": 0.82}},
    )
    assert calls == ["timeline_reopen_meta_gate"]
    assert row["path"] == "llm"
    assert row["allow"] is True
    assert "sonic" in (row.get("axes_allowed") or [])


def test_parse_gate_envelope_artifacts_and_text():
    from interview_mux.timeline_reopen_meta_gate import _parse_gate_envelope

    assert _parse_gate_envelope({"artifacts": {"allow": True, "expected_gain": 0.4}})[
        "allow"
    ] is True
    assert _parse_gate_envelope({"text": 'noise {"allow": false, "refuse_reason": "x"} tail'})[
        "allow"
    ] is False
    assert _parse_gate_envelope({"artifacts": {"allow": "yes"}}) is None


def test_commit_selection_preserves_order_when_meta_gate_refuses(run_ctx, monkeypatch):
    """Under soft freeze, refused order change must no-op — not raise/spin."""
    from interview_mux import seat_authority as sa
    from interview_mux.air_order_boundary import commit_selection_mutation
    from interview_mux.artifact_sanitize.reentry import stamp_matches

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *a, **k: {
            "allow": False,
            "refuse_reason": "opportunity_below_threshold",
            "opportunity_score": 0.3,
        },
    )
    frozen = ["seg_a", "seg_b", "seg_c"]
    run_ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": frozen,
            "excluded_segment_ids": [],
            "order_content_hash": "frozen_hash",
        },
    )
    sa.stamp_soft_seat_freeze(run_ctx, reason="test")
    out = commit_selection_mutation(
        run_ctx,
        {
            "ordered_segment_ids": ["seg_c", "seg_a", "seg_b"],
            "excluded_segment_ids": [],
            "note": "attempted_reorder",
        },
        producer="transitions",
        stage_key="transitions",
        checkpoint_mode="repair",
        skip_checkpoint=True,
        write_committed=True,
    )
    assert out.get("ordered_segment_ids") == frozen
    disk = run_ctx.read_json("master/selection.json")
    assert disk.get("ordered_segment_ids") == frozen
    assert stamp_matches(
        disk, content_keys=["ordered_segment_ids", "order_content_hash"]
    )


def test_seat_rewrite_allows_packaging_sanitize_order_change(run_ctx):
    from interview_mux.timeline_reopen_meta_gate import decide_seat_rewrite

    row = decide_seat_rewrite(
        run_ctx,
        proposed_delta={
            "ops": [],
            "order_change": True,
            "source": "artifact_sanitize.selection",
            "stage_key": "selection_order_sanitize",
        },
        reason="selection_commit:artifact_sanitize.selection",
        symptoms=["order_change", "selection_commit"],
    )
    assert row["allow"] is True
    assert row["opportunity_score"] >= 0.65

    cta = decide_seat_rewrite(
        run_ctx,
        proposed_delta={"ops": [], "from": "media_ip_cta_editorial_omits"},
        reason="media_ip_cta_editorial_omits",
        symptoms=["media_ip_cta"],
    )
    assert cta["allow"] is True
    assert cta["opportunity_score"] >= 0.65


def test_selection_framing_apply_marks_done_under_seat_freeze(run_ctx, monkeypatch):
    """Seat-freeze no-op must sticky-complete so mix seed-order does not thrash."""
    from interview_mux import seat_authority as sa
    from interview_mux.refinement_passes import run_selection_framing_apply

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: [],
    )
    sa.stamp_soft_seat_freeze(run_ctx, reason="test")
    sa.stamp_hard_seat_freeze(run_ctx, reason="vo_synthesize")
    assert not run_ctx.is_done("selection_framing_apply")
    run_selection_framing_apply(run_ctx)
    assert run_ctx.is_done("selection_framing_apply")


def test_seed_order_skips_framing_apply_after_edl_hard_freeze(run_ctx, monkeypatch):
    from interview_mux import seat_authority as sa
    from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage
    from interview_mux.v2.config import DELIVERY_ORDER

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda ctx, stage: ctx.is_done(stage),
    )
    for stage in DELIVERY_ORDER:
        if stage == "mix":
            break
        if stage == "selection_framing_apply":
            continue
        (run_ctx.run_dir / ".stage_done" / stage).write_text("", encoding="utf-8")
    # A4 footgun #4: sticky needs honest EDL body, not hollow marker alone.
    run_ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_001",
                    "source_start_ms": 0,
                    "source_end_ms": 1000,
                    "timeline_start_ms": 0,
                    "duration_ms": 1000,
                }
            ],
        },
        skip_handoff=True,
    )
    sa.stamp_hard_seat_freeze(run_ctx, reason="vo_synthesize")
    assert not run_ctx.is_done("selection_framing_apply")
    earliest = _earliest_incomplete_seed_stage(run_ctx, "mix")
    assert earliest != "selection_framing_apply"
    assert run_ctx.is_done("selection_framing_apply")
