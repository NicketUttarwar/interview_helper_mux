"""Platform fault-tolerance: quality vocab, heal registry, lattice, seed policy."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_quality_status_enum_matches_schemas():
    from interview_mux.quality_status import (
        QUALITY_STATUS_SCHEMA_ENUM_PATHS,
        QUALITY_STATUS_VALUES,
        STATUS_ADVISORY_FAIL,
        qc_summary_flags,
    )
    import json

    root = Path(__file__).resolve().parents[1]
    for rel, prop in QUALITY_STATUS_SCHEMA_ENUM_PATHS:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        enum = set((data["properties"][prop]["enum"]))
        assert enum == set(QUALITY_STATUS_VALUES)

    flags = qc_summary_flags(STATUS_ADVISORY_FAIL, publish_allowed=True)
    assert flags["advisory"] is True
    assert flags["blocking"] is False
    assert flags["passed"] is False
    assert flags["publish_allowed"] is True


def test_heal_registry_incomplete_cut_and_mmaudio():
    from interview_mux.heal_routing import (
        PLAYBOOK_REGISTRY,
        resume_stage_for_error_class,
    )

    assert resume_stage_for_error_class("incomplete_cut_unresolved") == "junction_snip_qa"
    assert resume_stage_for_error_class("mmaudio_incomplete") == "mmaudio_sfx"
    assert resume_stage_for_error_class("g1_vo_incomplete") == "vo_synthesize"
    # Every registry key has a resume stage.
    for key, spec in PLAYBOOK_REGISTRY.items():
        assert spec.resume_stage, key


def _mark_honest_edl(ctx) -> None:
    """A4 footgun #4: sticky needs done marker + real edl.json body."""
    (ctx.run_dir / ".stage_done").mkdir(exist_ok=True)
    (ctx.run_dir / ".stage_done" / "edl").touch()
    ctx.write_json(
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


def test_seed_policy_freeze_sticky(tmp_path, monkeypatch):
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy

    ctx = RunContext(str(tmp_path / "exec_seed"), create=True)
    ctx.write_json("run_meta.json", {"delivery_epoch": {"vo_seats_freeze": {"hard": True}}})
    _mark_honest_edl(ctx)

    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _c: True,
    )
    assert seed_policy.seed_stage_satisfied_by_policy(ctx, "selection_framing_apply")
    assert seed_policy.seed_stage_satisfied_by_policy(ctx, "gap_framing_recompose")
    assert not seed_policy.seed_stage_satisfied_by_policy(ctx, "mix")

    sealed = seed_policy.seal_freeze_sticky_stages(ctx)
    assert "selection_framing_apply" in sealed
    assert "gap_framing_recompose" in sealed
    assert ctx.is_done("selection_framing_apply")
    assert ctx.is_done("gap_framing_recompose")
    assert ctx.artifact_exists("operator/seed_sanitized.json")


def test_seed_policy_probe_error_sticky_with_edl_and_freeze_artifact(
    tmp_path, monkeypatch
):
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_seed_probe"), create=True)
    ctx.write_json(
        "run_meta.json",
        {"delivery_epoch": {"vo_seats_freeze": {"hard": True, "fingerprint": "fp1"}}},
        skip_handoff=True,
    )
    _mark_honest_edl(ctx)

    def _boom(_c):
        raise RuntimeError("hard_freeze_active boom")

    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        _boom,
    )
    assert seed_policy.seed_stage_satisfied_by_policy(ctx, "selection_framing_apply")


def test_seed_policy_probe_error_without_evidence_not_sticky(tmp_path, monkeypatch):
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_seed_probe2"), create=True)
    ctx.write_json("run_meta.json", {}, skip_handoff=True)

    def _boom(_c):
        raise RuntimeError("hard_freeze_active boom")

    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        _boom,
    )
    assert not seed_policy.seed_stage_satisfied_by_policy(ctx, "selection_framing_apply")


def test_seed_policy_probe_error_soft_fingerprint_not_sticky(tmp_path, monkeypatch):
    """A4-1: soft freeze fingerprint alone must not sticky-complete framing."""
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_seed_soft_fp"), create=True)
    ctx.write_json(
        "run_meta.json",
        {
            "delivery_epoch": {
                "vo_seats_freeze": {"soft": True, "hard": False, "fingerprint": "fp_soft"}
            }
        },
        skip_handoff=True,
    )
    _mark_honest_edl(ctx)

    def _boom(_c):
        raise RuntimeError("hard_freeze_active boom")

    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        _boom,
    )
    assert not seed_policy.seed_stage_satisfied_by_policy(ctx, "selection_framing_apply")


def test_seed_policy_soft_plus_level_hard_not_sticky(tmp_path, monkeypatch):
    """A4 thorough: hard:False wins over contradictory level=hard."""
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_seed_soft_lvl"), create=True)
    ctx.write_json(
        "run_meta.json",
        {
            "delivery_epoch": {
                "vo_seats_freeze": {
                    "soft": True,
                    "hard": False,
                    "level": "hard",
                    "fingerprint": "fp_lie",
                }
            }
        },
        skip_handoff=True,
    )
    _mark_honest_edl(ctx)

    def _boom(_c):
        raise RuntimeError("hard_freeze_active boom")

    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        _boom,
    )
    for sid in seed_policy.freeze_sticky_seed_stages():
        assert not seed_policy.seed_stage_satisfied_by_policy(ctx, sid)


def test_seed_policy_soft_freeze_active_never_sticky(tmp_path, monkeypatch):
    """Happy path: soft freeze alone must not sticky any registered stage."""
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy
    from interview_mux.seat_authority import stamp_soft_seat_freeze

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_seed_soft_live"), create=True)
    ctx.write_json("run_meta.json", {"delivery_epoch": {}}, skip_handoff=True)
    _mark_honest_edl(ctx)
    stamp_soft_seat_freeze(ctx, reason="test_soft")
    for sid in seed_policy.freeze_sticky_seed_stages():
        assert not seed_policy.seed_stage_satisfied_by_policy(ctx, sid)
    assert seed_policy.seal_freeze_sticky_stages(ctx) == []


def test_seed_policy_hard_freeze_sticky_all_core_stages(tmp_path, monkeypatch):
    """Hard freeze + EDL → every core sticky stage satisfies policy."""
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy
    from interview_mux.seat_authority import stamp_hard_seat_freeze

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_seed_hard_all"), create=True)
    ctx.write_json("run_meta.json", {"delivery_epoch": {}}, skip_handoff=True)
    _mark_honest_edl(ctx)
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    for sid in seed_policy.FREEZE_STICKY_SEED_STAGES_CORE:
        assert seed_policy.seed_stage_satisfied_by_policy(ctx, sid)


def test_seed_policy_config_extra_stage_sticky(tmp_path, monkeypatch):
    """Known pipeline extras (not denied) join the sticky set via config."""
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {
            "seed_policy": {"freeze_sticky_extra_stages": ["air_script_compose"]}
        },
    )
    assert "air_script_compose" in seed_policy.freeze_sticky_seed_stages()
    assert seed_policy.is_freeze_sticky_stage("air_script_compose")
    assert "air_script_compose" in seed_policy.FREEZE_STICKY_SEED_STAGES

    ctx = RunContext(str(tmp_path / "exec_seed_extra"), create=True)
    ctx.write_json(
        "run_meta.json",
        {"delivery_epoch": {"vo_seats_freeze": {"hard": True, "level": "hard"}}},
        skip_handoff=True,
    )
    _mark_honest_edl(ctx)

    def _boom(_c):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        _boom,
    )
    assert seed_policy.seed_stage_satisfied_by_policy(ctx, "air_script_compose")


def test_seed_policy_config_extra_denied_critical_not_sticky(tmp_path, monkeypatch):
    """Footgun #2: config cannot sticky-complete mix / vo / ship stages."""
    from interview_mux import seed_policy

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"seed_policy": {"freeze_sticky_extra_stages": ["mix", "vo_synthesize"]}},
    )
    stages = seed_policy.freeze_sticky_seed_stages()
    assert "mix" not in stages
    assert "vo_synthesize" not in stages
    assert not seed_policy.is_freeze_sticky_stage("mix")


def test_seed_policy_hollow_edl_marker_not_sticky(tmp_path, monkeypatch):
    """Footgun #4: bare .stage_done/edl without edl.json must not sticky."""
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy
    from interview_mux.seat_authority import stamp_hard_seat_freeze

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_seed_hollow_edl"), create=True)
    ctx.write_json("run_meta.json", {"delivery_epoch": {}}, skip_handoff=True)
    (ctx.run_dir / ".stage_done").mkdir(exist_ok=True)
    (ctx.run_dir / ".stage_done" / "edl").touch()
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    for sid in seed_policy.FREEZE_STICKY_SEED_STAGES_CORE:
        assert not seed_policy.seed_stage_satisfied_by_policy(ctx, sid)


def test_seed_policy_junk_edl_dict_not_sticky(tmp_path, monkeypatch):
    """A4 residual: versionless / non-spine edl.json must not sticky."""
    from interview_mux.run_context import RunContext
    from interview_mux import seed_policy
    from interview_mux.seat_authority import stamp_hard_seat_freeze

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = RunContext(str(tmp_path / "exec_junk_edl"), create=True)
    ctx.write_json("run_meta.json", {"delivery_epoch": {}}, skip_handoff=True)
    (ctx.run_dir / ".stage_done").mkdir(exist_ok=True)
    (ctx.run_dir / ".stage_done" / "edl").touch()
    # Bypass schema so we can plant a junk body that would otherwise validate-fail.
    path = ctx.final_path("master", "edl.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"note":"not a real edl"}', encoding="utf-8")
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    for sid in seed_policy.FREEZE_STICKY_SEED_STAGES_CORE:
        assert not seed_policy.seed_stage_satisfied_by_policy(ctx, sid)


def test_unlock_seat_freeze_clears_level_hard(tmp_path):
    """Footgun #1: unlock must not leave level=hard with hard:False."""
    from interview_mux.run_context import RunContext
    from interview_mux.seat_authority import (
        stamp_hard_seat_freeze,
        unlock_seat_freeze,
        read_seat_freeze,
    )

    ctx = RunContext(str(tmp_path / "exec_unlock_lvl"), create=True)
    ctx.write_json("run_meta.json", {"delivery_epoch": {}}, skip_handoff=True)
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    fr = unlock_seat_freeze(ctx, reason="test_unlock", clear_hard=True, clear_soft=False)
    assert fr.get("hard") is False
    assert fr.get("soft") is True
    assert fr.get("level") == "soft"
    fr2 = unlock_seat_freeze(ctx, reason="clear_soft", clear_hard=True, clear_soft=True)
    assert fr2.get("hard") is False
    assert not fr2.get("soft")
    assert fr2.get("level") == "unlocked"
    assert read_seat_freeze(ctx).get("level") == "unlocked"


def test_freeze_artifact_proves_hard_matrix() -> None:
    from interview_mux.seed_policy import freeze_artifact_proves_hard

    assert freeze_artifact_proves_hard({"hard": True, "fingerprint": "x"})
    assert freeze_artifact_proves_hard({"level": "hard"})
    assert not freeze_artifact_proves_hard({"soft": True, "fingerprint": "x"})
    assert not freeze_artifact_proves_hard(
        {"soft": True, "hard": False, "level": "hard", "fingerprint": "x"}
    )
    assert not freeze_artifact_proves_hard({})
    assert not freeze_artifact_proves_hard(None)


def test_playability_ssot_blank_and_cta():
    from interview_mux.playability import (
        blank_excluded_ids,
        is_unplayable_for_hard_keep,
        is_unplayable_for_primary_impact,
        unplayable_segment_ids,
    )

    sel = {
        "ordered_segment_ids": ["seg_ok"],
        "excluded_segment_ids": [
            {"segment_id": "seg_blank", "reason": "blank_or_unusable_answer_audio"},
            {"segment_id": "seg_cta", "reason": "media_ip_cta"},
        ],
    }
    assert blank_excluded_ids(None, sel) == {"seg_blank"}
    assert "seg_blank" in unplayable_segment_ids(None, sel)
    assert "seg_cta" in unplayable_segment_ids(None, sel)
    assert is_unplayable_for_primary_impact(None, "seg_blank", sel)
    assert not is_unplayable_for_primary_impact(None, "seg_cta", sel)
    assert is_unplayable_for_hard_keep(None, "seg_cta", sel)


def test_seal_selection_lattice_strips_unplayable(monkeypatch):
    from interview_mux import selection_constraints

    class _Ctx:
        def artifact_exists(self, rel):
            return False

        def log(self, *a, **k):
            return None

        def read_json(self, rel):
            raise FileNotFoundError(rel)

    monkeypatch.setattr(
        "interview_mux.framing_coverage_guard.enforce_framing_ranking",
        lambda ctx, arts: arts,
    )
    monkeypatch.setattr(
        "interview_mux.hard_keep.enforce_hard_keeps",
        lambda ctx, arts: arts,
    )
    monkeypatch.setattr(
        "interview_mux.hard_keep.hard_keep_segment_ids",
        lambda ctx, **k: set(),
    )
    monkeypatch.setattr(
        "interview_mux.framing_coverage_guard.validate_framing_ranking",
        lambda ctx, sel: [],
    )
    arts = {
        "ordered_segment_ids": ["seg_ok", "seg_blank"],
        "excluded_segment_ids": [
            {"segment_id": "seg_blank", "reason": "blank_or_unusable_answer_audio"},
        ],
    }
    out = selection_constraints.seal_selection_lattice(_Ctx(), arts, fail_closed=True)
    assert out["ordered_segment_ids"] == ["seg_ok"]
    assert "seg_blank" not in out["ordered_segment_ids"]


def test_seal_selection_lattice_fail_closed_on_missing_keep(monkeypatch):
    from interview_mux import selection_constraints
    import pytest

    class _Ctx:
        def artifact_exists(self, rel):
            return False

        def log(self, *a, **k):
            return None

    monkeypatch.setattr(
        "interview_mux.framing_coverage_guard.enforce_framing_ranking",
        lambda ctx, arts: arts,
    )
    monkeypatch.setattr(
        "interview_mux.hard_keep.enforce_hard_keeps",
        lambda ctx, arts: arts,
    )
    monkeypatch.setattr(
        "interview_mux.hard_keep.hard_keep_segment_ids",
        lambda ctx, **k: {"seg_must"},
    )
    monkeypatch.setattr(
        "interview_mux.framing_coverage_guard.validate_framing_ranking",
        lambda ctx, sel: [],
    )
    with pytest.raises(ValueError, match="selection_lattice_seal_refused"):
        selection_constraints.seal_selection_lattice(
            _Ctx(),
            {"ordered_segment_ids": ["seg_other"], "excluded_segment_ids": []},
            fail_closed=True,
        )


def test_selection_constraints_apply_order(monkeypatch):
    from interview_mux import selection_constraints

    calls: list[str] = []

    def _framing(ctx, artifacts):
        calls.append("framing")
        return {**artifacts, "framed": True}

    def _hard(ctx, artifacts):
        calls.append("hard")
        return {**artifacts, "kept": True}

    monkeypatch.setattr(
        "interview_mux.framing_coverage_guard.enforce_framing_ranking",
        _framing,
    )
    monkeypatch.setattr(
        "interview_mux.hard_keep.enforce_hard_keeps",
        _hard,
    )
    out = selection_constraints.apply_selection_constraints(
        None, {"ordered_segment_ids": ["a"]}
    )
    assert calls == ["framing", "hard"]
    assert out.get("framed") and out.get("kept")


def test_residual_stale_state_does_not_block(tmp_path):
    from interview_mux.run_context import RunContext
    from interview_mux.delivery_guardrails import (
        DELIVERY_RESIDUALS_REL,
        critical_residual_view,
        record_delivery_residual,
        stamp_delivery_epoch,
    )

    ctx = RunContext(str(tmp_path / "exec_res"), create=True)
    ctx.write_json("run_meta.json", {})
    stamp_delivery_epoch(ctx, junction_residuals_generation=2)
    record_delivery_residual(
        ctx,
        kind="on_a_roll",
        severity="critical",
        stage="junction_snip_qa",
        state="stale",
    )
    # Force-write stale row with old generation
    ctx.write_json(
        DELIVERY_RESIDUALS_REL,
        {
            "version": 1,
            "generation": 2,
            "residuals": [
                {
                    "kind": "on_a_roll",
                    "severity": "critical",
                    "state": "stale",
                    "generation": 1,
                    "stage": "junction_snip_qa",
                }
            ],
            "critical_count": 0,
        },
        skip_handoff=True,
    )
    view = critical_residual_view(ctx)
    assert view.count == 0


def test_dual_brain_resume_helper_shared():
    """0.1.0 and 0.0.0 both use resume_stage_for_error_class SSOT."""
    from interview_mux.heal_routing import resume_stage_for_error_class

    assert resume_stage_for_error_class("incomplete_cut_unresolved") == "junction_snip_qa"
    # Linear brain path historically hard-coded mix; registry must win.
    assert resume_stage_for_error_class("incomplete_cut_unresolved") != "mix"


def test_audit_quality_status_forbids_hardcoded_consumers():
    """CI audit must pass: schemas match vocab and no stray advisory_fail literals."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "tools" / "audit_quality_status_enum.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
