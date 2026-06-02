"""Hardware-aware MLX model selection via llmfit JSON output."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import repo_root
from interview_mux.local_llm_config import DEFAULT_MODEL_ID

# Medium quality floor (llmfit quality dimension 0–100).
MIN_QUALITY_SCORE = 45
ALLOWED_FIT = frozenset({"perfect", "good"})
MLX_PREFIX = "mlx-community/"

LLMFIT_RECOMMEND_CMD = (
    "llmfit recommend --json --force-runtime mlx --limit 50"
)
LLMFIT_FIT_FALLBACK_CMD = "llmfit --cli --json fit -n 50"


@dataclass(frozen=True)
class LlmfitCandidate:
    model_id: str
    context_length: int
    fit: str
    quality: float
    score: float
    raw: dict[str, Any]


@dataclass(frozen=True)
class SelectionManifest:
    model_id: str
    context_length: int
    fit: str
    quality: float
    llmfit_version: str
    selected_at: str
    command: str
    score: float | None = None
    source: str = "llmfit"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "model_id": self.model_id,
            "context_length": self.context_length,
            "fit": self.fit,
            "quality": self.quality,
            "llmfit_version": self.llmfit_version,
            "selected_at": self.selected_at,
            "command": self.command,
            "source": self.source,
        }
        if self.score is not None:
            out["score"] = self.score
        return out


def selection_manifest_path() -> Path:
    from interview_mux.local_llm_config import selection_manifest_path as _path

    return _path()


def load_selection_manifest(path: Path | None = None) -> dict[str, Any] | None:
    p = path or selection_manifest_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_selection_manifest(manifest: SelectionManifest, path: Path | None = None) -> Path:
    p = path or selection_manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    return p


def _normalize_models_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [m for m in data if isinstance(m, dict)]
    if isinstance(data, dict):
        for key in ("models", "recommendations", "results", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [m for m in val if isinstance(m, dict)]
    return []


def _field_str(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _field_float(row: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        val = row.get(key)
        if val is None:
            scores = row.get("scores")
            if isinstance(scores, dict) and key in scores:
                val = scores[key]
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return default


def _field_int(row: dict[str, Any], *keys: str) -> int:
    for key in keys:
        val = row.get(key)
        if val is None:
            scores = row.get("scores")
            if isinstance(scores, dict) and key in scores:
                val = scores[key]
        if val is not None:
            try:
                return int(float(val))
            except (TypeError, ValueError):
                continue
    return 0


def _normalize_fit(fit: str) -> str:
    f = fit.strip().lower().replace(" ", "_")
    if f in ALLOWED_FIT:
        return f
    # llmfit may return "Perfect", "Good", etc.
    for allowed in ALLOWED_FIT:
        if allowed in f:
            return allowed
    return f


def parse_llmfit_candidates(data: Any) -> list[LlmfitCandidate]:
    rows = _normalize_models_payload(data)
    out: list[LlmfitCandidate] = []
    for row in rows:
        name = _field_str(row, "name", "model", "id", "model_id", "hf_id")
        if not name.startswith(MLX_PREFIX):
            continue
        fit = _normalize_fit(_field_str(row, "fit", "fit_level", "memory_fit"))
        quality = _field_float(row, "quality", default=0.0)
        ctx = _field_int(row, "context", "context_length", "ctx", "max_context")
        score = _field_float(row, "score", "composite_score", default=0.0)
        out.append(
            LlmfitCandidate(
                model_id=name,
                context_length=ctx,
                fit=fit,
                quality=quality,
                score=score,
                raw=row,
            )
        )
    return out


def filter_candidates(
    candidates: list[LlmfitCandidate],
    *,
    min_quality: float = MIN_QUALITY_SCORE,
) -> list[LlmfitCandidate]:
    return [
        c
        for c in candidates
        if c.fit in ALLOWED_FIT and c.quality >= min_quality
    ]


def pick_best_candidate(
    candidates: list[LlmfitCandidate],
    *,
    min_quality: float = MIN_QUALITY_SCORE,
) -> LlmfitCandidate | None:
    eligible = filter_candidates(candidates, min_quality=min_quality)
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda c: (c.context_length, c.quality, c.score),
    )


def run_llmfit_json(command: str) -> Any:
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"llmfit failed (exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    stdout = proc.stdout.strip()
    if not stdout:
        raise RuntimeError("llmfit returned empty output")
    return json.loads(stdout)


def llmfit_version() -> str:
    proc = subprocess.run(
        ["llmfit", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().splitlines()[0]
    proc = subprocess.run(
        ["llmfit", "-V"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().splitlines()[0]
    return "unknown"


def fetch_llmfit_recommendations() -> tuple[Any, str]:
    """Run llmfit and return (parsed JSON, command used)."""
    try:
        return run_llmfit_json(LLMFIT_RECOMMEND_CMD), LLMFIT_RECOMMEND_CMD
    except (RuntimeError, json.JSONDecodeError):
        return run_llmfit_json(LLMFIT_FIT_FALLBACK_CMD), LLMFIT_FIT_FALLBACK_CMD


def select_from_llmfit_json(
    data: Any,
    *,
    min_quality: float = MIN_QUALITY_SCORE,
    fallback_model_id: str = DEFAULT_MODEL_ID,
) -> tuple[LlmfitCandidate | None, list[LlmfitCandidate]]:
    candidates = parse_llmfit_candidates(data)
    best = pick_best_candidate(candidates, min_quality=min_quality)
    if best is not None:
        return best, candidates
    # No eligible mlx-community model — caller may use fallback
    return None, candidates


def build_manifest(
    candidate: LlmfitCandidate,
    *,
    command: str,
    source: str = "llmfit",
) -> SelectionManifest:
    return SelectionManifest(
        model_id=candidate.model_id,
        context_length=candidate.context_length,
        fit=candidate.fit,
        quality=candidate.quality,
        score=candidate.score,
        llmfit_version=llmfit_version(),
        selected_at=datetime.now(timezone.utc).isoformat(),
        command=command,
        source=source,
    )


def build_fallback_manifest(
    fallback_model_id: str = DEFAULT_MODEL_ID,
    *,
    reason: str = "no_eligible_llmfit_candidates",
) -> SelectionManifest:
    return SelectionManifest(
        model_id=fallback_model_id,
        context_length=0,
        fit="fallback",
        quality=0.0,
        llmfit_version=llmfit_version() if _which("llmfit") else "n/a",
        selected_at=datetime.now(timezone.utc).isoformat(),
        command=f"fallback:{reason}",
        source="fallback",
    )


def _which(cmd: str) -> bool:
    from shutil import which

    return which(cmd) is not None


def weights_ready_for_model(model_id: str, models_dir: Path | None = None) -> bool:
    from interview_mux.local_llm_config import default_models_dir, repo_slug

    base = models_dir or default_models_dir()
    slug_dir = base / repo_slug(model_id)
    if not slug_dir.is_dir():
        return False
    # Require at least one weight/config file beyond our manifest
    for pattern in ("*.safetensors", "*.json", "config.json"):
        if list(slug_dir.glob(pattern)):
            return True
    return bool(list(slug_dir.iterdir()))


def selection_cache_valid(
    *,
    refresh: bool = False,
    models_dir: Path | None = None,
) -> bool:
    if refresh:
        return False
    manifest = load_selection_manifest()
    if not manifest:
        return False
    model_id = str(manifest.get("model_id") or "").strip()
    if not model_id:
        return False
    return weights_ready_for_model(model_id, models_dir=models_dir)
