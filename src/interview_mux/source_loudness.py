"""Source loudness stabilize for ingest (post-preclean, pre-STT).

Default chain: mild dynaudnorm (within-file leveling) + EBU R128 loudnorm
to a podcast-friendly headroom target (−18 LUFS). Master finalize still
loudnorms the assembly bus to −16 LUFS.
"""

from __future__ import annotations

from typing import Any

# Mild speech-oriented defaults — dynaudnorm levels wandering talk;
# loudnorm sets integrated loudness with true-peak ceiling.
DEFAULT_TARGET_LUFS = -18.0
DEFAULT_TRUE_PEAK_DBTP = -1.5
DEFAULT_LRA = 11.0
DEFAULT_DYNAUDNORM_FRAME_MS = 150
DEFAULT_DYNAUDNORM_GAUSS_SIZE = 15
DEFAULT_DYNAUDNORM_PEAK = 0.95
DEFAULT_DYNAUDNORM_MAXGAIN = 10.0


def loudness_stabilize_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        import interview_mux.config as mux_config

        cfg = mux_config.merged_config()
    ingest = cfg.get("ingest") if isinstance(cfg.get("ingest"), dict) else {}
    raw = ingest.get("loudness_stabilize") if isinstance(ingest, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "target_lufs": float(raw.get("target_lufs", DEFAULT_TARGET_LUFS)),
        "true_peak_dbtp": float(raw.get("true_peak_dbtp", DEFAULT_TRUE_PEAK_DBTP)),
        "lra": float(raw.get("lra", DEFAULT_LRA)),
        "dual_mono": bool(raw.get("dual_mono", True)),
        "dynaudnorm": bool(raw.get("dynaudnorm", True)),
        "dynaudnorm_frame_ms": float(raw.get("dynaudnorm_frame_ms", DEFAULT_DYNAUDNORM_FRAME_MS)),
        "dynaudnorm_gausssize": int(raw.get("dynaudnorm_gausssize", DEFAULT_DYNAUDNORM_GAUSS_SIZE)),
        "dynaudnorm_peak": float(raw.get("dynaudnorm_peak", DEFAULT_DYNAUDNORM_PEAK)),
        "dynaudnorm_maxgain": float(raw.get("dynaudnorm_maxgain", DEFAULT_DYNAUDNORM_MAXGAIN)),
    }


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
        parts.append(
            f"dynaudnorm=f={frame_ms:g}:g={gauss}:p={peak:g}:m={maxgain:g}:b=1"
        )
    parts.append(loudnorm)
    return ",".join(parts)


def loudness_lineage_payload(loud_cfg: dict[str, Any], *, af_filter: str | None) -> dict[str, Any]:
    """Artifact metadata written beside ingest/normalized.wav."""
    enabled = af_filter is not None
    return {
        "enabled": enabled,
        "af_filter": af_filter,
        "target_lufs": float(loud_cfg.get("target_lufs", DEFAULT_TARGET_LUFS)) if enabled else None,
        "true_peak_dbtp": float(loud_cfg.get("true_peak_dbtp", DEFAULT_TRUE_PEAK_DBTP))
        if enabled
        else None,
        "lra": float(loud_cfg.get("lra", DEFAULT_LRA)) if enabled else None,
        "dynaudnorm": bool(loud_cfg.get("dynaudnorm", True)) if enabled else False,
        "note": (
            "Source stabilize after optional preclean; master_finalize still targets podcast LUFS."
            if enabled
            else "Loudness stabilize disabled — format normalize only."
        ),
    }
