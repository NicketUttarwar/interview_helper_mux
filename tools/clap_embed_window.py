#!/usr/bin/env python3
"""CLAP audio embedding for a WAV time slice — runs inside ASSETS/local_mmaudio/venv."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def _respond(payload: dict[str, object], *, exit_code: int = 0) -> None:
    print(json.dumps(payload))
    raise SystemExit(exit_code)


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
    start_ms = int(payload.get("start_ms") or 0)
    end_ms = int(payload.get("end_ms") or 0)
    model_id = str(payload.get("model_id") or "laion/clap-htsat-fused")

    try:
        import torch
        from transformers import ClapModel, ClapProcessor
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
                embed = model.get_text_features(**inputs)
                vec = embed[0].cpu().numpy().tolist()
        else:
            if not wav_path.is_file():
                _respond({"available": False, "error": f"missing_wav: {wav_path}"})
            if end_ms <= start_ms:
                _respond({"available": False, "error": "invalid_time_range"})
            import librosa

            audio, sr = librosa.load(str(wav_path), sr=48000, mono=True, offset=start_ms / 1000.0)
            duration_sec = max((end_ms - start_ms) / 1000.0, 0.05)
            max_samples = int(duration_sec * sr)
            audio = audio[:max_samples]
            inputs = processor(audios=audio, sampling_rate=48000, return_tensors="pt", padding=True)
            with torch.no_grad():
                embed = model.get_audio_features(**inputs)
                vec = embed[0].cpu().numpy().tolist()
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
