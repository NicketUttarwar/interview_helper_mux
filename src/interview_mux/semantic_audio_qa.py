"""Optional semantic (CLAP-style) audio QA — fail-open when disabled or unavailable."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_json


def _mmaudio_cfg() -> dict[str, Any]:
    cfg = merged_config().get("mmaudio") or {}
    return cfg if isinstance(cfg, dict) else {}


def apply_semantic_verdict(row: dict[str, Any], semantic: dict[str, Any] | None) -> None:
    """Merge Tier-2 semantic QA fields into an mmaudio_qa asset row."""
    if not semantic:
        return
    score = semantic.get("score")
    if score is not None:
        row["semantic_similarity"] = score
    verdict = semantic.get("verdict")
    if verdict:
        row["semantic_qa_verdict"] = verdict
    skipped = semantic.get("skipped_reason")
    if skipped:
        row["semantic_qa_skipped_reason"] = skipped
    model_id = semantic.get("model_id")
    if model_id:
        row["semantic_qa_model_id"] = model_id
    threshold = semantic.get("threshold")
    if threshold is not None:
        row["semantic_qa_threshold"] = threshold

    if verdict == "fail":
        role = str(row.get("role") or "")
        gen = str(row.get("generation_status") or "").lower()
        # MusicGen theme stems often score below CLAP vs prose prompts; do not
        # fail-closed and regenerate in a loop when the WAV already exists.
        if role.startswith("theme_") and gen in {"", "pass", "ok"}:
            if row.get("verdict") == "pass":
                row["verdict"] = "warn"
            row.setdefault("reasons", []).append("low_semantic_similarity")
            if row.get("recommended_action") == "pass":
                row["recommended_action"] = "refine"
        else:
            row["verdict"] = "fail"
            row.setdefault("reasons", []).append("low_semantic_similarity")
            row["recommended_action"] = "refine"
    elif verdict == "warn" and row.get("verdict") == "pass":
        row["verdict"] = "warn"
        row.setdefault("reasons", []).append("low_semantic_similarity")
        if row.get("recommended_action") == "pass":
            row["recommended_action"] = "refine"


def maybe_semantic_similarity(
    *,
    wav_path: Path,
    prompt_text: str,
    asset_id: str,
) -> dict[str, Any] | None:
    """Return semantic QA payload when enabled; None when Tier-2 is disabled."""
    cfg = _mmaudio_cfg()
    if not cfg.get("semantic_qa_enabled"):
        return None

    threshold = float(cfg.get("semantic_qa_threshold", 0.18))
    fail_on_low = bool(cfg.get("semantic_qa_fail_on_low", False))
    model_id = str(cfg.get("semantic_qa_model_id", "laion/clap-htsat-fused"))
    timeout_sec = int(cfg.get("semantic_qa_timeout_sec", 120))

    if not prompt_text.strip():
        return {
            "score": None,
            "verdict": "skipped",
            "skipped_reason": "empty_prompt",
            "threshold": threshold,
        }
    if not wav_path.is_file():
        return {
            "score": None,
            "verdict": "skipped",
            "skipped_reason": "missing_wav",
            "threshold": threshold,
        }

    _ = asset_id
    try:
        result = run_runtime_json(
            "mmaudio",
            "tools/clap_similarity.py",
            {
                "wav_path": str(wav_path.resolve()),
                "text": prompt_text.strip(),
                "model_id": model_id,
            },
            timeout_sec=timeout_sec,
        )
    except LocalRuntimeUnavailable as exc:
        return {
            "score": None,
            "verdict": "skipped",
            "skipped_reason": str(exc)[:200],
            "threshold": threshold,
        }

    if not result.get("available"):
        return {
            "score": None,
            "verdict": "skipped",
            "skipped_reason": str(result.get("error") or "clap_unavailable")[:200],
            "threshold": threshold,
        }

    score = float(result["score"])
    if score >= threshold:
        verdict = "pass"
    elif fail_on_low:
        verdict = "fail"
    else:
        verdict = "warn"

    return {
        "score": round(score, 4),
        "verdict": verdict,
        "model_id": str(result.get("model_id") or model_id),
        "threshold": threshold,
    }
