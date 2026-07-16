from __future__ import annotations

from interview_mux.coverage_limits import delivery_output_ideal_ratio, delivery_output_min_ratio, listenability_tier
from interview_mux.delivery_brief import build_delivery_brief
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
    assert delivery_output_min_ratio() == 0.10
    assert delivery_output_ideal_ratio() == 0.45
    assert listenability_tier(0.35) == "strict"
