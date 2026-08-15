"""In-memory underbed EQ and stem-aware automated A/B quality control."""

from __future__ import annotations

import math
from typing import Any

from pydub import AudioSegment

_RMS_FLOOR = 1e-9


def underbed_eq_settings(
    mix_cfg: dict[str, Any] | None = None,
    *,
    depth_override_db: float | None = None,
) -> dict[str, Any]:
    """Return bounded EQ settings; the carve is enabled by default."""
    mix = mix_cfg or {}
    raw = mix.get("underbed_eq")
    cfg = raw if isinstance(raw, dict) else {}
    low_hz = max(80, int(cfg.get("low_hz", 1500)))
    high_hz = max(low_hz + 100, int(cfg.get("high_hz", 4000)))
    depth = float(cfg.get("carve_db", cfg.get("depth_db", 3.0)))
    if depth_override_db is not None:
        depth = float(depth_override_db)
    max_depth = max(0.0, min(12.0, float(cfg.get("max_carve_db", 6.0))))
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "low_hz": low_hz,
        "high_hz": high_hz,
        "depth_db": max(0.0, min(max_depth, depth)),
        "max_depth_db": max_depth,
    }


def apply_underbed_eq(
    segment: AudioSegment,
    settings: dict[str, Any],
) -> AudioSegment:
    """Apply a broad subtractive speech-band carve without mutating the source.

    Pydub's immutable filters isolate the target band. Mixing an inverted,
    scaled copy back into the original attenuates that band while retaining
    material outside the crossover range. Any DSP failure returns the source.
    """
    if not isinstance(segment, AudioSegment):
        return segment
    if not settings.get("enabled", True) or len(segment) <= 0:
        return segment
    depth_db = max(0.0, float(settings.get("depth_db", 3.0)))
    if depth_db <= 0.0:
        return segment
    try:
        low_hz = max(80, int(settings.get("low_hz", 1500)))
        high_hz = max(low_hz + 100, int(settings.get("high_hz", 4000)))
        band = segment.high_pass_filter(low_hz).low_pass_filter(high_hz)
        retained = 10.0 ** (-depth_db / 20.0)
        # First-order crossover filters are below unity through much of this
        # broad band. Compensate their pass-band loss so requested depth is
        # close to the measured attenuation around the speech-band center.
        cancel = min(0.95, max(_RMS_FLOOR, (1.0 - retained) * 1.5))
        cancel_gain_db = 20.0 * math.log10(cancel)
        return segment.overlay(band.invert_phase().apply_gain(cancel_gain_db))
    except Exception:
        return segment


def _band_rms(segment: AudioSegment, low_hz: int, high_hz: int) -> float:
    if len(segment) <= 0:
        return 0.0
    filtered = segment.high_pass_filter(low_hz).low_pass_filter(high_hz)
    max_value = float(1 << (8 * filtered.sample_width - 1))
    return float(filtered.rms) / max(max_value, 1.0)


def _db(value: float) -> float:
    return 20.0 * math.log10(max(_RMS_FLOOR, float(value)))


def _level_dbfs(segment: AudioSegment) -> float:
    if len(segment) <= 0 or segment.rms <= 0:
        return -180.0
    return float(segment.dBFS)


def underbed_qc_settings(mix_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    mix = mix_cfg or {}
    raw = mix.get("underbed_ab_qc")
    cfg = raw if isinstance(raw, dict) else {}
    legacy = mix.get("bed_presence_qc")
    legacy_cfg = legacy if isinstance(legacy, dict) else {}
    return {
        "enabled": bool(cfg.get("enabled", legacy_cfg.get("enabled", True))),
        "fail_closed": bool(
            cfg.get("fail_closed_on_masking", legacy_cfg.get("fail_closed", True))
        ),
        "min_bed_relative_db": float(cfg.get("min_bed_relative_db", -38.0)),
        "min_rendered_bed_dbfs": float(cfg.get("min_rendered_bed_dbfs", -62.0)),
        "max_masking_excess_db": float(
            cfg.get("max_speech_band_excess_db", cfg.get("max_masking_excess_db", -6.0))
        ),
        "speech_active_floor_dbfs": float(cfg.get("speech_active_floor_dbfs", -55.0)),
        "min_window_ms": max(50, int(cfg.get("min_window_ms", 250))),
        "duck_step_db": max(0.0, min(6.0, float(cfg.get("duck_step_db", 2.0)))),
        "carve_step_db": max(0.0, min(3.0, float(cfg.get("carve_step_db", 1.5)))),
        "bed_lift_step_db": max(
            0.0, min(4.0, float(cfg.get("lift_step_db", cfg.get("bed_lift_step_db", 2.0))))
        ),
        "max_total_bed_lift_db": max(
            0.0, min(8.0, float(cfg.get("max_total_bed_lift_db", 4.0)))
        ),
        "max_remux_cycles": max(0, min(2, int(cfg.get("max_remux_cycles", 2)))),
    }


def analyze_underbed_ab_qc(
    speech_stem: AudioSegment,
    overlays: list[dict[str, Any]],
    *,
    mix_cfg: dict[str, Any] | None = None,
    eq_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure known speech and rendered underbed stems in their overlap windows."""
    settings = underbed_qc_settings(mix_cfg)
    eq = eq_settings or underbed_eq_settings(mix_cfg)
    low_hz = int(eq.get("low_hz", 1500))
    high_hz = int(eq.get("high_hz", 4000))
    windows: list[dict[str, Any]] = []

    if settings["enabled"]:
        for index, overlay in enumerate(overlays):
            if not isinstance(overlay, dict) or overlay.get("role") != "bed":
                continue
            bed = overlay.get("audio")
            if not isinstance(bed, AudioSegment) or len(bed) < settings["min_window_ms"]:
                continue
            start_ms = max(0, int(overlay.get("position_ms") or 0))
            end_ms = min(len(speech_stem), start_ms + len(bed))
            if end_ms - start_ms < settings["min_window_ms"]:
                continue
            duration_ms = end_ms - start_ms
            speech = speech_stem[start_ms:end_ms]
            rendered_bed = bed[:duration_ms]
            speech_band_dbfs = _db(_band_rms(speech, low_hz, high_hz))
            bed_band_dbfs = _db(_band_rms(rendered_bed, low_hz, high_hz))
            speech_level_dbfs = _level_dbfs(speech)
            bed_level_dbfs = _level_dbfs(rendered_bed)
            bed_relative_db = bed_level_dbfs - speech_level_dbfs
            excess_db = bed_band_dbfs - speech_band_dbfs
            speech_active = speech_band_dbfs >= settings["speech_active_floor_dbfs"]
            masking = speech_active and excess_db > settings["max_masking_excess_db"]
            inaudible = (
                bed_level_dbfs < settings["min_rendered_bed_dbfs"]
                or (
                    speech_level_dbfs >= settings["speech_active_floor_dbfs"]
                    and bed_relative_db < settings["min_bed_relative_db"]
                )
            )
            verdict = "masking" if masking else ("inaudible" if inaudible else "pass")
            reason = (
                f"bed speech-band excess {excess_db:.1f} dB exceeds "
                f"{settings['max_masking_excess_db']:.1f} dB"
                if masking
                else (
                    f"rendered bed is {bed_relative_db:.1f} dB relative to speech "
                    f"at {bed_level_dbfs:.1f} dBFS"
                    if inaudible
                    else "rendered bed is audible without excessive speech-band masking"
                )
            )
            windows.append(
                {
                    "window_id": str(
                        overlay.get("cue_id")
                        or overlay.get("asset_id")
                        or f"underbed_{index + 1}"
                    ),
                    "asset_id": str(overlay.get("asset_id") or ""),
                    "segment_ids": [
                        str(value)
                        for value in (overlay.get("segment_ids") or [])
                        if value
                    ],
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "speech_baseline_dbfs": round(speech_band_dbfs, 2),
                    "speech_level_dbfs": round(speech_level_dbfs, 2),
                    "rendered_bed_level_dbfs": round(bed_level_dbfs, 2),
                    "rendered_bed_relative_db": round(bed_relative_db, 2),
                    "rendered_bed_residual_dbfs": round(bed_band_dbfs, 2),
                    "speech_band_masking_excess_db": round(excess_db, 2),
                    "speech_active": speech_active,
                    "verdict": verdict,
                    "reason": reason,
                }
            )

    masking_count = sum(row["verdict"] == "masking" for row in windows)
    inaudible_count = sum(row["verdict"] == "inaudible" for row in windows)
    if masking_count:
        verdict = "remux_masking"
        reason = f"{masking_count} underbed window(s) mask the known speech stem"
    elif inaudible_count:
        verdict = "remux_lift"
        reason = f"{inaudible_count} underbed window(s) are below the audibility floor"
    else:
        verdict = "pass"
        reason = "all rendered underbed windows passed" if windows else "no underbed windows"
    return {
        "version": 1,
        "automated": True,
        "verdict": verdict,
        "reason": reason,
        "windows_checked": len(windows),
        "masking_windows": masking_count,
        "inaudible_windows": inaudible_count,
        "settings": {**settings, "underbed_eq": dict(eq)},
        "windows": windows,
    }
