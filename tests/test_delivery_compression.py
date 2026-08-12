from __future__ import annotations

from interview_mux.coverage_limits import (
    delivery_output_ideal_ratio,
    delivery_output_max_ratio,
    delivery_output_min_ratio,
    listenability_tier,
)
from interview_mux.delivery_brief import build_delivery_brief
from interview_mux.post_master_quality import selection_duration_ship_ok
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_delivery_brief_uses_ratio_defaults(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "delivery_ratio")
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "delivery_brief": {
                    "enabled": True,
                    "ideal_fraction_of_source": 0.45,
                    "min_ratio_of_source": 0.10,
                    "max_ratio_of_source": 1.5,
                }
            }
        },
    )
    ctx.write_json(
        "transcript/full.json",
        {"duration_ms": 900_000, "items": [{"end_ms": 900_000}]},
    )
    brief = build_delivery_brief(ctx)
    ideal = (brief.get("target_duration_sec") or {}).get("ideal")
    assert ideal == 405  # 900s * 0.45
    tmax = (brief.get("target_duration_sec") or {}).get("max")
    assert tmax is not None and tmax >= int(900 * 1.5)  # ceiling allows 1.5× source
    assert delivery_output_min_ratio() == 0.10
    assert delivery_output_ideal_ratio() == 0.45
    assert delivery_output_max_ratio() == 1.5
    assert listenability_tier(0.35) == "strict"


def test_selection_duration_ship_ok_enforces_min_and_max(tmp_path, monkeypatch):
    import json as _json

    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "delivery_brief": {
                    "enabled": True,
                    "enforce_duration": True,
                    "ideal_fraction_of_source": 0.45,
                    "min_ratio_of_source": 0.10,
                    "max_ratio_of_source": 1.5,
                },
                "coverage_limits": {
                    "delivery_output_min_ratio_of_source": 0.10,
                    "delivery_output_ideal_ratio_of_source": 0.45,
                    "delivery_output_max_ratio_of_source": 1.5,
                },
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "duration_ship_band")
    # 1000s source
    ctx.write_json(
        "transcript/full.json",
        {"duration_ms": 1_000_000, "items": [{"end_ms": 1_000_000}]},
    )

    def _write_raw(rel: str, doc: dict) -> None:
        path = ctx.path(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(doc), encoding="utf-8")

    _write_raw(
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "source_duration_ms": 1_000_000,
            "target_duration_sec": {"min": 100, "ideal": 450, "max": 1500},
            "question_budget": {"min": 0, "ideal": 1, "max": 2},
            "chapter_budget": {"min": 1, "ideal": 2, "max": 4},
            "selection_mode": "creative",
            "sfx_density": {"max_beds": 1, "max_punctuators": 1, "max_foley": 0},
        },
    )

    def _seg(sid: str, end_ms: int) -> dict:
        return {
            "segment_id": sid,
            "start_ms": 0,
            "end_ms": end_ms,
            "type": "speech",
            "speaker_id": "spk_1",
            "speaker_role": "guest",
            "topic_tags": [],
        }

    # In-band (~0.5×)
    _write_raw("segments/manifest.json", {"segments": [_seg("seg_a", 500_000)]})
    _write_raw("master/selection.json", {"ordered_segment_ids": ["seg_a"]})
    ok = selection_duration_ship_ok(ctx)
    assert ok["ok"] is True
    assert ok["max_ratio_of_source"] == 1.5

    # Below hard floor (<0.10×)
    _write_raw("segments/manifest.json", {"segments": [_seg("seg_short", 50_000)]})
    _write_raw("master/selection.json", {"ordered_segment_ids": ["seg_short"]})
    low = selection_duration_ship_ok(ctx)
    assert low["ok"] is False
    assert any("min" in r for r in low["reasons"])

    # Above hard ceiling (>1.5×)
    _write_raw("segments/manifest.json", {"segments": [_seg("seg_long", 1_600_000)]})
    _write_raw("master/selection.json", {"ordered_segment_ids": ["seg_long"]})
    high = selection_duration_ship_ok(ctx)
    assert high["ok"] is False
    assert any("max" in r for r in high["reasons"])
