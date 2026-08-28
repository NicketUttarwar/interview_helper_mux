"""Tests for duration-scaled air-order policy resolution."""

from __future__ import annotations

from interview_mux.air_order_policy import _resolve_scaled_ms, air_order_integrity_cfg


def test_opening_window_scales_short_interview():
    cfg = {
        "mastering": {
            "air_order_integrity": {
                "opening_window_ms": 180_000,
                "opening_window_ratio": 0.05,
                "opening_window_min_ms": 90_000,
                "opening_window_max_ms": 300_000,
            }
        }
    }
    pol_cfg = air_order_integrity_cfg(cfg)
    window = _resolve_scaled_ms(
        pol_cfg,
        static_key="opening_window_ms",
        static_default=180_000,
        ratio_key="opening_window_ratio",
        min_key="opening_window_min_ms",
        min_default=90_000,
        max_key="opening_window_max_ms",
        max_default=300_000,
        source_duration_ms=600_000,
    )
    assert window == 90_000


def test_opening_window_scales_long_interview_clamped():
    cfg = {
        "mastering": {
            "air_order_integrity": {
                "opening_window_ratio": 0.05,
                "opening_window_min_ms": 90_000,
                "opening_window_max_ms": 300_000,
            }
        }
    }
    pol_cfg = air_order_integrity_cfg(cfg)
    window = _resolve_scaled_ms(
        pol_cfg,
        static_key="opening_window_ms",
        static_default=180_000,
        ratio_key="opening_window_ratio",
        min_key="opening_window_min_ms",
        min_default=90_000,
        max_key="opening_window_max_ms",
        max_default=300_000,
        source_duration_ms=10_800_000,
    )
    assert window == 300_000


def test_reverse_jump_margin_scales():
    cfg = {
        "mastering": {
            "air_order_integrity": {
                "reverse_jump_margin_ratio": 0.083,
                "reverse_jump_margin_min_ms": 120_000,
                "reverse_jump_margin_max_ms": 600_000,
            }
        }
    }
    pol_cfg = air_order_integrity_cfg(cfg)
    margin = _resolve_scaled_ms(
        pol_cfg,
        static_key="reverse_jump_margin_ms",
        static_default=300_000,
        ratio_key="reverse_jump_margin_ratio",
        min_key="reverse_jump_margin_min_ms",
        min_default=120_000,
        max_key="reverse_jump_margin_max_ms",
        max_default=600_000,
        source_duration_ms=3_600_000,
    )
    assert margin == 298_800
