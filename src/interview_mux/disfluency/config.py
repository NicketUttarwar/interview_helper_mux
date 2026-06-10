from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root

DEFAULT_FILLER_LEXICON = frozenset(
    {
        "um",
        "uh",
        "er",
        "ah",
        "hmm",
        "hm",
        "umm",
        "uhh",
        "eh",
        "mm",
        "mhm",
        "uh-huh",
        "uh huh",
    }
)


def _block(cfg: dict[str, Any] | None, key: str) -> dict[str, Any]:
    base = merged_config() if cfg is None else cfg
    block = base.get(key) or {}
    return block if isinstance(block, dict) else {}


def disfluency_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(_block(cfg, "disfluency_extract").get("enabled", True))


def disfluency_restore_enabled(cfg: dict[str, Any] | None = None, run_meta: dict[str, Any] | None = None) -> bool:
    if run_meta and isinstance(run_meta.get("disfluency_restore"), dict):
        override = run_meta["disfluency_restore"].get("enabled")
        if override is not None:
            return bool(override)
    return bool(_block(cfg, "disfluency_restore").get("enabled", True))


def extract_settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = _block(cfg, "disfluency_extract")
    root = repo_root()
    weights = block.get("weights_dir") or "ASSETS/local_stt/models"
    weights_path = Path(str(weights))
    if not weights_path.is_absolute():
        weights_path = root / weights_path
    lexicon = block.get("filler_lexicon")
    if isinstance(lexicon, list):
        filler_lexicon = frozenset(str(x).strip().lower() for x in lexicon if str(x).strip())
    else:
        filler_lexicon = DEFAULT_FILLER_LEXICON
    return {
        "whisper_model": str(block.get("whisper_model") or "base"),
        "compute_type": str(block.get("compute_type") or "int8"),
        "gap_min_ms": int(block.get("gap_min_ms") or 80),
        "gap_max_ms": int(block.get("gap_max_ms") or 2500),
        "pad_ms": int(block.get("pad_ms") or 80),
        "min_event_ms": int(block.get("min_event_ms") or 60),
        "max_events": int(block.get("max_events") or 2000),
        "vad_energy_dbfs": float(block.get("vad_energy_dbfs") or -42.0),
        "weights_dir": weights_path,
        "filler_lexicon": filler_lexicon,
    }


def restore_settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = _block(cfg, "disfluency_restore")
    return {
        "max_inter_segment_gap_ms": int(block.get("max_inter_segment_gap_ms") or 1200),
        "crossfade_ms": int(block.get("crossfade_ms") or 30),
        "min_speech_slice_ms": int(block.get("min_speech_slice_ms") or 200),
        "dedupe_overlap_ms": int(block.get("dedupe_overlap_ms") or 40),
    }
