#!/usr/bin/env python3
"""CLAP audio embedding for WAV time slice(s) — runs inside ASSETS/local_mmaudio/venv.

Single window (legacy):
  {"wav_path","start_ms","end_ms","model_id"} -> {"available","vector","dim",...}

Batch (preferred — load model once):
  {"wav_path","windows":[{"start_ms","end_ms"},...],"model_id","output_path"?}
    -> {"available","vectors":[[...],...],"dim",...}  (or small receipt when output_path set)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# HuggingFace / tqdm progress on stdout poisons json.loads of the contract payload.
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


def _respond(payload: dict[str, object], *, exit_code: int = 0) -> None:
    print(json.dumps(payload))
    raise SystemExit(exit_code)


def _emit_result(
    payload: dict[str, object],
    *,
    output_path: Path | None,
    exit_code: int = 0,
) -> None:
    """Write the full contract to output_path (if set) and print a small stdout receipt."""
    if output_path is None:
        _respond(payload, exit_code=exit_code)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload), encoding="utf-8")
    _respond(
        {
            "available": bool(payload.get("available")),
            "count": payload.get("count") or payload.get("dim"),
            "dim": payload.get("dim"),
            "model_id": payload.get("model_id"),
            "output_path": str(output_path),
            "error": payload.get("error"),
        },
        exit_code=exit_code,
    )


def _embed_audio(model, processor, audio, *, torch) -> list[float]:
    inputs = processor(audio=audio, sampling_rate=48000, return_tensors="pt", padding=True)
    with torch.no_grad():
        out = model.get_audio_features(**inputs)
        embed = getattr(out, "pooler_output", None)
        if embed is None:
            embed = out[0]
        return embed[0].cpu().numpy().tolist()


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        _respond({"available": False, "error": f"invalid_json: {exc}"})

    if not isinstance(payload, dict):
        _respond({"available": False, "error": "payload_must_be_object"})

    text_only = bool(payload.get("text_only"))
    text = str(payload.get("text") or "").strip()
    wav_path = Path(str(payload.get("wav_path") or ""))
    model_id = str(payload.get("model_id") or "laion/clap-htsat-fused")
    output_path_raw = str(payload.get("output_path") or "").strip()
    output_path = Path(output_path_raw) if output_path_raw else None
    windows_raw = payload.get("windows")
    batch_windows: list[dict[str, int]] = []
    if isinstance(windows_raw, list) and windows_raw:
        for row in windows_raw:
            if not isinstance(row, dict):
                continue
            batch_windows.append(
                {
                    "start_ms": int(row.get("start_ms") or 0),
                    "end_ms": int(row.get("end_ms") or 0),
                }
            )

    try:
        import torch
        from transformers import ClapModel, ClapProcessor
        try:
            from transformers.utils import logging as hf_logging

            hf_logging.set_verbosity_error()
        except Exception:
            pass
    except ImportError as exc:
        _respond({"available": False, "error": f"missing_deps: {exc}"})

    try:
        processor = ClapProcessor.from_pretrained(model_id)
        model = ClapModel.from_pretrained(model_id)
        model.eval()
        if text_only:
            if not text:
                _respond({"available": False, "error": "empty_text"})
            inputs = processor(text=[text], return_tensors="pt", padding=True)
            with torch.no_grad():
                out = model.get_text_features(**inputs)
                embed = getattr(out, "pooler_output", None)
                if embed is None:
                    embed = out[0] if not hasattr(out, "pooler_output") else out.pooler_output
                vec = embed[0].cpu().numpy().tolist()
            _respond(
                {
                    "available": True,
                    "vector": vec,
                    "dim": len(vec),
                    "model_id": model_id,
                }
            )

        if not wav_path.is_file():
            _respond({"available": False, "error": f"missing_wav: {wav_path}"})

        import librosa

        if batch_windows:
            vectors: list[list[float]] = []
            for win in batch_windows:
                start_ms = int(win["start_ms"])
                end_ms = int(win["end_ms"])
                if end_ms <= start_ms:
                    end_ms = start_ms + 50
                audio, sr = librosa.load(
                    str(wav_path), sr=48000, mono=True, offset=start_ms / 1000.0
                )
                duration_sec = max((end_ms - start_ms) / 1000.0, 0.05)
                max_samples = int(duration_sec * sr)
                audio = audio[:max_samples]
                vectors.append(_embed_audio(model, processor, audio, torch=torch))
            dim = len(vectors[0]) if vectors else 0
            _emit_result(
                {
                    "available": True,
                    "vectors": vectors,
                    "dim": dim,
                    "count": len(vectors),
                    "model_id": model_id,
                },
                output_path=output_path,
            )

        start_ms = int(payload.get("start_ms") or 0)
        end_ms = int(payload.get("end_ms") or 0)
        if end_ms <= start_ms:
            _respond({"available": False, "error": "invalid_time_range"})
        audio, sr = librosa.load(str(wav_path), sr=48000, mono=True, offset=start_ms / 1000.0)
        duration_sec = max((end_ms - start_ms) / 1000.0, 0.05)
        max_samples = int(duration_sec * sr)
        audio = audio[:max_samples]
        vec = _embed_audio(model, processor, audio, torch=torch)
        _respond(
            {
                "available": True,
                "vector": vec,
                "dim": len(vec),
                "model_id": model_id,
            }
        )
    except Exception as exc:  # noqa: BLE001
        _respond({"available": False, "error": str(exc)[:500]})


if __name__ == "__main__":
    main()
