"""Shared llmfit / RAM-tier selection helpers for local MLX runtimes."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from shutil import which

from interview_mux.config import repo_root
from interview_mux.hardware_detect import is_apple_silicon, system_memory_gb


def write_json_manifest(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def llmfit_recommend_json(*, limit: int = 50) -> list[dict[str, Any]]:
    if which("llmfit") is None:
        return []
    for cmd in (
        ["llmfit", "recommend", "--json", "--force-runtime", "mlx", "--limit", str(limit)],
        ["llmfit", "--cli", "--json", "fit", "-n", str(limit)],
    ):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
            if proc.returncode != 0 or not proc.stdout.strip():
                continue
            data = json.loads(proc.stdout)
            if isinstance(data, dict):
                for key in ("models", "recommendations", "results", "data"):
                    val = data.get(key)
                    if isinstance(val, list):
                        return [m for m in val if isinstance(m, dict)]
            if isinstance(data, list):
                return [m for m in data if isinstance(m, dict)]
        except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired):
            continue
    return []


def pick_llmfit_model(
    rows: list[dict[str, Any]],
    *,
    prefix: str = "mlx-community/",
    min_quality: float = 45.0,
) -> dict[str, Any] | None:
    allowed_fit = {"perfect", "good"}
    candidates: list[tuple[int, float, dict[str, Any]]] = []
    for row in rows:
        name = str(row.get("name") or row.get("model") or row.get("model_id") or "").strip()
        if prefix and not name.startswith(prefix):
            continue
        fit = str(row.get("fit") or "").lower()
        if fit and fit not in allowed_fit:
            continue
        try:
            quality = float(row.get("quality") or row.get("score") or 0)
        except (TypeError, ValueError):
            quality = 0.0
        if quality < min_quality:
            continue
        try:
            ctx = int(row.get("context") or row.get("context_length") or 0)
        except (TypeError, ValueError):
            ctx = 0
        candidates.append((ctx, quality, row))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    _ctx, _q, best = candidates[0]
    return best


@dataclass(frozen=True)
class SpeechTier:
    stt_model_id: str
    diarization_mode: str
    diarization_model_id: str | None
    s2s_model_id: str
    capabilities: tuple[str, ...]


def speech_tier_for_ram(ram_gb: float) -> SpeechTier:
    if ram_gb <= 10:
        return SpeechTier(
            stt_model_id="mlx-community/whisper-large-v3-turbo-asr-fp16",
            diarization_mode="sortformer",
            diarization_model_id="mlx-community/diar_sortformer_4spk-v1-fp32",
            s2s_model_id="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
            capabilities=("stt", "diarization", "synthesize", "tone"),
        )
    if ram_gb <= 18:
        return SpeechTier(
            stt_model_id="mlx-community/whisper-large-v3-turbo",
            diarization_mode="sortformer",
            diarization_model_id="mlx-community/diar_sortformer_4spk-v1-fp32",
            s2s_model_id="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
            capabilities=("stt", "diarization", "synthesize", "convert", "tone", "context"),
        )
    return SpeechTier(
        stt_model_id="mlx-community/whisper-large-v3-turbo",
        diarization_mode="sortformer",
        diarization_model_id="mlx-community/diar_sortformer_4spk-v1-fp32",
        s2s_model_id="mlx-community/csm-1b",
        capabilities=("stt", "diarization", "synthesize", "convert", "tone", "context"),
    )


def build_speech_selection(*, source: str = "tier_fallback") -> dict[str, Any]:
    ram = system_memory_gb()
    tier = speech_tier_for_ram(ram)
    return {
        "stt_model_id": tier.stt_model_id,
        "diarization_mode": tier.diarization_mode,
        "diarization_model_id": tier.diarization_model_id,
        "s2s_model_id": tier.s2s_model_id,
        "capabilities": list(tier.capabilities),
        "selection_source": source,
        "ram_gb": round(ram, 1),
        "selected_at": datetime.now(timezone.utc).isoformat(),
    }


def speech_selection_path() -> Path:
    return repo_root() / "ASSETS" / "local_speech" / "selection.json"


def load_speech_selection() -> dict[str, Any] | None:
    path = speech_selection_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def apple_silicon_required() -> bool:
    return is_apple_silicon()
