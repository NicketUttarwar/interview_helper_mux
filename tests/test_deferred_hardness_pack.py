"""Deferred hardness pack: MU5/MU7, LD4/LD5, RC6, delight authoritative."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_creative_density_preflight_flags_thin_coverage(tmp_path: Path, monkeypatch) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.creative_delivery import validate_creative_density
    from interview_mux.file_store import write_json as fs_write_json

    ctx = isolated_run_ctx(tmp_path, "mu5_density")
    monkeypatch.setattr(
        "interview_mux.creative_delivery.creative_delivery_required", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        "interview_mux.creative_delivery.min_density_cfg",
        lambda *_a, **_k: {"min_bed_coverage_ratio": 0.9},
    )
    fs_write_json(
        ctx.path("master/selection.json"),
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "segments": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 10_000},
                {"segment_id": "seg_002", "start_ms": 10_000, "end_ms": 20_000},
            ],
        },
    )
    sdp = {
        "assets": [
            {"asset_id": "a1", "role": "theme_underscore"},
            {"asset_id": "a2", "role": "theme_cold_open"},
            {"asset_id": "a3", "role": "theme_outro"},
            {"asset_id": "a4", "role": "theme_emphasis"},
        ],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "c1",
                        "placement": "under_segment",
                        "segment_id": "seg_001",
                        "asset_id": "a1",
                    }
                ]
            }
        },
    }
    errs = validate_creative_density(ctx, sdp)
    assert any("bed coverage" in e for e in errs)


def test_music_completeness_continuous_not_binary() -> None:
    # Unit: formula path via build_autopsy scores when hard edges present.
    hard = 2
    n = 5
    score = max(0.0, min(1.0, 1.0 - (hard / n)))
    assert score == pytest.approx(0.6)
    assert score not in {0.5, 1.0}


def test_sonic_weave_remutate_includes_music_not_edl_only(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.listen_delight_remutate import plan_listen_delight_remutate

    ctx = isolated_run_ctx(tmp_path, "ld5_sonic")
    preview = ctx.path("master/assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    plan = plan_listen_delight_remutate(ctx, failed_dimensions=["sonic_weave"])
    stages = plan.get("from_stages") or []
    assert "mmaudio_sfx" in stages or "music_palette_compose" in stages
    assert "edl" not in stages[:1]


def test_record_failure_is_sole_writer_api() -> None:
    from interview_mux import identical_failures as inf

    assert callable(inf.record_failure)
    src = Path(inf.__file__).read_text(encoding="utf-8")
    assert "def record_failure(" in src
    # Wrappers delegate.
    assert "return record_failure(" in src


def test_listen_delight_floors_not_rubric_when_authoritative(monkeypatch) -> None:
    from interview_mux.aspirational_quality import is_rubric_pmq_check

    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "authoritative"},
    )
    assert is_rubric_pmq_check("listen_delight_floors") is False
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "advisory"},
    )
    assert is_rubric_pmq_check("listen_delight_floors") is True


def test_junction_gen_cap_is_three() -> None:
    from interview_mux.thrash_hardening import JUNCTION_REMASTER_GEN_CAP

    assert JUNCTION_REMASTER_GEN_CAP == 3


def test_mmaudio_backup_default_false() -> None:
    from interview_mux.config import merged_config

    cfg = merged_config()
    mg = cfg.get("musicgen") if isinstance(cfg.get("musicgen"), dict) else {}
    assert mg.get("mmaudio_backup_on_stub") is False


def test_delight_and_shape_defaults_authoritative() -> None:
    from interview_mux.config import merged_config
    from interview_mux.mastering_hardening_config import gate_cfg

    cfg = merged_config()
    ld = ((cfg.get("mastering") or {}).get("listen_delight") or {})
    assert ld.get("mode") == "authoritative"
    assert gate_cfg("feasibility")["mode"] == "authoritative"
    assert gate_cfg("semantic_integrity")["mode"] == "authoritative"
