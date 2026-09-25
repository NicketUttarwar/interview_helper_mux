"""Wave 3 Cluster C + Wave 5 Cluster B residual hardening tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.execution_invalidation_profiles import (
    INVALIDATION_PROFILES,
    apply_bounded_invalidation,
)
from interview_mux.gap_fill_eligibility import hosted_framing_requires_synthetic_vo
from interview_mux.v2.config import DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw, patch_executions_root


def test_c02_finalize_after_vo_synthesize_in_delivery_order() -> None:
    """C-02: sound_design_vo_finalize must follow vo_synthesize."""
    assert DELIVERY_ORDER.index("vo_synthesize") < DELIVERY_ORDER.index(
        "sound_design_vo_finalize"
    )
    assert DELIVERY_ORDER.index("vo_line_adjudicate") < DELIVERY_ORDER.index(
        "vo_synthesize"
    )


def test_c02_vo_finalize_refuses_mark_done_when_vo_bridge_missing_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-02: cannot mark_done while vo_bridge cues lack WAVs."""
    import json

    from interview_mux.analysis_memory import default_sound_design_plan
    from interview_mux.stages.sound_design_vo_finalize import run_sound_design_vo_finalize

    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "c02_finalize_refuse")
    plan = default_sound_design_plan()
    plan["assets"] = [
        {
            "asset_id": "a1",
            "role": "vo_bridge",
            "description": "VO",
            "duration_seconds": 1.0,
        }
    ]
    plan["flow_plans"]["podcast"]["cues"] = [
        {
            "cue_id": "cue_1",
            "asset_id": "a1",
            "role": "vo_bridge",
            "line_id": "vo_layup_seg_001",
            "placement": "before_segment",
        }
    ]
    # Bypass SDP sanitize (which strips non-seed cues) — write committed path directly.
    dest = ctx.final_path("understanding", "sound_design_plan.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(plan), encoding="utf-8")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "text": "Hello.",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    run_sound_design_vo_finalize(ctx)
    assert not ctx.is_done("sound_design_vo_finalize")
    doc = ctx.read_json("mastering/sound_design_vo_finalize.json")
    assert doc.get("refused") is True
    assert doc.get("reason") == "vo_bridge_cues_need_wavs"


def test_c04_g1_skip_waives_hosted_framing_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-04: sticky hosted_framing_floor_waived ⇒ requires_synthetic_vo False."""
    ctx = isolated_run_ctx(tmp_path, "c04_floor_waive")
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "hosted_1to1"},
        skip_handoff=True,
    )
    ctx.write_json(
        "run_meta.json",
        {
            "g1_vo_skipped_optional": True,
            "hosted_framing_floor_waived": True,
        },
        skip_handoff=True,
    )
    assert hosted_framing_requires_synthetic_vo(ctx) is False


def test_c01_vo_line_owners_and_resume_stick_synth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-01: owner table + same-fingerprint stick on vo_synthesize."""
    from interview_mux.delivery_invariants import (
        OWNER_SYNTH,
        VO_LINE_OWNERS_REL,
        note_seed_resume,
        resolve_g1_vo_open_resume,
        sync_vo_line_owners,
    )

    ctx = isolated_run_ctx(tmp_path, "c01_owners")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_synth_001",
                    "delivery": "synthesize",
                    "text": "Bridge.",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "vo_line_adjudicate")
    ctx.write_json(
        "understanding/vo_line_adjudication.json",
        {"lines": []},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid == "vo_line_adjudicate",
    )
    doc = sync_vo_line_owners(ctx)
    assert ctx.artifact_exists(VO_LINE_OWNERS_REL)
    assert doc["owners"]["vo_synth_001"] == OWNER_SYNTH
    fp = str(doc.get("fingerprint") or "")
    note_seed_resume(ctx, from_stage=OWNER_SYNTH, because_of="g1_vo_open", fingerprint=fp)
    resume = resolve_g1_vo_open_resume(ctx)
    assert resume == OWNER_SYNTH


def test_b01_seg_resplit_heal_profile_excludes_delivery() -> None:
    """B-01: seg_resplit_heal clear window never includes delivery/EDL."""
    profile = INVALIDATION_PROFILES["seg_resplit_heal"]
    assert "edl" in profile.forbidden_clear or "edl" not in profile.allowed_clear
    assert "mix" in profile.forbidden_clear
    assert "nugget_layup_compose" in profile.forbidden_clear
    assert "segment_classification" in profile.allowed_clear
    assert profile.max_invocations == 2


def test_b01_apply_seg_resplit_heal_unmarks_consumers_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "b01_resplit")
    for sid in (
        "segment_classification",
        "content_brief_reanchor",
        "vernacular_segment_sanitize",
        "edl",
        "mix",
    ):
        mark_done_raw(ctx, sid)
    result = apply_bounded_invalidation(ctx, "seg_resplit_heal", reason="test")
    cleared = set(result.get("cleared") or [])
    assert "segment_classification" in cleared
    assert "edl" not in cleared
    assert ctx.is_done("edl")
    assert ctx.is_done("mix")


def test_b05_hitch_profiles_forbid_late_delivery() -> None:
    """B-05: hitch profiles never clear late edl/mix/mmaudio."""
    for pid in ("hitch_id_churn", "hitch_listen_restage"):
        profile = INVALIDATION_PROFILES[pid]
        for late in ("edl", "mix", "mmaudio_sfx", "master_finalize", "vo_synthesize"):
            assert late in profile.forbidden_clear or late not in profile.allowed_clear


def test_b07_recommendability_maps_to_other_failing_dim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-07: recommendability + conversation_fit → conversation producers, not mix-only."""
    from interview_mux.listen_delight_remutate import plan_listen_delight_remutate

    ctx = isolated_run_ctx(tmp_path, "b07_reco")
    (ctx.run_dir / ".stage_done" / "edl").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / ".stage_done" / "mmaudio_sfx").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "assembly_preview.wav").write_bytes(b"RIFF")
    plan = plan_listen_delight_remutate(
        ctx, failed_dimensions=["recommendability", "conversation_fit"]
    )
    assert "recommendability" not in (plan.get("expanded_dimensions") or [])
    assert plan["from_stage"] in {"transitions", "vo_line_adjudicate", "air_script_seams"}
    assert plan["from_stage"] != "mix"


def test_b07_apply_uses_bounded_delight_axis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.listen_delight_remutate import (
        apply_listen_delight_remutate,
        plan_listen_delight_remutate,
    )

    ctx = isolated_run_ctx(tmp_path, "b07_apply")
    (ctx.run_dir / ".stage_done" / "edl").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / ".stage_done" / "mmaudio_sfx").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / ".stage_done" / "transitions").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / ".stage_done" / "mix").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "assembly_preview.wav").write_bytes(b"RIFF")
    plan = plan_listen_delight_remutate(
        ctx, failed_dimensions=["conversation_fit", "story_followability"]
    )
    applied = apply_listen_delight_remutate(ctx, plan)
    assert applied.get("ok") is True or applied.get("reason") == "refused_low_gain"
    if applied.get("ok"):
        assert "delight_axis_story" in (applied.get("profiles") or [])
        assert not ctx.is_done("transitions") or "transitions" in (applied.get("cleared") or [])


def test_b04_structural_failure_signature_includes_predicate(
    tmp_path: Path,
) -> None:
    from interview_mux.identical_failures import failure_signature_by_class

    isolated_run_ctx(tmp_path, "b04_sig")
    bare = failure_signature_by_class(
        failed_stage="edl", error_class="incomplete_cut_unresolved"
    )
    with_pred = failure_signature_by_class(
        failed_stage="edl",
        error_class="incomplete_cut_unresolved",
        predicate_token="pred_abc",
    )
    assert bare != with_pred
