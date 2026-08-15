"""Source loudness stabilize for ingest (post-preclean, pre-STT).

Default chain: upward-only soft boost (FFmpeg ``acompressor`` mode=upward)
then EBU R128 loudnorm to a podcast-friendly headroom target (−18 LUFS).

Upward mode raises quiet passages toward a threshold and leaves already-loud
speech alone — it must not ride gain down on louder syllables (classic
``dynaudnorm`` did that and ducked mid-word peaks). Opt into
``dynaudnorm_mode=classic`` only if you explicitly want bidirectional leveling.

Master finalize still loudnorms the assembly bus to −16 LUFS.
"""

from __future__ import annotations

from typing import Any

# Mild speech-oriented defaults — upward boost for soft talk;
# loudnorm sets integrated loudness with true-peak ceiling.
DEFAULT_TARGET_LUFS = -18.0
DEFAULT_TRUE_PEAK_DBTP = -1.5
DEFAULT_LRA = 11.0
DEFAULT_DYNAUDNORM_MODE = "upward_only"
DEFAULT_DYNAUDNORM_FRAME_MS = 500
DEFAULT_DYNAUDNORM_GAUSS_SIZE = 31
DEFAULT_DYNAUDNORM_PEAK = 0.95
DEFAULT_DYNAUDNORM_MAXGAIN = 10.0
# Linear amplitude threshold (~−18 dBFS). Material below this is boosted;
# material at/above it is unchanged (no downward gain riding).
DEFAULT_UPWARD_THRESHOLD = 0.125
DEFAULT_UPWARD_RATIO = 3.0
DEFAULT_UPWARD_ATTACK_MS = 50.0
DEFAULT_UPWARD_RELEASE_MS = 300.0
DEFAULT_UPWARD_KNEE = 2.5

_VALID_DYNAUDNORM_MODES = frozenset({"upward_only", "classic"})


def loudness_stabilize_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        import interview_mux.config as mux_config

        cfg = mux_config.merged_config()
    ingest = cfg.get("ingest") if isinstance(cfg.get("ingest"), dict) else {}
    raw = ingest.get("loudness_stabilize") if isinstance(ingest, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    mode = str(raw.get("dynaudnorm_mode", DEFAULT_DYNAUDNORM_MODE)).strip().lower()
    if mode not in _VALID_DYNAUDNORM_MODES:
        mode = DEFAULT_DYNAUDNORM_MODE
    return {
        "enabled": bool(raw.get("enabled", True)),
        "target_lufs": float(raw.get("target_lufs", DEFAULT_TARGET_LUFS)),
        "true_peak_dbtp": float(raw.get("true_peak_dbtp", DEFAULT_TRUE_PEAK_DBTP)),
        "lra": float(raw.get("lra", DEFAULT_LRA)),
        "dual_mono": bool(raw.get("dual_mono", True)),
        "dynaudnorm": bool(raw.get("dynaudnorm", True)),
        "dynaudnorm_mode": mode,
        "dynaudnorm_frame_ms": float(raw.get("dynaudnorm_frame_ms", DEFAULT_DYNAUDNORM_FRAME_MS)),
        "dynaudnorm_gausssize": int(raw.get("dynaudnorm_gausssize", DEFAULT_DYNAUDNORM_GAUSS_SIZE)),
        "dynaudnorm_peak": float(raw.get("dynaudnorm_peak", DEFAULT_DYNAUDNORM_PEAK)),
        "dynaudnorm_maxgain": float(raw.get("dynaudnorm_maxgain", DEFAULT_DYNAUDNORM_MAXGAIN)),
        "upward_threshold": float(raw.get("upward_threshold", DEFAULT_UPWARD_THRESHOLD)),
        "upward_ratio": float(raw.get("upward_ratio", DEFAULT_UPWARD_RATIO)),
        "upward_attack_ms": float(raw.get("upward_attack_ms", DEFAULT_UPWARD_ATTACK_MS)),
        "upward_release_ms": float(raw.get("upward_release_ms", DEFAULT_UPWARD_RELEASE_MS)),
        "upward_knee": float(raw.get("upward_knee", DEFAULT_UPWARD_KNEE)),
    }


def _build_upward_soft_boost(cfg: dict[str, Any]) -> str:
    """Boost only below threshold; never attenuate louder speech."""
    threshold = float(cfg["upward_threshold"])
    ratio = float(cfg["upward_ratio"])
    attack = float(cfg["upward_attack_ms"])
    release = float(cfg["upward_release_ms"])
    knee = float(cfg["upward_knee"])
    if not 0.000976563 <= threshold <= 1.0:
        raise ValueError("ingest.loudness_stabilize.upward_threshold must be in [0.000976563, 1]")
    if not 1.0 <= ratio <= 20.0:
        raise ValueError("ingest.loudness_stabilize.upward_ratio must be 1–20")
    if not 0.01 <= attack <= 2000.0:
        raise ValueError("ingest.loudness_stabilize.upward_attack_ms must be 0.01–2000")
    if not 0.01 <= release <= 9000.0:
        raise ValueError("ingest.loudness_stabilize.upward_release_ms must be 0.01–9000")
    if not 1.0 <= knee <= 8.0:
        raise ValueError("ingest.loudness_stabilize.upward_knee must be 1–8")
    return (
        f"acompressor=mode=upward:threshold={threshold:g}:ratio={ratio:g}:"
        f"attack={attack:g}:release={release:g}:makeup=1:knee={knee:g}:"
        "detection=rms:link=maximum"
    )


def _build_classic_dynaudnorm(cfg: dict[str, Any]) -> str:
    """Legacy bidirectional dynaudnorm (can duck loud syllables — opt-in only)."""
    frame_ms = float(cfg["dynaudnorm_frame_ms"])
    gauss = int(cfg["dynaudnorm_gausssize"])
    peak = float(cfg["dynaudnorm_peak"])
    maxgain = float(cfg["dynaudnorm_maxgain"])
    if not 10.0 <= frame_ms <= 8000.0:
        raise ValueError("ingest.loudness_stabilize.dynaudnorm_frame_ms must be 10–8000")
    if gauss < 3 or gauss % 2 == 0:
        raise ValueError(
            "ingest.loudness_stabilize.dynaudnorm_gausssize must be odd and >= 3"
        )
    if not 0.0 < peak <= 1.0:
        raise ValueError("ingest.loudness_stabilize.dynaudnorm_peak must be in (0, 1]")
    if not 1.0 <= maxgain <= 100.0:
        raise ValueError("ingest.loudness_stabilize.dynaudnorm_maxgain must be 1–100")
    # curve=max(p,peak): never request gain < 1 even in classic mode when peaks
    # already meet the target (still can ride mid-word via Gaussian smoothing).
    return (
        f"dynaudnorm=f={frame_ms:g}:g={gauss}:p={peak:g}:m={maxgain:g}:b=1:"
        f"v='max(p\\,{peak:g})'"
    )


def build_ingest_loudness_filter(loud_cfg: dict[str, Any] | None = None) -> str | None:
    """Return ffmpeg ``-af`` chain for source stabilize, or None when disabled."""
    cfg = loud_cfg if loud_cfg is not None else loudness_stabilize_cfg()
    if not bool(cfg.get("enabled", True)):
        return None

    target = float(cfg["target_lufs"])
    true_peak = float(cfg["true_peak_dbtp"])
    lra = float(cfg["lra"])
    if not -70.0 <= target <= -5.0:
        raise ValueError("ingest.loudness_stabilize.target_lufs must be between -70 and -5")
    if not -9.0 <= true_peak <= 0.0:
        raise ValueError("ingest.loudness_stabilize.true_peak_dbtp must be between -9 and 0")
    if not 1.0 <= lra <= 50.0:
        raise ValueError("ingest.loudness_stabilize.lra must be between 1 and 50")

    dual = "true" if bool(cfg.get("dual_mono", True)) else "false"
    loudnorm = (
        f"loudnorm=I={target:g}:TP={true_peak:g}:LRA={lra:g}:dual_mono={dual}"
    )

    parts: list[str] = []
    if bool(cfg.get("dynaudnorm", True)):
        mode = str(cfg.get("dynaudnorm_mode", DEFAULT_DYNAUDNORM_MODE)).strip().lower()
        if mode == "classic":
            parts.append(_build_classic_dynaudnorm(cfg))
        else:
            parts.append(_build_upward_soft_boost(cfg))
    parts.append(loudnorm)
    return ",".join(parts)


def loudness_lineage_payload(loud_cfg: dict[str, Any], *, af_filter: str | None) -> dict[str, Any]:
    """Artifact metadata written beside ingest/normalized.wav."""
    enabled = af_filter is not None
    dyn_on = bool(loud_cfg.get("dynaudnorm", True)) if enabled else False
    mode = (
        str(loud_cfg.get("dynaudnorm_mode", DEFAULT_DYNAUDNORM_MODE))
        if dyn_on
        else None
    )
    return {
        "enabled": enabled,
        "af_filter": af_filter,
        "target_lufs": float(loud_cfg.get("target_lufs", DEFAULT_TARGET_LUFS)) if enabled else None,
        "true_peak_dbtp": float(loud_cfg.get("true_peak_dbtp", DEFAULT_TRUE_PEAK_DBTP))
        if enabled
        else None,
        "lra": float(loud_cfg.get("lra", DEFAULT_LRA)) if enabled else None,
        "dynaudnorm": dyn_on,
        "dynaudnorm_mode": mode,
        "note": (
            "Source stabilize after optional preclean; soft-only upward boost by default "
            "(no loud-syllable ducking); master_finalize still targets podcast LUFS."
            if enabled
            else "Loudness stabilize disabled — format normalize only."
        ),
    }
