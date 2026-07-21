"""Subprocess runner for local MLX STT (mlx-audio)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.local_model_selection import load_speech_selection
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_script
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext


def local_speech_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return (cfg or merged_config()).get("local_speech") or {}


def speech_available() -> bool:
    from interview_mux.local_runtime import resolve_venv_python

    try:
        resolve_venv_python("speech")
        return True
    except LocalRuntimeUnavailable:
        return False


def resolve_stt_model_id(cfg: dict[str, Any] | None = None) -> str:
    block = local_speech_cfg(cfg)
    override = str(block.get("stt_model_id") or "").strip()
    if override:
        return override
    sel = load_speech_selection() or {}
    return str(sel.get("stt_model_id") or "mlx-community/whisper-large-v3-turbo")


def resolve_diarization_mode(cfg: dict[str, Any] | None = None) -> str:
    block = local_speech_cfg(cfg)
    override = str(block.get("diarization_mode") or "").strip()
    if override:
        return override
    sel = load_speech_selection() or {}
    return str(sel.get("diarization_mode") or "sortformer")


def transcribe_audio(
    ctx: RunContext,
    audio_path: Path,
    *,
    output_json: Path | None = None,
) -> dict[str, Any]:
    """Run mlx-audio STT; return raw words JSON."""
    cfg = merged_config()
    block = local_speech_cfg(cfg)
    model_id = resolve_stt_model_id(cfg)
    diarization_mode = resolve_diarization_mode(cfg)
    timeout = int(block.get("stt_timeout_sec", 3600))

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_path = Path(tmp.name)
    try:
        args = [
            "--audio",
            str(audio_path),
            "--output",
            str(out_path),
            "--model",
            model_id,
            "--diarization-mode",
            diarization_mode,
        ]
        with logged_step("stt/transcribe", ctx=ctx, stage="transcribe"):
            proc = run_runtime_script(
                "speech",
                "tools/stt_transcribe.py",
                args,
                timeout_sec=timeout,
                ctx=ctx,
                stage="transcribe",
            )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:500]
            raise LocalRuntimeUnavailable(f"STT failed: {err}")
        raw = json.loads(out_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise LocalRuntimeUnavailable("STT returned non-object JSON")
        if raw.get("error"):
            raise LocalRuntimeUnavailable(str(raw["error"]))
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        return raw
    finally:
        out_path.unlink(missing_ok=True)
