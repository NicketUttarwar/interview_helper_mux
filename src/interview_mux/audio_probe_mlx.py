"""MLX / local-speech wiring for audio probes (warm-up TTS + STT listen).

Certified listen path: clip → speech-venv STT → evidence → parent answerer.
Fail-open by design: any local-runtime miss returns heuristic path with reasons.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from interview_mux.audio_probe_registry import probe_by_id
from interview_mux.config import merged_config, repo_root
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_json

LogFn = Callable[..., None]


def _speech_cfg() -> dict[str, Any]:
    return dict((merged_config().get("local_speech") or {}))


def _probes_cfg() -> dict[str, Any]:
    return dict((merged_config().get("audio_probes") or {}))


def resolve_listen_model_id() -> str:
    """STT model used for certified stt_listen classify."""
    speech = _speech_cfg()
    for key in ("interrogate_model_id", "stt_model_id"):
        val = str(speech.get(key) or "").strip()
        if val:
            return val
    try:
        from interview_mux.stt_runner import resolve_stt_model_id

        return str(resolve_stt_model_id() or "").strip()
    except Exception:
        return "mlx-community/whisper-large-v3-turbo"


def resolve_warmup_tts_model_id() -> str:
    speech = _speech_cfg()
    val = str(speech.get("warmup_tts_model_id") or speech.get("s2s_model_id") or "").strip()
    if val:
        return val
    try:
        from interview_mux.s2s_runner import resolve_s2s_model_id

        return str(resolve_s2s_model_id() or "").strip()
    except Exception:
        return ""


def prompt_text_for_probe(probe_id: str) -> str:
    meta = probe_by_id(probe_id) or {}
    fname = str(meta.get("prompt_file") or "")
    path = repo_root() / "docs" / "prompts" / "audio_probes" / fname
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return (
        "Answer YES or NO only. YES if this clip mixes languages or uncommon local English."
    )


def warmup_cache_path(probe_id: str, prompt: str, model_id: str) -> Path:
    digest = hashlib.sha256(f"{probe_id}|{model_id}|{prompt}".encode("utf-8")).hexdigest()[:16]
    root = repo_root() / "ASSETS" / "local_speech" / "warmup_cache"
    return root / f"{probe_id.replace('.', '_')}_{digest}.wav"


def resolve_neutral_ref_audio() -> Path | None:
    """Fixed neutral warm-up voice — never host/guest clone."""
    cfg = _speech_cfg()
    rel = str(cfg.get("warmup_voice_wav") or "ASSETS/local_speech/warmup_voice/neutral.wav")
    path = Path(rel)
    if not path.is_absolute():
        path = repo_root() / path
    if path.is_file():
        return path
    # Auto-ensure once (macOS say / silence fallback).
    try:
        from interview_mux.warmup_voice import ensure_neutral_warmup_voice

        ensured = ensure_neutral_warmup_voice(path)
        return ensured if ensured and ensured.is_file() else None
    except Exception:
        return None


def ensure_warmup_wav(
    probe_id: str,
    *,
    ctx: Any = None,
    stage: str = "audio_probe_build",
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Ensure spoken system-prompt warm-up wav exists (cache or synthesize)."""
    prompt = prompt_text_for_probe(probe_id)
    model_id = resolve_warmup_tts_model_id()
    cache = warmup_cache_path(probe_id, prompt, model_id or "none")
    if cache.is_file() and cache.stat().st_size > 44:
        if log:
            log(
                f"Warm-up cache hit: {probe_id}",
                level="info",
                stage=stage,
                action_id="audio_probes.warmup.cache_hit",
                detail={"probe_id": probe_id, "path": str(cache)},
            )
        return {"ok": True, "path": str(cache), "source": "cache", "prompt": prompt}

    if not model_id:
        if log:
            log(
                f"Warm-up skipped (no warmup TTS model): {probe_id}",
                level="info",
                stage=stage,
                action_id="audio_probes.warmup.skip",
                detail={"probe_id": probe_id, "reason": "no_model"},
            )
        return {"ok": False, "path": None, "source": "skipped", "prompt": prompt, "reason": "no_model"}

    ref = resolve_neutral_ref_audio()
    if ref is None:
        if log:
            log(
                f"Warm-up skipped (missing neutral voice): {probe_id}",
                level="warning",
                stage=stage,
                action_id="audio_probes.warmup.skip",
                detail={"probe_id": probe_id, "reason": "no_neutral_ref"},
            )
        return {
            "ok": False,
            "path": None,
            "source": "skipped",
            "prompt": prompt,
            "reason": "no_neutral_ref",
        }

    cache.parent.mkdir(parents=True, exist_ok=True)
    speech = _speech_cfg()
    timeout = int(speech.get("interrogate_timeout_sec") or speech.get("s2s_timeout_sec") or 120)
    try:
        result = run_runtime_json(
            "speech",
            "tools/s2s_interrogate.py",
            {
                "mode": "warmup",
                "text": prompt,
                "out_wav": str(cache),
                "model_id": model_id,
                "ref_audio": str(ref),
                "timeout_sec": timeout,
            },
            timeout_sec=timeout,
            ctx=ctx,
            stage=stage,
        )
    except LocalRuntimeUnavailable as exc:
        if log:
            log(
                f"Warm-up MLX unavailable: {probe_id}: {exc}",
                level="warning",
                stage=stage,
                action_id="audio_probes.warmup.fail_open",
                detail={"probe_id": probe_id, "error": str(exc)[:300]},
            )
        return {
            "ok": False,
            "path": None,
            "source": "runtime_unavailable",
            "prompt": prompt,
            "reason": str(exc)[:300],
        }

    if result.get("ok") and cache.is_file():
        if log:
            log(
                f"Warm-up synthesized: {probe_id}",
                level="success",
                stage=stage,
                action_id="audio_probes.warmup.ok",
                detail={"probe_id": probe_id, "path": str(cache)},
            )
        return {"ok": True, "path": str(cache), "source": "tts", "prompt": prompt, "raw": result}

    if log:
        log(
            f"Warm-up fail-open: {probe_id}: {result.get('error')}",
            level="warning",
            stage=stage,
            action_id="audio_probes.warmup.fail_open",
            detail={"probe_id": probe_id, "result": {k: result.get(k) for k in ("error", "fallback")}},
        )
    return {
        "ok": False,
        "path": None,
        "source": "tts_failed",
        "prompt": prompt,
        "reason": str(result.get("error") or "tts_failed")[:300],
        "raw": result,
    }


def extract_flow_clip(
    *,
    source_wav: Path,
    dest_wav: Path,
    start_ms: int,
    end_ms: int,
    log: LogFn | None = None,
    stage: str = "audio_probe_build",
) -> Path | None:
    if not source_wav.is_file():
        if log:
            log(
                "Flow clip skip: source wav missing",
                level="warning",
                stage=stage,
                action_id="audio_probes.clip.skip",
                detail={"source": str(source_wav)},
            )
        return None
    if end_ms <= start_ms:
        return None
    try:
        from interview_mux.audio_clips import extract_clip

        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        extract_clip(source_wav, dest_wav, start_ms, end_ms)
        if dest_wav.is_file() and dest_wav.stat().st_size > 44:
            return dest_wav
    except Exception as exc:  # noqa: BLE001 — fail-open
        if log:
            log(
                f"Flow clip extract failed: {exc}",
                level="warning",
                stage=stage,
                action_id="audio_probes.clip.fail_open",
                detail={"error": str(exc)[:300]},
            )
    return None


def classify_clip_mlx(
    *,
    probe_id: str,
    clip_wav: Path,
    warmup_wav: Path | None,
    output_contract: str,
    ctx: Any = None,
    stage: str = "audio_probe_build",
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Listen via STT; return evidence dict (ok + stt_text/words) or fail-open."""
    speech = _speech_cfg()
    model_id = resolve_listen_model_id()
    listen_mode = str(speech.get("interrogate_mode") or "stt_listen").strip() or "stt_listen"
    timeout = int(speech.get("interrogate_timeout_sec") or 120)
    payload = {
        "mode": "classify",
        "listen_mode": listen_mode,
        "clip_wav": str(clip_wav),
        "warmup_wav": str(warmup_wav) if warmup_wav else "",
        "interrogate_model_id": model_id,
        "stt_model_id": model_id,
        "output_contract": output_contract,
        "probe_id": probe_id,
    }
    try:
        result = run_runtime_json(
            "speech",
            "tools/s2s_interrogate.py",
            payload,
            timeout_sec=timeout,
            ctx=ctx,
            stage=stage,
        )
    except LocalRuntimeUnavailable as exc:
        if log:
            log(
                f"Listen STT unavailable: {probe_id}: {exc}",
                level="warning",
                stage=stage,
                action_id="audio_probes.classify.fail_open",
                detail={"probe_id": probe_id, "error": str(exc)[:300]},
            )
        return {
            "ok": False,
            "fallback": "heuristic",
            "error": str(exc)[:300],
            "source": "runtime_unavailable",
        }

    if result.get("ok") and (result.get("stt_text") or result.get("text") or result.get("words")):
        if log:
            log(
                f"Listen STT ok: {probe_id}",
                level="success",
                stage=stage,
                action_id="audio_probes.classify.ok",
                detail={
                    "probe_id": probe_id,
                    "source": result.get("source") or "stt_listen",
                    "chars": len(str(result.get("stt_text") or result.get("text") or "")),
                    "words": len(result.get("words") or []),
                },
            )
        return {
            "ok": True,
            "source": str(result.get("source") or "stt_listen"),
            "stt_text": str(result.get("stt_text") or result.get("text") or ""),
            "words": result.get("words") or [],
            "model_id": result.get("model_id") or model_id,
            "confidence": float(result.get("confidence") or 0.75),
            "raw": result,
        }

    if log:
        log(
            f"Listen fail-open→heuristic: {probe_id}: {result.get('error')}",
            level="info",
            stage=stage,
            action_id="audio_probes.classify.fallback_heuristic",
            detail={
                "probe_id": probe_id,
                "error": str(result.get("error") or "")[:300],
                "fallback": result.get("fallback"),
            },
        )
    return {
        "ok": False,
        "fallback": "heuristic",
        "error": str(result.get("error") or "classify_failed")[:300],
        "source": "mlx_fallback",
        "raw": result,
    }


def mlx_path_enabled() -> bool:
    """True when probes prefer MLX and local speech runtime is enabled."""
    probes = _probes_cfg()
    if not bool(probes.get("enabled", True)):
        return False
    if not bool(probes.get("prefer_mlx", True)):
        return False
    speech = _speech_cfg()
    return bool(speech.get("enabled", True))
