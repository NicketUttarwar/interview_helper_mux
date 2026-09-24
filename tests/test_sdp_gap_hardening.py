"""SDP gap hardening — deferred validate split, invent lint, force-enabled, reconcile."""

from __future__ import annotations

import pytest

from interview_mux.creative_delivery import sdp_compose_deferred, validate_creative_density
from interview_mux.sdp_cross_validate import validate_post_sound_plan
from interview_mux.stages import sound_design_stages as sds
from run_fixtures import (
    isolated_run_ctx,
    seed_analysis_ready_artifacts,
    sound_design_plan_with,
)


@pytest.fixture(autouse=True)
def _forensics_off(monkeypatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("MUX_E2E_SOFT_LISTENABILITY", raising=False)


def _theme_assets() -> list[dict]:
    return [
        {
            "asset_id": "motif_01",
            "role": "theme_cold_open",
            "palette_kind": "motif",
            "description": "Bright guitar piano motif phrase",
            "duration_seconds": 8,
        },
        {
            "asset_id": "bed_01",
            "role": "theme_underscore",
            "palette_kind": "underscore_loop",
            "description": "Calm guitar piano bed loop",
            "duration_seconds": 14,
        },
        {
            "asset_id": "sting_01",
            "role": "theme_emphasis",
            "palette_kind": "stinger",
            "description": "Short piano sting accent",
            "duration_seconds": 3,
        },
        {
            "asset_id": "outro_01",
            "role": "theme_outro",
            "palette_kind": "full_bed",
            "description": "Resolving ensemble full bed close",
            "duration_seconds": 16,
        },
    ]


def test_sdp_compose_deferred_helper():
    assert sdp_compose_deferred(
        {"flow_plans": {"podcast": {"compose_deferred": True, "cues": []}}}
    )
    assert not sdp_compose_deferred(
        {"flow_plans": {"podcast": {"compose_deferred": False, "cues": []}}}
    )
    assert not sdp_compose_deferred({})


def test_deferred_sdp_skips_bed_coverage_and_strict_slots(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_deferred_validate")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": [f"seg_{i:03d}" for i in range(1, 21)]},
        skip_handoff=True,
    )
    # Sparse placeholder bed — would fail ~40% coverage if seated.
    sdp = sound_design_plan_with(
        assets=_theme_assets(),
        flow_plans={
            "podcast": {
                "profile": "podcast",
                "compose_deferred": True,
                "cues": [
                    {
                        "cue_id": "palette_bed_placeholder",
                        "asset_id": "bed_01",
                        "role": "theme_underscore",
                        "placement": "under_segment",
                        "segment_id": "seg_001",
                    }
                ],
            }
        },
        motif_family={
            "motif_id": "m1",
            "prompt_dna": "bright guitar piano documentary pulse",
            "key_center": "G",
            "scale_or_mode": "major",
        },
    )
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)
    dens = validate_creative_density(ctx, sdp)
    assert not any("bed coverage" in e for e in dens)
    assert not any("under_segment bed cue" in e for e in dens)
    # Role invent still enforced.
    assert not any("missing music role" in e for e in dens)

    # Empty cue_slots via load_policy monkeypatch — avoid policy schema write.
    monkeypatch.setattr(
        "interview_mux.soundscape_policy.load_policy",
        lambda _ctx: {
            "version": 1,
            "underscore_policy": "normal",
            "cue_slots": [],
            "sfx_density": {"max_beds": 4, "max_punctuators": 2, "max_foley": 0},
            "mix_contract": {
                "underscore_policy": "normal",
                "bed_level_db_range": [-16, -12],
            },
        },
    )
    monkeypatch.setattr(
        "interview_mux.soundscape_policy.strict_slots", lambda cfg=None: True
    )
    errs = validate_post_sound_plan(ctx)
    assert not any("cue_slots" in e for e in errs)


def test_seated_sdp_still_enforces_coverage(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_seated_coverage")
    seed_analysis_ready_artifacts(ctx)
    ordered = [f"seg_{i:03d}" for i in range(1, 21)]
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ordered},
        skip_handoff=True,
    )
    # Patch coverage estimate low so one bed fails seated density.
    monkeypatch.setattr(
        "interview_mux.creative_delivery._estimate_bed_coverage_ratio",
        lambda _ctx, _cues: 0.05,
    )

    sdp = sound_design_plan_with(
        assets=_theme_assets(),
        flow_plans={
            "podcast": {
                "profile": "podcast",
                "compose_deferred": False,
                "cues": [
                    {
                        "cue_id": "one_bed",
                        "asset_id": "bed_01",
                        "role": "theme_underscore",
                        "placement": "under_segment",
                        "segment_id": "seg_001",
                    }
                ],
            }
        },
        motif_family={
            "motif_id": "m1",
            "prompt_dna": "bright guitar piano documentary pulse",
        },
    )
    dens = validate_creative_density(ctx, sdp)
    assert any("bed coverage" in e for e in dens)


def test_invent_lint_rejects_banned_texture():
    sdp = {
        "assets": [
            {
                "asset_id": "whoosh_01",
                "role": "theme_emphasis",
                "palette_kind": "stinger",
                "description": "big whoosh riser slap",
                "duration_seconds": 2,
            },
            {
                "asset_id": "bed_01",
                "role": "theme_underscore",
                "palette_kind": "underscore_loop",
                "description": "guitar bed",
                "duration_seconds": 12,
            },
            {
                "asset_id": "open_01",
                "role": "theme_cold_open",
                "palette_kind": "motif",
                "description": "piano motif",
                "duration_seconds": 8,
            },
        ],
        "motif_family": {"prompt_dna": "guitar piano pulse"},
    }
    errs = sds._lint_sdp_invent(sdp)
    assert any("banned_texture" in e or "banned_asset_id" in e for e in errs)


def test_invent_lint_accepts_clean_theme_inventory():
    sdp = {
        "assets": _theme_assets(),
        "motif_family": {"prompt_dna": "bright guitar piano documentary pulse"},
    }
    assert sds._lint_sdp_invent(sdp) == []


def test_force_enabled_full_auto(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_force_enabled")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json(
        "run_meta.json",
        {"full_auto": True, "run_mode": "full-auto"},
        skip_handoff=True,
    )
    monkeypatch.setitem(
        __import__("interview_mux.config", fromlist=["merged_config"]).merged_config().setdefault(
            "sound_design", {}
        )
        if False
        else {},
        "enabled",
        False,
    )
    # Patch merged_config to report enabled=false.
    import interview_mux.config as cfg_mod

    real = cfg_mod.merged_config

    def _cfg():
        c = dict(real())
        sd = dict(c.get("sound_design") or {})
        sd["enabled"] = False
        c["sound_design"] = sd
        return c

    monkeypatch.setattr(cfg_mod, "merged_config", _cfg)
    monkeypatch.setattr(sds, "merged_config", _cfg)
    assert sds._sound_design_enabled(ctx) is True


def test_force_enabled_lab_omit_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_lab_omit")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json("run_meta.json", {"full_auto": True}, skip_handoff=True)
    ctx.write_json("operator/music_omitted.json", {"omitted": []}, skip_handoff=True)

    import interview_mux.config as cfg_mod

    real = cfg_mod.merged_config

    def _cfg():
        c = dict(real())
        sd = dict(c.get("sound_design") or {})
        sd["enabled"] = False
        c["sound_design"] = sd
        return c

    monkeypatch.setattr(cfg_mod, "merged_config", _cfg)
    monkeypatch.setattr(sds, "merged_config", _cfg)
    assert sds._sound_design_enabled(ctx) is False


def test_clear_invent_obligation():
    sdp = {
        "coherence": {"invent_obligation": "sound_design_plan", "sonic_identity": ""},
        "_meta": {"invent_obligation": "sound_design_plan"},
    }
    sds._clear_sdp_invent_obligation(sdp)
    assert sdp["coherence"]["invent_obligation"] == ""
    assert sdp["coherence"]["musical_direction_complete"] is True
    assert sdp["_meta"]["invent_obligation"] == ""


def test_clamp_durations_inplace():
    sdp = {
        "assets": [
            {
                "asset_id": "bed_01",
                "role": "theme_underscore",
                "duration_seconds": 2.2,
            }
        ]
    }
    sds._clamp_sdp_asset_durations_inplace(sdp)
    d = float(sdp["assets"][0]["duration_seconds"])
    assert d >= 5.0  # role band floor for theme_underscore


def test_safe_bed_skips_banned(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_safe_bed")
    seed_analysis_ready_artifacts(ctx)
    monkeypatch.setattr(
        "interview_mux.sonic_context.load_sonic_context",
        lambda _ctx: {
            "segment_flags": {
                "overlap_high": ["seg_001"],
                "trauma_adjacent": ["seg_002"],
            }
        },
    )
    ordered = ["seg_001", "seg_002", "seg_003"]
    assert sds._safe_placeholder_bed_segment(ctx, ordered) == "seg_003"


def test_reconcile_fail_closed_full_auto(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_reconcile_fc")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json("run_meta.json", {"full_auto": True}, skip_handoff=True)
    assert sds._sdp_fail_closed_reconcile(ctx) is True
    ctx.write_json("run_meta.json", {"run_mode": "manual"}, skip_handoff=True)
    assert sds._sdp_fail_closed_reconcile(ctx) is False


def test_mix_completeness_full_auto_hard_sfx(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_mix_hard_sfx")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json("run_meta.json", {"full_auto": True}, skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.mix_completeness.completeness_gate_mode", lambda: "block"
    )
    monkeypatch.setattr(
        "interview_mux.mix_completeness.completeness_gate_enabled", lambda: True
    )
    # Avoid beds_deferred soft path.
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.beds_deferred_for_mix",
        lambda _ctx: False,
    )
    from interview_mux.mix_completeness import enforce_mix_completeness

    with pytest.raises(RuntimeError, match="missing mix assets"):
        enforce_mix_completeness(
            ctx,
            flow="podcast",
            stage="mix",
            missing_sfx=["bed_01"],
        )
